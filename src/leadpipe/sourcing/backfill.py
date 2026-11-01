"""Find emails for Notion prospects that were written without one.

For every Prospects row with an empty Email whose Notes contain a YouTube channel link
(rows from `run.py source`; --all-empty also takes any row with a website or channel):
YouTube About/description -> their website (free) -> Hunter (--hunter, credits) and,
optionally, the Apify Instagram contact Actor (--apify-contacts). Found emails are written
back to the row's Email column and noted in Notes. Never contacts anyone.
"""
from __future__ import annotations

import re
from datetime import date

from ..budget import BudgetGuard
from . import daily
from .notion import Notion, build_properties, plain
from .youtube import channel_about

CH_RE = re.compile(r"youtube\.com/channel/(UC[\w-]{22})")


def run(cfg, guard: BudgetGuard, *, dry_run: bool, use_hunter: bool, use_apify: bool, all_empty: bool,
        limit: int, notion: Notion | None = None, about_fn=channel_about, lookup_mx=None, apify=None) -> dict:
    s = cfg.settings["sourcing"]
    notion = notion or Notion(cfg.secret("NOTION_TOKEN"))
    schema = notion.schema(s["notion_prospects_ds"])
    todo = []
    for row in notion.all_rows(s["notion_prospects_ds"]):
        props = row.get("properties", {})
        if plain(props.get(s["col_email"], {})).strip():
            continue
        notes = plain(props.get(s["col_notes"], {}))
        m = CH_RE.search(notes)
        if not m and not all_empty:
            continue
        if not m and "SOURCING" not in notes and not all_empty:
            continue
        name = plain(props.get(s["col_name"], {})).strip()
        ig = plain(props.get(s["col_instagram"], {})).strip() or None
        todo.append({"page_id": row["id"], "channel": name, "channel_id": m.group(1) if m else None,
                     "instagram": ig, "notes": notes, "websites": [], "about_text": ""})
    todo = todo[:limit] if limit else todo
    print(f"[emails] {len(todo)} prospects without an email")
    for c in todo:
        if c["channel_id"]:
            try:
                about = about_fn(c["channel_id"])
                c["websites"] = daily._website(about.get("links", []))
                c["about_text"] = about.get("description", "")
                c["instagram"] = c["instagram"] or about.get("instagram")
            except Exception as e:  # one bad page must not stop the rest
                print(f"[emails] {c['channel']}: couldn't read YouTube About ({type(e).__name__}: {e})")
        print(f"[emails] {c['channel']}: site {c['websites'][:1] or 'none'}, IG {c['instagram'] or 'none'}")

    saved = cfg.settings["sourcing"].get("instagram_contacts", True)
    cfg.settings["sourcing"]["instagram_contacts"] = use_apify
    try:
        daily.find_emails(todo, cfg, guard, use_hunter, lookup_mx, apify)
    finally:
        cfg.settings["sourcing"]["instagram_contacts"] = saved

    found = [c for c in todo if c.get("email")]
    for c in found:
        print(f"[emails] FOUND {c['channel']}: {c['email']} ({c['email_source']}, {c.get('email_provider')})")
        if not dry_run:
            note = (c["notes"] + f" · Email found {date.today().isoformat()} via {c['email_source']}").strip(" ·")
            notion.update_row(c["page_id"], build_properties(schema, {
                s["col_email"]: c["email"], s["col_notes"]: note,
                s["col_instagram"]: c["instagram"] if c["instagram"] else None}))
    return {"checked": len(todo), "found": len(found), "written": 0 if dry_run else len(found)}
