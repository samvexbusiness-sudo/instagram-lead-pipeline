# Kallaway: AI/Claude content system, extracted for Sam

Sources (all read in full): gEdt3AGLWjI "7 Proven Ways To Automate Social Media Content with AI (Claude)", vwlK6MbdAto "How to Use Claude To Grow From 0 to 100K Followers (Full Course)", Cnk9NQ8JpCs "5 Claude Skills To Grow Faster Than 99%", B9l9TRhu5Vw "Copy This System, It'll Blow Up Your Social Media".
Transcripts are auto-captions, so quotes keep their wording but punctuation is approximate. Kallaway never shows the skill files themselves, only what they do and what they output (the files are "linked below"). Only B9l9 gives full prompts.

Key dependency: almost every skill runs on the Sandcastles.ai MCP (his own product). It provides per-video performance data, outlier scores, transcripts, "deep analysis" tags (topic, hook, format, story structure), watchlists and CSV export. His words: without the data "Claude is just guessing... that's where you get AI slop" (vwlK). Sam has no Sandcastles. His data sources are vidIQ (IG/TikTok outlier search, ig_profile_reels, transcripts), Apify, the browser and the YouTube Shorts fallback. Every gap below has to run on those.

---

## 1. Skills and workflows, one by one

### 0. Setup (Cnk9)
- Claude desktop app, Cowork mode (not browser chat). Any folder can be the work folder.
- Folder: `<name>-co/` with `context/` and `work/`. Each workstream inside `work/` (YouTube, short form, SFA...) gets the same five subfolders: archive, assets, references, skills, videos.
- `context/` holds 4 files: `how-i-talk.md` (voice fingerprint plus how Claude should talk to you; his asks for metaphors), `how-you-work.md` (org flows, hours, people, who owns what), `who-i-am.md` (projects, goals, status against goals, struggles, personal life if you want), `claude.md` (tells Cowork to read the other three first).
- An interview skill builds all 4 files from your answers in 10 to 15 minutes. You drag them into `context/`.
- Optional: voice-to-text (Whisper Flow) because "talking is four times faster than typing". Also the Sandcastles MCP.
- In vwlK he runs everything on "Fable 5" ("the most expensive but the best model... You can probably run with Opus 5 as well").

### Niche Interviewer (gEdt "skill zero", vwlK skill 1)
- Does: about a 5-minute interview of 6 questions. Outputs a positioning doc and a "positioning blueprint card". This is the foundation every other skill reads.
- The 6 questions (vwlK, demoed as "Dr. Callaway, plastic surgeon"):
  1. Business context: "what do you actually sell? Who pays you? What procedures make up most of your revenue?"
  2. "The chair test": put one core viewer in a chair. Demographics, psychographics, beliefs.
  3. Their dream outcome.
  4. Their pain points.
  5. Target authority statement: one sentence on how you want to come across. His example: "I do facial plastic surgery explained honestly for women who've spent years on injectables and are quietly wondering if it's time for something real."
  6. Your unfair advantage.
- Outputs: ideal avatar, target authority statement, avatar pains, dream outcome, potential competitive differentiation, and a first guess at positioning across the 7 attributes (before any competitor data).
- His rule on inputs: go deep and spend 5 to 10 minutes per answer. "The more you give, the better the targeting will be." He used Claude to draft very detailed answers.

### Unique Positioning Builder / Positioning Wheel (vwlK skill 2)
- Inputs: niche interviewer doc plus Sandcastles.
- Steps: (1) builds a competitor watchlist automatically: "these eight accounts are the closest", plus tier B accounts that are adjacent but off-avatar, and it creates the watchlist inside Sandcastles. (2) Deep-analyzes a few top videos per account. (3) Plots each competitor on a "positioning wheel" across 7 attributes and marks what is crowded and where the white space is.
- The 7 differentiation attributes: topic selection; substance depth; unique stories or proof; avatar specificity; delivery style (voice, rhythm, tone); storytelling formats; visual format. You combine several of them to carve a lane.
- Manual list-building tips: search by description, filter by platform and size (micro/small/medium), use "find similar" to one perfect account, paste outside URLs, and mine "who a good competitor follows".

### Audience Bullseye Builder (gEdt #2 "new and improved", vwlK skill 3, Cnk9 #2)
- Question it answers: "how broad or narrow should I make my content if I'm trying to optimize for views, for conversions, or both?"
- Steps: framing questions about the avatar (or feed it the niche interviewer doc). Builds 5 concentric rings, center = exact buyer, each ring broader. You confirm the rings.
  - His rings: business owners using social to grow their business, then creators/entrepreneurs building a personal brand, then anyone growing on social, then anyone making video, then marketing/psychology concepts for anyone.
  - Dr. Callaway: affluent LA woman 48 to 58 researching a facelift, then filler-fatigued women 45 to 65, then any woman considering facial surgery, then women 35+ curious about their aging face, then all beauty/skincare.
  - Cnk9 example: high-ticket B2B tech sales, then B2B tech sales, then B2B sales, then sales, then business.
- Improved version (gEdt): deep-analyzes ALL your videos and plots each one on a ring. Scores views, conversions and conversion rate per video and per ring, with a second bullseye per topic bucket. The report then says which ring wins and how to apply it: "use these words, say these phrases, make sure this filter applies". Run it on a competitor if you are new. Run it on yourself once you have 25+ videos (he used about 130).
- His finding: the expected tradeoff (narrow = fewer views but more conversions) did NOT hold. For him and the others he ran it on, "one of these five rings drives both lots of views and lots of conversions". He did not say which ring.
- Needs per-video conversion data. Without it, "this doesn't work".
- Mix rules (they conflict, see section 4):
  - Cnk9 "322": of 7 videos, 3 in the bullseye, 2 between levels 2 and 3, 2 at level 4. None at the broadest level. In this video level 1 = broadest ("business").
  - vwlK "321": 3 topic buckets, two videos each, plus 1 "chaos agent" per 7. One broad bucket at ring 4, for reach and followers that still build trust in the right direction. Two narrow buckets at rings 2 to 3. Chaos agent anywhere from ring 1 to ring 4, never ring 5: "if you... go viral on accident, you could mess up the page... the algorithm will get confused".
  - vwlK version also proposes topic buckets per ring (narrow, broad, chaos ideas), shows a 7-day plan, lets you swap buckets, and projects a rebalance after 2 to 3 batches.

### Topic Scanner (vwlK skill 4) = B9l9 step 1 (topic prompt)
- Does: takes the top videos across the competitor watchlist, screens out off-topic ones (lifestyle vlogs, other procedures) before spending credits, deep-analyzes the rest and ranks them against your buckets and avatar.
- Demo numbers: 400 watchlist videos from the last 180 days, then top 130, then 73 qualified and 57 excluded, then top 50 deep-analyzed. Takes 20 to 30 minutes.
- Outputs: topic performance graph, format performance, placement of each topic on the bullseye, and the "Top 50 doc": each video's topic bucket, original link and analysis link, sorted by views and outlier score, with your green-lit buckets starred.
- How he uses it: go down the list and ask of each one: is it relevant to my buyer, do I have something different or better to say, do I have an edge? Skip freely. He needs 7 per week and reruns it weekly. Pick from anywhere on the list, not only the top.
- The manual version in B9l9: build a watchlist of 20 to 30 channels in the 10K to 1M follower range ("You don't want to go any bigger"). Filter videos to the last 3 or 6 months, sort by outlier score, minimum engagement 2%. Bulk deep-analyze about 100, export to CSV, upload to Claude with this prompt (verbatim):
  > "I'm uploading a report of the top 100 videos in my niche over the last X months. These were posted by the top creators in my niche. For background, I make content in X niche with the goal of helping build an audience of Y avatar. Specifically, my target authority statement is I help X people with Y thing to accomplish Z goal. First, I want you to go through the list and screen out any videos that aren't on the topic that I'd be covering. So, if there's any random trend or personal story from the creator that isn't on topic, get rid of those. With the videos you have left, run two analyses for me. First, I want you to list all the videos in order by outlier score. I want you to give me the topic, the link to the original video, and a one to two line sentence pitching me on why you think this would be a good video to make given my target authority statement. The topic should not be at the category level. They should be a three to five word framing that summarizes what the video is about specifically. Some of these may overlap, but I'd expect dozens and dozens of unique topics. Second, I want you to run another analysis clustering the videos by topic category. There's no specific set number of topic buckets I'm going for, but I want clear delineation and break points between. I'd expect somewhere between 8 to 15 different categories. I want you to rank these buckets in order based on highest average outlier score from the videos within them. Within each bucket, I also want you to list the individual videos... the topic... the link to the original and then again the one to two line sentence explaining why this would be a good video for me to make."
  - Run time about 4 to 5 minutes. For news-driven niches, cut the post date to 2 to 7 days. Most niches are evergreen, and a video from 4 months ago remixed still works.
  - Sandcastles automation: auto-analyze any watchlist video above a 5x outlier with 2%+ engagement, so the next batch is ready.

### Format Finder (gEdt #1, vwlK skill 5) = B9l9 step 2 (format prompt)
- Does: qualifies the avatar, finds competitor channels with the same audience, screens unrelated videos, deep-analyzes the top 5 to 10 per channel. Plots each video on a heat-map matrix: rows = story structure (case study, Q&A, problem/solution, listicle...), columns = visual layout (talking head, podcast clip, split screen, mirror drawing...). Click a cell to see its videos. Empty cells are white space. Example: "mirror drawing" was open, and it fits the doctor's stated skill.
- Format = how the information is structured + how it is shown. About 20 formats dominate. Most creators settle on 2 to 3 hero formats. Pick 2 to 3 per round of 7 while experimenting. Use Sandcastles Collections for 5 to 10 examples per format.
- B9l9 prompt (verbatim): "Give me a breakout of all the videos by storytelling format. rank them based on the highest outlier score and then list within each bucket all of the individual links and the names of those formats." Then open the top links in a bucket, find a "flavor" you can copy and use it as the model.
- Restrictive formats (S-tier list, A vs B, clone, rating/ranking) put rails on the contrarian take and help when you struggle to find one. Loose formats (breakdown, case study, scenario) suit freestyling.

### Content Formula Miner (gEdt #5)
- Content formula = topic + format + visual layout. Goal: 5 to 10 formulas that work and that you like making. Typical mix: 3 to 4 topic buckets x 2 to 3 formats x 1 to 3 visual layouts. His: 4 topics x 4 formats x 1 layout (split-screen cinematic) = 16.
- Does: buckets your videos into formulas ranked by performance, overall and per topic bucket. Shows a heat map of untried swaps. Runs the same analysis on top competitors to find formulas you are not using.
- Cadence: a recurring Claude task once a week on the newly posted videos, flagging changes in the ranking.
- Principle: "test and double down or test and kill".

### CTA Analysis (gEdt #3)
- Input: only the spoken CTAs at the end of your scripts, plus conversions per video.
- Does: statistical testing of terms, phrases, length and how the lead magnet is teased, against conversions.
- His result: 4 attributes used together took him from 8.3 to 31.3 leads per 1,000 views ("4x"). Dozens of other tweaks over about 100 videos had no significance. He does NOT reveal the 4 attributes.
- Can also run on a competitor channel that is strong on lead gen.

### Hook Genius Report (gEdt #4, Sandcastles feature, then Claude)
- In Sandcastles: Reports, Hook Genius, pick one channel, choose the most recent 50 or the biggest outliers (one-shot or recurring). Output: 3 to 5 hook strategies that work, with examples and links, plus "not to do" (what the losers shared).
- The "continue with MCP" code button gives a prompt to paste into Claude. He then had Claude build a hook dashboard plus a "mini SaaS app": enter a topic, get 10 hooks built on the report's principles.

### Hook Machine (Cnk9 #5) and the hook Mad Lib prompt (B9l9 step 4)
- Hook Machine steps: (1) take one channel (yours if you have winners, else one competitor), already deep-analyzed. (2) Extract the written hooks. (3) Cluster them, find the principles shared across winners. (4) Merge those with his hard-coded storytelling pillars into one rubric of "15 or 20 rules". (5) New topic in, hooks generated and graded on the rubric. (6) Feed it YOUR hook and it grades it and gives higher-graded alternatives. He calls it his most advanced skill and built it so hooks use data but don't read as slop.
- B9l9 hook prompt (verbatim): "I want you to run an analysis on all the hooks that we've pulled from the top 100 videos. First, I want you to bucket the videos by storytelling format. Rank the performance of the videos within each format based on outlier score. Extract out the hooks that were used for each one and extract out the hook Mad Lib format that's plug-and-play. I want you to list out the original topic, the video URL, the hook that was used, and the Mad Lib hook format. So that when I give you a new topic and I tell you what storytelling format I'm using, I want you to pull all the hooks from within that bucket and generate all new hooks using those Mad Lib hook formats. No matter what topic I give you, depending on how many hooks this nets me, maybe I'll ask you to run this hook conversion process again for another storytelling format that is adjacent. I want you to build this into a hook writing skill and let me know when you're ready for my first topic."
  - Why match by format: "Sometimes hooks don't transport well across formats."
  - Order: spoken hook first (from data), then open the source videos and study the visual and text hook BY EYE, then copy the visual execution of the one that hooked you.
- vwlK "spoken hooks engine": ranks hooks by type and psychology and builds a power-word/phrase cloud ("hypnotizes the scroll", "physically cannot scroll away", "the opposite of slop"). Also a text-hook engine (formats + frames) and a script-template engine, all set to update as new videos come in.

### Research / Brain-dump flow (vwlK video workflow) = B9l9 step 3 (substance)
- New chat with 3 skills (research, hooks/scripts, finished script). Pick a topic from the Top 50 and brain dump by voice: "What do you know that most people don't know? What do you believe to be true that most people don't believe to be true?"
- Optional research: it searches YOUR deep-analyzed winners, the Top 50, everything you ever analyzed, and the global Sandcastles database for videos on the same topic. "It's not just a random... Claude browser research." Output = a "substance sheet" (your core claims first, then the research merged in).
- Final output: 3 text hook options (rendered on a phone mock), 3 spoken hooks, 2 scripts (one from your context only, one with the research).
- B9l9 substance method: substance = a contrarian or non-obvious take + evidence (facts, metaphors, stories, case studies, examples, opinions, proof, A vs B). The topic must be at topic level, not category level. You find the take yourself. AI helps with evidence. Prompt (verbatim): "Hey, I'm making a video about this topic. My contrarian take is this. Can you help me think through what the evidence or research would need to be for this claim to make sense?"

### Script Writing Profile (B9l9 step 5)
- Pick ONE creator (yourself if you have winners). Take their last 6 months sorted by outlier score with 2%+ engagement. Deep-analyze 10 to 20 top videos in the same style/format and skip odd ones (for example an "about me" story). Export CSV, new chat. Prompt (verbatim):
  > "I'm looking to build a short form scripting profile based on the transcripts that I've just uploaded. First, I want you to take all the transcripts and fix if there are any small typos or weird things. Rewrite and fix them so they're clean. Then, I want you to take all those clean transcripts, feed them in, and build a short form script writing profile model based on these. I want to be able to feed you a topic, a format, a contrarian take, and a hook. And I want you to be able to write a script in the tone, rhythm, and style of the script model you've just made. I want you to save this as a script writing skill. So, anytime I make a new video, I can open this and let it rip."
- Do not combine several creators: "speaking patterns are like fingerprints... it'll confuse the writer and make it generic."

### Channel Analysis (Cnk9 #1)
- Run on your own channel several times a week, and on competitors. Deep-analyze ALL videos in a 30 to 60 day window (so it sees winners AND losers), or only the top 10 to 15 by outlier score in about 3 months. He bulk-analyzes in the Sandcastles web app first because it is faster than doing it through the MCP.
- Output: a dynamic HTML report with the best topics, hooks, formats and "non-obvious patterns", thumbnails linking back to each video. Then you can query it further, or set a recurring task to refresh it every 2 weeks and ping you.
- His claim: from month 1 to month 2 on the new channel he "just run this analysis and do what it said" and growth picked up.

### Outlier Pulse (Cnk9 #3)
- Scheduled every morning at 7 a.m. An ordered list of competitor posts from the watchlist: above 25,000 views and 1x outlier, last 7 days, with outlier score and raw link. Variant "all recent" pulls every video. Uses surface metrics only, so no analysis credits.
- Delivery: in Claude, a Slack channel, a Notion page, or a "mini live leaderboard" web page Claude updates. Options: run 6 to 12x a day, or real-time alerts when a post crosses a threshold. Purpose: no doom scrolling.

### Creator Breakout Detector (Cnk9 #4) and Content Strategy Coach / eras (gEdt #6)
- Breakout detector: maps a channel chronologically (default lookback 730 days, cut it to 45 to 100 to go faster), finds the spike video(s), pulls them, then you deep-analyze around them. Uses surface metrics, so no credits are needed.
- Strategy coach: splits the channel's history into "eras" and explains for each what the topics, formats and scripting were, "what changed and what held true". His own channel: era 1 testing (first 15 to 20 videos), era 2 "two lanes found", era 3 "consolidation". Use it when a channel took off "out of nowhere", yours or a competitor's.

### Contrarian Take Vault, Brand Association, Uniqueness Mapper, Formula Lab, Positioning Canvas (gEdt #7: an 8-skill pack, 45 to 60 minutes)
- Order: (1) niche interviewer (analyzes your last 30 videos if you have a channel), (2) competitor scout (finds and screens competitors, "fingerprints" their best videos), (3) niche bullseye (simplified, plots competitors on the rings too), (4) **contrarian take vault**: mines the top competitor videos for what they all say and pitches each claim to you, so you can say if you have a contrarian take. "You don't have to force it and lie, but often times we find business owners have three to five like hero principles that are different from their niche." Saved to a vault. (5) **brand association**: "Google AdWords for the brain", the words or phrases you want to own, mapped to the strategy. (6) **uniqueness mapper**: competitors plotted on 5 attributes (topic, substance, avatar, format, visual layout) with white-space options. (7) **formula lab**: topic + format + layout, yours vs theirs vs white space. (8) one-page **positioning canvas**.
- His advice: run the standalone skills first, because they go deeper. The canvas uses simpler versions.

### Content Coach / weekly learning loop (vwlK)
- The Sandcastles dashboard "content strategy audit" (Reports tab, any channel, configurable to the last 30 or 50 videos, every 7 or 30 days) breaks down which topics, hooks, formats and script tactics work. "Continue with MCP" pulls it into Claude as the "channel coach" skill, so you can ask things like "should I do this bucket next week?" and get do more / do less for the next 7.
- Example: storytelling was dropping and personal-brand growth was rising, so he shifted.

---

## 2. End-to-end pipeline

Cadence (vwlK): strategy every 30 days, topic workflow every video, content coach every 7 days.

1. **Setup**: context files, folder structure, Sandcastles MCP, voice-to-text.
2. **Strategy and positioning (monthly)**: niche interviewer, positioning wheel (7 attributes), bullseye plus the 3-2-1 mix, topic scanner (Top 50 doc), format finder matrix. Optional extras: content formulas, CTA analysis, breakout/eras, positioning canvas with the contrarian vault.
3. **Research (continuous)**: watchlist of 20 to 30 channels (10K to 1M followers); daily outlier pulse; auto-analysis of 5x+ outliers; CSV of the top 100.
4. **Idea** = topic + format + substance (B9l9). Topic: fully data-driven ("I lean completely on data and AI"). Format: mostly data, picked by eye from the top bucket. Substance: a human contrarian take, with AI brainstorming evidence. He only moves on once topic and format are locked.
5. **Hook**: spoken hook from the format-matched Mad Lib bank or the Hook Machine rubric; text and visual hook copied by eye from the source videos in that format. Hook = visual + text + spoken.
6. **Script**: the voice-profile skill on topic + format + take + hook, then a human last mile. In vwlK he says he writes his own: reads top transcripts of his own outliers with "show sections", scans his own hooks sorted by outlier score for power phrases, adapts them, deletes what is "too corny", and copies the rhythm and sentence flow, never the words.
7. **Record and edit**: no Claude skills. Copy a model video's angles, distance, lighting, positions, text placement, cadence, timing, pacing, sequencing. Outsource editing ("you should not be editing... too low leverage"). Four editing paths: a low-edit format, brute force yourself, Claude Code + Remotion (about "2 out of 10, three out of 10"), hire an editor.
8. **Post**: batches. B9l9 "10x batch": one topic/format research pull feeds 10 videos (substance to edit, 10 times), posted daily for 10 days.
9. **Analyze**: three metrics in order: conversions per video/view (for example via ManyChat), then followers per video/view, then views relative to the batch. Rules per batch of 10: nothing at 5x+ average = start the research over (usually something obvious is wrong); a 5 to 10x winner = tweak the topic/format (new take or format) for 3 of the next 10; 10x+ = the same topic AND format again for 3 of the next 10 ("liquid gold"), never all 10. Goal: about 3 winning combinations that fill each batch. Plus the weekly content coach and the recurring formula, channel and bullseye reruns.

Kallaway's own results claimed: Kallaway Marketing on IG went 0 to 75,000 followers in about 4 months, 30,000 email subs, "over a 100,000 in attributable revenue" (vwlK). He posts 50+ unique shorts a month on IG (B9l9).

---

## 3. Gap list for Sam, ranked by value for a coach-focused editor

What Sam already covers (no need to rebuild): the brick model and 11-point audit; outlier mining every 2 weeks; the client winner pattern sheet plus niche outliers plus Results Gate (sam-freelance-script 2i: last 10 to 15 reels, top 3 vs bottom 3, constants/variables/gap); the TAS filter; the batch-of-10 review with triple-down; the funnel audit and keyword CTA rules; hook doctrine; voice files for his own channel; a recurring Loom pack. Kallaway's context files ≈ Sam's skills + CLAUDE.md.

What Sam lacks is Kallaway's layer that sits around a client account: a per-client positioning doc, conversion-scored ring analysis, a ranked topic feed, data-built hook rubrics per client, and a scheduled coach report. Ranked:

1. **Client Niche Interviewer → `claude/CLIENT-<name>.md`.** Every other client skill, including Results Gate, needs a fixed avatar/TAS/pain doc in the coach's own words. Build: run the 6 questions (business, chair test, dream outcome, pains, TAS, unfair advantage) from a call transcript or intake form, add the 7-attribute first pass, save one file per client, and have sam-freelance-script and sam-content-brain read it first.
2. **Coach Bullseye + mix plan.** This answers the coach's biggest question ("broad or narrow?") and protects on-target virality, which sam-content-brain already treats as the main goal. Build: draft 5 rings from the client doc, let Sam confirm them, plot the client's last 25+ reels (vidIQ ig_profile_reels views) on rings and topic buckets, mark views per ring, add the conversion per ring if the client shares ManyChat or lead counts, and output a 7-video 3-2-1 plan (flag the 321 vs 322 conflict).
3. **Content Coach report every batch (scheduled).** Sam has the batch-of-10 rule but no automatic report. A recurring report keeps clients on retainer, because the editor delivers strategy, not only cuts. Build: a scheduled task per client that pulls new reels, ranks topic/format/hook formulas, applies the 5x / 10x carry-forward (3 of next 10), names ONE brick to test, and writes a one-page report.
4. **Topic Scanner (Top 50 doc).** This turns Sam's manual 2-weekly mining into a list a coach can pick from. Build: wrap Kallaway's top-100 prompt on vidIQ outlier search + transcripts for the client's watchlist. Screen off-topic, give a 3 to 5 word topic + link + a 1 to 2 line pitch tied to the client's TAS, cluster into 8 to 15 buckets ranked by average outlier, star the client's buckets.
5. **Contrarian Take Vault per client.** Coaches fail on substance, and Kallaway says AI can't produce the take. So mine the consensus claims and let the coach react. Build: extract the claims competitors repeat from their transcripts, turn each into a question for the coach ("do you disagree?"), store the answers in `claude/VAULT-<name>.md`, and feed them into hooks. This also works as a no-ask value touch in follow-ups.
6. **Client Hook Machine (rubric + grader + format-matched Mad Libs).** Sam's hook rules are general. This one is per client, from data. Build: extract the hooks of the client's winners + the niche outliers, bucket them by format, write Mad Lib templates, build a 15 to 20 rule rubric merged with sam-content-brain section 3, then generate and grade, or grade Sam's draft text hook/title and return better-scoring alternatives. Plugs into Results Gate (b)/(c).
7. **CTA Analyzer.** Kallaway's biggest measured lift (8.3 to 31.3 leads per 1,000 views) and it fits Sam's funnel focus. Build: transcribe the end CTA of each client reel, tag attributes (length, what is teased, keyword, who it is for), compare against leads per 1,000 views from the client's ManyChat. If there is no data, a possible proxy is keyword-comment count per 1,000 views from public comments. Kallaway never mentions this proxy and it is untested.
8. **Outlier Pulse (scheduled).** Cheap daily or weekly feed per client niche, so no scrolling, and it feeds the scanner and the Loom pack. Build: a scheduled task over each client watchlist that lists posts above a views floor and 1x outlier in the last 7 days, sorted, with links, written to a Notion page or an artifact leaderboard. Check vidIQ credit cost per run first, because Kallaway's version is free only because it uses surface metrics.
9. **Client Script Voice Profile.** Useful for coaches who script (not clip). One creator only. Build: 10 to 20 top transcripts of the coach in one format, clean them, build a voice profile, save it as `claude/VOICE-<name>.md`, and use it when writing hooks/CTAs the coach will say.
10. **Format Finder / Formula matrix.** It makes "constants vs gap" visual and shows white space. Build: from the scanner data, a story-structure x visual-layout heat map (and topic x format x layout ranking for the client's own reels), with links in each cell.
11. **Breakout / Eras detector.** Good Loom material for prospects ("here is when your account changed and why"). Build: pull a prospect's reel history, find spike videos vs median, split into eras, write what changed, give one line for the Loom.
12. **Positioning Canvas pack.** Later, as a paid strategy upsell. It chains 1, the competitor scout, 2, 5, brand association, the uniqueness mapper (5 attributes), 10, and a one-page canvas.

---

## 4. What Kallaway says AI is bad at / should not be used for

- **One-shot script writing**: "oneshotting writing with Claude is the final frontier. I do not believe Claude is able to write as good as a human today." Expect 80 to 90%, tweak by hand, feed the tweaked version back "20 or 30 times". "On day one, this will not be able to oneshot scripts that are better than what you could write." (vwlK) He does not use his own last-mile script skill. He writes hooks and scripts by hand. "Nobody's using AI to oneshot these scripts."
  - Conflict: in B9l9 he says a voice-profile skill fed topic + format + take + hook gets "90 to 95% of the way there" and you tweak about 5%. The difference is the inputs: it works when the human supplies the take, evidence and hook.
- **Contrarian takes / novel ideas**: "AI is good at regurgitating what it's been trained on... not great at coming up with novel things outside the box." Use it for evidence after you have the take (B9l9). Vault rule: don't "force it and lie" (gEdt).
- **AI without data = slop**: without real performance data "Claude is just guessing... it just generates absolute trash" (vwlK).
- **Visual and text hook study**: he does it by eye. "I can do this faster with my eyes than I could from a visual AI telling me like, oh, put the block up there." (B9l9)
- **Recording and editing**: "There are no clawed skills or claude workflows for recording and editing. You don't really need them." Auto-edit templates "are all pretty trash" (vwlK). Claude Code + Remotion is "2 out of 10, three out of 10" in complexity: "I wouldn't put all the eggs in this basket" (B9l9). He has "not used extensively" the Remotion, Higgsfield and Beehiiv MCPs (Cnk9).
- **Voice cloning across creators**: combining several creators "will confuse the writer and make it generic".
- **Pattern spotting**: AI extends human pattern-matching across hundreds of videos, it does not replace your judgment. You still pick topics by asking "do I have something different to say?"
- **Data hygiene limits**: no conversion data, no bullseye or CTA analysis. Mega accounts (>1M) are excluded from watchlists. The chaos agent never goes to the broadest ring.
- **Note**: the "skill files" are behind his links, and several outputs depend on his hard-coded storytelling pillars (Hook Machine), which he does not show. Don't claim to reproduce them exactly.

## 5. Conflicts to flag to Sam
- Mix: 322 (Cnk9) vs 321 + chaos agent (vwlK). Ring numbering is reversed between the two videos (Cnk9 level 1 = broadest; vwlK ring 1 = center).
- Outlier band: Kallaway watchlists are 10K to 1M followers. Sam's ruling is 10K to 250K.
- Triple-down: Kallaway = 3 of the next 10 (5 to 10x tweak, 10x+ exact rerun). Sam = 3 to 5 more of a 10x.
- Script AI ceiling: 80 to 90% (vwlK) vs 90 to 95% (B9l9).
