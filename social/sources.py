"""Where post ideas come from: OverlapIQ blog, OverlapIQ fund data, and trending topics.

Each source returns a "brief" dict that the writer turns into a carousel:
    {source_type, source_ref, title, url, material, data(optional), facts_locked(bool)}
`source_ref` is used to avoid posting about the same thing twice.
"""
import itertools
import json
import random
import re
from collections import defaultdict
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

import requests

from . import config as C, db, llm

UA = {"User-Agent": "OverlapIQ-SocialAgent/1.0 (+https://overlapiq.in)"}


def used_refs(source_type, limit=500):
    rows = db.select(C.POSTS_TABLE, {"source_type": f"eq.{source_type}", "select": "source_ref",
                                     "order": "created_at.desc"}, limit=limit)
    return {r["source_ref"] for r in rows if r.get("source_ref")}


# =============================================================== BLOG =====
class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg", "form", "button"}

    def __init__(self):
        super().__init__()
        self.depth_skip = 0
        self.parts = []
        self.title = ""
        self.meta_desc = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.depth_skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta" and a.get("name", "").lower() == "description":
            self.meta_desc = a.get("content", "")
        if tag in ("h1", "h2", "h3", "li", "p", "tr", "br"):
            self.parts.append("\n")
            if tag in ("h1", "h2", "h3"):
                self.parts.append("## ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth_skip:
            self.depth_skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.depth_skip:
            self.parts.append(data)

    def text(self):
        t = "".join(self.parts)
        t = re.sub(r"[ \t]+", " ", t)
        return re.sub(r"\n\s*\n+", "\n", t).strip()


def blog_urls():
    r = requests.get(f"{C.SITE_URL}/sitemap.xml", headers=UA, timeout=30)
    r.raise_for_status()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.fromstring(r.content)
    items = []
    for u in root.findall("s:url", ns):
        loc = (u.findtext("s:loc", default="", namespaces=ns) or "").strip()
        lastmod = u.findtext("s:lastmod", default="", namespaces=ns) or ""
        if "/blog/" in loc:
            items.append((lastmod, loc))
    items.sort(reverse=True)  # newest first when lastmod exists
    return [loc for _, loc in items]


def fetch_page(url):
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    p = _TextExtractor()
    p.feed(r.text)
    return p.title.strip(), p.meta_desc.strip(), p.text()


def blog_brief(ref=None):
    """Newest blog post not yet turned into a post (or a specific URL via `ref`)."""
    if ref:
        url = ref
    else:
        done = used_refs("blog")
        fresh = [u for u in blog_urls() if u.rstrip("/").split("/")[-1] not in done]
        if not fresh:
            return None
        url = fresh[0]
    slug = url.rstrip("/").split("/")[-1]
    title, desc, text = fetch_page(url)
    return {
        "source_type": "blog", "source_ref": slug, "title": title or slug, "url": url,
        "material": f"BLOG POST: {title}\nURL: {url}\nSUMMARY: {desc}\n\nFULL TEXT:\n{text[:14000]}",
        "facts_locked": True,
    }


# =============================================================== DATA =====
EQUITY_HINTS = ("cap", "elss", "flexi", "index", "focused", "value", "contra", "multi", "dividend",
                "thematic", "sectoral", "aggressive")


def load_holdings():
    months = db.select("holdings", {"select": "as_of_month", "order": "as_of_month.desc"}, limit=1)
    if not months:
        return None, {}, {}
    month = months[0]["as_of_month"]
    rows = db.select_all("holdings", {"select": "family_id,stock_name,weight_pct,sector",
                                      "as_of_month": f"eq.{month}"})
    schemes = {s["family_id"]: s for s in db.select_all("schemes", {"select": "family_id,name,amc,category"})}
    by_fund = defaultdict(dict)
    for r in rows:
        if r.get("weight_pct") is not None:
            by_fund[r["family_id"]][r["stock_name"]] = float(r["weight_pct"])
    return month, by_fund, schemes


def overlap_pct(a, b):
    """Weight-based overlap: sum over common stocks of min(weight_a, weight_b)."""
    common = set(a) & set(b)
    return round(sum(min(a[s], b[s]) for s in common), 1), sorted(
        common, key=lambda s: -min(a[s], b[s]))


def _short(name):
    name = re.sub(r"\s*-\s*(Direct|Regular).*$", "", name or "", flags=re.I)
    return re.sub(r"\s+(Fund|Plan|Growth)\b", "", name).strip()


def insight_most_held(month, by_fund, schemes):
    count = defaultdict(int)
    for f in by_fund.values():
        for s in f:
            count[s] += 1
    n = len(by_fund)
    top = sorted(count.items(), key=lambda kv: -kv[1])[:8]
    return {
        "kind": "most_held", "ref": f"most_held:{month}",
        "headline": f"The {len(top)} stocks that show up in the most mutual funds",
        "chart": {"type": "bars", "unit": "% of funds",
                  "items": [{"label": s, "value": round(100 * c / n)} for s, c in top]},
        "facts": {"funds_analysed": n, "month": month,
                  "top": [{"stock": s, "funds_holding": c, "pct_of_funds": round(100 * c / n)} for s, c in top]},
    }


def insight_pair(month, by_fund, schemes, done):
    eq = [f for f in by_fund if any(h in (schemes.get(f, {}).get("category") or "").lower() for h in EQUITY_HINTS)
          and len(by_fund[f]) >= 10]
    best = []
    for a, b in itertools.combinations(eq, 2):
        sa, sb = schemes.get(a, {}), schemes.get(b, {})
        if sa.get("amc") == sb.get("amc"):
            continue
        ref = f"pair:{min(a, b)}-{max(a, b)}:{month}"
        if ref in done:
            continue
        pct, common = overlap_pct(by_fund[a], by_fund[b])
        # Most interesting: high overlap between funds sold as *different* categories
        bonus = 15 if sa.get("category") != sb.get("category") else 0
        best.append((pct + bonus, pct, a, b, common, ref))
    if not best:
        return None
    best.sort(reverse=True)
    _, pct, a, b, common, ref = random.choice(best[:5])
    sa, sb = schemes[a], schemes[b]
    return {
        "kind": "pair_overlap", "ref": ref,
        "headline": f"{_short(sa['name'])} vs {_short(sb['name'])}: {pct}% overlap",
        "chart": {"type": "bars", "unit": "% weight (lower of the two)",
                  "items": [{"label": s, "value": round(min(by_fund[a][s], by_fund[b][s]), 1)} for s in common[:6]]},
        "stat": {"value": f"{pct}%", "label": "portfolio overlap"},
        "facts": {"month": month, "overlap_pct": pct, "common_stocks": len(common),
                  "fund_a": {"name": sa["name"], "category": sa.get("category"), "amc": sa.get("amc"),
                             "holdings_count": len(by_fund[a])},
                  "fund_b": {"name": sb["name"], "category": sb.get("category"), "amc": sb.get("amc"),
                             "holdings_count": len(by_fund[b])},
                  "top_common": [{"stock": s, "weight_a": by_fund[a][s], "weight_b": by_fund[b][s]}
                                 for s in common[:6]]},
    }


def insight_category(month, by_fund, schemes, done):
    cats = defaultdict(list)
    for f in by_fund:
        c = schemes.get(f, {}).get("category")
        if c and len(by_fund[f]) >= 10:
            cats[c].append(f)
    options = [c for c, fs in cats.items() if len(fs) >= 6 and f"category:{c}:{month}" not in done]
    if not options:
        return None
    cat = random.choice(options)
    fs = cats[cat]
    pairs = [overlap_pct(by_fund[a], by_fund[b])[0] for a, b in itertools.combinations(fs, 2)]
    avg = round(sum(pairs) / len(pairs), 1)
    count = defaultdict(int)
    for f in fs:
        for s in by_fund[f]:
            count[s] += 1
    top = sorted(count.items(), key=lambda kv: -kv[1])[:6]
    return {
        "kind": "category", "ref": f"category:{cat}:{month}",
        "headline": f"Two random {cat} funds share {avg}% of their portfolio on average",
        "stat": {"value": f"{avg}%", "label": f"average overlap between two {cat} funds"},
        "chart": {"type": "bars", "unit": f"% of {cat} funds holding it",
                  "items": [{"label": s, "value": round(100 * c / len(fs))} for s, c in top]},
        "facts": {"month": month, "category": cat, "funds_in_category": len(fs), "avg_pair_overlap_pct": avg,
                  "max_pair_overlap_pct": max(pairs), "min_pair_overlap_pct": min(pairs),
                  "most_common": [{"stock": s, "funds_holding": c} for s, c in top]},
    }


def data_brief():
    month, by_fund, schemes = load_holdings()
    if not by_fund:
        return None
    done = used_refs("data")
    makers = [lambda: insight_pair(month, by_fund, schemes, done),
              lambda: insight_category(month, by_fund, schemes, done),
              lambda: None if f"most_held:{month}" in done else insight_most_held(month, by_fund, schemes)]
    random.shuffle(makers)
    for make in makers:
        ins = make()
        if ins:
            return {
                "source_type": "data", "source_ref": ins["ref"], "title": ins["headline"],
                "url": C.SITE_URL, "insight": ins,
                "material": "OVERLAPIQ DATA INSIGHT (numbers computed from fund factsheet holdings; "
                            "use ONLY these numbers):\n" + json.dumps(ins, indent=1),
                "facts_locked": True,
            }
    return None


# =========================================================== TRENDING =====
TREND_SYSTEM = """You scout Instagram post ideas for OverlapIQ (overlapiq.in), an Indian personal-finance
education brand. OverlapIQ helps Indian retail investors check mutual fund portfolio overlap and covers
international investing (US/global funds, GIFT City, LRS), SIFs, REITs/InvITs and ETFs.
Audience: Indian retail investors aged 22-40, beginner to intermediate.
Only propose topics that are EDUCATIONAL (explain a rule change, a concept, a number, a myth) and that tie back
to diversification, overlap, fund selection, international investing, costs or taxation.
Never propose stock tips, buy/sell calls, price predictions, or 'hot fund' picks."""


def trending_brief():
    recent = sorted(used_refs("trending", limit=60))
    user = f"""Search the web for what Indian retail investors are talking about in the last 7 days
(SEBI/AMFI circulars, new fund categories, tax changes, NFO waves, international investing news, viral myths).
Propose 3 post ideas. Avoid these already-covered topics: {recent or 'none'}.

Return ONLY JSON:
```json
{{"ideas":[{{"topic":"short topic key","angle":"the educational hook in one line","why_now":"what happened, with date",
"key_facts":["fact with number + date + source name", "..."],"sources":["url", "..."]}}]}}
```"""
    text, srcs = llm.call(TREND_SYSTEM, user, web_search=True, max_searches=6, max_tokens=3000)
    ideas = llm.extract_json(text).get("ideas", [])
    ideas = [i for i in ideas if i.get("topic") and i["topic"] not in recent]
    if not ideas:
        return None
    idea = ideas[0]
    return {
        "source_type": "trending", "source_ref": idea["topic"], "title": idea.get("angle", idea["topic"]),
        "url": (idea.get("sources") or [None])[0],
        "material": "TRENDING TOPIC (researched via web search):\n" + json.dumps(idea, indent=1),
        "sources": idea.get("sources") or [s["url"] for s in srcs[:5]],
        "facts_locked": True,
    }


BRIEF_MAKERS = {"blog": blog_brief, "data": data_brief, "trending": trending_brief}
