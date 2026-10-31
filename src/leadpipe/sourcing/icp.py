"""ICP for YouTube-sourced coaches: free keyword/activity checks first, then Claude
judges the 7 checks against ICP_CRITERIA.md (word for word, same as qualify.py).
"""
from __future__ import annotations

import json
from datetime import date

from ..budget import BudgetGuard, Estimate
from ..qualify import FALLBACK_MODELS, _usage_cost, estimate_cost

CHECKS = ["tactical_business_coach", "solo_not_agency", "sells_to_founders_professionals",
          "real_offer_or_funnel", "english", "talking_head", "active_30_days"]

SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {"type": "object", "properties": {c: {"type": "boolean"} for c in CHECKS},
                   "required": CHECKS, "additionalProperties": False},
        "qualified": {"type": "boolean"},
        "tier": {"type": "string", "enum": ["A", "B", "C"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "offer": {"type": "string"},
        "clip_idea": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["checks", "qualified", "tier", "reasons", "offer", "clip_idea", "confidence"],
    "additionalProperties": False,
}

WRAPPER = """You screen YouTube channels as prospects for a short-form video editor who edits
business coaches' long-form footage into Instagram reels. Judge ONLY against the ICP below.
Run these 7 checks, each true/false, from the data given (say so in reasons when data is thin):
1 tactical_business_coach: teaches sales, marketing, content, client acquisition or leadership,
  tactical not mindset/manifesting/spiritual/emotional
2 solo_not_agency: the coach is the face and the business, not an agency or company brand
3 sells_to_founders_professionals: sells coaching/programs/info to business owners or professionals
4 real_offer_or_funnel: a visible paid offer, call booking, application, lead magnet or course
5 english: content is in English
6 talking_head: the coach talks to camera (solo, podcast or interview), not slides/screen-only/b-roll
7 active_30_days: posted within the last 30 days (today's date is given)
qualified = all 7 true. Tier A = all clearly true, B = all true with one soft spot, C = otherwise.
offer: one line naming their offer if visible, else "not visible".
clip_idea: one line on which recent video and moment would make the best 30-60 s reel.

=== ICP CRITERIA (from the business owner, use as written) ===
"""


def free_checks(card: dict, rules: dict, today: date, max_subscribers: int | None = None) -> list[str]:
    """Cheap reasons to drop before any paid step. Empty list = continue.
    Subscriber cap = [sourcing] max_subscribers (falls back to max_followers in hard_filters.toml)."""
    text = " ".join([card.get("channel") or "", card.get("description") or "",
                     " ".join(v.get("title") or "" for v in card.get("recent_videos", []))]).lower()
    reasons = []
    subs, cap = card.get("subscribers"), max_subscribers or rules.get("max_followers")
    if subs and cap and subs > cap:
        reasons.append(f"{subs:,} subscribers, over the {cap:,} cap")
    for kw in rules.get("exclude_any", []):
        if kw.lower() in text:
            reasons.append(f"excluded keyword: {kw.strip()}")
            break
    last = card.get("last_upload")
    max_days = rules.get("max_days_since_last_post", 30)
    if last and (today - date.fromisoformat(last)).days > max_days:
        reasons.append(f"last upload {last}, over {max_days} days")
    titles = " ".join(v.get("title") or "" for v in card.get("recent_videos", []))
    if titles:
        ascii_share = sum(c.isascii() for c in titles) / len(titles)
        if ascii_share < 0.9:
            reasons.append("titles mostly non-English")
    return reasons


def judge(cards: list[dict], icp_text: str, s: dict, guard: BudgetGuard, today: date) -> dict[str, dict]:
    """Claude API verdicts keyed by channel_id. Needs ANTHROPIC_API_KEY."""
    import anthropic

    if not cards:
        return {}
    guard.authorize(Estimate("claude", f"ICP check {len(cards)} channels with {s['model']}",
                             estimate_cost(len(cards), s)))
    client = anthropic.Anthropic()
    system = [{"type": "text", "text": WRAPPER + icp_text.strip(), "cache_control": {"type": "ephemeral"}}]
    out = {}
    for card in cards:
        kwargs = dict(model=s["model"], max_tokens=4000, system=system,
                      messages=[{"role": "user", "content": f"Today: {today.isoformat()}\nChannel:\n"
                                 + json.dumps(card, ensure_ascii=False)}],
                      output_config={"effort": s.get("effort", "low"),
                                     "format": {"type": "json_schema", "schema": SCHEMA}})
        try:
            if s["model"] in FALLBACK_MODELS:
                resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                   fallbacks="default", **kwargs)
            else:
                resp = client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            print("[icp] rate limited; the rest waits for the next run.")
            break
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            print(f"[icp] {card['channel_id']}: {e}")
            continue
        guard.record("claude", _usage_cost(resp.usage, s), f"icp {card['channel_id']}", meta={"model": s["model"]})
        if resp.stop_reason == "refusal":
            continue
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        try:
            v = json.loads(text)
        except json.JSONDecodeError:
            continue
        v["qualified"] = bool(v.get("qualified")) and all(v.get("checks", {}).get(c) for c in CHECKS)
        out[card["channel_id"]] = v
    return out
