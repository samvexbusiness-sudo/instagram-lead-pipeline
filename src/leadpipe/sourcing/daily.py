"""Daily prospect sourcing, footage first.

  1. Find coach channels on YouTube (search queries + channels suggested next to winners).
  2. Gate 0, footage: measure the newest long-forms and Short (metadata only) and tag
     the channel Spec edit / Spec, check frame / Spec, card layout / Mockup.
  3. ICP: free checks (keywords, activity, subscriber cap), then Claude's 7 checks.
  4. Email: YouTube About/description, their website, the Apify Instagram contact Actor
     (anyone with an Instagram handle), then Hunter only with --hunter. Any published
     email counts, support@ and info@ included.
  5. Notion: one row per survivor with the tag as Lane, plus a daily summary page.
     Never emails or DMs anyone.

Notion is the lead store. `data/sourcing/seen.json` only remembers which channels were
already scanned (and their verdict) so they aren't re-measured every day.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .. import contacts
from ..apify import ApifyClient, ApifyError
from ..budget import BudgetGuard, SpendNotApproved
from ..storage import GENERIC_LINK_DOMAINS, normalize_domain
from . import icp
from .notion import Notion, NotionError, build_properties, existing_keys, name_key
from .youtube import MOCKUP, SPEC, SPEC_CARD, SPEC_FRAME, TAGS, UNMEASURED, BotCheck, YtDlp, channel_about, measure_channel, related_channels

SOCIAL = ("instagram.com", "youtube.com", "youtu.be", "tiktok.com", "facebook.com", "linkedin.com",
          "twitter.com", "x.com", "threads.net", "spotify.com", "podcasts.apple.com", "apple.co", "pinterest.")


class Seen:
    """Scan memory: channel_id -> {status, at, name}. Not a lead list."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.d = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def skip(self, cid: str, recheck_days: int, today: date) -> bool:
        e = self.d.get(cid)
        if not e or e["status"] == UNMEASURED:
            return False
        return (today - date.fromisoformat(e["at"])).days < recheck_days

    def mark(self, cid: str, status: str, name: str | None, today: date) -> None:
        self.d[cid] = {"status": status, "at": today.isoformat(), "name": name}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.d, indent=1), encoding="utf-8")


def _website(links: list[str]) -> list[str]:
    return [("https://" + l) if "://" not in l else l for l in links
            if not any(s in l.lower() for s in SOCIAL)]


def _lead_for_contacts(c: dict) -> dict:
    """Shape a channel like a pipeline lead so contacts.py can be reused."""
    return {"username": c["channel_id"], "profile": {"full_name": c["channel"], "external_urls": c["websites"]},
            "contacts": {"emails": [], "phones": [], "best_email": None}}


def _ig_handle(url: str | None) -> str | None:
    if not url:
        return None
    h = url.rstrip("/").split("instagram.com/")[-1].split("/")[0].split("?")[0].lower()
    return h or None


def from_instagram_contacts(leads: list[dict], cfg, guard: BudgetGuard, apify=None) -> int:
    """Email behind the Instagram contact button, via the Apify contact Actor (paid,
    budget-capped, batched by contact_batch_size). Skips quietly when not allowed."""
    targets = [l for l in leads if not l["contacts"]["emails"] and l.get("ig_handle")]
    if not targets:
        return 0
    if apify is None:
        token = cfg.secret("APIFY_TOKEN")
        if not token:
            print("[sourcing] APIFY_TOKEN not set; skipping the Instagram contact step.")
            return 0
        apify = ApifyClient(token, guard, cfg.paths.raw, cfg.settings["apify"]["run_timeout_seconds"])
    # contacts.from_apify_actor matches results by lead["username"], so use the IG handle.
    ig_leads = [{"username": l["ig_handle"], "contacts": l["contacts"], "profile": l["profile"]} for l in targets]
    try:
        return contacts.from_apify_actor(ig_leads, apify, cfg.settings["apify"])
    except SpendNotApproved as e:
        print(f"[sourcing] Instagram contact step skipped: {e}")
    except ApifyError as e:
        print(f"[sourcing] Instagram contact step failed: {e}")
    return 0


def find_emails(cands: list[dict], cfg, guard: BudgetGuard, use_hunter: bool, lookup_mx=None, apify=None) -> None:
    s = cfg.settings["contacts"]
    leads = []
    for c in cands:
        lead = _lead_for_contacts(c)
        site = next((normalize_domain(u) for u in c["websites"] if normalize_domain(u) not in GENERIC_LINK_DOMAINS), None)
        for e in contacts.clean_emails(c.get("about_text", "")):
            contacts._add(lead, e, "youtube", "YouTube About/description", site)
        if not lead["contacts"]["emails"] and c["websites"] and s.get("fetch_websites", True):
            contacts.from_websites(lead, s["max_pages_per_lead"], s["request_timeout_seconds"])
        contacts._pick_best(lead)
        lead["ig_handle"] = _ig_handle(c.get("instagram"))
        c["_lead"] = lead
        leads.append(lead)
    if cfg.settings["sourcing"].get("instagram_contacts", True):
        from_instagram_contacts(leads, cfg, guard, apify)
        for lead in leads:
            contacts._pick_best(lead)
    key = cfg.secret("HUNTER_API_KEY")
    if use_hunter and key:
        try:
            contacts.from_hunter_finder(leads, key, guard)
            contacts.from_hunter(leads, key, guard)
        except SpendNotApproved as e:
            print(f"[sourcing] Hunter skipped: {e}")
    elif use_hunter:
        print("[sourcing] HUNTER_API_KEY not set; skipping Hunter.")
    contacts.check_providers(leads, **({"lookup": lookup_mx} if lookup_mx else {}))
    for c in cands:
        lc = c.pop("_lead")["contacts"]
        c["email"] = lc["best_email"]
        best = next((e for e in lc["emails"] if e["email"] == lc["best_email"]), None)
        c["email_source"] = best["source"] if best else None
        c["email_provider"] = lc.get("best_provider")


def notion_values(c: dict, s: dict, today: date) -> dict:
    v = c["footage"]["best"] or {}
    tag = c["footage"]["status"]
    lane = {SPEC: s["lane_spec"], SPEC_FRAME: s["lane_spec_frame"], SPEC_CARD: s["lane_spec_card"]}.get(tag, s["lane_mockup"])
    res = f'{v.get("width")}x{v.get("height")}' if v else "unmeasured"
    q = c.get("icp") or {}
    parts = [f"SOURCING {today.isoformat()} (YouTube, footage first)",
             f"tag {lane}",
             f"footage {tag}: {v.get('usable', 0)}px usable after 9:16 crop, measured {res} {v.get('kind', '')} "
             f"youtu.be/{v.get('id')} ({v.get('upload_date', '?')})" if v else "footage unmeasured",
             f"YouTube https://www.youtube.com/channel/{c['channel_id']}",
             f"{c.get('subscribers') or '?'} subs"]
    if q:
        parts.append(f"ICP tier {q.get('tier')} ({q.get('confidence')}): " + "; ".join(q.get("reasons", [])[:3]))
        parts.append(f"Offer: {q.get('offer')}")
        parts.append(f"Clip idea: {q.get('clip_idea')}")
    else:
        parts.append("ICP not checked yet")
    parts.append(f"Email from {c['email_source']} ({c.get('email_provider') or 'provider ?'})" if c.get("email")
                 else "No email found (checked YouTube About, website" + (", Hunter" if c.get("hunter_tried") else "") + ")")
    return {
        s["col_name"]: c["channel"],
        s["col_instagram"]: c.get("instagram"),
        s["col_email"]: c.get("email"),
        s["col_lane"]: lane,
        s["col_status"]: s["status_new"],
        s["col_asset"]: f"https://www.youtube.com/watch?v={v['id']}" if v else None,
        s["col_next"]: {SPEC: "Spec edit from the measured video", SPEC_FRAME: "Spec edit, check a frame of the Short first",
                        SPEC_CARD: "Spec edit in a card layout (1080p landscape)"}.get(tag, "Before/after mockup")
                       + ", Sam reviews first",
        s["col_notes"]: " · ".join(parts),
    }


def run(cfg, guard: BudgetGuard, *, dry_run: bool, max_channels: int | None = None, use_hunter: bool = False,
        yt: YtDlp | None = None, notion: Notion | None = None, today: date | None = None,
        about_fn=channel_about, related_fn=related_channels, lookup_mx=None, apify=None) -> dict:
    s = cfg.settings["sourcing"]
    today = today or date.today()
    yt = yt or YtDlp(sleep=s["sleep_seconds"], retries=s["bot_retries"],
                     cookies_from_browser=s.get("cookies_from_browser") or None)
    seen = Seen(cfg.paths.data / "sourcing" / "seen.json")
    max_channels = max_channels or s["max_channels_per_run"]
    stats = {"date": today.isoformat(), "searched_queries": 0, "candidates": 0, "skipped_known": 0,
             "scanned": 0, **{t: 0 for t in TAGS}, UNMEASURED: 0, "dropped_free_checks": 0, "too_big": 0, "icp_checked": 0,
             "icp_pass": 0, "icp_pending": 0, "rows": {t: 0 for t in TAGS}, "with_email": 0, "written": 0,
             "bot_checks": 0}

    # ---- Notion: who do we already have? ----
    known: set[str] = set()
    schema = None
    if notion is None and cfg.secret("NOTION_TOKEN"):
        notion = Notion(cfg.secret("NOTION_TOKEN"))
    if notion:
        schema = notion.schema(s["notion_prospects_ds"])
        known = existing_keys(notion.all_rows(s["notion_prospects_ds"]))
        print(f"[sourcing] Notion: {len(known)} identifying keys from existing prospects")
    elif not dry_run:
        raise NotionError("NOTION_TOKEN is not set; can't dedupe or write. Run with --dry-run to preview.")
    else:
        print("[sourcing] NOTION_TOKEN not set: dry run without Notion dedupe.")

    # ---- 1. discover ----
    cands: dict[str, dict] = {}

    def add(cid, name, source):
        if not cid or cid in cands:
            return
        stats["candidates"] += 1
        if f"yt:{cid}" in known or seen.skip(cid, s["recheck_days"], today):
            stats["skipped_known"] += 1
            return
        cands[cid] = {"channel_id": cid, "channel": name, "source": source}

    for q in s["queries"]:
        try:
            for e in yt.search(q, s["per_query"]):
                add(e["channel_id"], e["channel"], f"search: {q}")
            stats["searched_queries"] += 1
        except BotCheck:
            stats["bot_checks"] += 1
        print(f"[sourcing] '{q}': {len(cands)} new channels so far")

    # ---- 2. footage (Gate 0), with competitor expansion from winners ----
    order = list(cands)
    measured: list[dict] = []
    expanded = 0
    while order and stats["scanned"] < max_channels:
        cid = order.pop(0)
        c = cands[cid]
        fp = measure_channel(yt, cid, s["long_form_n"], s["shorts_n"], s["min_usable_width"],
                             s.get("max_subscribers"))
        stats["scanned"] += 1
        if fp.too_big:
            name = (fp.videos[0].get("channel") if fp.videos else None) or c["channel"]
            stats["too_big"] += 1
            seen.mark(cid, "TOO_BIG", name, today)
            print(f"[too big]  {fp.too_big:>9,} subs  {name}")
            continue
        stats[fp.status] += 1
        stats["bot_checks"] += fp.bot_checked
        c["footage"] = {"status": fp.status, "best": fp.best, "videos": fp.videos}
        c["last_upload"] = fp.last_upload.isoformat() if fp.last_upload else None
        if fp.videos:
            c["channel"] = fp.videos[0].get("channel") or c["channel"]
            c["subscribers"] = fp.videos[0].get("subscribers")
        seen.mark(cid, fp.status, c["channel"], today)
        print(f"[footage] {fp.status:<10} {(fp.best or {}).get('usable', 0):>5}px  {c['channel']}")
        if fp.status == UNMEASURED:
            continue
        measured.append(c)
        if fp.status != MOCKUP and expanded < s["expand_from_winners"]:
            expanded += 1
            new = []
            try:
                new += [(x, None, f"suggested next to youtu.be/{fp.best['id']}")
                        for x in related_fn(fp.best["id"])[: s["related_per_winner"]]]
            except Exception:  # related channels are a bonus; never fail the run on them
                stats["bot_checks"] += 1
            try:
                new += [(e["channel_id"], e["channel"], f"similar to {c['channel']}")
                        for e in yt.search(fp.best["title"] or c["channel"], s["related_per_winner"])]
            except BotCheck:
                stats["bot_checks"] += 1
            for x, name, src in new:
                before = len(cands)
                add(x, name, src)
                if len(cands) > before:
                    order.append(x)
    if not dry_run:  # a dry run must not hide channels from the real run
        seen.save()

    # ---- 3. ICP ----
    cards = []
    for c in measured:
        try:
            about = about_fn(c["channel_id"])
        except Exception:
            about = {"links": [], "description": "", "instagram": None}
        c["instagram"] = about.get("instagram")
        c["websites"] = _website(about.get("links", []))
        c["about_text"] = about.get("description", "") + " " + " ".join(
            v.get("description", "") for v in c["footage"]["videos"][:1])
        if (c["instagram"] and f"ig:{c['instagram'].rstrip('/').split('/')[-1].lower()}" in known) \
                or ("name:" + (c["channel"] or "").lower()) in known \
                or (name_key(c["channel"]) and name_key(c["channel"]) in known):
            stats["skipped_known"] += 1
            c["drop"] = "already in Notion"
            continue
        card = {"channel_id": c["channel_id"], "channel": c["channel"], "subscribers": c.get("subscribers"),
                "description": about.get("description", "")[:1500], "links": about.get("links", [])[:10],
                "last_upload": c["last_upload"],
                "recent_videos": [{k: v.get(k) for k in ("title", "upload_date", "duration", "kind")} |
                                  {"resolution": f"{v['width']}x{v['height']}"} for v in c["footage"]["videos"]]}
        why = icp.free_checks(card, cfg.hard_filters, today, s.get("max_subscribers"))
        if why:
            stats["dropped_free_checks"] += 1
            c["drop"] = "; ".join(why)
            seen.mark(c["channel_id"], "ICP_FAIL", c["channel"], today)
            continue
        cards.append(card)

    by_id = {c["channel_id"]: c for c in measured}
    api_ready = cfg.secret("ANTHROPIC_API_KEY") is not None
    if api_ready:
        icp_settings = dict(cfg.settings["claude"], model=s.get("icp_model") or cfg.settings["claude"]["model"])
        try:
            verdicts = icp.judge(cards, cfg.icp_text, icp_settings, guard, today)
            stats["icp_checked"] = len(verdicts)
        except SpendNotApproved as e:
            if not dry_run:
                raise
            print(f"[sourcing] ICP check skipped in dry run: {e}")
            verdicts, api_ready = {}, False
    else:
        verdicts = {}
        if not dry_run:
            raise RuntimeError("ANTHROPIC_API_KEY is not set: the daily job needs it for the ICP checks.")
        print("[sourcing] ANTHROPIC_API_KEY not set: dry run shows footage survivors with ICP unchecked.")
    survivors = []
    for card in cards:
        c = by_id[card["channel_id"]]
        v = verdicts.get(card["channel_id"])
        if v is None:
            if api_ready:
                continue  # API failed for this one; retried next run (not marked as seen-fail)
            stats["icp_pending"] += 1
            c["icp"] = None
            survivors.append(c)
        elif v["qualified"]:
            stats["icp_pass"] += 1
            c["icp"] = v
            survivors.append(c)
        else:
            c["drop"] = "ICP: " + "; ".join([k for k, ok in v.get("checks", {}).items() if not ok]
                                            + v.get("reasons", [])[:2])
            seen.mark(c["channel_id"], "ICP_FAIL", c["channel"], today)
    if not dry_run:  # a dry run must not hide channels from the real run
        seen.save()

    # ---- 4. email ----
    for c in survivors:
        c["hunter_tried"] = use_hunter
    find_emails(survivors, cfg, guard, use_hunter, lookup_mx, apify)

    # ---- 5. rows ----
    rows = []
    for c in sorted(survivors, key=lambda c: (TAGS.index(c["footage"]["status"]), (c.get("icp") or {}).get("tier", "Z"))):
        stats["rows"][c["footage"]["status"]] += 1
        stats["with_email"] += bool(c.get("email"))
        rows.append(notion_values(c, s, today))

    if not dry_run:
        for r in rows:
            try:
                notion.create_row(s["notion_prospects_ds"], build_properties(schema, r))
                stats["written"] += 1
            except NotionError as e:  # one bad row must not lose the rest
                stats.setdefault("write_errors", []).append(f"{r.get(s['col_name'])}: {e}")
                print(f"[notion] skipped {r.get(s['col_name'])}: {e}")
        notion.create_page(s["notion_summary_parent"], f"Sourcing · {today.isoformat()}", summary_lines(stats, rows, s))

    report = cfg.paths.data / "sourcing" / f"run_{today.isoformat()}{'_dry' if dry_run else ''}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"stats": stats, "rows": rows,
                                  "dropped": {c["channel"]: c.get("drop") for c in measured if c.get("drop")}},
                                 indent=1, ensure_ascii=False), encoding="utf-8")
    return {"stats": stats, "rows": rows, "report": str(report)}


def summary_lines(stats: dict, rows: list[dict], s: dict) -> list[str]:
    st = stats
    lines = [
        f"Channels scanned: {st['scanned']} (new candidates {st['candidates']}, already known {st['skipped_known']})",
        f"Footage: {st[SPEC]} spec edit, {st[SPEC_FRAME]} spec check-frame, {st[SPEC_CARD]} spec card-layout, "
        f"{st[MOCKUP]} mockup, {st[UNMEASURED]} unmeasured (bot checks: {st['bot_checks']}, retried next run)",
        f"Dropped by free checks: {st['dropped_free_checks']}. ICP checked by Claude: {st['icp_checked']}, passed: {st['icp_pass']}"
        + (f", not checked (no API key): {st['icp_pending']}" if st["icp_pending"] else ""),
        "New rows: " + ", ".join(f"{n} {t.lower()}" for t, n in st["rows"].items()) +
        f". With an email: {st['with_email']}. Written to Notion: {st['written']}",
    ]
    for r in rows[:10]:
        lines.append(f"- {r[s['col_name']]} · {r[s['col_lane']]} · {r.get(s['col_email']) or 'no email'}")
    return lines
