"""YouTube side of daily sourcing: find coach channels and measure their footage.

Everything here reads metadata only (`yt-dlp -J --skip-download` and public pages).
Nothing is downloaded or stored except the numbers.

Footage gate (Gate 0) tags each channel by its best recent video. Usable width is what's
left after a 9:16 crop at full height: min(width, round(height * 9 / 16)).
  SPEC        long-form with usable width >= min_width (3840x2160 -> 1215)  -> "Spec edit"
  SPEC_FRAME  only a vertical Short passes (1080x1920 -> 1080)            -> "Spec, check frame"
  SPEC_CARD   1080p-or-better landscape long-form (1920x1080 -> 608)     -> "Spec, card layout"
  MOCKUP      720p or lower, or nothing usable (reel-only)               -> "Mockup"
YouTube bot checks ("Sign in to confirm you're not a bot", HTTP 429) are never a verdict:
the channel is UNMEASURED and gets retried on the next run.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import date, datetime

import requests

BOT_MARKERS = ("sign in to confirm", "not a bot", "http error 429", "too many requests", "confirm your age")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

SPEC, SPEC_FRAME, SPEC_CARD, MOCKUP, UNMEASURED = "SPEC", "SPEC_FRAME", "SPEC_CARD", "MOCKUP", "UNMEASURED"
TAGS = [SPEC, SPEC_FRAME, SPEC_CARD, MOCKUP]          # best first


class BotCheck(Exception):
    """YouTube refused the request (bot check or rate limit). Not a footage verdict."""


def usable_width(w: int, h: int) -> int:
    """Width left after cropping the frame to 9:16 at full height."""
    if not w or not h:
        return 0
    return min(w, round(h * 9 / 16))


@dataclass
class YtDlp:
    sleep: float = 2.0                  # pause between calls, be polite
    retries: int = 3                    # extra attempts after a bot check, with backoff
    cookies_from_browser: str | None = None   # e.g. "chrome" on Sam's PC, optional
    binary: str = "yt-dlp"
    runner: object = subprocess.run     # swapped in tests
    timeout: int = 90
    calls: int = 0

    def json(self, args: list[str]) -> dict | None:
        """Run yt-dlp -J. Returns parsed JSON, None on an ordinary failure
        (private/removed video), raises BotCheck if YouTube keeps refusing."""
        cmd = [self.binary, "-J", "--no-warnings", "--ignore-config"]
        if self.cookies_from_browser:
            cmd += ["--cookies-from-browser", self.cookies_from_browser]
        cmd += args
        for attempt in range(self.retries + 1):
            if self.calls:
                time.sleep(self.sleep)
            self.calls += 1
            try:
                r = self.runner(cmd, capture_output=True, text=True, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                continue
            if r.returncode == 0 and r.stdout.strip():
                try:
                    return json.loads(r.stdout)
                except json.JSONDecodeError:
                    return None
            err = (r.stderr or "").lower()
            if any(m in err for m in BOT_MARKERS):
                time.sleep(self.sleep * (4 ** attempt))   # 1x, 4x, 16x the base sleep
                continue
            return None
        raise BotCheck(" ".join(args[-1:]))

    # ---------- discovery ----------
    def search(self, query: str, n: int) -> list[dict]:
        d = self.json(["--flat-playlist", f"ytsearch{n}:{query}"]) or {}
        out = []
        for e in d.get("entries") or []:
            if e.get("channel_id"):
                out.append({"video_id": e.get("id"), "title": e.get("title"), "channel_id": e["channel_id"],
                            "channel": e.get("channel") or e.get("uploader"), "duration": e.get("duration")})
        return out

    def latest_ids(self, channel_id: str, tab: str, n: int) -> list[str]:
        d = self.json(["--flat-playlist", "--playlist-end", str(n),
                       f"https://www.youtube.com/channel/{channel_id}/{tab}"]) or {}
        return [e["id"] for e in (d.get("entries") or []) if e.get("id")][:n]

    # ---------- measurement ----------
    def video(self, video_id: str) -> dict | None:
        d = self.json(["--skip-download", f"https://www.youtube.com/watch?v={video_id}"])
        if not d:
            return None
        best = (0, 0)
        for f in d.get("formats") or []:
            if f.get("vcodec") in (None, "none") or not f.get("width") or not f.get("height"):
                continue
            if f["width"] * f["height"] > best[0] * best[1]:
                best = (f["width"], f["height"])
        if best == (0, 0) and d.get("width") and d.get("height"):
            best = (d["width"], d["height"])
        return {"id": video_id, "width": best[0], "height": best[1], "usable": usable_width(*best),
                "title": d.get("title"), "upload_date": d.get("upload_date"), "duration": d.get("duration"),
                "channel": d.get("channel"), "channel_id": d.get("channel_id"),
                "channel_url": d.get("channel_url"), "subscribers": d.get("channel_follower_count"),
                "language": d.get("language"), "description": (d.get("description") or "")[:1500]}


@dataclass
class Footage:
    channel_id: str
    status: str = UNMEASURED
    best: dict | None = None          # the video that gave the best usable width
    videos: list = field(default_factory=list)
    bot_checked: int = 0
    too_big: int = 0                  # subscriber count, when over the cap (measuring stopped)

    @property
    def last_upload(self) -> date | None:
        ds = [v["upload_date"] for v in self.videos if v.get("upload_date")]
        return datetime.strptime(max(ds), "%Y%m%d").date() if ds else None


def video_tag(v: dict, min_width: int = 900) -> str:
    if v["kind"] == "long-form" and v["usable"] >= min_width:
        return SPEC
    if v["kind"] == "short" and v["usable"] >= min_width:
        return SPEC_FRAME
    if v["kind"] == "long-form" and v["width"] > v["height"] and v["height"] >= 1080:
        return SPEC_CARD
    return MOCKUP


def measure_channel(yt: YtDlp, channel_id: str, long_n: int = 2, shorts_n: int = 1,
                    min_width: int = 900, max_subscribers: int | None = None) -> Footage:
    """Newest `long_n` long-form videos + newest `shorts_n` Short; the best tag wins.
    Stops after the first video if the channel is over `max_subscribers` (fp.too_big)."""
    fp = Footage(channel_id)
    ids: list[tuple[str, str]] = []
    for tab, n in (("videos", long_n), ("shorts", shorts_n)):
        try:
            ids += [(i, tab) for i in yt.latest_ids(channel_id, tab, n)]
        except BotCheck:
            fp.bot_checked += 1
    for vid, tab in ids:
        try:
            v = yt.video(vid)
        except BotCheck:
            fp.bot_checked += 1
            continue
        if v:
            v["kind"] = "short" if tab == "shorts" else "long-form"
            v["tag"] = video_tag(v, min_width) if v["usable"] else None
            fp.videos.append(v)
            if max_subscribers and (v.get("subscribers") or 0) > max_subscribers:
                fp.too_big = v["subscribers"]
                return fp
    measured = [v for v in fp.videos if v["tag"]]
    if measured:
        fp.best = min(measured, key=lambda v: (TAGS.index(v["tag"]), -v["usable"]))
        fp.status = fp.best["tag"]
    return fp


# ---------- channel pages (free HTML, best effort) ----------

LINK_RE = re.compile(r'"link":\{"content":"([^"]+)"')
DESC_RE = re.compile(r'"description":"((?:[^"\\]|\\.){0,3000})"')
SUBS_RE = re.compile(r"([\d.,]+[KMB]?) subscribers")
BROWSE_RE = re.compile(r'"browseId":"(UC[\w-]{22})"')


def _get_page(url: str, timeout: int = 20, get=requests.get) -> str:
    r = get(url, headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=timeout)
    if r.status_code == 429 or "consent.youtube.com" in getattr(r, "url", ""):
        raise BotCheck(url)
    r.raise_for_status()
    return r.text


def channel_about(channel_id: str, get=requests.get) -> dict:
    """Links, description and anything that looks like an email from the About page."""
    html = _get_page(f"https://www.youtube.com/channel/{channel_id}/about", get=get)
    links = list(dict.fromkeys(LINK_RE.findall(html)))
    m = DESC_RE.search(html)
    desc = json.loads(f'"{m.group(1)}"') if m else ""
    subs = SUBS_RE.search(html)
    insta = next((l for l in links if "instagram.com/" in l), None)
    if not insta:
        mi = re.search(r"instagram\.com/([A-Za-z0-9_.]{2,30})", desc)
        insta = f"instagram.com/{mi.group(1)}" if mi else None
    return {"links": links, "description": desc, "subscribers_text": subs.group(1) if subs else None,
            "instagram": ("https://www." + insta.split("://")[-1].removeprefix("www.")) if insta else None}


def related_channels(video_id: str, get=requests.get) -> list[str]:
    """Other channels YouTube suggests next to a video (competitors). Best effort."""
    html = _get_page(f"https://www.youtube.com/watch?v={video_id}", get=get)
    return list(dict.fromkeys(BROWSE_RE.findall(html)))
