"""JSON lead store with deduplication.

One file, data/leads.json, holds every profile we've ever seen, keyed by a
normalised username. That single index is what stops us paying to scrape or
qualify the same person twice.

Lead lifecycle (the `status` field):
    discovered -> prefilter_fail | prefilter_pass
    prefilter_pass -> rejected | qualified
    qualified -> exported
Outreach is tracked by hand in `outreach_status`; the pipeline never sends anything.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = 1

STATUSES = (
    "discovered",
    "prefilter_fail",
    "prefilter_pass",
    "rejected",
    "qualified",
    "exported",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_username(value: str) -> str:
    """'@Some.Coach ' / 'https://instagram.com/some.coach/' -> 'some.coach'."""
    v = (value or "").strip().lower()
    v = re.sub(r"^https?://(www\.)?instagram\.com/", "", v)
    v = v.split("?")[0].strip("/").lstrip("@")
    return v


def normalize_domain(url_or_email: str | None) -> str | None:
    if not url_or_email:
        return None
    v = url_or_email.strip().lower()
    if "@" in v and "/" not in v:
        v = v.split("@", 1)[1]
    v = re.sub(r"^[a-z]+://", "", v)
    v = v.split("/")[0].split("?")[0].split(":")[0]
    if v.startswith("www."):
        v = v[4:]
    return v or None


def new_lead(username: str, source: str, source_detail: str = "") -> dict:
    ts = now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "username": normalize_username(username),
        "ig_id": None,
        "status": "discovered",
        "first_seen_at": ts,
        "updated_at": ts,
        "sources": [{"type": source, "detail": source_detail, "at": ts}],
        "profile": {},           # normalised profile fields (see enrichment.py)
        "prefilter": None,       # {"passed": bool, "reasons": [...]}
        "qualification": None,   # Claude's verdict (see qualify.py)
        "contacts": {"emails": [], "phones": [], "best_email": None, "checked_at": None},
        "export": None,          # {"exported_at": ..., "file": ...}
        "outreach_status": "not_contacted",  # you update this by hand
        "notes": "",
    }


class LeadStore:
    def __init__(self, path: Path, do_not_contact: set[str] | None = None):
        self.path = Path(path)
        self.do_not_contact = do_not_contact or set()
        self.leads: dict[str, dict] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text() or "{}")
            self.leads = data.get("leads", {})

    # ---------- persistence ----------
    def save(self) -> None:
        """Atomic write: never leaves a half-written leads.json behind."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": SCHEMA_VERSION, "saved_at": now_iso(), "leads": self.leads}
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=1, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, self.path)

    # ---------- dedup ----------
    def get(self, username: str) -> dict | None:
        return self.leads.get(normalize_username(username))

    def is_blocked(self, lead_or_username) -> bool:
        if isinstance(lead_or_username, str):
            return normalize_username(lead_or_username) in self.do_not_contact
        lead = lead_or_username
        if lead["username"] in self.do_not_contact:
            return True
        domain = normalize_domain(lead.get("profile", {}).get("external_url"))
        if domain and domain in self.do_not_contact:
            return True
        for e in lead.get("contacts", {}).get("emails", []):
            addr = e["email"].lower()
            if addr in self.do_not_contact or normalize_domain(addr) in self.do_not_contact:
                return True
        return False

    def seen_recently(self, username: str, days: int) -> bool:
        lead = self.get(username)
        if not lead:
            return False
        last = datetime.fromisoformat(lead["updated_at"])
        return datetime.now(timezone.utc) - last < timedelta(days=days)

    def filter_new(self, usernames: Iterable[str], recheck_after_days: int) -> list[str]:
        """Usernames worth paying to scrape: not seen recently, not blocked, unique."""
        out, seen = [], set()
        for u in usernames:
            n = normalize_username(u)
            if not n or n in seen or self.is_blocked(n) or self.seen_recently(n, recheck_after_days):
                continue
            seen.add(n)
            out.append(n)
        return out

    def upsert(self, username: str, source: str, source_detail: str = "") -> tuple[dict, bool]:
        """Return (lead, created). Existing leads just get the extra source noted."""
        key = normalize_username(username)
        if key in self.leads:
            lead = self.leads[key]
            if not any(s["type"] == source and s["detail"] == source_detail for s in lead["sources"]):
                lead["sources"].append({"type": source, "detail": source_detail, "at": now_iso()})
            return lead, False
        lead = new_lead(key, source, source_detail)
        self.leads[key] = lead
        return lead, True

    def touch(self, lead: dict) -> None:
        lead["updated_at"] = now_iso()

    def duplicates_by_contact(self) -> dict[str, list[str]]:
        """Different handles sharing an email or website domain (same business, two accounts)."""
        groups: dict[str, list[str]] = {}
        for lead in self.leads.values():
            keys = {e["email"].lower() for e in lead["contacts"].get("emails", [])}
            dom = normalize_domain(lead["profile"].get("external_url"))
            if dom and dom not in GENERIC_LINK_DOMAINS:
                keys.add(dom)
            for k in keys:
                groups.setdefault(k, []).append(lead["username"])
        return {k: v for k, v in groups.items() if len(v) > 1}

    # ---------- queries ----------
    def by_status(self, *statuses: str) -> list[dict]:
        return [l for l in self.leads.values() if l["status"] in statuses]

    def counts(self) -> dict[str, int]:
        c = {s: 0 for s in STATUSES}
        for l in self.leads.values():
            c[l["status"]] = c.get(l["status"], 0) + 1
        return c


# Link-in-bio services: shared by thousands of accounts, so never a dedup key.
GENERIC_LINK_DOMAINS = {
    "linktr.ee", "beacons.ai", "stan.store", "bio.link", "linkin.bio", "lnk.bio",
    "taplink.cc", "campsite.bio", "solo.to", "msha.ke", "carrd.co", "komi.io",
    "hoo.be", "later.com", "linkpop.com", "snipfeed.co", "koji.to", "tap.bio",
    "calendly.com", "youtube.com", "youtu.be", "instagram.com", "facebook.com",
    "linkedin.com", "tiktok.com", "x.com", "twitter.com", "wa.me", "bit.ly",
}
