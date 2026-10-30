# Architecture & plan

Goal: ~20 qualified Instagram business-coach leads per day, each with a public
business contact, for a short-form video editing offer. Low cost, your ICP
criteria untouched, nothing paid or sent without your approval.

Rule of thumb used everywhere: **Python does anything with a right answer**
(counting, filtering, dedup, regex, budgets). **Claude only does judgement**
(does this person match the ICP, and what would a mockup for them show).

---

## 1. Pipeline

```
 keywords.txt ──► [1 DISCOVER]  Apify instagram-search-scraper (searchType=user)
                       │        returns full profiles: bio, followers, link, last ~12 posts
                       ▼
                 [2 STORE + DEDUP]  data/leads.json  (one record per handle, forever)
                       │            raw Apify output kept in data/raw/ (never pay twice)
                       ▼
                 [3 PRE-FILTER]  Python, free. hard_filters.toml: followers, activity,
                       │         private, link-in-bio, include/exclude words
                       ▼
                 [4 QUALIFY]  Claude + YOUR ICP_CRITERIA.md (verbatim)
                       │      manual mode (claude.ai chat, $0) or API mode (paid, capped)
                       ▼
                 [5 CONTACTS]  free first: IG fields → bio → website/link-in-bio crawl
                       │       optional: Hunter domain search → Apify contact Actor
                       ▼
                 [6 EXPORT]  leads_<date>.csv/.json  +  data/handoff/mockup_queue/<user>.json
                       │                                   └─► your mockup workflow (later)
                       ▼
                 [7 SNOWBALL]  "related profiles" of qualified leads → profile scraper
                               (lookalikes of people who already fit; usually best yield)
```

Every step reads and writes the same `leads.json`, so steps can run on
different days, be re-run safely, or be swapped out independently.

Code map (`src/leadpipe/`):

| Step | File | Uses Claude? | Costs money? |
|---|---|---|---|
| Settings, keys, paths | `config.py` | no | no |
| Store + dedup | `storage.py` | no | no |
| Budget caps + approval gate | `budget.py` | no | no |
| Apify calls | `apify.py` | no | **yes** (capped) |
| Normalise profiles | `enrichment.py` | no | no |
| Pre-filter | `prefilter.py` | no | no |
| Qualify | `qualify.py` | **yes** | manual: no / API: **yes** (capped) |
| Emails | `contacts.py` | no | Hunter / Apify fallback only, opt-in |
| Export + hand-off | `export.py`, `integrations/mockup.py` | no | no |
| Commands | `cli.py` (run via `run.py`) | | |

---

## 2. Apify Actor research (Oct 2026, FREE-tier prices; paid Apify tiers are cheaper)

### Keyword-based discovery

| Actor | Price | Notes | Verdict |
|---|---|---|---|
| `apify/instagram-search-scraper` (official) | $0.0027 / result | 38k users, 4.84★. `searchType: "user"` returns **full profile data** (bio, followers, link, category, recent posts, related profiles). Comma-separate many terms in one run. | **Primary.** Discovery and enrichment in one paid call. |
| `memo23/instagram-search-scraper` | $0.002 / result + $0.004 enrich | Built-in `onlyBusiness`, `minFollowers`, `onlyWithEmail` filters, pulls public email. Community-made, 1 rating. | Backup / A-B test. Could be cheaper per *qualified* lead thanks to its filters. |
| `data-slayer/instagram-search-users` | $0.0025 basic, $0.012 enriched | Enriched tier adds email/phone. | Pricier than official + own crawl. |
| `afanasenko/instagram-influencer-search` | $0.01 / profile | AI discovery, many filters. | 4x the price. Skip for now. |
| `data-slayer/instagram-search-reels` | $0.0025 / reel (+start fee) | Finds people *posting reels* on a topic. | Optional second discovery source: everyone found already posts short-form. |

Limitation to plan around: Instagram search only returns a limited set of
accounts per term. Many narrow terms (`config/keywords.txt`) + snowballing
beats a few broad ones.

### Profile enrichment (you already have usernames)

| Actor | Price | Notes | Verdict |
|---|---|---|---|
| `apify/instagram-profile-scraper` (official) | $0.0026 / profile | 268k users, 4.75★. Same fields as search. **No email field** in its output. "About" add-on $0.007 (join date/country) – not needed. | **Primary** for snowball/refresh. |
| `coderx/instagram-profile-scraper-bio-posts` | $0.0011 / result | 5★ (9 ratings). Cheaper. | Test later as a cost cut. |

### Contact extraction (last-resort, paid)

| Actor | Price | Notes |
|---|---|---|
| `memo23/instagram-email-phone-scraper` | $0.002 / profile + $0.005 / contact found | Follows link-in-bio pages. **Wired in as optional fallback.** |
| `zaver.api/instagram-email-contact-extractor` | $0.004 / profile + $0.01 / contact | Alternative. |
| `seemuapps/instagram-contact-scraper` | $0.0065 / result | 2.3★. Skip. |

Swapping Actors = change the name/price in `config/settings.toml`, plus a small
field mapping in `enrichment.normalize_profile` if their output differs.

---

## 3. Storage & dedup

* **One file:** `data/leads.json`, keyed by normalised username
  (`@Some.Coach`, `instagram.com/some.coach/` → `some.coach`). Writes are atomic.
* **Before paying** (snowball): `LeadStore.filter_new()` drops handles seen in the last
  `recheck_after_days` (90), blocked handles, and repeats in the same batch.
* **After scraping:** same handle from two keywords = one lead with two `sources`.
* **Same business, two accounts:** `status` command lists handles that share an email
  or website domain (link-in-bio domains like linktr.ee are ignored for this).
* **Do-not-contact:** `config/do_not_contact.txt` (handles, emails or domains) is checked
  at pre-filter and export, forever.
* **Audit trail:** every paid Apify result is saved under `data/raw/<date>/`; every cost
  is a line in `data/spend_ledger.jsonl`.
* `data/` is git-ignored: it holds people's contact details.

Lead record (abridged):

```json
{
  "username": "some.coach", "ig_id": "123", "status": "qualified",
  "sources": [{"type": "keyword_search", "detail": "business coach", "at": "..."}],
  "profile": {"bio": "...", "followers": 14200, "external_urls": ["..."],
              "posts": {"days_since_last_post": 2, "video_share": 0.67, "recent": ["..."]},
              "related_usernames": ["..."]},
  "prefilter": {"passed": true, "reasons": []},
  "qualification": {"qualified": true, "score": 86, "tier": "A", "reasons": ["..."],
                    "content_observations": "...", "mockup_angle": "...", "confidence": "high"},
  "contacts": {"best_email": "hello@site.com",
               "emails": [{"email": "hello@site.com", "source": "website", "score": 75}]},
  "outreach_status": "not_contacted"
}
```

Statuses: `discovered → prefilter_fail | prefilter_pass → rejected | qualified → exported`.
`outreach_status` is yours to edit by hand; the pipeline never contacts anyone.

---

## 4. Qualification (your ICP, not a new one)

Two layers:

1. **Pre-filter (`hard_filters.toml`, Python, free).** Only obvious misses: private,
   follower range, inactive, no link, excluded words/categories. Set the numbers from
   your ICP and keep them loose. Each rejection stores its reason so you can audit it.
2. **Claude judgement (`ICP_CRITERIA.md`).** Your criteria are pasted in verbatim. The
   pipeline wraps them with one instruction: return a fixed JSON verdict
   (`qualified, score, tier, reasons, disqualifiers, content_observations,
   mockup_angle, confidence`). Claude sees a compact "profile card" (bio, numbers,
   links, last 6 post captions/stats), not raw scraped data, which keeps tokens low.

Modes:

* **manual (default):** `qualify` writes `data/handoff/qualify_batch_*.md`. Paste it into
  claude.ai (or your existing Claude Project with your workflows), save the JSON reply,
  `import-verdicts` it. Uses your chat plan, no API bill. ~40–60 profiles per paste.
* **api:** same prompt via the Claude API. System prompt is prompt-cached, effort is
  `low`, structured JSON output is enforced, refusals fall back server-side, every call's
  real token cost goes in the ledger. Model is a setting: default `claude-opus-5-5`;
  `claude-haiku-5-5` is ~95% cheaper — compare both on the test batch before choosing.

If your existing workflow uses its own prompt or output format, replace `WRAPPER` /
`VERDICT_FIELDS` in `qualify.py`; nothing else depends on the wording.

---

## 5. Public business email extraction

Only for **qualified** leads (never spend on rejects). Cheapest first, stop when found:

1. **Instagram data** – email fields some Actors return, plus emails/obfuscated
   `name [at] site [dot] com` in the bio. Free.
2. **Their website** – follow the bio link. If it's Linktree/Beacons/Stan etc., hop to
   their own domain. Read home + `/contact`, `/about`, `/work-with-me`. Collect `mailto:` and
   visible emails; drop junk (noreply, image names, Wix/Sentry IDs, placeholders). Max 4
   pages per lead, polite timeouts. Free.
3. **Hunter (optional, `--hunter`)** – `domain-search` on their own website domain only
   (not gmail, not link-in-bio domains). Counted in credits against `hunter_monthly_credits`.
4. **Apify contact Actor (optional, `--apify-contacts`)** – last resort for leads still
   without an email. Budget-capped like other Apify runs.

Each email keeps `source`, `found_at` and a `score` (own-domain > freemail; IG-listed and
website beat guesses). `best_email` = highest score. You review before any use.

Compliance notes: only collect contact details people published for business. Cold
email is legal in many places but has rules (CAN-SPAM in the US: real sender identity,
physical address, working opt-out; GDPR/PECR in the UK/EU are stricter — legitimate
interest + easy opt-out, and B2B to sole traders can count as personal data). Honour
opt-outs by adding them to `do_not_contact.txt`. Scraping Instagram is against its
terms of use; using Apify keeps your own account out of it, but don't log in with your
account anywhere in this pipeline.

---

## 6. 100-profile test

Run `python run.py plan-test` for the exact commands. Summary:

| Step | Command | Max cost |
|---|---|---|
| Discover 5 keywords × 20 | `discover --max-keywords 5 --per-keyword 20 --max-profiles 100 --approve-spend` | $0.27 |
| Pre-filter | `prefilter` | $0 |
| Qualify ~40 | `qualify` (manual) / `qualify --mode api --approve-spend` | $0 / ~$1.00 (Opus) / ~$0.05 (Haiku) |
| Contacts | `contacts` (+ `--hunter` up to ~15 credits) | $0 |
| Export | `export --include-no-email` | $0 |

**Total: under $1.50**, under $0.30 in manual mode. Caps stop anything more.

What to measure (fill in after the run):

* pre-filter pass rate = `prefilter_pass / discovered`
* Claude qualify rate = `qualified / prefilter_pass`
* email hit rate = `qualified with best_email / qualified`, broken down by source
* **cost per qualified lead with email** = total spend / that count
* accuracy: you label 20–30 profiles yourself; compare with Claude's verdicts
  (and Opus vs Haiku if you test API mode). Tighten `hard_filters.toml` where the
  pre-filter let obvious junk through; check which keywords produced the most qualified leads.

Go/no-go: if cost per qualified-with-email lead < ~$0.25 and you agree with ≥ 80% of
verdicts, scale to the daily run below.

---

## 7. Costs and recommended limits

Assumed funnel (replace with test results): 35% pass pre-filter, 40% of those qualify,
55% of qualified have a findable email → **~7.7% of discovered profiles** become a
usable lead. 20/day ⇒ ~260 profiles/day discovered (less once snowball kicks in).

| Item | Per day | Per month (30d) |
|---|---|---|
| Apify discovery, 260 × $0.0027 | $0.70 | ~$21 |
| Apify snowball, 50 × $0.0026 | $0.13 | ~$4 |
| Apify contact fallback (optional, ~15 leads) | $0.10 | ~$3 |
| Claude, ~90 profiles — manual mode | $0 | $0 (your chat plan) |
| Claude API — Opus 5.5 (~$0.025/profile est.) | ~$2.25 | ~$68 |
| Claude API — Haiku 5.5 (~$0.0007/profile est.) | ~$0.06 | ~$2 |
| Hunter free plan | 50 credits/mo | $0 |
| **Total, manual Claude** | **~$0.95** | **~$28** |
| **Total, API Opus / API Haiku** | ~$3.20 / ~$1.00 | ~$96 / ~$30 |

Platform plans: Apify's free plan includes $5/month of usage — enough for the test and a
few days, not a month. Apify Starter is about $29/month and includes $29 of usage, which
covers the daily run. Hunter free = 50 credits/month; Starter ≈ $49/month for 2,000
(only worth it if the test shows website crawling misses lots of emails). Third-party
price reports vary, so check apify.com/pricing and hunter.io/pricing before upgrading.

Recommended caps (already set in `config/settings.toml`):

| | Per run | Per day | Per month |
|---|---|---|---|
| Apify | $2.00 | $1.50 | $35 |
| Claude API | $3.00 | $3.00 | $75 (lower to $15 if you pick Haiku) |
| Hunter | – | – | 45 credits (stay inside the free 50) |

Also set a hard usage limit inside the Apify console and a monthly spend limit in the
Anthropic Console as a second safety net. During the test, lower `apify_per_run_usd` to $0.50.

---

## 8. Hand-off record (for your mockup workflow)

`export` writes one JSON per lead to `data/handoff/mockup_queue/<username>.json`
(`handoff_version: 1`): username, profile_url, name, category, followers, engagement,
website, best_email + source, tier, score, reasons, `content_observations`,
`mockup_angle`, last 6 posts (URL, caption, stats, thumbnail), profile pic, bio.
To connect your workflow, implement a class with `submit(record)` in
`integrations/mockup.py` and pass it to `export.run()`. Fields will only ever be added,
not renamed, without bumping `handoff_version`.

## 9. Later

* Schedule the daily run (cron / GitHub Actions) once the test numbers look good.
* Message Batches API for API-mode qualification (50% cheaper, not real-time).
* Add a reels-search discovery source and A/B it against keyword user search.
* Track reply/booking outcomes in `outreach_status` and feed them back into the ICP.
