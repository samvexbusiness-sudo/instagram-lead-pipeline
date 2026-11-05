# Handoff: run the pipeline from a local Claude Code session (Sam's PC)

You're on Sam's Windows PC in C:\Users\Antol\instagram-lead-pipeline. Sam wants you to run the commands for him
instead of him pasting them into PowerShell. Keys are in .env (never print or commit them).

Start every session with `git pull`. Runbook: docs/SOURCING.md. Budget caps: config/settings.toml.

## Hard rules
- Never send or draft emails/DMs to prospects. Sourcing only.
- Never invent emails or numbers. Only emails the coach publishes; Hunter accept-all = UNVERIFIED.
- No Google/DuckDuckGo scraping by code. Sam collects Google results himself (bookmarklet, "email | @handle" lines).
- Paid steps need `--approve-spend` AND Sam's yes in chat for that run. Respect the daily caps; don't raise them without asking.
- Do-not-contact: Kirsten Roldan, Kate McKibbin, Michael Chu's Hunter guess, Marcus H, Christian Polk, Camden, Angelo Turri, Thomas Hutcheson.

## The lanes
- Tier A (spec edits, footage-first YouTube): `python run.py source` (dry) then `--write`. Add `--hunter` to spend Hunter credits.
- Tier B (mockups, cheap volume): Sam pastes his bookmarklet output into google.txt, then
  `python run.py import-google google.txt --check-profiles --approve-spend` (preview) and add `--write` to save.
  Already-checked handles are remembered in data/sourcing/google_import_done.json, so the full growing list is fine.
- Paid IG keyword search: `python run.py broad` (dry) / `--write`. About $0.13 per lead; use sparingly.
- Email backfill for Notion rows: `python run.py emails` / `--write`.
- Spend so far: `python run.py status`.

## Money (as of 5 Nov 2026)
Apify free plan, ~$2.30 left until 27 Nov. Hunter ~37 credits, resets 15 Nov.
Always do the dry run first, show Sam the summary, and ask before --write on paid runs.
