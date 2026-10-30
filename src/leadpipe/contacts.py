"""Public business-email extraction. Cheapest sources first, paid ones only if asked.

Order for each QUALIFIED lead (we never spend on unqualified ones):
  1. Instagram itself  - email fields in the scraped data + emails written in the bio. Free.
  2. Their own website - follow the bio link (and link-in-bio pages like Linktree),
                         read the homepage + contact/about pages, collect mailto: and
                         visible emails. Free, plain HTTP requests.
  3. Hunter (optional) - domain search on their own website domain. Uses Hunter credits.
  4. Apify (optional)  - a contact-scraper Actor as a last resort. Costs a little per profile.
Every email keeps its source, so you can see where it came from before using it.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urljoin, urlparse

import requests

from .budget import BudgetGuard, Estimate
from .storage import GENERIC_LINK_DOMAINS, normalize_domain

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")
OBFUSCATED_RE = re.compile(
    r"([A-Za-z0-9._%+\-]+)\s*[\[\(]\s*at\s*[\]\)]\s*([A-Za-z0-9.\-]+)\s*[\[\(]\s*dot\s*[\]\)]\s*([A-Za-z]{2,24})", re.I)
HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#]+)["']""", re.I)

JUNK_DOMAINS = {
    "example.com", "domain.com", "email.com", "sentry.io", "wixpress.com", "sentry-next.wixpress.com",
    "godaddy.com", "squarespace.com", "shopify.com", "wordpress.com", "yourdomain.com", "mysite.com",
    "test.com", "linktr.ee", "beacons.ai", "stan.store",
}
JUNK_LOCAL = {"noreply", "no-reply", "donotreply", "privacy", "abuse", "postmaster", "webmaster", "user", "name", "email"}
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
FREEMAIL = {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "proton.me", "protonmail.com", "aol.com"}
CONTACT_PATHS = ("/contact", "/contact-us", "/about", "/work-with-me")
UA = "Mozilla/5.0 (compatible; lead-research-bot/0.1; public contact lookup)"


def clean_emails(text: str) -> list[str]:
    found = EMAIL_RE.findall(text or "")
    found += [f"{a}@{b}.{c}" for a, b, c in OBFUSCATED_RE.findall(text or "")]
    out = []
    for e in found:
        e = e.strip(".").lower()
        local, _, dom = e.partition("@")
        if (dom in JUNK_DOMAINS or local in JUNK_LOCAL or e.endswith(IMAGE_EXT)
                or re.fullmatch(r"[0-9a-f]{16,}", local)):
            continue
        if e not in out:
            out.append(e)
    return out


def score_email(email: str, source: str, site_domain: str | None, hunter_conf: int | None = None) -> int:
    dom = normalize_domain(email)
    s = {"instagram": 60, "website": 45, "hunter": 35, "apify_contact": 40}.get(source, 30)
    if site_domain and dom == site_domain:
        s += 30
    elif dom in FREEMAIL:
        s += 5
    if hunter_conf is not None:
        s += hunter_conf // 10
    return min(s, 100)


def _add(lead: dict, email: str, source: str, where: str, site_domain: str | None, conf: int | None = None) -> None:
    emails = lead["contacts"]["emails"]
    if any(e["email"] == email for e in emails):
        return
    emails.append({"email": email, "source": source, "found_at": where,
                   "score": score_email(email, source, site_domain, conf)})


def _pick_best(lead: dict) -> None:
    emails = sorted(lead["contacts"]["emails"], key=lambda e: e["score"], reverse=True)
    lead["contacts"]["emails"] = emails
    lead["contacts"]["best_email"] = emails[0]["email"] if emails else None


# ---------------- 1. Instagram data ----------------

def from_instagram(lead: dict) -> None:
    p = lead["profile"]
    site = _own_site_domain(p.get("external_urls") or [])
    for e in clean_emails(" ".join(p.get("listed_emails") or []) + " " + (p.get("bio") or "")):
        _add(lead, e, "instagram", "profile", site)
    if p.get("business_phone") and p["business_phone"] not in lead["contacts"]["phones"]:
        lead["contacts"]["phones"].append(p["business_phone"])


# ---------------- 2. Website crawl ----------------

def _own_site_domain(urls: list[str]) -> str | None:
    for u in urls:
        d = normalize_domain(u)
        if d and d not in GENERIC_LINK_DOMAINS:
            return d
    return None


def _get(url: str, timeout: int) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400 or "text/html" not in r.headers.get("content-type", "text/html"):
            return None
        return r.text[:600_000]
    except requests.RequestException:
        return None


def _mailtos(html: str) -> list[str]:
    return [h[7:].split("?")[0] for h in HREF_RE.findall(html) if h.lower().startswith("mailto:")]


def _outbound_sites(html: str, base: str) -> list[str]:
    """From a link-in-bio page, collect links that look like the person's own website."""
    out = []
    for h in HREF_RE.findall(html):
        url = urljoin(base, unescape(h))
        d = normalize_domain(url)
        if url.startswith("http") and d and d not in GENERIC_LINK_DOMAINS and d not in JUNK_DOMAINS and url not in out:
            out.append(url)
    return out[:5]


def from_websites(lead: dict, max_pages: int, timeout: int) -> None:
    urls = list(lead["profile"].get("external_urls") or [])
    if not urls:
        return
    queue, visited = [], set()
    for u in urls:
        queue.append(u if u.startswith("http") else "https://" + u)
    site_domain = _own_site_domain(urls)
    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        html = _get(url, timeout)
        if not html:
            continue
        dom = normalize_domain(url)
        for e in clean_emails(" ".join(_mailtos(html)) + " " + unescape(re.sub(r"<[^>]+>", " ", html))):
            _add(lead, e, "website", url, site_domain)
        if dom in GENERIC_LINK_DOMAINS:
            # Link-in-bio page: hop to their real site.
            for out in _outbound_sites(html, url):
                if not site_domain:
                    site_domain = normalize_domain(out)
                queue.append(out)
        elif dom == site_domain and not lead["contacts"]["emails"]:
            root = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            queue.extend(root + p for p in CONTACT_PATHS)
    lead["contacts"]["website_domain"] = site_domain


# ---------------- 3. Hunter (optional) ----------------

def from_hunter(leads: list[dict], api_key: str, guard: BudgetGuard) -> int:
    targets = [l for l in leads if not l["contacts"]["emails"] and l["contacts"].get("website_domain")
               and normalize_domain(l["contacts"]["website_domain"]) not in FREEMAIL]
    if not targets:
        return 0
    guard.authorize(Estimate("hunter", f"Hunter domain search for {len(targets)} domains", len(targets), "credits"))
    used = 0
    for lead in targets:
        domain = lead["contacts"]["website_domain"]
        try:
            r = requests.get("https://api.hunter.io/v2/domain-search",
                             params={"domain": domain, "api_key": api_key, "limit": 10}, timeout=20)
        except requests.RequestException:
            continue
        if r.status_code == 429:
            print("[hunter] rate limit or credits exhausted; stopping.")
            break
        if r.status_code >= 400:
            print(f"[hunter] {domain}: {r.status_code} {r.text[:200]}")
            continue
        used += 1
        data = r.json().get("data", {})
        for item in data.get("emails", []):
            e = (item.get("value") or "").lower()
            if e and e in clean_emails(e):
                _add(lead, e, "hunter", f"hunter:{domain}", domain, item.get("confidence"))
        _pick_best(lead)
    guard.record("hunter", used, f"domain search x{used}", unit="credits")
    return used


# ---------------- 4. Apify contact Actor (optional) ----------------

def from_apify_actor(leads: list[dict], apify, settings: dict) -> int:
    targets = [l for l in leads if not l["contacts"]["emails"]]
    if not targets:
        return 0
    price = settings["contact_price_per_profile"] + settings["contact_price_per_contact"] * 2
    # This Actor only processes 3 profiles per run on Apify's free plan (found in the 2026-10-30 test).
    batch = settings.get("contact_batch_size", 3)
    items = []
    for i in range(0, len(targets), batch):
        chunk = targets[i:i + batch]
        items += apify.run_actor(settings["contact_actor"],
                                 {"usernames": [l["username"] for l in chunk], "scrapeLinkInBio": True},
                                 max_items=len(chunk), price_per_item=price, label="contacts")
    by_user = {l["username"]: l for l in targets}
    hits = 0
    for item in items:
        lead = by_user.get(str(item.get("username", "")).lower())
        if not lead:
            continue
        # Field names differ between Actors, so scan the whole item for emails.
        for e in clean_emails(json.dumps(item)):
            _add(lead, e, "apify_contact", settings["contact_actor"], lead["contacts"].get("website_domain"))
            hits += 1
        _pick_best(lead)
    return hits


# ---------------- orchestration ----------------

def run(store, cfg, guard: BudgetGuard, use_hunter: bool, apify=None) -> dict:
    s = cfg.settings["contacts"]
    leads = [l for l in store.by_status("qualified") if not l["contacts"].get("checked_at")]
    for lead in leads:
        from_instagram(lead)
        if s.get("fetch_websites", True):
            from_websites(lead, s["max_pages_per_lead"], s["request_timeout_seconds"])
        _pick_best(lead)
        lead["contacts"]["checked_at"] = datetime.now(timezone.utc).isoformat()
        store.touch(lead)
    store.save()
    hunter_used = 0
    if use_hunter:
        key = cfg.secret("HUNTER_API_KEY")
        if not key:
            print("[hunter] HUNTER_API_KEY not set; skipping.")
        else:
            hunter_used = from_hunter(leads, key, guard)
    apify_hits = from_apify_actor(leads, apify, cfg.settings["apify"]) if apify else 0
    store.save()
    found = sum(1 for l in leads if l["contacts"]["best_email"])
    return {"checked": len(leads), "with_email": found, "hunter_credits": hunter_used, "apify_contacts": apify_hits}
