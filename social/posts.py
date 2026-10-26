"""Post rules applied in code: slide clean-up, data numbers locked to the database, final caption."""
from . import config as C

DISCLAIMER = ("For education only, not investment advice. Mutual fund investments are subject to market "
              "risks; read all scheme-related documents carefully.")

VALID_TYPES = {"cover", "point", "stat", "bars", "compare", "tip", "cta"}


def normalize(post, insight=None):
    """Make a Claude-written post safe to render. `insight` is the database-computed data (data posts only)."""
    slides = [dict(s) for s in (post.get("slides") or []) if isinstance(s, dict) and s.get("type") in VALID_TYPES]
    slides = slides[:C.MAX_SLIDES]
    if not slides:
        raise ValueError("Post has no valid slides")
    if slides[0]["type"] != "cover":
        first = slides[0]
        slides[0] = {"type": "cover", "kicker": first.get("kicker", ""),
                     "title": first.get("title") or first.get("heading", ""),
                     "subtitle": first.get("subtitle") or first.get("body", "")}
    if slides[-1]["type"] != "cta":
        if len(slides) == C.MAX_SLIDES:
            slides.pop()
        slides.append({"type": "cta", "heading": "How much do your funds overlap?",
                       "body": f"Check your portfolio free at {C.BRAND['site']}"})
    for s in slides:
        if s["type"] == "bars":
            if insight and insight.get("chart"):
                s["items"], s["unit"] = insight["chart"]["items"], insight["chart"]["unit"]
            else:  # no database numbers -> never draw a chart
                s.update(type="tip", heading=s.get("title", ""), body=s.get("note", ""))
        if s["type"] == "stat" and insight and insight.get("stat"):
            s["value"] = insight["stat"]["value"]  # the headline number always comes from the database
        if s["type"] == "compare":
            s["left"] = list(s.get("left") or [])[:4]
            s["right"] = list(s.get("right") or [])[:4]
    tags = []
    for t in post.get("hashtags") or []:
        t = "#" + str(t).strip().lstrip("#").replace(" ", "")
        if len(t) > 1 and t.lower() not in {x.lower() for x in tags}:
            tags.append(t)
    return {"slides": slides, "hashtags": tags[:15]}


def full_caption(post):
    """Caption as it will be published: body + disclaimer + hashtags (IG max 2,200 chars, 30 hashtags)."""
    body = (post.get("caption") or "").strip()
    tags = " ".join((post.get("hashtags") or [])[:30])
    tail = f"\n\n{DISCLAIMER}\n\n{tags}".rstrip()
    if len(body) + len(tail) > 2200:
        body = body[:2200 - len(tail) - 1].rstrip() + "…"
    return (body + tail).strip()
