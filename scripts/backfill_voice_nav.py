"""
backfill_voice_nav.py — bring every /voices/<slug>/ page up to the canonical
site chrome: the Home + Topics mega-menu + Resources nav, plus the Topics-submenu
CSS the mega-menu needs to render.

Background: voice pages were generated across two eras. Newer/older ones already
carry the canonical Topics nav + submenu CSS (they pass check_nav_consistency);
~543 older ones still have the pre-Topics nav (Home + Resources only) and lack the
submenu CSS. Injecting the nav HTML without the CSS (as the generic backfill_nav.py
does) leaves the mega-menu unstyled, so this script does BOTH.

Single source of truth: the canonical nav + CSS are imported from
curator.voice_generator (which reads them from frontend/template.html), so
backfilled pages and freshly generated pages are guaranteed identical.

Idempotent: pages already canonical are skipped.

Run:
    cd christiancurator
    python scripts/backfill_voice_nav.py [--dry-run]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curator.voice_generator import NAV_HTML, TOPICS_SUBMENU_CSS  # noqa: E402

VOICES_DIR = REPO_ROOT / "docs" / "voices"

NAV_RE = re.compile(r'<nav class="cc-nav">.*?</nav>', re.DOTALL)
TOPICS_BUTTON_RE = re.compile(r'<button[^>]*>\s*Topics\s*</button>', re.I)
SUBMENU_CSS_MARKER = "CC-NAV-TOPICS-SUBMENU"


def process(path: Path) -> str:
    html = path.read_text(encoding="utf-8")
    original = html
    actions = []

    # 1. Ensure the canonical Topics nav (replace the whole cc-nav block if it
    #    lacks the Topics button).
    m = NAV_RE.search(html)
    if m and not TOPICS_BUTTON_RE.search(m.group(0)):
        html = html[: m.start()] + NAV_HTML.strip() + html[m.end():]
        actions.append("nav")

    # 2. Ensure the submenu CSS is present (inject into the first <style>).
    if TOPICS_SUBMENU_CSS and SUBMENU_CSS_MARKER not in html:
        idx = html.find("</style>")
        if idx != -1:
            html = html[:idx] + "\n    " + TOPICS_SUBMENU_CSS.strip() + "\n  " + html[idx:]
            actions.append("css")

    if html == original:
        return "unchanged"
    path.write_text(html, encoding="utf-8")
    return "updated (" + "+".join(actions) + ")"


def main(argv: list[str]) -> None:
    dry = "--dry-run" in argv
    updated = unchanged = 0
    detail = {"nav": 0, "css": 0}
    for d in sorted(VOICES_DIR.iterdir()):
        page = d / "index.html"
        if not d.is_dir() or not page.exists():
            continue
        if dry:
            html = page.read_text(encoding="utf-8")
            m = NAV_RE.search(html)
            needs_nav = bool(m and not TOPICS_BUTTON_RE.search(m.group(0)))
            needs_css = bool(TOPICS_SUBMENU_CSS and SUBMENU_CSS_MARKER not in html)
            if needs_nav or needs_css:
                updated += 1
                detail["nav"] += needs_nav
                detail["css"] += needs_css
            else:
                unchanged += 1
            continue
        result = process(page)
        if result.startswith("updated"):
            updated += 1
            if "nav" in result:
                detail["nav"] += 1
            if "css" in result:
                detail["css"] += 1
        else:
            unchanged += 1

    verb = "would update" if dry else "updated"
    print(f"{verb}={updated} (nav={detail['nav']}, css={detail['css']}) unchanged={unchanged}")


if __name__ == "__main__":
    main(sys.argv)
