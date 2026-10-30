"""Deterministic pre-filter. Free, instant, explainable.

Only throws out obvious misses using numbers from config/icp/hard_filters.toml.
The real ICP judgement happens in qualify.py with your own criteria.
"""
from __future__ import annotations


import re

OFFER_RE = re.compile(
    r"\b(dm|comment|message)\b[^.\n]{0,25}[\"“'”]?[A-Z]{3,}|link in (my )?bio|apply|book (a|your|now)|free (training|masterclass|guide|"
    r"workshop|class|call|checklist|webinar)|waitlist|enrol|enroll|join (my|the|our)|work with me|start here|strategy (call|session)",
    re.I)


def has_offer_signal(profile: dict) -> bool:
    """Money proxy: they already sell something (Sam: an offer/funnel matters more than follower count)."""
    if profile.get("external_url"):
        return True
    text = (profile.get("bio") or "") + " " + " ".join(r.get("caption") or "" for r in (profile.get("posts") or {}).get("recent", []))
    return bool(OFFER_RE.search(text))


def check(profile: dict, rules: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    followers = profile.get("followers")
    text = " ".join(str(profile.get(k) or "") for k in ("bio", "category", "full_name")).lower()

    if rules.get("require_public", True) and profile.get("is_private"):
        reasons.append("private account")
    if rules.get("exclude_verified") and profile.get("is_verified"):
        reasons.append("verified (checkmark)")
    if followers is not None:
        if followers < rules.get("min_followers", 0):
            reasons.append(f"followers {followers} < {rules['min_followers']}")
        if rules.get("max_followers") and followers > rules["max_followers"]:
            reasons.append(f"followers {followers} > {rules['max_followers']}")
    if (profile.get("posts_count") or 0) < rules.get("min_posts", 0):
        reasons.append(f"posts {profile.get('posts_count')} < {rules['min_posts']}")

    days = (profile.get("posts") or {}).get("days_since_last_post")
    limit = rules.get("max_days_since_last_post")
    if limit and days is not None and days > limit:
        reasons.append(f"last post {days:.0f} days ago (> {limit})")

    posts = profile.get("posts") or {}
    vs = posts.get("video_share")
    if rules.get("min_video_share") is not None and vs is not None and vs < rules["min_video_share"]:
        reasons.append(f"few videos ({vs:.0%} of recent posts)")
    oa = posts.get("original_audio_share")
    if rules.get("min_original_audio_share") is not None and oa is not None and oa < rules["min_original_audio_share"]:
        reasons.append(f"reels mostly music, not talking ({oa:.0%} original audio)")
    if rules.get("require_english"):
        en = posts.get("english_score")
        if en is not None and en < rules.get("min_english_score", 0.12):
            reasons.append(f"captions not in English (score {en})")

    if rules.get("require_offer_signal") and not has_offer_signal(profile):
        reasons.append("no visible offer or funnel (no link, no DM/comment keyword, no apply/book CTA)")

    if rules.get("require_business_or_creator_account") and not profile.get("is_business"):
        reasons.append("not a business/creator account")
    if rules.get("require_external_link") and not profile.get("external_url"):
        reasons.append("no link in bio")

    include = [w.lower() for w in rules.get("include_any", [])]
    if include and not any(w in text for w in include):
        reasons.append("no ICP keyword in bio/category/name")
    hits = [w for w in rules.get("exclude_any", []) if w.lower() in text]
    if hits:
        reasons.append("excluded keyword: " + ", ".join(hits))
    if profile.get("category") in set(rules.get("exclude_categories", [])):
        reasons.append(f"excluded category: {profile.get('category')}")

    return (not reasons), reasons


def run(store, rules: dict) -> dict:
    passed = failed = 0
    for lead in store.by_status("discovered"):
        if store.is_blocked(lead):
            ok, reasons = False, ["on do-not-contact list"]
        else:
            ok, reasons = check(lead["profile"], rules)
        lead["prefilter"] = {"passed": ok, "reasons": reasons}
        lead["status"] = "prefilter_pass" if ok else "prefilter_fail"
        store.touch(lead)
        passed += ok
        failed += not ok
    return {"passed": passed, "failed": failed}
