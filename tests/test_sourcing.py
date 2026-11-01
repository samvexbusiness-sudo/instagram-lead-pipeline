"""Offline tests for footage-first sourcing. No network: yt-dlp, YouTube pages,
Notion and DNS are all faked. Run: python -m unittest discover tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leadpipe.budget import BudgetGuard, SpendNotApproved  # noqa: E402
from leadpipe.config import load_config  # noqa: E402
from leadpipe.sourcing import daily, icp, notion  # noqa: E402
from leadpipe.sourcing.youtube import (MOCKUP, SPEC, SPEC_CARD, SPEC_FRAME, UNMEASURED, BotCheck, YtDlp,  # noqa: E402
                                       measure_channel, usable_width)

TODAY = date(2026, 10, 31)


def fmt(w, h):
    return {"formats": [{"vcodec": "avc1", "width": 640, "height": 360}, {"vcodec": "avc1", "width": w, "height": h},
                        {"vcodec": "none", "width": None, "height": None}]}


class FakeYouTube:
    """Answers yt-dlp command lines from a dict of channels."""

    def __init__(self, channels, search, bot_ids=()):
        self.channels, self.search_results, self.bot_ids = channels, search, set(bot_ids)

    def __call__(self, cmd, **kw):
        target = cmd[-1]
        ok = lambda d: subprocess.CompletedProcess(cmd, 0, json.dumps(d), "")
        if any(b in target for b in self.bot_ids):
            return subprocess.CompletedProcess(cmd, 1, "", "ERROR: Sign in to confirm you're not a bot")
        if target.startswith("ytsearch"):
            q = target.split(":", 1)[1]
            return ok({"entries": self.search_results.get(q, [])})
        if "/channel/" in target:
            cid, tab = target.split("/channel/")[1].split("/")
            return ok({"entries": [{"id": v} for v in self.channels[cid][tab]]})
        vid = target.split("v=")[1]
        for cid, ch in self.channels.items():
            if vid in ch["meta"]:
                w, h = ch["meta"][vid]
                return ok(fmt(w, h) | {"title": f"{ch['name']} video {vid}", "upload_date": "20261028",
                                       "channel": ch["name"], "channel_id": cid, "channel_follower_count": ch.get("subs", 5000),
                                       "description": ch.get("desc", "")})
        return subprocess.CompletedProcess(cmd, 1, "", "ERROR: Video unavailable")


CHANNELS = {
    "UC" + "A" * 22: {"name": "Sales Coach Ana", "videos": ["a1", "a2"], "shorts": [], "meta": {"a1": (3840, 2160), "a2": (1920, 1080)},
                      "desc": "Book a call: ana@anasales.com"},
    "UC" + "B" * 22: {"name": "Funnel Coach Ben", "videos": ["b1", "b2"], "shorts": [], "meta": {"b1": (1920, 1080), "b2": (1280, 720)}},
    "UC" + "C" * 22: {"name": "Bot Checked Cara", "videos": ["c1"], "shorts": [], "meta": {"c1": (3840, 2160)}},
    "UC" + "D" * 22: {"name": "Spiritual Soul Healing", "videos": ["d1"], "shorts": [], "meta": {"d1": (3840, 2160)}},
    "UC" + "E" * 22: {"name": "Already Known Eve", "videos": ["e1"], "shorts": [], "meta": {"e1": (3840, 2160)}},
    "UC" + "F" * 22: {"name": "Offer Coach Fay", "videos": ["f1"], "shorts": ["f2"], "meta": {"f1": (1280, 720), "f2": (1080, 1920)}},
    "UC" + "G" * 22: {"name": "Low Res Coach Gil", "videos": ["g1"], "shorts": ["g2"], "meta": {"g1": (1280, 720), "g2": (720, 1280)}},
    "UC" + "H" * 22: {"name": "Huge Sales Coach", "videos": ["h1"], "shorts": [], "meta": {"h1": (3840, 2160)}, "subs": 477000},
}
SEARCH = {"coach q": [{"id": f"s{i}", "channel_id": cid, "channel": ch["name"]} for i, (cid, ch) in enumerate(CHANNELS.items())]}


class TestFootage(unittest.TestCase):
    def test_usable_width(self):
        self.assertEqual(usable_width(1920, 1080), 608)
        self.assertEqual(usable_width(3840, 2160), 1215)
        self.assertEqual(usable_width(1080, 1920), 1080)
        self.assertEqual(usable_width(1080, 1350), 759)   # 4:5 vertical is height-limited too
        self.assertEqual(usable_width(720, 1280), 720)    # Instagram reel download

    def test_tags_and_bot_check_is_unmeasured(self):
        yt = YtDlp(sleep=0, retries=1, runner=FakeYouTube(CHANNELS, SEARCH, bot_ids={"c1"}))
        ana = measure_channel(yt, "UC" + "A" * 22)
        self.assertEqual((ana.status, ana.best["id"]), (SPEC, "a1"))                    # 4K long-form
        self.assertEqual(measure_channel(yt, "UC" + "B" * 22).status, SPEC_CARD)        # 1080p landscape
        self.assertEqual(measure_channel(yt, "UC" + "F" * 22).status, SPEC_FRAME)       # only the Short passes
        self.assertEqual(measure_channel(yt, "UC" + "G" * 22).status, MOCKUP)           # 720p everywhere
        cara = measure_channel(yt, "UC" + "C" * 22)
        self.assertEqual(cara.status, UNMEASURED)
        self.assertEqual(cara.bot_checked, 1)

    def test_bot_check_raises_after_retries(self):
        yt = YtDlp(sleep=0, retries=2, runner=FakeYouTube(CHANNELS, SEARCH, bot_ids={"x9"}))
        with self.assertRaises(BotCheck):
            yt.video("x9")
        self.assertEqual(yt.calls, 3)


class TestNotionHelpers(unittest.TestCase):
    def test_build_properties_follows_schema_types(self):
        schema = {"Name": "title", "IG": "url", "Email": "email", "Lane": "select", "Status": "select", "Notes": "rich_text"}
        props = notion.build_properties(schema, {"Name": "Ana", "IG": None, "Email": "a@b.com", "Lane": "Spec edit",
                                                 "Notes": "x", "Unknown col": "y"})
        self.assertEqual(props["Name"]["title"][0]["text"]["content"], "Ana")
        self.assertEqual(props["Lane"], {"select": {"name": "Spec edit"}})
        self.assertNotIn("IG", props)
        self.assertNotIn("Unknown col", props)

    def test_existing_keys(self):
        rows = [{"properties": {"Name": {"type": "title", "title": [{"plain_text": "Eve Coach"}]},
                                "IG": {"type": "url", "url": "https://www.instagram.com/eve.coach/"},
                                "Notes": {"type": "rich_text", "rich_text": [{"plain_text": "YouTube https://www.youtube.com/channel/UC" + "E" * 22}]},
                                "Email": {"type": "email", "email": "eve@x.com"}}}]
        keys = notion.existing_keys(rows)
        self.assertTrue({"name:eve coach", "ig:eve.coach", "yt:UC" + "E" * 22, "email:eve@x.com"} <= keys)


class FakeNotion:
    def __init__(self):
        self.rows, self.pages = [], []

    def schema(self, ds):
        return {"Name": "title", "IG": "url", "Email": "email", "Lane": "select", "Status": "select",
                "Asset": "url", "Next touch": "rich_text", "Notes": "rich_text"}

    def all_rows(self, ds):
        return [{"properties": {"Notes": {"type": "rich_text", "rich_text": [
            {"plain_text": "https://www.youtube.com/channel/UC" + "E" * 22}]}}}]

    def create_row(self, ds, props):
        self.rows.append(props)

    def create_page(self, parent, title, lines):
        self.pages.append((title, lines))


class FakeApify:
    def __init__(self, emails, raise_spend=False):
        self.emails, self.raise_spend, self.calls = emails, raise_spend, []

    def run_actor(self, actor, run_input, max_items, price_per_item, label):
        if self.raise_spend:
            raise SpendNotApproved("needs --approve-spend")
        self.calls.append(run_input["usernames"])
        return [{"username": u, "publicEmail": self.emails[u]} for u in run_input["usernames"] if u in self.emails]


class TestInstagramContacts(unittest.TestCase):
    def _leads(self, n):
        return [{"username": f"UC{i}", "ig_handle": f"coach{i}", "profile": {"full_name": "x", "external_urls": []},
                 "contacts": {"emails": [], "phones": [], "best_email": None}} for i in range(n)]

    def test_batches_by_contact_batch_size(self):
        cfg = load_config()
        api = FakeApify({"coach4": "c4@x.com"})
        leads = self._leads(5)
        hits = daily.from_instagram_contacts(leads, cfg, None, api)
        self.assertEqual([len(c) for c in api.calls], [3, 2])
        self.assertEqual(hits, 1)
        self.assertEqual(leads[4]["contacts"]["emails"][0]["email"], "c4@x.com")

    def test_unapproved_spend_is_skipped_not_fatal(self):
        cfg = load_config()
        self.assertEqual(daily.from_instagram_contacts(self._leads(2), cfg, None, FakeApify({}, raise_spend=True)), 0)


class TestDailyRun(unittest.TestCase):
    def _run(self, dry):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        cfg = load_config(data_dir=Path(tmp.name))
        cfg.settings["sourcing"] |= {"queries": ["coach q"], "per_query": 10, "sleep_seconds": 0, "bot_retries": 1,
                                     "expand_from_winners": 0}
        cfg.settings["contacts"]["fetch_websites"] = False
        guard = BudgetGuard(Path(tmp.name) / "ledger.jsonl", cfg.settings["budget"])
        yt = YtDlp(sleep=0, retries=1, runner=FakeYouTube(CHANNELS, SEARCH, bot_ids={"c1"}))
        fn = FakeNotion()
        handles = {"F": "offercoachfay", "G": "lowresgil", "B": "funnelben"}
        about = lambda cid: {"links": [], "description": CHANNELS[cid].get("desc", ""),
                             "instagram": f"https://www.instagram.com/{handles[cid[2]]}/" if cid[2] in handles else None}
        self.apify = FakeApify({"offercoachfay": "fay@offercoach.com"})
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        out = daily.run(cfg, guard, dry_run=dry, yt=yt, notion=fn, today=TODAY, about_fn=about,
                        related_fn=lambda v: [], lookup_mx=lambda d: ["aspmx.l.google.com"],
                        apify=self.apify)
        return out, fn

    def test_dry_run_buckets_and_writes_nothing(self):
        out, fn = self._run(dry=True)
        st = out["stats"]
        self.assertEqual(st["skipped_known"], 1)                     # Eve is already in Notion
        self.assertEqual((st[SPEC], st[SPEC_FRAME], st[SPEC_CARD], st[MOCKUP], st[UNMEASURED], st["too_big"]), (2, 1, 1, 1, 1, 1))
        self.assertEqual(st["dropped_free_checks"], 1)               # spiritual/soul/healing (477k is too_big)
        self.assertEqual(st["rows"], {SPEC: 1, SPEC_FRAME: 1, SPEC_CARD: 1, MOCKUP: 1})
        lanes = [r["Lane"] for r in out["rows"]]
        self.assertEqual(lanes, ["Spec edit", "Spec - check frame", "Spec - card layout", "Mockup"])
        ana = out["rows"][0]
        self.assertEqual((ana["Name"], ana["Email"]), ("Sales Coach Ana", "ana@anasales.com"))
        self.assertIn("1215px usable after 9:16 crop, measured 3840x2160 long-form youtu.be/a1", ana["Notes"])
        fay = out["rows"][1]
        self.assertEqual(fay["Email"], "fay@offercoach.com")         # from the Instagram contact Actor
        self.assertIn("Email from apify_contact", fay["Notes"])
        self.assertEqual([sorted(c) for c in self.apify.calls], [["funnelben", "lowresgil", "offercoachfay"]])  # one batch of 3
        self.assertEqual(fn.rows, [])
        self.assertFalse((Path(self.tmp) / "sourcing" / "seen.json").exists())
        self.assertEqual(fn.pages, [])

    def test_write_needs_api_key_for_icp(self):
        with self.assertRaises(RuntimeError):
            self._run(dry=False)


if __name__ == "__main__":
    unittest.main()


class TestNameKey(unittest.TestCase):
    def test_variants_match(self):
        self.assertEqual(notion.name_key("Joanna Lott Coaching"), notion.name_key("Joanna Lott"))
        self.assertEqual(notion.name_key("Justin Jay Johnson | Software Sales Coach"), "nm:justin jay")
        self.assertEqual(notion.name_key("Eden"), "")

    def test_unicode_report_writes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.json"
            p.write_text(json.dumps({"n": "Salesman․com"}, ensure_ascii=False), encoding="utf-8")
            self.assertIn("․", p.read_text(encoding="utf-8"))


class TestSubscriberCap(unittest.TestCase):
    def test_sourcing_cap_overrides_instagram_cap(self):
        card = {"channel": "x", "description": "", "recent_videos": [], "subscribers": 45000}
        rules = {"max_followers": 150000}
        self.assertEqual(icp.free_checks(card, rules, TODAY), [])
        self.assertTrue(icp.free_checks(card, rules, TODAY, 40000))


class TestTooBigEarly(unittest.TestCase):
    def test_stops_after_first_video(self):
        yt = YtDlp(sleep=0, retries=1, runner=FakeYouTube(CHANNELS, SEARCH))
        fp = measure_channel(yt, "UC" + "H" * 22, max_subscribers=40000)
        self.assertEqual((fp.too_big, len(fp.videos)), (477000, 1))


class TestEmailBackfill(unittest.TestCase):
    def test_finds_and_writes_back(self):
        from leadpipe.sourcing import backfill

        class N:
            updates = []
            def schema(self, ds): return {"Name": "title", "Email": "email", "Notes": "rich_text", "IG": "url"}
            def all_rows(self, ds):
                note = lambda t: {"type": "rich_text", "rich_text": [{"plain_text": t}]}
                return [
                    {"id": "p1", "properties": {"Name": {"type": "title", "title": [{"plain_text": "Ana Coach"}]},
                     "Email": {"type": "email", "email": None},
                     "Notes": note("SOURCING · YouTube https://www.youtube.com/channel/UC" + "A" * 22)}},
                    {"id": "p2", "properties": {"Name": {"type": "title", "title": [{"plain_text": "Has Mail"}]},
                     "Email": {"type": "email", "email": "x@y.com"}, "Notes": note("youtube.com/channel/UC" + "B" * 22)}},
                    {"id": "p3", "properties": {"Name": {"type": "title", "title": [{"plain_text": "Old IG lead"}]},
                     "Email": {"type": "email", "email": None}, "Notes": note("PIPELINE 30 Oct")}}]
            def update_row(self, pid, props): self.updates.append((pid, props))

        with tempfile.TemporaryDirectory() as d:
            cfg = load_config(data_dir=Path(d))
            cfg.settings["contacts"]["fetch_websites"] = False
            n = N()
            about = lambda cid: {"links": [], "description": "contact: hello@anacoach.com", "instagram": None}
            out = backfill.run(cfg, BudgetGuard(Path(d) / "l", cfg.settings["budget"]), dry_run=False, use_hunter=False,
                               use_apify=False, all_empty=False, limit=0, notion=n, about_fn=about,
                               lookup_mx=lambda dom: ["aspmx.l.google.com"])
        self.assertEqual((out["checked"], out["found"]), (1, 1))
        self.assertEqual(n.updates[0][0], "p1")
        self.assertEqual(n.updates[0][1]["Email"], {"email": "hello@anacoach.com"})
