"""Editor-niche analysis: which reel formats get views for video-editor accounts.
Input: Apify instagram profile/search scraper dumps (JSON with "items"). Usage:
  python research/editor_niche.py dump1.txt dump2.txt ...
"""
import json, re, sys, statistics as st
from collections import defaultdict

FORMATS = [  # first match wins
    ("tutorial",   r"\bhow (to|i)\b|tutorial|here'?s how|step[- ]by[- ]step|prompt|workflow|in after ?effects|in premiere|plugin|preset|recreat"),
    ("tool_news",  r"\b(ai|chatgpt|claude|capcut|edits app|instagram edits|new feature|update|just got|just dropped|higgsfield|invideo|veo|kling)\b"),
    ("before_after", r"before|after|\braw\b|b/a|transform|\$\d+ ?(vs|edit)|vs\.? me"),
    ("showreel",   r"recent (work|edit|frames)|my (work|recent)|edits? i (made|did)|portfolio|showreel|reel ?(of|from) (my|the)|frames|sample \d|edit(ed)? for @"),
    ("story",      r"\bi (just|quit|won|started|hit|got|was|went|made \$)|followers|competition|journey|giveaway|day \d+|my first"),
]
CTA = [("project_file", r"project ?file|comment.{0,25}(file|project|preset|template|link|assets)"),
       ("comment_keyword", r"comment ['\"“]?\w+"),
       ("dm", r"\bdm\b|direct message|message me"),]

def classify(rx_list, text, default):
    for name, rx in rx_list:
        if re.search(rx, text, re.I):
            return name
    return default

def main(paths):
    seen, accounts = set(), []
    for p in paths:
        for it in json.load(open(p))["items"]:
            u = it.get("username")
            bio = (it.get("biography") or "") + " " + (it.get("fullName") or "")
            if not u or u in seen or not re.search(r"edit|motion|video|reels|content", bio, re.I):
                continue
            seen.add(u)
            posts = [x for x in it.get("latestPosts", []) if x.get("videoViewCount")]
            if len(posts) < 3 or (it.get("followersCount") or 0) > 100_000:
                continue
            accounts.append((u, it.get("followersCount") or 0, posts))
    rows = []
    for u, foll, posts in accounts:
        med = st.median(p["videoViewCount"] for p in posts)
        for p in posts:
            cap = p.get("caption") or ""
            mentions = p.get("mentions") or []
            rows.append(dict(user=u, foll=foll, views=p["videoViewCount"], lift=p["videoViewCount"] / max(med, 1),
                             fmt=classify(FORMATS, cap, "other"), cta=classify(CTA, cap, "none"),
                             tags_creator=bool(mentions or p.get("taggedUsers"))))
    print(f"{len(accounts)} editor accounts, {len(rows)} reels\n")

    def table(key, title, subset=rows):
        g = defaultdict(list)
        for r in subset: g[r[key]].append(r)
        print(f"== {title} ==\n{'group':16}{'reels':>6}{'accts':>6}{'med views':>11}{'med lift':>10}{'% >2x own median':>18}")
        for k, rs in sorted(g.items(), key=lambda kv: -st.median(r['lift'] for r in kv[1])):
            print(f"{str(k):16}{len(rs):>6}{len({r['user'] for r in rs}):>6}{int(st.median(r['views'] for r in rs)):>11}"
                  f"{st.median(r['lift'] for r in rs):>10.2f}{100*sum(r['lift']>2 for r in rs)/len(rs):>17.0f}%")
        print()
    table("fmt", "Format (all accounts; lift = views / that account's own median)")
    table("fmt", "Format, small accounts only (<2,000 followers)", [r for r in rows if r["foll"] < 2000])
    table("cta", "CTA type")
    table("tags_creator", "Tags/mentions the creator in the footage")
    band = lambda f: "<500" if f < 500 else "500-2k" if f < 2000 else "2k-10k" if f < 10000 else "10k-100k"
    for r in rows: r["band"] = band(r["foll"])
    table("band", "Follower band (absolute views)")

if __name__ == "__main__":
    main(sys.argv[1:])
