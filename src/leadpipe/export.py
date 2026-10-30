"""Daily export: the finished lead list, plus a hand-off for the mockup workflow.

Output per run (in data/exports/):
  leads_<date>.csv   - open in Sheets/Excel, for your own review
  leads_<date>.json  - same leads in the stable hand-off format (HANDOFF_VERSION)
And for each lead, one file in data/handoff/mockup_queue/ (see integrations/mockup.py).
Nothing is sent to anyone. Outreach stays manual.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .integrations.mockup import FolderQueueHandoff, MockupHandoff

HANDOFF_VERSION = 1
TIER_ORDER = {"A": 0, "B": 1, "C": 2}


def handoff_record(lead: dict) -> dict:
    p, q, c = lead["profile"], lead["qualification"] or {}, lead["contacts"]
    return {
        "handoff_version": HANDOFF_VERSION,
        "username": lead["username"],
        "profile_url": p.get("profile_url"),
        "full_name": p.get("full_name"),
        "category": p.get("category"),
        "followers": p.get("followers"),
        "engagement_rate_pct": p.get("engagement_rate_pct"),
        "website": p.get("external_url"),
        "best_email": c.get("best_email"),
        "email_source": next((e["source"] for e in c.get("emails", []) if e["email"] == c.get("best_email")), None),
        "all_emails": [e["email"] for e in c.get("emails", [])],
        "phones": c.get("phones", []),
        "tier": q.get("tier"),
        "score": q.get("score"),
        "reasons": q.get("reasons", []),
        "content_observations": q.get("content_observations"),
        "mockup_angle": q.get("mockup_angle"),
        "recent_posts": (p.get("posts") or {}).get("recent", []),
        "profile_pic": p.get("profile_pic"),
        "bio": p.get("bio"),
    }


def select(store, limit: int, require_email: bool) -> list[dict]:
    leads = [l for l in store.by_status("qualified") if not store.is_blocked(l)]
    if require_email:
        leads = [l for l in leads if l["contacts"].get("best_email")]
    leads.sort(key=lambda l: (TIER_ORDER.get((l["qualification"] or {}).get("tier"), 9),
                              -((l["qualification"] or {}).get("score") or 0)))
    return leads[:limit]


def run(store, out_dir: Path, handoff_dir: Path, limit: int, require_email: bool = True,
        handoff: MockupHandoff | None = None) -> dict:
    leads = select(store, limit, require_email)
    if not leads:
        return {"exported": 0}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    records = [handoff_record(l) for l in leads]

    json_path = Path(out_dir) / f"leads_{stamp}.json"
    json_path.write_text(json.dumps(records, indent=1, ensure_ascii=False))

    csv_path = Path(out_dir) / f"leads_{stamp}.csv"
    cols = ["username", "profile_url", "full_name", "tier", "score", "best_email", "email_source",
            "website", "followers", "engagement_rate_pct", "category", "mockup_angle", "content_observations"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)

    handoff = handoff or FolderQueueHandoff(Path(handoff_dir) / "mockup_queue")
    for rec in records:
        handoff.submit(rec)

    now = datetime.now(timezone.utc).isoformat()
    for l in leads:
        l["status"] = "exported"
        l["export"] = {"exported_at": now, "file": json_path.name}
        store.touch(l)
    store.save()
    return {"exported": len(leads), "json": str(json_path), "csv": str(csv_path)}
