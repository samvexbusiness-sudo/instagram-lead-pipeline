"""Command line. Run `python run.py --help`.

Safe by default: any step that costs money prints its estimate and stops
unless you add --approve-spend.
"""
from __future__ import annotations

import argparse
import re
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import contacts, enrichment, export, prefilter, qualify
from .apify import ApifyClient, ApifyError
from .budget import BudgetGuard, SpendNotApproved
from .config import load_config
from .storage import LeadStore


def _ctx(args, data_dir=None):
    cfg = load_config(data_dir=data_dir)
    store = LeadStore(cfg.paths.leads_db, cfg.do_not_contact)
    guard = BudgetGuard(cfg.paths.ledger, cfg.settings["budget"], approved=getattr(args, "approve_spend", False))
    return cfg, store, guard


def _apify(cfg, guard):
    return ApifyClient(cfg.secret("APIFY_TOKEN"), guard, cfg.paths.raw, cfg.settings["apify"]["run_timeout_seconds"])


# ---------------- commands ----------------

def cmd_status(args):
    cfg, store, guard = _ctx(args)
    print("Leads by status:")
    for k, v in store.counts().items():
        print(f"  {k:<15} {v}")
    with_email = sum(1 for l in store.by_status("qualified", "exported") if l["contacts"].get("best_email"))
    print(f"  qualified/exported with email: {with_email}")
    print("\nSpend (today / this month):")
    for svc in ("apify", "claude"):
        print(f"  {svc:<7} ${guard.spent(svc, 'day'):.2f} / ${guard.spent(svc, 'month'):.2f}"
              f"   (caps ${guard.caps(svc)['daily']:.2f}/day, ${guard.caps(svc)['monthly']:.2f}/month)")
    print(f"  hunter  {guard.spent('hunter', 'month'):.0f} credits this month (cap {guard.caps('hunter')['monthly']})")
    dups = store.duplicates_by_contact()
    if dups:
        print(f"\nPossible duplicate businesses (same email/site): {len(dups)}")
        for k, v in list(dups.items())[:5]:
            print(f"  {k}: {', '.join(v)}")


def cmd_discover(args):
    cfg, store, guard = _ctx(args)
    s = cfg.settings["apify"]
    keywords = cfg.keywords[: args.max_keywords] if args.max_keywords else cfg.keywords
    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    max_items = len(keywords) * args.per_keyword
    if args.max_profiles:
        max_items = min(max_items, args.max_profiles)
    run_input = {"search": ", ".join(keywords), "searchType": "user", "searchLimit": args.per_keyword}
    print(f"Discovery: {len(keywords)} keywords x {args.per_keyword} = up to {max_items} profiles")
    items = _apify(cfg, guard).run_actor(s["discovery_actor"], run_input, max_items,
                                         s["discovery_price_per_result"], "discover")
    result = enrichment.apply_items(store, items, "keyword_search")
    store.save()
    print(f"Done: {result}")


def cmd_snowball(args):
    """Lookalikes: Instagram's 'related profiles' of leads you already qualified."""
    cfg, store, guard = _ctx(args)
    s = cfg.settings["apify"]
    seeds = store.by_status("qualified", "exported")
    # Best seeds first (tier A, high score), so the paid limit goes to the best lookalikes.
    seeds.sort(key=lambda l: -((l.get("qualification") or {}).get("score") or 0))
    names = {}
    for l in seeds:
        for r in l["profile"].get("related", []):
            names.setdefault(r["username"].lower(), r.get("full_name") or "")
    candidates = [u for l in seeds for u in l["profile"].get("related_usernames", [])]
    fresh = store.filter_new(candidates, cfg.settings["pipeline"]["recheck_after_days"])
    # Free pre-screen on the name Instagram already gave us (2026-10-30 test: 274 -> 91, and
    # those 91 qualified at 19% vs 2-13% for keyword search).
    good = re.compile(cfg.hard_filters.get("lookalike_name_include", "."), re.I)
    bad = re.compile(cfg.hard_filters.get("lookalike_name_exclude", "$^"), re.I)
    before = len(fresh)
    fresh = [u for u in fresh if good.search(u + " " + names.get(u, "")) and not bad.search(u + " " + names.get(u, ""))]
    print(f"Name pre-screen (free): {before} -> {len(fresh)}")
    fresh = fresh[: args.limit]
    if not fresh:
        print("No new related profiles to check yet. Qualify some leads first.")
        return
    print(f"Snowball: {len(fresh)} new related profiles from {len(seeds)} qualified leads")
    items = _apify(cfg, guard).run_actor(s["profile_actor"], {"usernames": fresh}, len(fresh),
                                         s["profile_price_per_result"], "snowball")
    print(f"Done: {enrichment.apply_items(store, items, 'related_profile')}")
    store.save()


def cmd_prefilter(args):
    cfg, store, _ = _ctx(args)
    print(f"Pre-filter: {prefilter.run(store, cfg.hard_filters)}")
    store.save()


def cmd_qualify(args):
    cfg, store, guard = _ctx(args)
    s = cfg.settings["claude"]
    mode = args.mode or s["mode"]
    limit = args.limit or s["max_profiles_per_run"]
    if mode == "manual":
        path = qualify.export_manual_batch(store, cfg.icp_text, cfg.paths.handoff, limit)
        if not path:
            print("Nothing to qualify. Run discover + prefilter first.")
            return
        print(f"Wrote {path}\n\nNext:\n  1. Open that file, copy everything, paste into a claude.ai chat.\n"
              f"  2. Save Claude's reply (the JSON array) to a file, e.g. data/handoff/reply.json\n"
              f"  3. python run.py import-verdicts data/handoff/reply.json")
    else:
        print(f"Qualify (API): {qualify.qualify_via_api(store, cfg.icp_text, s, guard, limit)}")
        store.save()


def cmd_import_verdicts(args):
    cfg, store, _ = _ctx(args)
    print(f"Imported: {qualify.import_manual_batch(store, Path(args.file))}")
    store.save()


def cmd_contacts(args):
    cfg, store, guard = _ctx(args)
    apify = _apify(cfg, guard) if args.apify_contacts else None
    use_hunter = args.hunter or cfg.settings["contacts"].get("use_hunter", False)
    print(f"Contacts: {contacts.run(store, cfg, guard, use_hunter, apify)}")


def cmd_export(args):
    cfg, store, _ = _ctx(args)
    limit = args.limit or cfg.settings["pipeline"]["daily_qualified_target"]
    print(f"Export: {export.run(store, cfg.paths.exports, cfg.paths.handoff, limit, not args.include_no_email)}")


def cmd_plan_test(args):
    """Print the 100-profile test plan with cost estimates. Free."""
    cfg, store, guard = _ctx(args)
    a, c = cfg.settings["apify"], cfg.settings["claude"]
    n, per_kw = 100, 20
    kws = cfg.keywords[: n // per_kw]
    disc = n * a["discovery_price_per_result"]
    passers = int(n * 0.4)
    claude_cost = qualify.estimate_cost(passers, c)
    print(f"""100-profile test plan (nothing runs until you approve each step)

1. Discover   {len(kws)} keywords x {per_kw}: {', '.join(kws)}
              python run.py discover --max-keywords {len(kws)} --per-keyword {per_kw} --max-profiles {n} --approve-spend
              Apify cost: up to ${disc:.2f}
2. Pre-filter python run.py prefilter                              free
3. Qualify    python run.py qualify --limit {passers}               (manual mode: $0, uses your chat plan)
              API mode with {c['model']}: ~${claude_cost:.2f} for ~{passers} profiles
4. Contacts   python run.py contacts                               free (website crawl)
              optional: --hunter (<= 15 free credits) / --apify-contacts (~$0.10)
5. Export     python run.py export --include-no-email              free
6. Review     python run.py status, open data/exports/*.csv, mark which verdicts you disagree with.

Worst case total: about ${disc + claude_cost + 0.10:.2f}. Caps in config/settings.toml stop anything above that.""")


def load_fixture(path: Path) -> list[dict]:
    """Fixture dates are stored relative to `reference_date`; shift them so they look recent."""
    data = json.loads(path.read_text(encoding="utf-8"))
    shift = datetime.now(timezone.utc) - datetime.fromisoformat(data["reference_date"])
    for item in data["items"]:
        for post in item.get("latestPosts", []):
            t = datetime.fromisoformat(post["timestamp"].replace("Z", "+00:00")) + shift
            post["timestamp"] = t.isoformat()
    return data["items"]


def cmd_demo(args):
    """Full pipeline on built-in fake data. No keys, no network, no cost."""
    root = Path(__file__).resolve().parents[2]
    demo_dir = root / "data" / "demo"
    if demo_dir.exists():
        shutil.rmtree(demo_dir)
    cfg, store, guard = _ctx(args, data_dir=demo_dir)
    fixtures = root / "tests" / "fixtures"
    items = load_fixture(fixtures / "sample_search_results.json")
    print("1. discover (fixture):", enrichment.apply_items(store, items, "keyword_search"))
    print("2. prefilter:          ", prefilter.run(store, cfg.hard_filters))
    store.save()
    batch = qualify.export_manual_batch(store, cfg.icp_text, cfg.paths.handoff, 50)
    print("3. qualify batch file: ", batch.relative_to(root) if batch else None)
    print("   import verdicts:    ", qualify.import_manual_batch(store, fixtures / "sample_verdicts.json"))
    cfg.settings["contacts"]["fetch_websites"] = False  # offline demo
    cfg.settings["contacts"]["check_mail_provider"] = False
    print("4. contacts:           ", contacts.run(store, cfg, guard, use_hunter=False))
    print("5. export:             ", export.run(store, cfg.paths.exports, cfg.paths.handoff, 20, True))
    print(f"\nDemo output is in {demo_dir.relative_to(root)}/ (safe to delete).")


def cmd_source(args):
    from .sourcing import daily
    from .sourcing.youtube import MOCKUP, SPEC, SPEC_CARD, SPEC_FRAME, UNMEASURED

    cfg, _store, guard = _ctx(args)
    dry = not args.write
    out = daily.run(cfg, guard, dry_run=dry, max_channels=args.max_channels or None, use_hunter=args.hunter)
    st, rows = out["stats"], out["rows"]
    print("\n=== Sourcing", "DRY RUN (nothing written)" if dry else "run", st["date"], "===")
    print(f"Channels scanned: {st['scanned']}  (new candidates {st['candidates']}, skipped as known {st['skipped_known']})")
    print(f"Footage: Spec edit {st[SPEC]} | Spec, check frame {st[SPEC_FRAME]} | Spec, card layout {st[SPEC_CARD]} "
          f"| Mockup {st[MOCKUP]} | UNMEASURED {st[UNMEASURED]}  (bot checks {st['bot_checks']})")
    print(f"Too big (over the subscriber cap, skipped before measuring) {st['too_big']}")
    print(f"Free-check drops {st['dropped_free_checks']} | ICP checked {st['icp_checked']} | ICP pass {st['icp_pass']}"
          + (f" | ICP not run (no API key or no --approve-spend) {st['icp_pending']}" if st["icp_pending"] else ""))
    print("Rows: " + " | ".join(f"{t} {n}" for t, n in st["rows"].items())
          + f" | with email {st['with_email']} | written {st['written']}")
    print(f"Full report: {out['report']}")
    for r in rows[: 5 if dry else 0]:
        print("\n" + "\n".join(f"  {k}: {v}" for k, v in r.items() if v))
    if dry:
        print("\nNothing was written to Notion. If this looks right: python run.py source --write --approve-spend")


def cmd_emails(args):
    from .sourcing import backfill

    cfg, _store, guard = _ctx(args)
    out = backfill.run(cfg, guard, dry_run=not args.write, use_hunter=args.hunter, use_apify=args.apify_contacts,
                       all_empty=args.all_empty, limit=args.limit)
    print(f"\nChecked {out['checked']} | emails found {out['found']} | written to Notion {out['written']}")
    if not args.write and out["found"]:
        print("Nothing written yet. To save them: add --write")


def main(argv=None):
    p = argparse.ArgumentParser(prog="run.py", description="Instagram business-coach lead pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    add("status", cmd_status, "counts and spend so far")
    add("demo", cmd_demo, "run everything on fake sample data (free, offline)")
    add("plan-test", cmd_plan_test, "show the 100-profile test plan and costs (free)")

    sp = add("discover", cmd_discover, "find profiles by keyword (Apify, paid)")
    sp.add_argument("--per-keyword", type=int, default=20)
    sp.add_argument("--max-keywords", type=int, default=0)
    sp.add_argument("--max-profiles", type=int, default=0)
    sp.add_argument("--keywords", help="comma-separated, overrides config/keywords.txt")
    sp.add_argument("--approve-spend", action="store_true")

    sp = add("snowball", cmd_snowball, "check lookalikes of qualified leads (Apify, paid)")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--approve-spend", action="store_true")

    add("prefilter", cmd_prefilter, "free yes/no checks from hard_filters.toml")

    sp = add("qualify", cmd_qualify, "judge profiles against your ICP with Claude")
    sp.add_argument("--mode", choices=["manual", "api"])
    sp.add_argument("--limit", type=int, default=0)
    sp.add_argument("--approve-spend", action="store_true")

    sp = add("import-verdicts", cmd_import_verdicts, "load Claude's JSON reply from manual mode")
    sp.add_argument("file")

    sp = add("contacts", cmd_contacts, "find public business emails for qualified leads")
    sp.add_argument("--hunter", action="store_true", help="also use Hunter credits")
    sp.add_argument("--apify-contacts", action="store_true", help="also use the paid Apify contact Actor")
    sp.add_argument("--approve-spend", action="store_true")

    sp = add("export", cmd_export, "write today's lead list + mockup hand-off files")
    sp.add_argument("--limit", type=int, default=0)
    sp.add_argument("--include-no-email", action="store_true")

    sp = add("source", cmd_source, "daily footage-first sourcing from YouTube into Notion (dry run by default)")
    sp.add_argument("--write", action="store_true", help="write rows + summary to Notion (default: dry run)")
    sp.add_argument("--max-channels", type=int, default=0, help="cap footage checks this run")
    sp.add_argument("--hunter", action="store_true", help="use Hunter credits for missing emails")
    sp.add_argument("--approve-spend", action="store_true")

    sp = add("emails", cmd_emails, "find emails for Notion prospects that have none (preview by default)")
    sp.add_argument("--write", action="store_true", help="save found emails into Notion")
    sp.add_argument("--hunter", action="store_true", help="use Hunter credits")
    sp.add_argument("--apify-contacts", action="store_true", help="also try the Instagram contact Actor (paid)")
    sp.add_argument("--all-empty", action="store_true", help="any row without an email, not just YouTube-sourced ones")
    sp.add_argument("--limit", type=int, default=0)
    sp.add_argument("--approve-spend", action="store_true")

    args = p.parse_args(argv)
    try:
        args.fn(args)
    except SpendNotApproved as e:
        print(f"\n{e}")
        sys.exit(2)
    except ApifyError as e:
        print(f"\nApify problem: {e}")
        sys.exit(1)
    except RuntimeError as e:  # missing API keys, Notion errors
        print(f"\n{e}")
        sys.exit(1)
