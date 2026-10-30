"""Turn raw Apify items into one normalised profile shape. Pure Python.

Both apify/instagram-search-scraper (searchType=user) and
apify/instagram-profile-scraper return the same profile fields, so one
normaliser covers discovery and enrichment. Other Actors can be supported by
adding a small mapping here; nothing downstream needs to change.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")

# Free proxies for "scripted talking head" (we can't watch the videos):
#  - original audio on a reel = someone talking, a licensed song = b-roll / aesthetic / trend
#  - list or how-to style captions = scripted educational reels
LIST_CAPTION_RE = re.compile(
    r"^\W*(\d+\s+\w+|how to\b|why\b|stop\b|the (biggest|real|#?1)\b|if you\b|most\b|don'?t\b|you'?re\b|here'?s\b)"
    r"|\b\d+\s+(mistakes|ways|tips|things|steps|reasons|signs|rules|lessons|questions)\b",
    re.I | re.M)
EN_WORDS = set("the and you your to of a in is it for that this with are i my me we on be not do what how why if can will just more".split())


def english_score(text: str) -> float | None:
    """Share of words that are common English words. ~0.2+ for English, ~0 otherwise."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    total = len(re.findall(r"\w+", text.lower()))
    if total < 15:
        return None
    return round(sum(w in EN_WORDS for w in words) / total, 3)


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _uses_original_audio(post: dict) -> bool:
    m = post.get("musicInfo")
    if not m:
        return True
    return bool(m.get("uses_original_audio"))


def summarize_posts(posts: list[dict], max_posts: int = 12) -> dict:
    posts = [p for p in (posts or []) if isinstance(p, dict)][:max_posts]
    times = sorted((t for t in (_parse_ts(p.get("timestamp")) for p in posts) if t), reverse=True)
    videos = [p for p in posts if p.get("type") == "Video" or p.get("productType") == "clips" or p.get("videoUrl")]
    likes = [p.get("likesCount") or 0 for p in posts if isinstance(p.get("likesCount"), (int, float)) and p.get("likesCount", 0) >= 0]
    comments = [p.get("commentsCount") or 0 for p in posts if isinstance(p.get("commentsCount"), (int, float))]
    views = [p.get("videoViewCount") or p.get("videoPlayCount") or 0 for p in videos]
    # Apify only includes musicInfo when a reel uses a licensed song; no musicInfo = original audio.
    original_audio = [_uses_original_audio(p) for p in videos]
    captions = [p.get("caption") or "" for p in posts]
    list_caps = sum(1 for c in captions if c and LIST_CAPTION_RE.search(c[:200]))
    now = datetime.now(timezone.utc)
    days_between = None
    if len(times) >= 2:
        span = (times[0] - times[-1]).total_seconds() / 86400
        days_between = round(span / (len(times) - 1), 1)
    return {
        "sample_size": len(posts),
        "last_post_at": times[0].isoformat() if times else None,
        "days_since_last_post": round((now - times[0]).total_seconds() / 86400, 1) if times else None,
        "avg_days_between_posts": days_between,
        "video_share": round(len(videos) / len(posts), 2) if posts else None,
        "avg_likes": round(sum(likes) / len(likes)) if likes else None,
        "avg_comments": round(sum(comments) / len(comments)) if comments else None,
        "avg_video_views": round(sum(views) / len(views)) if views else None,
        # talking-head proxies
        "original_audio_share": round(sum(original_audio) / len(original_audio), 2) if original_audio else None,
        "list_caption_share": round(list_caps / len(posts), 2) if posts else None,
        "english_score": english_score(" ".join(captions)),
        "recent": [
            {
                "url": p.get("url"),
                "type": p.get("type"),
                "timestamp": p.get("timestamp"),
                "caption": (p.get("caption") or "")[:280],
                "likes": p.get("likesCount"),
                "comments": p.get("commentsCount"),
                "views": p.get("videoViewCount") or p.get("videoPlayCount"),
                "thumbnail": p.get("displayUrl"),
                "original_audio": _uses_original_audio(p) if p.get("type") == "Video" else None,
                "pinned": p.get("isPinned"),
            }
            for p in posts[:6]
        ],
    }


def normalize_profile(item: dict) -> dict:
    """Map an Apify Instagram profile item to our profile dict."""
    links = []
    if item.get("externalUrl"):
        links.append(item["externalUrl"])
    for l in item.get("externalUrls") or []:
        url = l.get("url") if isinstance(l, dict) else l
        if url and url not in links:
            links.append(url)
    bio = item.get("biography") or ""
    followers = item.get("followersCount")
    posts = summarize_posts(item.get("latestPosts") or [])
    engagement = None
    if followers and posts["avg_likes"] is not None:
        engagement = round(((posts["avg_likes"] or 0) + (posts["avg_comments"] or 0)) / followers * 100, 2)
    # Any email-like field some Actors include, plus anything in the bio.
    listed_emails = [item.get(k) for k in ("businessEmail", "publicEmail", "email", "contactEmail") if item.get(k)]
    return {
        "full_name": item.get("fullName"),
        "bio": bio,
        "category": item.get("businessCategoryName"),
        "is_business": item.get("isBusinessAccount"),
        "is_private": item.get("private"),
        "is_verified": item.get("verified"),
        "followers": followers,
        "following": item.get("followsCount"),
        "posts_count": item.get("postsCount"),
        "external_url": links[0] if links else None,
        "external_urls": links,
        "profile_url": item.get("url") or f"https://www.instagram.com/{item.get('username')}/",
        "profile_pic": item.get("profilePicUrlHD") or item.get("profilePicUrl"),
        "engagement_rate_pct": engagement,
        "posts": posts,
        "related_usernames": [r.get("username") for r in item.get("relatedProfiles") or [] if r.get("username") and not r.get("is_private")],
        "related": [{"username": r.get("username"), "full_name": r.get("full_name")}
                    for r in item.get("relatedProfiles") or [] if r.get("username") and not r.get("is_private")],
        "listed_emails": listed_emails + EMAIL_RE.findall(bio),
        "business_phone": item.get("businessPhoneNumber") or item.get("publicPhoneNumber"),
        "address_city": (item.get("businessAddress") or {}).get("city_name"),
        "search_term": item.get("searchTerm"),
    }


def apply_items(store, items: list[dict], source: str, source_detail_key: str = "searchTerm") -> dict:
    """Upsert Apify items into the store. Returns simple counts."""
    created = updated = skipped = 0
    for item in items:
        username = item.get("username")
        if not username or item.get("error"):
            skipped += 1
            continue
        lead, is_new = store.upsert(username, source, str(item.get(source_detail_key) or ""))
        lead["ig_id"] = item.get("id") or lead.get("ig_id")
        lead["profile"] = normalize_profile(item)
        # A refreshed profile gets re-screened from scratch, unless already exported.
        if lead["status"] != "exported":
            lead["status"] = "discovered"
            lead["prefilter"] = None
        store.touch(lead)
        created += is_new
        updated += not is_new
    return {"new": created, "updated": updated, "skipped": skipped}
