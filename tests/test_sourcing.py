"""Offline tests for footage-first sourcing. No network: yt-dlp, YouTube pages,
Notion and DNS are all faked. Run: python -m unittest discover tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from leadpipe.budget import BudgetGuard  # noqa: E402
from leadpipe.config import load_config  # noqa: E402
from leadpipe.sourcing import daily, notion  # noqa: E402
from leadpipe.sourcing.youtube import FAIL, PASS, UNMEASURED, BotCheck, YtDlp, measure_channel, usable_width  # noqa: E402

TODAY = date(2026, 10, 31)


def fmt(w, h):
    return {"formats": [{"vcodec": "avc1", "width": 640, "height": 360}, {"vcodec": "avc1", "width": w, "height": h},
                        {"vcodec": "none", "width": None, "height": None}]}


class FakeYouTube:
    """Answers yt-dlp command lines from a dict of channels."""

    def __init__(self, channels, search, bot_ids=()):
        self.channels, self.search_results, self.bot_ids = channels, search, set(bot_ids)

    def __call__(self, cmd, **kw):
        target = cmd[-1]
        ok = lambda d: subprocess.CompletedProcess(cmd, 0, json.dumps(d), "")
        if any(b in target for b in self.bot_ids):
            return subprocess.CompletedProcess(cmd, 1, "", "ERROR: Sign in to confirm you're not a bot")
        if target.startswith("ytsearch"):
            q = target.split(":", 1)[1]
            return ok({"entries": self.search_results.get(q, [])})
        if "/channel/" in target:
            cid, tab = target.split("/channel/")[1].split("/")
            return ok({"entries": [{"id": v} for v in self.channels[cid][tab]]})
        vid = target.split("v=")[1]
        for cid, ch in self.channels.items():
            if vid in ch["meta"]:
                w, h = ch["meta"][vid]
                return ok(fmt(w, h) | {"title": f"{ch['name']} video {vid}", "upload_date": "20261028",
                                       "channel": ch["name"], "channel_id": cid, "channel_follower_count": 5000,
                                       "description": ch.get("desc", "")})
        return subprocess.CompletedProcess(cmd, 1, "", "ERROR: Video unavailable")


CHANNELS = {
    "UC" + "A" * 22: {"name": "Sales Coach Ana", "videos": ["a1", "a2"], "shorts": [], "meta": {"a1": (3840, 2160), "a2": (1920, 1080)},
                      "desc": "Book a call: ana@anasales.com"},
    "UC" + "B" * 22: {"name": "Funnel Coach Ben", "videos": ["b1", "b2"], "shorts": [], "meta": {"b1": (1920, 1080), "b2": (1280, 720)}},
    "UC" + "C" * 22: {"name": "Bot Checked Cara", "videos": ["c1"], "shorts": [], "meta": {"c1": (3840, 2160)}},
    "UC" + "D" * 22: {"name": "Spiritual Soul Healing", "videos": ["d1"], "shorts": [], "meta": {"d1": (3840, 2160)}},
    "UC" + "E" * 22: {"name": "Already Known Eve", "videos": ["e1"], "shorts": [], "meta": {"e1": (3840, 2160)}},
}
SEARCH = {"coach q": [{"id": f"s{i}", "channel_id": cid, "channel": ch["name"]} for i, (cid, ch) in enumerate(CHANNELS.items())]}


class TestFootage(unittest.TestCase):
    def test_usable_width(self):
        self.assertEqual(usable_width(1920, 1080), 608)
        self.assertEqual(usable_width(3840, 2160), 1215)
        self.assertEqual(usable_width(1080, 1920), 1080)
        self.assertEqual(usable_width(1080, 1350), 759)   # 4:5 vertical is height-limited too
        self.assertEqual(usable_width(720, 1280), 720)    # Instagram reel download

    def test_pass_fail_and_bot_check_is_unmeasured(self):
        yt = YtDlp(sleep=0, retries=1, runner=FakeYouTube(CHANNELS, SEARCH, bot_ids={"c1"}))
        self.assertEqual(measure_channel(yt, "UC" + "A" * 22).status, PASS)
        self.assertEqual(measure_channel(yt, "UC" + "B" * 22).status, FAIL)
        cara = measure_channel(yt, "UC" + "C" * 22)
        self.assertEqual(cara.status, UNMEASURED)
        self.assertEqual(cara.bot_checked, 1)

    def test_bot_check_raises_after_retries(self):
        yt = YtDlp(sleep=0, retries=2, runner=FakeYouTube(CHANNELS, SEARCH, bot_ids={"x9"}))
        with self.assertRaises(BotCheck):
            yt.video("x9")
        self.assertEqual(yt.calls, 3)


class TestNotionHelpers(unittest.TestCase):
    def test_build_properties_follows_schema_types(self):
        schema = {"Name": "title", "IG": "url", "Email": "email", "Lane": "select", "Status": "select", "Notes": "rich_text"}
        props = notion.build_properties(schema, {"Name": "Ana", "IG": None, "Email": "a@b.com", "Lane": "Spec edit",
                                                 "Notes": "x", "Unknown col": "y"})
        self.assertEqual(props["Name"]["title"][0]["text"]["content"], "Ana")
        self.assertEqual(props["Lane"], {"select": {"name": "Spec edit"}})
        self.assertNotIn("IG", props)
        self.assertNotIn("Unknown col", props)

    def test_existing_keys(self):
        rows = [{"properties": {"Name": {"type": "title", "title": [{"plain_text": "Eve Coach"}]},
                                "IG": {"type": "url", "url": "https://www.instagram.com/eve.coach/"},
                                "Notes": {"type": "rich_text", "rich_text": [{"plain_text": "YouTube https://www.youtube.com/channel/UC" + "E" * 22}]},
                                "Email": {"type": "email", "email": "eve@x.com"}}}]
        keys = notion.existing_keys(rows)
        self.assertTrue({"name:eve coach", "ig:eve.coach", "yt:UC" + "E" * 22, "email:eve@x.com"} <= keys)


class FakeNotion:
    def __init__(self):
        self.rows, self.pages = [], []

    def schema(self, ds):
        return {"Name": "title", "IG": "url", "Email": "email", "Lane": "select", "Status": "select",
                "Asset": "url", "Next touch": "rich_text", "Notes": "rich_text"}

    def all_rows(self, ds):
        return [{"properties": {"Notes": {"type": "rich_text", "rich_text": [
            {"plain_text": "https://www.youtube.com/channel/UC" + "E" * 22}]}}}]

    def create_row(self, ds, props):
        self.rows.append(props)

    def create_page(self, parent, title, lines):
        self.pages.append((title, lines))


class TestDailyRun(unittest.TestCase):
    def _run(self, dry):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg = load_config(data_dir=Path(tmp.name))
        cfg.settings["sourcing"] |= {"queries": ["coach q"], "per_query": 10, "sleep_seconds": 0, "bot_retries": 1,
                                     "expand_from_winners": 0}
        cfg.settings["contacts"]["fetch_websites"] = False
        guard = BudgetGuard(Path(tmp.name) / "ledger.jsonl", cfg.settings["budget"])
        yt = YtDlp(sleep=0, retries=1, runner=FakeYouTube(CHANNELS, SEARCH, bot_ids={"c1"}))
        fn = FakeNotion()
        about = lambda cid: {"links": [], "description": CHANNELS[cid].get("desc", ""), "instagram": None}
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        out = daily.run(cfg, guard, dry_run=dry, yt=yt, notion=fn, today=TODAY, about_fn=about,
                        related_fn=lambda v: [], lookup_mx=lambda d: ["aspmx.l.google.com"])
        return out, fn

    def test_dry_run_buckets_and_writes_nothing(self):
        out, fn = self._run(dry=True)
        st = out["stats"]
        self.assertEqual(st["skipped_known"], 1)                     # Eve is already in Notion
        self.assertEqual((st[PASS], st[FAIL], st[UNMEASURED]), (2, 1, 1))
        self.assertEqual(st["dropped_free_checks"], 1)               # spiritual/soul/healing
        self.assertEqual((st["spec"], st["mockup"]), (1, 1))         # Ana spec, Ben mockup
        ana = out["rows"][0]
        self.assertEqual((ana["Name"], ana["Lane"], ana["Email"]), ("Sales Coach Ana", "Spec edit", "ana@anasales.com"))
        self.assertIn("1215px usable from 3840x2160", ana["Notes"])
        self.assertEqual(out["rows"][1]["Lane"], "Mockup")
        self.assertEqual(fn.rows, [])
        self.assertEqual(fn.pages, [])

    def test_write_needs_api_key_for_icp(self):
        with self.assertRaises(RuntimeError):
            self._run(dry=False)


if __name__ == "__main__":
    unittest.main()
