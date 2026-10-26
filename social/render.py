"""Render carousel slides (branded HTML template) to 1080x1350 JPEGs with headless Chromium."""
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from . import config as C

TEMPLATES = Path(__file__).parent / "templates"

# Shrinks text on any slide whose content would collide with the footer, then reports what still overflows.
FIT_JS = """
() => {
  const issues = [];
  document.querySelectorAll('.slide').forEach((sl, idx) => {
    const foot = sl.querySelector('.foot').getBoundingClientRect().top - 24;
    const els = sl.querySelectorAll('h1,h2,.text,.label,.ctx,.note,.col li,.big,.num,p');
    const bottom = () => Math.max(...[...sl.querySelectorAll('.body,.mid')].map(e => e.getBoundingClientRect().bottom));
    let tries = 0;
    while (bottom() > foot && tries < 10) {
      els.forEach(e => { const fs = parseFloat(getComputedStyle(e).fontSize); e.style.fontSize = (fs * 0.93) + 'px'; });
      tries++;
    }
    if (bottom() > foot) issues.push(idx + 1);
  });
  return issues;
}
"""


def _highlight(text):
    """*word* in a cover title is rendered in the accent colour."""
    return Markup(re.sub(r"\*(.+?)\*", r"<em>\1</em>", str(escape(text or ""))))


def build_html(slides):
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    env.filters["highlight"] = _highlight
    return env.get_template("slides.html.j2").render(slides=slides, b=C.BRAND, W=C.SLIDE_W, H=C.SLIDE_H)


def render_slides(slides, out_dir):
    """Returns (list of JPEG paths, list of slide numbers that still overflow)."""
    from playwright.sync_api import sync_playwright

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    html = build_html(slides)
    (out_dir / "slides.html").write_text(html, encoding="utf-8")
    paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": C.SLIDE_W, "height": C.SLIDE_H}, device_scale_factor=1)
        page.set_content(html, wait_until="networkidle", timeout=30000)
        try:
            page.evaluate("document.fonts.ready")
        except Exception:
            pass
        overflow = page.evaluate(FIT_JS)
        for i in range(1, len(slides) + 1):
            path = out_dir / f"slide-{i:02d}.jpg"
            page.locator(f"#s{i}").screenshot(path=str(path), type="jpeg", quality=92)
            paths.append(path)
        browser.close()
    return paths, overflow
