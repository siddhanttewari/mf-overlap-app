"""Turns a source brief into a carousel: slide copy + caption + hashtags, then a compliance review pass."""
import json

from . import config as C, llm

DISCLAIMER = ("For education only, not investment advice. Mutual fund investments are subject to market "
              "risks; read all scheme-related documents carefully.")

SLIDE_TYPES = """Slide types you can use (JSON objects):
- {"type":"cover","kicker":"2-4 word label","title":"hook, max 9 words","subtitle":"max 14 words"}
- {"type":"point","n":1,"heading":"max 8 words","body":"max 35 words"}
- {"type":"stat","value":"e.g. 62%","label":"max 8 words","context":"max 25 words"}
- {"type":"bars","title":"max 9 words","note":"max 18 words"}   <- ONLY for data posts; chart numbers are filled in by code
- {"type":"compare","title":"max 8 words","left_title":"max 3 words","left":["max 6 words x3-4"],"right_title":"max 3 words","right":["max 6 words x3-4"]}
- {"type":"tip","heading":"max 8 words","body":"max 35 words"}
- {"type":"cta","heading":"max 9 words","body":"max 22 words"}"""

SYSTEM = f"""You write Instagram carousels for OverlapIQ (overlapiq.in), a free tool that shows Indian investors how much
their mutual funds overlap, plus plain-English guides on international investing, SIFs, REITs, GIFT City and ETFs.

VOICE: a smart friend who explains money simply. Short sentences. Concrete numbers. No jargon without a 5-word
explanation. No hype, no emojis in slide text (max 2 in the caption), no exclamation marks on slides.
Write for Indian retail investors aged 22-40; use ₹, lakh/crore, Indian examples.

HARD RULES (Indian securities regulation; OverlapIQ is not a SEBI-registered adviser):
- Educational only. Never tell anyone to buy, sell, switch, hold or avoid a specific fund, stock or product.
- No return predictions, price targets, "best fund" claims, or guaranteed outcomes.
- Naming specific funds is allowed only to describe facts from the provided material (e.g. their overlap).
- Use ONLY numbers/facts present in the source material. Never invent statistics, dates or quotes.
- Do not use stock price movements from the last 3 months as content.

STRUCTURE: 5-8 slides. Slide 1 = "cover" (scroll-stopping hook). Last slide = "cta" pointing people to check
their own portfolio overlap free at overlapiq.in (or read the full guide there). Each slide makes ONE point.

{SLIDE_TYPES}

CAPTION: 80-180 words. First line is a hook (it shows before "more"). Then 2-4 short lines of value, then a CTA
("Link in bio" / "Check your overlap free at overlapiq.in"). Do NOT include the disclaimer or hashtags in the caption;
they are added separately. HASHTAGS: 6-10 relevant, mix of broad (#mutualfunds) and niche (#portfoliooverlap).
ALT_TEXT: one sentence describing the carousel for screen readers."""


def build_user_prompt(brief, feedback=None, previous=None):
    parts = [f"SOURCE TYPE: {brief['source_type']}", brief["material"]]
    if brief["source_type"] == "data":
        parts.append("This is a DATA post: include one 'stat' slide and one 'bars' slide; the code fills chart values. "
                     "Mention the data month and that it's based on disclosed fund holdings.")
    if brief["source_type"] == "blog":
        parts.append(f"Final slide/caption should point to the full guide: {brief['url']}")
    if previous:
        parts.append("PREVIOUS DRAFT:\n" + json.dumps(previous, ensure_ascii=False, indent=1))
    if feedback:
        parts.append("EDITOR FEEDBACK TO APPLY (highest priority):\n" + feedback)
    parts.append("""Return ONLY JSON:
```json
{"slides":[...],"caption":"...","hashtags":["#..."],"alt_text":"...","topic_summary":"one line for the review queue"}
```""")
    return "\n\n".join(parts)


def _clean(post, brief):
    slides = [s for s in post.get("slides", []) if isinstance(s, dict) and s.get("type")][:C.MAX_SLIDES]
    if not slides or slides[0]["type"] != "cover":
        raise llm.LLMError("First slide must be a cover")
    if slides[-1]["type"] != "cta":
        slides.append({"type": "cta", "heading": "How much do your funds overlap?",
                       "body": f"Check your portfolio free at {C.BRAND['site']}"})
    ins = brief.get("insight")
    for s in slides:
        if s["type"] == "bars":
            if not ins or "chart" not in ins:
                s["type"] = "tip"; s.setdefault("heading", s.get("title", "")); s.setdefault("body", s.get("note", ""))
            else:
                s["items"], s["unit"] = ins["chart"]["items"], ins["chart"]["unit"]
        if s["type"] == "stat" and ins and ins.get("stat"):
            s["value"] = ins["stat"]["value"]  # numbers always come from code, never the model
    tags = []
    for t in post.get("hashtags", []):
        t = "#" + str(t).lstrip("#").replace(" ", "")
        if t.lower() not in {x.lower() for x in tags}:
            tags.append(t)
    return {
        "slides": slides,
        "caption": post.get("caption", "").strip(),
        "hashtags": tags[:15],
        "alt_text": post.get("alt_text", "")[:1000],
        "topic_summary": post.get("topic_summary", brief["title"])[:300],
    }


REVIEW_SYSTEM = """You are a compliance and quality reviewer for an Indian finance-education Instagram account that is NOT
a SEBI-registered adviser. Review the draft against its source material. Flag only real problems:
1. ADVICE: any buy/sell/switch/hold/avoid recommendation, 'best fund' claim, return promise or prediction.
2. UNSUPPORTED: any number, date or fact not present in the source material.
3. RECENT_PRICE: content based on stock price moves from the last 3 months.
4. CLARITY: slide text that is confusing, too long, or jargon-heavy.
Return ONLY JSON: ```json {"flags":[{"severity":"high|medium|low","slide":0,"issue":"...","fix":"..."}]}``` (empty list if clean)."""


def review(post, brief):
    user = f"SOURCE MATERIAL:\n{brief['material'][:12000]}\n\nDRAFT:\n{json.dumps(post, ensure_ascii=False, indent=1)}"
    try:
        text, _ = llm.call(REVIEW_SYSTEM, user, max_tokens=1500)
        return llm.extract_json(text).get("flags", [])
    except Exception as e:  # review is advisory; never block a draft on it
        return [{"severity": "low", "slide": None, "issue": f"Automatic review failed: {e}", "fix": "Review manually"}]


def write_post(brief, feedback=None, previous=None):
    prompt = build_user_prompt(brief, feedback, previous)
    last_err = None
    for _ in range(2):
        try:
            text, _ = llm.call(SYSTEM, prompt, max_tokens=4000,
                               web_search=False)
            post = _clean(llm.extract_json(text), brief)
            post["flags"] = review(post, brief)
            return post
        except llm.LLMError as e:
            last_err = e
            prompt += f"\n\nYour previous answer was invalid ({e}). Return valid JSON exactly as specified."
    raise last_err


def full_caption(post, extra_sources=None):
    """Caption as it will be published: body + disclaimer + hashtags (IG max 2,200 chars, 30 hashtags)."""
    body = post["caption"].strip()
    tags = " ".join(post.get("hashtags", [])[:30])
    text = f"{body}\n\n{DISCLAIMER}\n\n{tags}".strip()
    if len(text) > 2200:
        room = 2200 - len(f"\n\n{DISCLAIMER}\n\n{tags}") - 1
        text = f"{body[:room].rstrip()}…\n\n{DISCLAIMER}\n\n{tags}"
    return text
