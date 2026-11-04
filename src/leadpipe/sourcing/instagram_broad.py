"""Tier B volume lane: about 20-25 mockup-ready leads with an email per day.

Broader than the main ICP on purpose (Sam, 4 Nov): outbound needs volume and mockups are
automated, so a decent fit with a usable email beats a perfect fit without one.

  1. Seeds: Instagram handles already in Notion Prospects (rotated, never the same seed twice
     in 30 days). Their "related profiles" are lookalikes (about 20% qualified on 30 Oct).
  2. Free name screen (lookalike regexes in hard_filters.toml), skip anyone already in Notion.
  3. Apify profile scrape, then the free prefilter (talking-head video, active, English, offer).
  4. Claude Haiku with the BROAD criteria below (tier A or B passes).
  5. Email: Instagram bio/business email, their website, then the Apify contact Actor.
     MX check drops dead domains. Rows WITHOUT an email are not written.
  6. Notion: Lane "Mockup", Status "Queued", Notes start "IG-BROAD <date>". Stops at the target.
Never emails or DMs anyone.
"""
from __future__ import annotations

import json
import random
import re
from datetime import date

from .. import contacts, enrichment, prefilter
from ..apify import ApifyClient
from ..budget import BudgetGuard, Estimate, SpendNotApproved
from ..qualify import _usage_cost, estimate_cost, profile_card
from .notion import Notion, NotionError, build_properties, existing_keys, name_key, plain

BROAD_ICP = """BROAD ICP (volume lane, mockup only). Pass when ALL of these hold:
- A coach, consultant, strategist or expert who sells their own knowledge (coaching, programs,
  courses, memberships, done-for-you services they personally lead) to business owners,
  professionals or aspiring entrepreneurs. Business, sales, marketing, content, leadership,
  career, money or productivity topics are all fine.
- Posts talking-to-camera video (reels where they speak).
- Shows some offer or funnel (link in bio, DM/comment keyword, call booking, waitlist, course).
- English content, posted in the last 30 days.
Fail only for: fitness/nutrition/health/therapy/spiritual/manifesting/relationships, crypto or
trading signals, real estate agents, software companies, video/content/social media agencies or
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


IG_HANDLE = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})")


def _seeds(rows: list[dict], s: dict, log: SeedLog, today: date, n: int) -> list[str]:
    """Prospects that replied or got sent first (best signal), then the rest."""
    def rank(row):
        st = plain(row["properties"].get(s["col_status"], {}))
        return {"Client": 0, "Call booked": 0, "Replied": 1, "Sent": 2, "Queued": 3}.get(st, 4)
    out = []
    for row in sorted(rows, key=lambda r: (rank(r), random.random())):
        m = IG_HANDLE.search(plain(row["properties"].get(s["col_instagram"], {})))
        if m and log.fresh(m.group(1).lower(), today):
            out.append(m.group(1).lower())
        if len(out) >= n:
            break
    return out


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

    # 1. seeds -> related profiles
    seeds = _seeds(rows, s, log, today, b["seeds_per_run"])
    stats["seeds"] = len(seeds)
    if not seeds:
        print("[broad] no fresh seeds (every Notion IG handle was used in the last 30 days)")
        return stats
    seed_items = apify.run_actor(a["profile_actor"], {"usernames": seeds}, len(seeds), a["profile_price_per_result"], "broad-seeds")
    names = {}
    for it in seed_items:
        for r in it.get("relatedProfiles") or []:
            if r.get("username") and not r.get("is_private"):
                names.setdefault(r["username"].lower(), r.get("full_name") or "")
    stats["lookalikes"] = len(names)

    # 2. free screen
    good = re.compile(cfg.hard_filters.get("lookalike_name_include", "."), re.I)
    bad = re.compile(cfg.hard_filters.get("lookalike_name_exclude", "$^"), re.I)
    cands = [u for u, n in names.items()
             if f"ig:{u}" not in known and good.search(u + " " + n) and not bad.search(u + " " + n)
             and not (name_key(n) and name_key(n) in known)]
    cands = cands[: b["max_profiles_per_run"]]
    stats["after_name_screen"] = len(cands)
    print(f"[broad] {len(seeds)} seeds -> {len(names)} lookalikes -> {len(cands)} after free screen")
    if not cands:
        for sd in seeds:
            log.mark(sd, today)
        if not dry_run:
            log.save()
        return stats

    # 3. scrape + prefilter (looser follower cap than the strict lane)
    items = apify.run_actor(a["profile_actor"], {"usernames": cands}, len(cands), a["profile_price_per_result"], "broad-profiles")
    stats["scraped"] = len(items)
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
    leads = [l for l in leads if l["contacts"]["best_email"] and f"email:{l['contacts']['best_email']}" not in known]
    stats["with_email"] = len(leads)

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
                f"IG-BROAD {today.isoformat()} (volume lane, mockup only)", f"tier {v['tier']} ({v['confidence']})",
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
    for sd in seeds:
        log.mark(sd, today)
    if not dry_run:
        log.save()
    return stats
