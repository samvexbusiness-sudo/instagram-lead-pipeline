"""Notion is the only lead store. This reads Prospects (to skip anyone already there)
and writes new rows + a daily summary page. Needs NOTION_TOKEN (an internal integration
shared with the Outreach HQ page). Property names and types are read from the live
schema, so renaming a column in Notion doesn't silently break writes.
"""
from __future__ import annotations

import re

import requests

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"


class NotionError(RuntimeError):
    pass


class Notion:
    def __init__(self, token: str, session=None):
        if not token:
            raise NotionError("NOTION_TOKEN is not set.")
        self.s = session or requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Notion-Version": VERSION,
                               "Content-Type": "application/json"})

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        r = self.s.request(method, API + path, json=body, timeout=30)
        if r.status_code >= 400:
            raise NotionError(f"{method} {path}: {r.status_code} {r.text[:300]}")
        return r.json()

    def schema(self, data_source_id: str) -> dict[str, str]:
        """{property name: type}"""
        d = self._call("GET", f"/data_sources/{data_source_id}")
        return {name: p["type"] for name, p in d.get("properties", {}).items()}

    def all_rows(self, data_source_id: str) -> list[dict]:
        rows, cursor = [], None
        while True:
            body = {"page_size": 100} | ({"start_cursor": cursor} if cursor else {})
            d = self._call("POST", f"/data_sources/{data_source_id}/query", body)
            rows += d.get("results", [])
            if not d.get("has_more"):
                return rows
            cursor = d.get("next_cursor")

    def create_row(self, data_source_id: str, properties: dict) -> dict:
        return self._call("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": data_source_id},
                                             "properties": properties})

    def create_page(self, parent_page_id: str, title: str, lines: list[str]) -> dict:
        blocks = [{"object": "block", "type": "paragraph",
                   "paragraph": {"rich_text": [{"type": "text", "text": {"content": l[:1900]}}]}} for l in lines]
        return self._call("POST", "/pages", {"parent": {"page_id": parent_page_id},
                                             "properties": {"title": {"title": [{"text": {"content": title}}]}},
                                             "children": blocks})


# ---------------- reading rows ----------------

def plain(prop: dict) -> str:
    """Any Notion property value as plain text."""
    t = prop.get("type")
    v = prop.get(t)
    if t in ("title", "rich_text"):
        return "".join(x.get("plain_text", "") for x in v or [])
    if t in ("url", "email", "phone_number"):
        return v or ""
    if t in ("select", "status"):
        return (v or {}).get("name", "")
    if t == "multi_select":
        return " ".join(x.get("name", "") for x in v or [])
    return ""


IG_RE = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})", re.I)
YT_RE = re.compile(r"(UC[\w-]{22})|youtube\.com/(@[\w.-]+)", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def keys_from_text(text: str) -> set[str]:
    keys = set()
    keys |= {"ig:" + m.lower().rstrip(".") for m in IG_RE.findall(text)}
    for cid, handle in YT_RE.findall(text):
        keys.add("yt:" + (cid or handle.lower()))
    keys |= {"email:" + e.lower() for e in EMAIL_RE.findall(text)}
    return keys


FILLER = {"coaching", "coach", "official", "llc", "inc", "co", "the", "with", "by", "academy", "consulting", "tv"}


def name_key(name: str) -> str:
    """'Joanna Lott Coaching' and 'Joanna Lott' -> 'nm:joanna lott'."""
    words = [w for w in re.findall(r"[a-z]+", (name or "").lower().split("|")[0]) if w not in FILLER]
    return "nm:" + " ".join(words[:2]) if len(words) >= 2 else ""


def existing_keys(rows: list[dict]) -> set[str]:
    """Everything that identifies a prospect already in Notion: IG handle, YouTube
    channel, email, and the name (lowercased)."""
    keys = set()
    for row in rows:
        props = row.get("properties", {})
        text = " ".join(plain(p) for p in props.values())
        keys |= keys_from_text(text)
        for p in props.values():
            if p.get("type") == "title":
                name = plain(p).strip().lower()
                if name:
                    keys.add("name:" + name)
                    if name_key(name):
                        keys.add(name_key(name))
    return keys


# ---------------- writing rows ----------------

def build_properties(schema: dict[str, str], values: dict) -> dict:
    """values {column: python value} -> Notion property JSON, by the column's real type.
    Unknown columns and empty values are skipped."""
    out = {}
    for name, value in values.items():
        t = schema.get(name)
        if t is None or value in (None, ""):
            continue
        s = str(value)
        if t == "title":
            out[name] = {"title": [{"text": {"content": s[:1900]}}]}
        elif t == "rich_text":
            out[name] = {"rich_text": [{"text": {"content": s[:1900]}}]}
        elif t in ("url", "email", "phone_number"):
            out[name] = {t: s}
        elif t == "select":
            out[name] = {"select": {"name": s}}
        elif t == "status":
            out[name] = {"status": {"name": s}}
        elif t == "multi_select":
            out[name] = {"multi_select": [{"name": x} for x in (value if isinstance(value, list) else [s])]}
        elif t == "checkbox":
            out[name] = {"checkbox": bool(value)}
        elif t == "number":
            out[name] = {"number": float(value)}
        elif t == "date":
            out[name] = {"date": {"start": s}}
    return out
