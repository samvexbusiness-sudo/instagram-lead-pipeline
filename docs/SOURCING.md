# Daily sourcing, footage first: how to run it on the PC

**What it does, every day:**
1. Searches YouTube for business coaches (24 queries in `config/settings.toml` → `[sourcing]`), plus channels suggested next to the ones that pass.
2. **Footage check first (Gate 0).** It measures the newest 2 long-form videos and the newest Short from metadata only, with nothing downloaded. A channel passes when its best video still has at least **900 px of width after a 9:16 crop**.
   - The formula is usable width = min(width, height × 9/16).
   - So 1920×1080 gives 608 (fail), 3840×2160 gives 1215 (pass) and 1080×1920 gives 1080 (pass).
   - A YouTube bot check is never counted as a fail. The channel is marked UNMEASURED and tried again the next day.
3. **ICP:** free keyword and activity checks first, then Claude runs the 7 checks against `config/icp/ICP_CRITERIA.md`.
4. **Email:** YouTube About page and description, then their website, then Hunter (only with `--hunter`). Any published email counts, support@ and info@ included.
5. **Notion Prospects:** one row per survivor, written with:
   - Lane **Spec edit** if the footage passed, **Mockup** if it failed.
   - Status Queued.
   - The measured resolution and video ID in Notes, and the video link in Asset.
   - Plus a "Sourcing · date" summary page under Outreach HQ.

It never emails or DMs anyone. It skips anyone already in Notion, matched by YouTube channel, IG handle, email or name.

## One-time setup on the PC

```bash
git clone https://github.com/samvexbusiness-sudo/instagram-lead-pipeline
```

```bash
cd instagram-lead-pipeline
```

```bash
git checkout claude/tender-ritchie-1yitvw
```

```bash
pip install -U yt-dlp requests anthropic
```

Create a file called `.env` in the repo folder (it is gitignored, never commit it):

```
NOTION_TOKEN=secret_...        # Notion → Settings → Connections → Develop or manage integrations → New internal integration
ANTHROPIC_API_KEY=sk-ant-...   # console.anthropic.com → API keys
HUNTER_API_KEY=...             # optional
```

In Notion, open **Outreach HQ** → ••• → **Connections** → add the integration, so it can read and write Prospects and add summary pages.

## Dry run (writes nothing)

```bash
python run.py source --max-channels 40 --approve-spend
```

It prints:
- How many channels were scanned.
- Footage PASS / FAIL / UNMEASURED counts.
- ICP passes, and how many have an email.
- The first 5 Notion rows it *would* write.

The full report is saved in `data/sourcing/run_<date>_dry.json`. `--approve-spend` is only needed for the Claude ICP checks: about $0.02-0.05 per channel that passes the free checks, inside the caps in `settings.toml`.

## After Sam says yes

```bash
python run.py source --write --approve-spend
```

```bash
powershell -ExecutionPolicy Bypass -File scripts\schedule_daily_sourcing.ps1
```

The scheduler runs it every day at 10:17. The log is at `data/sourcing/logs/sourcing.log`.

## If YouTube keeps bot-checking the PC

Set `cookies_from_browser = "chrome"` (or `"edge"` / `"firefox"`) in `[sourcing]`, so yt-dlp uses your signed-in browser session. Raising `sleep_seconds` to 4 also helps.

## Notes

- `data/sourcing/seen.json` only remembers which channels were already measured, so they aren't re-checked for 60 days. It isn't a lead list; Notion is.
- Reel-only coaches (Instagram downloads come out at 720 px wide) fail the footage check by design. They belong in the mockup lane.
