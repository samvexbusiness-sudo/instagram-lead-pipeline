"""ICP qualification: the one step that needs reasoning, so the one step that uses Claude.

Your criteria in config/icp/ICP_CRITERIA.md are passed to Claude word-for-word.
This module only adds a thin wrapper asking for a fixed JSON verdict, so the
rest of the pipeline (and your mockup workflow later) can read the result.

Two modes (set [claude] mode in settings.toml):
  * "manual" - writes a batch file you paste into claude.ai chat; you save Claude's
                JSON reply and import it. Uses your chat plan, no API bill.
  * "api"    - calls the Claude API directly. Budget-checked like every paid step.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .budget import BudgetGuard, Estimate

WRAPPER = """You qualify Instagram accounts as leads for a short-form video editing service.
Judge each profile ONLY against the ICP criteria below. If data needed for a criterion
is missing, say so in the reasons and lower your confidence; don't guess.

Return the verdict fields exactly as specified:
- qualified: true only if the profile meets the ICP criteria.
- score: 0-100 fit with the ICP.
- tier: "A" (strong fit), "B" (decent), "C" (weak or not a fit).
- reasons: short bullet-style reasons for the verdict.
- disqualifiers: anything that rules them out (empty list if none).
- content_observations: one or two sentences on their current short-form content
  (consistency, hooks, editing quality, captions) based on the post data given.
- mockup_angle: one sentence on what an editing mockup for them should show off.
- confidence: "low", "medium" or "high".

=== ICP CRITERIA (from the business owner, use as written) ===
"""

VERDICT_FIELDS = {
    "username": {"type": "string"},
    "qualified": {"type": "boolean"},
    "score": {"type": "integer"},
    "tier": {"type": "string", "enum": ["A", "B", "C"]},
    "reasons": {"type": "array", "items": {"type": "string"}},
    "disqualifiers": {"type": "array", "items": {"type": "string"}},
    "content_observations": {"type": "string"},
    "mockup_angle": {"type": "string"},
    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
}
VERDICT_SCHEMA = {
    "type": "object",
    "properties": VERDICT_FIELDS,
    "required": list(VERDICT_FIELDS),
    "additionalProperties": False,
}

# Models that accept server-side refusal fallbacks (see Claude API docs).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


def profile_card(lead: dict) -> dict:
    """The compact view of a lead that Claude sees. Keeps tokens (and cost) low."""
    p = lead["profile"]
    posts = p.get("posts") or {}
    return {
        "username": lead["username"],
        "full_name": p.get("full_name"),
        "bio": p.get("bio"),
        "category": p.get("category"),
        "followers": p.get("followers"),
        "posts_count": p.get("posts_count"),
        "is_business": p.get("is_business"),
        "verified": p.get("is_verified"),
        "links": p.get("external_urls"),
        "engagement_rate_pct": p.get("engagement_rate_pct"),
        "days_since_last_post": posts.get("days_since_last_post"),
        "avg_days_between_posts": posts.get("avg_days_between_posts"),
        "video_share_of_recent_posts": posts.get("video_share"),
        "avg_video_views": posts.get("avg_video_views"),
        "recent_posts": [
            {k: r.get(k) for k in ("type", "timestamp", "caption", "likes", "comments", "views")}
            for r in posts.get("recent", [])
        ],
    }


def apply_verdict(store, verdict: dict, source: str) -> bool:
    lead = store.get(verdict.get("username", ""))
    if not lead:
        print(f"[qualify] unknown username in verdict: {verdict.get('username')!r}, skipped")
        return False
    missing = [k for k in VERDICT_FIELDS if k not in verdict]
    if missing:
        print(f"[qualify] verdict for {lead['username']} missing {missing}, skipped")
        return False
    verdict = {k: verdict[k] for k in VERDICT_FIELDS}
    verdict["source"] = source
    verdict["at"] = datetime.now(timezone.utc).isoformat()
    lead["qualification"] = verdict
    if lead["status"] != "exported":
        lead["status"] = "qualified" if verdict["qualified"] else "rejected"
    store.touch(lead)
    return True


# ---------------- manual mode (claude.ai chat) ----------------

def export_manual_batch(store, icp_text: str, out_dir: Path, limit: int) -> Path | None:
    leads = store.by_status("prefilter_pass")[:limit]
    if not leads:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    path = Path(out_dir) / f"qualify_batch_{stamp}.md"
    cards = "\n".join(json.dumps(profile_card(l), ensure_ascii=False) for l in leads)
    path.write_text(
        WRAPPER + icp_text.strip() + "\n\n=== PROFILES (one JSON object per line) ===\n" + cards +
        "\n\n=== OUTPUT ===\nReply with ONLY a JSON array, one object per profile, each with exactly these keys: "
        + ", ".join(VERDICT_FIELDS) + ". No commentary before or after the array.\n"
    )
    return path


def import_manual_batch(store, reply_path: Path) -> dict:
    text = Path(reply_path).read_text()
    match = re.search(r"\[.*\]", text, re.S)   # tolerate ```json fences or stray text
    if not match:
        raise ValueError("Couldn't find a JSON array in that file.")
    verdicts = json.loads(match.group(0))
    ok = sum(apply_verdict(store, v, "claude_chat") for v in verdicts)
    return {"imported": ok, "in_file": len(verdicts)}


# ---------------- API mode ----------------

def estimate_cost(n: int, s: dict) -> float:
    per = (s["est_input_tokens_per_profile"] * s["input_usd_per_mtok"]
           + s["est_output_tokens_per_profile"] * s["output_usd_per_mtok"]) / 1_000_000
    return round(n * per, 4)


def _usage_cost(usage, s: dict) -> float:
    inp = getattr(usage, "input_tokens", 0) or 0
    cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cr = getattr(usage, "cache_read_input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    rate_in = s["input_usd_per_mtok"] / 1_000_000
    return inp * rate_in + cw * rate_in * 1.25 + cr * rate_in * 0.1 + out * s["output_usd_per_mtok"] / 1_000_000


def qualify_via_api(store, icp_text: str, s: dict, guard: BudgetGuard, limit: int) -> dict:
    import anthropic  # imported here so manual mode works without the package

    leads = store.by_status("prefilter_pass")[:limit]
    if not leads:
        return {"qualified": 0, "rejected": 0, "errors": 0}
    guard.authorize(Estimate("claude", f"qualify {len(leads)} profiles with {s['model']}",
                             estimate_cost(len(leads), s)))

    client = anthropic.Anthropic()
    # Same system prompt on every call -> cached after the first request.
    system = [{"type": "text", "text": WRAPPER + icp_text.strip(), "cache_control": {"type": "ephemeral"}}]
    counts = {"qualified": 0, "rejected": 0, "errors": 0}
    spent = 0.0
    for lead in leads:
        kwargs = dict(
            model=s["model"],
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": "Profile:\n" + json.dumps(profile_card(lead), ensure_ascii=False)}],
            output_config={"effort": s.get("effort", "low"),
                           "format": {"type": "json_schema", "schema": VERDICT_SCHEMA}},
        )
        try:
            if s["model"] in FALLBACK_MODELS:
                # If a safety classifier declines, the API retries on a fallback model server-side.
                resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                   fallbacks="default", **kwargs)
            else:
                resp = client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            print("[qualify] rate limited; stopping this run early (progress is saved).")
            break
        except anthropic.APIStatusError as e:
            print(f"[qualify] API error {e.status_code} on {lead['username']}: {e.message}")
            counts["errors"] += 1
            continue
        except anthropic.APIConnectionError:
            print("[qualify] network error; stopping this run early (progress is saved).")
            break

        cost = _usage_cost(resp.usage, s)
        spent += cost
        guard.record("claude", cost, f"qualify {lead['username']}", meta={"model": s["model"]})

        if resp.stop_reason == "refusal":
            lead["qualification"] = {"error": "refusal", "at": datetime.now(timezone.utc).isoformat()}
            counts["errors"] += 1
            continue
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        try:
            verdict = json.loads(text)
        except json.JSONDecodeError:
            counts["errors"] += 1
            continue
        verdict["username"] = lead["username"]  # trust our key, not the model's echo
        if apply_verdict(store, verdict, f"claude_api:{s['model']}"):
            counts["qualified" if verdict["qualified"] else "rejected"] += 1
        store.save()  # save as we go; a crash never loses paid work
    counts["spent_usd"] = round(spent, 4)
    return counts
