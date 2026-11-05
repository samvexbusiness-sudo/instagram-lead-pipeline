"""Import Instagram profiles + emails from Google results Sam collects by hand.

Sam searches Google himself (e.g. site:instagram.com "sales coach" "@gmail.com"), then saves the
results page (Ctrl+A, Ctrl+C into a .txt, "Save page as" .html, or any JSON export) and runs
`python run.py import-google FILE`. Google is never searched by code.

Free by default: parse handles + emails, skip anyone in Notion, drop dead domains, then Claude
Haiku judges each from the snippet (about $0.01 each). With --check-profiles, each handle is
scraped on Apify first (~$0.003) so inactive or reel-less accounts are dropped too.
"""
from __future__ import annotations

import json
import re
from datetime import date
from html import unescape

from .. import contacts
from ..apify import ApifyClient
from ..budget import BudgetGuard, SpendNotApproved
from . import instagram_broad as broad
from .notion import Notion, NotionError, build_properties, existing_keys

HANDLE_RES = [re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})", re.I), re.compile(r"\(@([A-Za-z0-9_.]{2,30})\)")]
NOT_HANDLES = {"p", "reel", "reels", "explore", "stories", "tv", "accounts", "about", "legal", "direct", "popular"}
# Google glues "Read more" / "..." onto truncated bios: "x@gmail.com. Read more" -> "x@gmail.com.read"
TAIL_RE = re.compile(r"(@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*?\.(?:com|net|org|io|co|uk|in|ie|au|ca|de|nz|us|me|biz|info))"
                     r"\.?\s*(?:read|more|see|…|\.\.\.)", re.I)


def _flatten_json(obj, out: list[str]) -> None:
    if isinstance(obj, dict):
        url = obj.get("url") or obj.get("link") or ""
        text = " ".join(str(obj.get(k) or "") for k in ("title", "description", "snippet", "text", "bio"))
        if url and text.strip():
            out.append(f"{url} {text}")
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _flatten_json(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_json(v, out)


def _parse_block(text: str, out: dict[str, dict], max_gap: int) -> None:
    text = TAIL_RE.sub(r"\1 ", text)
    marks = sorted((m.start(), m.group(1).lower().rstrip(".")) for rx in HANDLE_RES for m in rx.finditer(text))
    marks = [(pos, h) for pos, h in marks if h not in NOT_HANDLES and not h.isdigit()]
    for m in re.finditer(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}", text):
        before = [(pos, h) for pos, h in marks if pos <= m.start() and m.start() - pos < max_gap]
        if not before:
            continue
        pos, h = before[-1]
        cleaned = contacts.clean_emails(m.group(0))
        if cleaned and h not in out:
            out[h] = {"email": cleaned[0], "snippet": " ".join(text[pos:m.end() + 80].split())[:400]}


def parse(raw: str) -> dict[str, dict]:
    """handle -> {email, snippet}. An email belongs to the nearest handle before it in the same
    result (JSON: the same result object; text/HTML: within ~350 characters)."""
    out: dict[str, dict] = {}
    try:
        blocks: list[str] = []
        _flatten_json(json.loads(raw), blocks)
        for b in blocks:
            _parse_block(b, out, max_gap=2000)
        return out
    except (json.JSONDecodeError, ValueError):
        pass
    text = unescape(re.sub(r"<[^>]+>", " ", raw)) if "<html" in raw[:2000].lower() else raw
    # Sam's export format: one "email | @handle" per line (handle after the email).
    for line in text.splitlines():
        m = re.match(r"\s*(\S+@\S+)\s*\|\s*@([A-Za-z0-9_.]{2,30})\s*$", line)
        if m:
            e = contacts.clean_emails(TAIL_RE.sub(r"\1 ", m.group(1)) + " ")
            h = m.group(2).lower().rstrip(".")
            if e and h not in out and h not in NOT_HANDLES:
                out[h] = {"email": e[0], "snippet": line.strip()}
    if out:
        return out
    _parse_block(text, out, max_gap=350)
    return out


def run(cfg, guard: BudgetGuard, raw: str, *, dry_run: bool, check_profiles: bool, notion: Notion | None = None,
        apify=None, judge=None, lookup_mx=None, today: date | None = None, limit: int = 0) -> dict:
    s = cfg.settings["sourcing"]
    today = today or date.today()
    stats = {"date": today.isoformat(), "found": 0, "new": 0, "scraped": 0, "prefilter_pass": 0,
             "icp_pass": 0, "with_email": 0, "written": 0, "rows": []}
    found = parse(raw)
    stats["found"] = len(found)
    notion = notion or Notion(cfg.secret("NOTION_TOKEN"))
    schema = notion.schema(s["notion_prospects_ds"])
    known = existing_keys(notion.all_rows(s["notion_prospects_ds"]))
    done_path = cfg.paths.data / "sourcing" / "google_import_done.json"
    done = json.loads(done_path.read_text(encoding="utf-8")) if done_path.exists() else {}
    before = len(found)
    found = {h: v for h, v in found.items() if f"ig:{h}" not in known and f"email:{v['email']}" not in known
             and h not in done}
    stats["already_checked"] = before - len(found)
    if limit:
        found = dict(list(found.items())[:limit])
    stats["new"] = len(found)
    print(f"[google] {stats['found']} profiles with an email in the file, {stats['already_checked']} already checked "
          f"before or in Notion, {stats['new']} new")
    if not found:
        return stats

    if check_profiles:
        apify = apify or ApifyClient(cfg.secret("APIFY_TOKEN"), guard, cfg.paths.raw,
                                     cfg.settings["apify"]["run_timeout_seconds"])
        a = cfg.settings["apify"]
        items = apify.run_actor(a["profile_actor"], {"usernames": list(found)}, len(found),
                                a["profile_price_per_result"], "google-import")
        stats["scraped"] = len(items)
        broad.process(cfg, guard, items, stats, known=known, schema=schema, notion=notion, apify=apify,
                      judge=judge, lookup_mx=lookup_mx, today=today, dry_run=dry_run,
                      target=len(found), tag="IG-GOOGLE", extra_emails={h: v["email"] for h, v in found.items()})
        _remember(done, done_path, found, today, dry_run)
        return stats

    # Free path: judge from the Google snippet alone (no activity or reel check).
    leads = [{"username": h, "profile": {"full_name": h, "bio": v["snippet"]},
              "contacts": {"emails": [], "phones": [], "best_email": None}} for h, v in found.items()]
    for l in leads:
        contacts._add(l, found[l["username"]]["email"], "instagram", "Google result showing their bio", None)
    contacts.check_providers(leads, **({"lookup": lookup_mx} if lookup_mx else {}))
    leads = [l for l in leads if l["contacts"]["best_email"]]
    icp_settings = dict(cfg.settings["claude"], model=s.get("icp_model") or cfg.settings["claude"]["model"])
    cards = [{"username": l["username"], "google_result": l["profile"]["bio"],
              "note": "Only the Google snippet of their Instagram bio is known; judge on that."} for l in leads]
    try:
        verdicts = (judge or broad._judge)(cards, cfg.icp_text, icp_settings, guard)
    except SpendNotApproved as e:
        if not dry_run:
            raise
        print(f"[google] ICP skipped in dry run: {e}")
        verdicts = {}
    leads = [l | {"icp": verdicts[l["username"]]} for l in leads
             if verdicts.get(l["username"], {}).get("qualified") and verdicts[l["username"]].get("tier") in ("A", "B")]
    stats["prefilter_pass"] = stats["icp_pass"] = stats["with_email"] = len(leads)
    for l in leads:
        v, c = l["icp"], l["contacts"]
        values = {
            s["col_name"]: l["username"],
            s["col_instagram"]: f"https://www.instagram.com/{l['username']}/",
            s["col_email"]: c["best_email"],
            s["col_lane"]: s["lane_mockup"],
            s["col_status"]: s["status_new"],
            s["col_next"]: "Before/after mockup, Sam checks the profile is active first",
            s["col_notes"]: " · ".join([
                f"IG-GOOGLE {today.isoformat()} (volume lane, mockup only, from Sam's Google search)",
                f"tier {v['tier']} ({v['confidence']})", "NOT activity-checked, judged from the Google snippet",
                "; ".join(v.get("reasons", [])[:2]), f"Mockup angle: {v.get('mockup_angle')}",
                f"Email in their bio ({c.get('best_provider') or '?'})"]),
        }
        stats["rows"].append(values)
        if not dry_run:
            try:
                notion.create_row(s["notion_prospects_ds"], build_properties(schema, values))
                stats["written"] += 1
            except NotionError as e:
                print(f"[notion] skipped {l['username']}: {e}")
    _remember(done, done_path, found, today, dry_run)
    return stats


def _remember(done: dict, path, found: dict, today: date, dry_run: bool) -> None:
    """Handles already checked (passed or not) are skipped next time, so pasting the bookmarklet's
    ever-growing list never pays twice for the same person. Dry runs don't count."""
    if dry_run:
        return
    for h in found:
        done[h] = today.isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(done, indent=1), encoding="utf-8")
