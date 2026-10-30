# Instagram lead pipeline

Finds Instagram business coaches, checks them against **your** ICP criteria, finds a
public business email, and hands you ~20 leads a day plus files your mockup workflow
can pick up. It never sends outreach. Anything that costs money stops and shows you
the price first.

Full design, Actor research, costs and the test plan: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## What happens, in plain terms

1. **Discover** – Apify searches Instagram for your keywords and returns full profiles. (paid, pennies)
2. **Pre-filter** – Python throws out obvious misses (private, tiny, inactive, wrong niche). (free)
3. **Qualify** – Claude judges each remaining profile against your ICP file. (free in manual mode)
4. **Contacts** – Python finds public emails from the bio and their website. Hunter is optional. (free by default)
5. **Export** – a CSV for you + one JSON per lead for the mockup step. (free)

## Setup (once)

You need Python 3.11+.

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Then open `.env` and paste your `APIFY_TOKEN` (Apify console → Settings → API & Integrations).
`ANTHROPIC_API_KEY` and `HUNTER_API_KEY` are optional.

Then fill in the two files that make it yours:

* `config/icp/ICP_CRITERIA.md` – paste your existing ICP criteria, unchanged.
* `config/icp/hard_filters.toml` – follower range, activity, words to include/exclude.

## Try it for free first

```bash
python run.py demo
```

Runs the whole thing on fake sample profiles. No keys, no internet, no cost.

## Commands

| Command | What it does | Cost |
|---|---|---|
| `python run.py plan-test` | prints the 100-profile test plan with prices | free |
| `python run.py discover ... --approve-spend` | keyword search on Instagram | Apify |
| `python run.py prefilter` | cheap yes/no checks | free |
| `python run.py qualify` | writes a batch file to paste into claude.ai | free |
| `python run.py import-verdicts FILE` | loads Claude's answer | free |
| `python run.py contacts` | finds public emails (`--hunter`, `--apify-contacts` optional) | free / optional paid |
| `python run.py export` | today's CSV + mockup hand-off files | free |
| `python run.py snowball --approve-spend` | checks lookalikes of good leads | Apify |
| `python run.py status` | counts and money spent | free |

Without `--approve-spend`, a paid command only prints the estimate. Even with it, the
caps in `config/settings.toml` block anything over budget.

## Tests

```bash
python -m unittest discover tests
```
