"""Offline tests. Run: python -m unittest discover tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leadpipe import contacts, enrichment, prefilter, qualify  # noqa: E402
from leadpipe.budget import BudgetGuard, Estimate, SpendNotApproved  # noqa: E402
from leadpipe.cli import load_fixture  # noqa: E402
from leadpipe.config import load_config  # noqa: E402
from leadpipe.storage import LeadStore, normalize_domain, normalize_username  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


class TestDedup(unittest.TestCase):
    def test_normalize_username(self):
        for raw in ("@Some.Coach", " some.coach ", "https://www.instagram.com/some.coach/?hl=en"):
            self.assertEqual(normalize_username(raw), "some.coach")

    def test_normalize_domain(self):
        self.assertEqual(normalize_domain("https://www.Coach-Site.com/about"), "coach-site.com")
        self.assertEqual(normalize_domain("me@coach-site.com"), "coach-site.com")

    def test_same_handle_different_case_is_one_lead(self):
        with tempfile.TemporaryDirectory() as d:
            store = LeadStore(Path(d) / "leads.json")
            items = load_fixture(FIXTURES / "sample_search_results.json")
            r = enrichment.apply_items(store, items, "keyword_search")
            self.assertEqual(r["new"], 9)
            self.assertEqual(r["updated"], 1)

    def test_filter_new_skips_seen_and_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            store = LeadStore(Path(d) / "leads.json", do_not_contact={"blocked.one"})
            store.upsert("seen.one", "test")
            out = store.filter_new(["@Seen.One", "blocked.one", "fresh.one", "FRESH.ONE"], 90)
            self.assertEqual(out, ["fresh.one"])

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "leads.json"
            store = LeadStore(path)
            store.upsert("a.coach", "test")
            store.save()
            self.assertIn("a.coach", LeadStore(path).leads)


class TestPrefilter(unittest.TestCase):
    def setUp(self):
        self.rules = load_config().hard_filters

    def test_reasons(self):
        items = {i["username"]: i for i in load_fixture(FIXTURES / "sample_search_results.json")}
        get = lambda u: prefilter.check(enrichment.normalize_profile(items[u]), self.rules)
        self.assertTrue(get("demo.coach.alpha")[0])
        self.assertFalse(get("demo.private.delta")[0])
        self.assertFalse(get("demo.mega.foxtrot")[0])
        self.assertIn("excluded keyword", " ".join(get("demo.fitness.charlie")[1]))
        self.assertIn("last post", " ".join(get("demo.quiet.golf")[1]))


class TestContacts(unittest.TestCase):
    def test_clean_emails_drops_junk(self):
        text = ("Email me: Coach@RealCoachSite.com, or coach [at] realcoachsite [dot] com. "
                "logo@2x.png noreply@realcoachsite.com 5f1a2b3c4d5e6f7a8b9c@sentry.wixpress.com")
        self.assertEqual(contacts.clean_emails(text), ["coach@realcoachsite.com"])

    def test_link_in_bio_hops_to_own_site(self):
        pages = {
            "https://linktr.ee/somecoach": '<a href="https://somecoach.com">Site</a><a href="https://youtube.com/x">YT</a>',
            "https://somecoach.com": "<p>Welcome</p>",
            "https://somecoach.com/contact": '<a href="mailto:hello@somecoach.com?subject=hi">Email</a>',
        }
        original = contacts._get
        contacts._get = lambda url, timeout: pages.get(url.rstrip("/"))
        try:
            lead = {"profile": {"external_urls": ["https://linktr.ee/somecoach"]},
                    "contacts": {"emails": [], "phones": [], "best_email": None}}
            contacts.from_websites(lead, max_pages=6, timeout=5)
            contacts._pick_best(lead)
        finally:
            contacts._get = original
        self.assertEqual(lead["contacts"]["best_email"], "hello@somecoach.com")
        self.assertEqual(lead["contacts"]["website_domain"], "somecoach.com")

    def test_helpdesk_ranks_below_named_person(self):
        lead = {"contacts": {"emails": []}}
        contacts._add(lead, "help@funnels.co", "instagram", "x", "funnels.co")
        contacts._add(lead, "kate@funnels.co", "hunter", "x", "funnels.co", conf=90)
        contacts._pick_best(lead)
        self.assertEqual(lead["contacts"]["best_email"], "kate@funnels.co")

    def test_own_domain_email_ranks_above_gmail(self):
        lead = {"contacts": {"emails": []}}
        contacts._add(lead, "coach123@gmail.com", "website", "x", "coach.com")
        contacts._add(lead, "team@coach.com", "website", "x", "coach.com")
        contacts._pick_best(lead)
        self.assertEqual(lead["contacts"]["best_email"], "team@coach.com")


class TestMailProvider(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(contacts.classify_mx(["aspmx.l.google.com"]), "google")
        self.assertEqual(contacts.classify_mx(["coach-com.mail.protection.outlook.com"]), "microsoft")
        self.assertEqual(contacts.classify_mx(["mx00.ionos.co.uk"]), "other")
        self.assertEqual(contacts.classify_mx([]), "no_mail_server")

    def test_dead_domain_never_best_and_failed_lookup_kept(self):
        mx = {"deadcoach.com": [], "goodcoach.com": ["aspmx.l.google.com"], "flaky.com": None}
        lead = {"contacts": {"emails": []}}
        contacts._add(lead, "hi@deadcoach.com", "instagram", "x", "deadcoach.com")
        contacts._add(lead, "me@goodcoach.com", "website", "x", None)
        lead2 = {"contacts": {"emails": []}}
        contacts._add(lead2, "a@flaky.com", "website", "x", None)
        counts = contacts.check_providers([lead, lead2], lookup=lambda d: mx[d])
        self.assertEqual(lead["contacts"]["best_email"], "me@goodcoach.com")
        self.assertEqual(lead["contacts"]["best_provider"], "google")
        self.assertEqual(lead2["contacts"]["best_email"], "a@flaky.com")  # lookup failed: keep it
        self.assertEqual(counts, {"google": 1, "unknown": 1})


class TestPersonName(unittest.TestCase):
    def test_names(self):
        f = lambda n: contacts.person_name({"profile": {"full_name": n}})
        self.assertEqual(f("Lauren Evans | Business Finance Coach"), "Lauren Evans")
        self.assertEqual(f("KATE MCKIBBIN / HELLOFUNNELS"), "Kate Mckibbin")
        self.assertIsNone(f("Online Business Coach"))
        self.assertIsNone(f("Rosie"))


class TestBudget(unittest.TestCase):
    def _guard(self, d, approved):
        caps = {"apify_per_run_usd": 1, "apify_daily_usd": 1.5, "apify_monthly_usd": 10}
        return BudgetGuard(Path(d) / "ledger.jsonl", caps, approved=approved)

    def test_needs_approval(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SpendNotApproved):
                self._guard(d, False).authorize(Estimate("apify", "x", 0.2))
            self._guard(d, True).authorize(Estimate("apify", "x", 0.2))  # no raise

    def test_daily_cap_uses_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            g = self._guard(d, True)
            g.record("apify", 1.0, "earlier run")
            with self.assertRaises(SpendNotApproved):
                g.authorize(Estimate("apify", "x", 0.9))


class TestQualifyManual(unittest.TestCase):
    def test_batch_and_import(self):
        with tempfile.TemporaryDirectory() as d:
            store = LeadStore(Path(d) / "leads.json")
            enrichment.apply_items(store, load_fixture(FIXTURES / "sample_search_results.json"), "t")
            prefilter.run(store, load_config().hard_filters)
            batch = qualify.export_manual_batch(store, "MY ICP TEXT", Path(d), 50)
            text = batch.read_text()
            self.assertIn("MY ICP TEXT", text)
            self.assertIn("demo.coach.alpha", text)
            self.assertNotIn("demo.fitness.charlie", text)
            reply = Path(d) / "reply.txt"
            reply.write_text("```json\n" + (FIXTURES / "sample_verdicts.json").read_text() + "\n```")
            self.assertEqual(qualify.import_manual_batch(store, reply)["imported"], 4)
            self.assertEqual(store.get("demo.coach.alpha")["status"], "qualified")
            self.assertEqual(store.get("demo.consult.india")["status"], "rejected")

    def test_schema_matches_fixture_keys(self):
        verdict = json.loads((FIXTURES / "sample_verdicts.json").read_text())[0]
        self.assertEqual(set(verdict), set(qualify.VERDICT_SCHEMA["required"]))


if __name__ == "__main__":
    unittest.main()
