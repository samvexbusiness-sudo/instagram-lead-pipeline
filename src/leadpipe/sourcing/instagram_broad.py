"""Tier B volume lane: about 20-25 mockup-ready leads with an email per day.

Broader than the main ICP on purpose (Sam, 4 Nov): outbound needs volume and mockups are
automated, so a decent fit with a usable email beats a perfect fit without one.

  1. Instagram keyword search ([broad] keywords, rotated with a cooldown). Lookalikes
     ("related profiles") stopped working on 31 Oct, so search is the source.
  2. Free screen (exclude regex in hard_filters.toml), skip anyone already in Notion.
  3. The free prefilter (talking-head video, active, English, offer).
  4. Claude Haiku with the BROAD criteria below (tier A or B passes).
  5. Email: Instagram bio/business email, their website, then the Apify contact Actor.
     MX check drops dead domains. Rows WITHOUT an email are not written.
  6. Notion: Lane "Mockup", Status "Queued", Notes start "IG-BROAD <date>". Stops at the target.
Never emails or DMs anyone.
"""
from __future__ import annotations

import json
import re
from datetime import date

from .. import contacts, enrichment, prefilter
from ..apify import ApifyClient
from ..budget import BudgetGuard, Estimate, SpendNotApproved
from ..qualify import _usage_cost, estimate_cost, profile_card
from .notion import Notion, NotionError, build_properties, existing_keys, name_key

BROAD_ICP = """BROAD ICP (volume lane, mockup only). Pass when ALL of these hold:
- A coach, consultant, strategist or expert who sells their own knowledge (coaching, programs,
  courses, memberships, done-for-you services they personally lead) to business owners,
  professionals or aspiring entrepreneurs. Business, sales, marketing, content, leadership,
  career, money or productivity topics are all fine.
- Posts talking-to-camera video (reels where they speak).
- Shows some offer or funnel (link in bio, DM/comment keyword, call booking, waitlist, course).
- English content, posted in the last 30 days.
Fail only for: fitness/nutrition/health/therapy/spiritual/manifesting/relationships, crypto or
trading signals, network marketing/MLM, real estate agents, software companies, video/content/social media agencies or
editors (competitors), faceless/meme/quote pages, or brands with no person on camera.
Tier A = clear fit for the strict ICP below as well; Tier B = fits the broad lane only.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "qualified": {"type": "boolean"},
        "tier": {"type": "string", "enum": ["A", "B", "C"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "mockup_angle": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["qualified", "tier", "reasons", "mockup_angle", "confidence"],
    "additionalProperties": False,
}


class SeedLog:
    def __init__(self, path):
        self.path = path
        self.d = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def fresh(self, handle: str, today: date, days: int = 30) -> bool:
        return handle not in self.d or (today - date.fromisoformat(self.d[handle])).days >= days

    def mark(self, handle: str, today: date) -> None:
        self.d[handle] = today.isoformat()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.d, indent=1), encoding="utf-8")


class KeywordYield:
    """Per-keyword totals across runs: profiles found and rows with an email. Keywords that
    produce emails get picked first; untested ones get a fair chance; a keyword with 0 emails
    after 60+ profiles is skipped."""

    def __init__(self, path):
        self.path = path
        self.d = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def add(self, kw, profiles: int = 0, emails: int = 0) -> None:
        if not kw:
            return
        e = self.d.setdefault(kw, {"profiles": 0, "emails": 0})
        e["profiles"] += profiles
        e["emails"] += emails

    def score(self, kw: str) -> float:
        e = self.d.get(kw, {"profiles": 0, "emails": 0})
        return (e["emails"] + 1) / (e["profiles"] + 25)   # untested keywords score 0.04, like a decent one

    def pick(self, candidates: list[str], n: int) -> list[str]:
        alive = [k for k in candidates if not (self.d.get(k, {}).get("profiles", 0) >= 60
                                               and self.d.get(k, {}).get("emails", 0) == 0)]
        return sorted(alive, key=self.score, reverse=True)[:n]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.d, indent=1), encoding="utf-8")


def _judge(cards: list[dict], strict_icp: str, s: dict, guard: BudgetGuard) -> dict[str, dict]:
    import anthropic

    guard.authorize(Estimate("claude", f"broad ICP check {len(cards)} profiles with {s['model']}",
                             estimate_cost(len(cards), s)))
    client = anthropic.Anthropic()
    system = [{"type": "text", "cache_control": {"type": "ephemeral"},
               "text": "You screen Instagram accounts as prospects for a short-form video editor's "
                       "mockup outreach. Judge from the data given; when data is thin but nothing "
                       "rules them out, pass with lower confidence.\n\n" + BROAD_ICP
                       + "\n=== STRICT ICP (for tier A only) ===\n" + strict_icp.strip()}]
    out = {}
    for card in cards:
        try:
            resp = client.messages.create(
                model=s["model"], max_tokens=1500, system=system,
                messages=[{"role": "user", "content": "Profile:\n" + json.dumps(card, ensure_ascii=False)}],
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}})
        except anthropic.RateLimitError:
            print("[broad] rate limited; the rest waits for the next run.")
            break
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            print(f"[broad] {card['username']}: {e}")
            continue
        guard.record("claude", _usage_cost(resp.usage, s), f"broad icp {card['username']}", meta={"model": s["model"]})
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        try:
            v = json.loads(text)
        except json.JSONDecodeError:
            continue
        out[card["username"]] = v
    return out


FREEMAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com", "proton.me", "protonmail.com"}


def _email_is_theirs(lead: dict) -> bool:
    """A free-mail address scraped off a website must share a name part with the account
    (4 Nov: Shan's row got themadisonhatten@gmail.com from someone else's page). Addresses on
    their own domain, or given by Instagram itself, are trusted."""
    c = lead["contacts"]
    e = c["best_email"]
    src = next((x["source"] for x in c["emails"] if x["email"] == e), "")
    local, dom = e.split("@")
    if dom not in FREEMAIL or src in ("instagram", "apify_contact"):
        return True
    words = re.findall(r"[a-z]{4,}", ((lead["profile"].get("full_name") or "") + " " + lead["username"]).lower())
    return any(w in local.lower() for w in words)


def _best_reel(p: dict) -> str | None:
    recent = [r for r in (p.get("posts") or {}).get("recent", []) if r.get("type") == "Video" and r.get("url")]
    talking = [r for r in recent if r.get("original_audio")] or recent
    best = max(talking, key=lambda r: r.get("views") or 0, default=None)
    return best["url"] if best else None


def run(cfg, guard: BudgetGuard, *, dry_run: bool, target: int | None = None, notion: Notion | None = None,
        apify=None, judge=None, lookup_mx=None, today: date | None = None) -> dict:
    s, b = cfg.settings["sourcing"], cfg.settings["broad"]
    today = today or date.today()
    target = target or b["daily_target"]
    stats = {"date": today.isoformat(), "seeds": 0, "lookalikes": 0, "after_name_screen": 0, "scraped": 0,
             "prefilter_pass": 0, "icp_pass": 0, "with_email": 0, "written": 0, "rows": []}

    notion = notion or Notion(cfg.secret("NOTION_TOKEN"))
    schema = notion.schema(s["notion_prospects_ds"])
    rows = notion.all_rows(s["notion_prospects_ds"])
    known = existing_keys(rows)
    log = SeedLog(cfg.paths.data / "sourcing" / "ig_seeds_used.json")
    apify = apify or ApifyClient(cfg.secret("APIFY_TOKEN"), guard, cfg.paths.raw, cfg.settings["apify"]["run_timeout_seconds"])
    a = cfg.settings["apify"]

    # 1. keyword search (Instagram stopped returning "related profiles" on 31 Oct, so no lookalikes).
    #    The search Actor returns full profiles, so there's no second scrape.
    ylog = KeywordYield(cfg.paths.data / "sourcing" / "keyword_yield.json")
    kws = ylog.pick([k for k in b["keywords"] if log.fresh("kw:" + k, today, b["keyword_cooldown_days"])],
                    b["keywords_per_run"])
    stats["seeds"] = len(kws)
    if not kws:
        print("[broad] every keyword was used recently; add more to [broad] keywords or lower keyword_cooldown_days")
        return stats
    n = len(kws) * b["per_keyword"]
    items = apify.run_actor(a["discovery_actor"], {"search": ", ".join(kws), "searchType": "user",
                                                   "searchLimit": b["per_keyword"]},
                            n, a["discovery_price_per_result"], "broad-search")
    bad = re.compile(cfg.hard_filters.get("lookalike_name_exclude", "$^"), re.I)
    seen, fresh = set(), []
    for it in items:
        u = str(it.get("username", "")).lower()
        n_ = it.get("fullName") or ""
        if not u or u in seen or f"ig:{u}" in known or (name_key(n_) and name_key(n_) in known):
            continue
        seen.add(u)
        if bad.search(u + " " + n_ + " " + (it.get("biography") or "")):
            continue
        fresh.append(it)
    stats["lookalikes"] = len(items)
    stats["after_name_screen"] = stats["scraped"] = len(fresh)
    print(f"[broad] {len(kws)} keywords -> {len(items)} profiles -> {len(fresh)} new after free screen")
    items = fresh
    seeds = ["kw:" + k for k in kws]

    for it in items:
        ylog.add(it.get("searchTerm"), profiles=1)
    process(cfg, guard, items, stats, known=known, schema=schema, notion=notion, apify=apify, judge=judge,
            lookup_mx=lookup_mx, today=today, dry_run=dry_run, target=target, tag="IG-BROAD", ylog=ylog)
    if not dry_run:
        ylog.save()
    for sd in seeds:
        log.mark(sd, today)
    if not dry_run:
        log.save()
    return stats


def process(cfg, guard: BudgetGuard, items: list[dict], stats: dict, *, known: set, schema: dict, notion: Notion,
            apify, judge, lookup_mx, today: date, dry_run: bool, target: int, tag: str,
            ylog: "KeywordYield | None" = None, extra_emails: dict | None = None) -> None:
    """Shared back half: prefilter -> broad ICP -> email -> Notion rows. `extra_emails` maps a
    handle to an email already seen publicly (e.g. in a Google result showing their bio)."""
    s, b, a = cfg.settings["sourcing"], cfg.settings["broad"], cfg.settings["apify"]
    rules = dict(cfg.hard_filters, max_followers=b["max_followers"], require_external_link=False)
    leads = []
    for it in items:
        p = enrichment.normalize_profile(it)
        ok, _ = prefilter.check(p, rules)
        if ok:
            leads.append({"username": str(it.get("username", "")).lower(), "profile": p,
                          "contacts": {"emails": [], "phones": [], "best_email": None}})
    stats["prefilter_pass"] = len(leads)

    # 4. broad ICP
    icp_settings = dict(cfg.settings["claude"], model=s.get("icp_model") or cfg.settings["claude"]["model"])
    try:
        verdicts = (judge or _judge)([profile_card(l) for l in leads], cfg.icp_text, icp_settings, guard)
    except SpendNotApproved as e:
        if not dry_run:
            raise
        print(f"[broad] ICP skipped in dry run: {e}")
        verdicts = {}
    leads = [l | {"icp": verdicts[l["username"]]} for l in leads
             if verdicts.get(l["username"], {}).get("qualified") and verdicts[l["username"]].get("tier") in ("A", "B")]
    stats["icp_pass"] = len(leads)

    # 5. email: IG bio/business email, website, then the contact Actor for the rest
    for l in leads:
        if extra_emails and extra_emails.get(l["username"]):
            contacts._add(l, extra_emails[l["username"]], "instagram", "Google result showing their bio", None)
        contacts.from_instagram(l)
        if not l["contacts"]["emails"] and cfg.settings["contacts"].get("fetch_websites", True):
            contacts.from_websites(l, cfg.settings["contacts"]["max_pages_per_lead"],
                                   cfg.settings["contacts"]["request_timeout_seconds"])
        contacts._pick_best(l)
    try:
        contacts.from_apify_actor(leads, apify, a)
    except SpendNotApproved as e:
        print(f"[broad] Instagram contact step skipped: {e}")
    contacts.check_providers(leads, **({"lookup": lookup_mx} if lookup_mx else {}))
    leads = [l for l in leads if l["contacts"]["best_email"] and f"email:{l['contacts']['best_email']}" not in known
             and _email_is_theirs(l)]
    stats["with_email"] = len(leads)
    if ylog:
        for l in leads:
            ylog.add(l["profile"].get("search_term"), emails=1)

    # 6. Notion rows, tier A first, capped at the target
    leads.sort(key=lambda l: (l["icp"]["tier"], -(l["profile"].get("followers") or 0)))
    for l in leads[:target]:
        p, v, c = l["profile"], l["icp"], l["contacts"]
        src = next((e["source"] for e in c["emails"] if e["email"] == c["best_email"]), "?")
        values = {
            s["col_name"]: p.get("full_name") or l["username"],
            s["col_instagram"]: f"https://www.instagram.com/{l['username']}/",
            s["col_email"]: c["best_email"],
            s["col_lane"]: s["lane_mockup"],
            s["col_status"]: s["status_new"],
            s["col_asset"]: _best_reel(p),
            s["col_next"]: "Before/after mockup, Sam reviews first",
            s["col_notes"]: " · ".join([
                f"{tag} {today.isoformat()} (volume lane, mockup only)", f"tier {v['tier']} ({v['confidence']})",
                f"{p.get('followers') or '?'} followers", "; ".join(v.get("reasons", [])[:2]),
                f"Mockup angle: {v.get('mockup_angle')}", f"Email from {src} ({c.get('best_provider') or '?'})"]),
        }
        stats["rows"].append(values)
        if not dry_run:
            try:
                notion.create_row(s["notion_prospects_ds"], build_properties(schema, values))
                stats["written"] += 1
            except NotionError as e:
                print(f"[notion] skipped {values[s['col_name']]}: {e}")
