"""
unify_site_layout.py — Apply the homepage-style header, footer, and topic-index
grid to every hand-curated topic page under docs/topics/.

Problem solved:
  Topic pages launched with a minimal header (back-link + small logo) and a
  footer bar of pill-shaped topic links. They didn't match the homepage's
  full masthead/nav/footer, and the width differed too. This script unifies
  the chrome across all 70 topic pages.

What this script does on each topic page:
  1. Replace the minimal <header class="cc-header"> block with the full
     homepage header (top-bar + masthead + nav + Resources dropdown).
  2. Replace the short footer with the homepage footer (name / nav / tagline).
  3. Replace the bottom <nav class="cc-topics-strip"> pills with a 4-column
     <nav class="cc-topic-index"> grid that matches the homepage, grouped
     by category with the CURRENT topic highlighted.
  4. Widen .cc-root to 980px so the header/footer fill the outer frame,
     and add `class="cc-prose"` + CSS so <main> stays at 740px for reading.
  5. Inject any CSS rules the page is missing (masthead, tagline, nav
     dropdown, topic-index grid, full footer).

Content-additive / surgical: the topic hero, TL;DR, editorial, debate cards,
synthesis, related-topics block, breadcrumb, FAQ schema, and curated-article
list are all preserved exactly as they were.

Idempotent: every injected block is wrapped in AEO-SITE-HEADER / -FOOTER /
-TOPIC-INDEX marker comments. Re-running the script replaces those blocks
in place rather than duplicating them, so it's safe to run repeatedly.

Run:
    cd christiancurator
    python scripts/unify_site_layout.py
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"

sys.path.insert(0, str(REPO_ROOT))
from frontend.topics_data import TOPICS  # noqa: E402

# ── Markers ──────────────────────────────────────────────────────────
HDR_START = "<!-- AEO-SITE-HEADER:START -->"
HDR_END = "<!-- AEO-SITE-HEADER:END -->"
FTR_START = "<!-- AEO-SITE-FOOTER:START -->"
FTR_END = "<!-- AEO-SITE-FOOTER:END -->"
IDX_START = "<!-- AEO-TOPIC-INDEX:START -->"
IDX_END = "<!-- AEO-TOPIC-INDEX:END -->"
CSS_MARKER = "/* AEO-UNIFIED-CHROME */"

# ── Shared header HTML ───────────────────────────────────────────────
SHARED_HEADER = f"""{HDR_START}
<header class="cc-header">
<div class="cc-top-bar">
<span class="cc-top-label">Deep-Dive Topic</span>
<a class="cc-subscribe-btn" href="/#cc-email-box">Get the Daily Digest</a>
</div>
<div class="cc-masthead">
<div class="cc-masthead-h1"><a href="/" class="cc-site-name">Christian Curator</a></div>
<p class="cc-tagline">Curated perspectives &middot; updated daily</p>
</div>
<nav class="cc-nav">
<a href="/">Home</a>
<div class="cc-nav-dropdown">
<button class="cc-nav-dropdown-toggle">Resources</button>
<div class="cc-nav-dropdown-menu">
<a href="/about/">About</a>
<a href="/voices/">Voices</a>
<a href="/archive/">Archive</a>
</div>
</div>
</nav>
</header>
{HDR_END}"""

SHARED_FOOTER = f"""{FTR_START}
<footer class="cc-footer">
<div class="cc-footer-name">Christian Curator</div>
<div class="cc-footer-nav">
<a href="/about/">About</a>
<a href="/digest/">Daily Digest</a>
<a href="/voices/">Voices</a>
<a href="/archive/">Archive</a>
</div>
<div class="cc-footer-tagline">Curated from across the evangelical web.</div>
</footer>
{FTR_END}"""

# ── CSS block we inject / overwrite with ─────────────────────────────
UNIFIED_CSS = f"""
{CSS_MARKER}
/* Outer frame: 980px for header/footer consistency across pages. */
.cc-root {{ max-width: 980px; margin: 0 auto; padding: 0 20px 3rem; }}
/* Content stays narrow for long-form reading. */
main.cc-prose {{ max-width: 740px; margin: 0 auto; padding-top: 1.5rem; }}

/* Header chrome */
.cc-header {{ border-bottom: 1px solid #e0ddd8; padding: 0.75rem 0 0; margin-bottom: 0; }}
.cc-top-bar {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem; font-size: 12px; color: #888; letter-spacing: 0.02em; }}
.cc-top-label {{ font-size: 10px; font-weight: 600; letter-spacing: 0.16em; text-transform: uppercase; color: #2C4A2E; }}
.cc-subscribe-btn {{ background: #2C4A2E; color: #fff; border: none; padding: 5px 14px; font-size: 12px; border-radius: 3px; cursor: pointer; font-family: inherit; letter-spacing: 0.03em; text-decoration: none; display: inline-block; }}
.cc-subscribe-btn:hover {{ background: #3a5f3c; color: #fff; }}
.cc-masthead {{ text-align: center; padding: 0.5rem 0 1rem; border-bottom: 2.5px solid #1a1a1a; }}
.cc-masthead-h1 {{ margin: 0; line-height: 1; }}
.cc-masthead .cc-site-name {{ font-family: 'Lora', Georgia, serif; font-size: 46px; font-weight: 600; letter-spacing: -0.02em; line-height: 1; color: #1a1a1a; text-decoration: none; }}
@media (max-width: 600px) {{ .cc-masthead .cc-site-name {{ font-size: 32px; }} }}
.cc-tagline {{ font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase; color: #888; margin: 8px 0 0; font-weight: 300; }}
.cc-nav {{ display: flex; justify-content: center; align-items: center; gap: 2rem; padding: 0.6rem 0 0.75rem; border-top: 1px solid #e0ddd8; margin-top: 0.75rem; }}
.cc-nav a {{ font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #888; text-decoration: none; }}
.cc-nav a:hover {{ color: #2C4A2E; }}
.cc-nav-dropdown {{ position: relative; display: inline-block; }}
.cc-nav-dropdown-toggle {{ font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #888; cursor: pointer; display: flex; align-items: center; gap: 4px; background: none; border: none; font-family: inherit; padding: 0; }}
.cc-nav-dropdown-toggle:hover {{ color: #2C4A2E; }}
.cc-nav-dropdown-toggle::after {{ content: '\\25BE'; font-size: 10px; letter-spacing: 0; }}
.cc-nav-dropdown-menu {{ display: none; position: absolute; top: 100%; left: 50%; transform: translateX(-50%); background: #fff; border: 1px solid #e0ddd8; border-radius: 4px; padding: 14px 0 6px; min-width: 140px; z-index: 100; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
.cc-nav-dropdown:hover .cc-nav-dropdown-menu, .cc-nav-dropdown:focus-within .cc-nav-dropdown-menu {{ display: block; }}
.cc-nav-dropdown-menu a {{ display: block; padding: 7px 18px; font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #888; text-decoration: none; white-space: nowrap; }}
.cc-nav-dropdown-menu a:hover {{ color: #2C4A2E; background: #f7f5f2; }}

/* Topic index (4-col grid at bottom, replaces pills) */
.cc-topic-index {{ margin-top: 3rem; padding-top: 1.75rem; border-top: 1px solid #e0ddd8; }}
.cc-topic-index-header {{ border-bottom: 2px solid #1a1a1a; padding-bottom: 6px; margin-bottom: 1.25rem; display: flex; align-items: baseline; justify-content: space-between; }}
.cc-topic-index-label {{ font-size: 10px; font-weight: 600; letter-spacing: 0.16em; text-transform: uppercase; color: #1a1a1a; }}
.cc-topic-index-meta {{ font-size: 11px; color: #aaa; }}
.cc-topic-index-meta a {{ color: #2C4A2E; text-decoration: none; font-weight: 600; }}
.cc-topic-index-meta a:hover {{ text-decoration: underline; }}
.cc-topic-index-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 0 2rem; }}
@media (max-width: 760px) {{ .cc-topic-index-grid {{ grid-template-columns: 1fr 1fr; gap: 1.5rem 2rem; }} }}
@media (max-width: 480px) {{ .cc-topic-index-grid {{ grid-template-columns: 1fr; }} }}
.cc-topic-index-cat {{ font-size: 10px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: #2C4A2E; border-bottom: 1px solid #e0ddd8; padding-bottom: 5px; margin-bottom: 8px; }}
.cc-topic-index-link {{ display: block; font-size: 12.5px; color: #444; text-decoration: none; padding: 4px 0; border-bottom: 1px solid #f5f3f0; line-height: 1.35; font-family: 'Lora', Georgia, serif; }}
.cc-topic-index-link:hover {{ color: #2C4A2E; }}
.cc-topic-index-link.active {{ color: #2C4A2E; font-weight: 600; }}
.cc-topic-index-link:last-child {{ border-bottom: none; }}

/* Unified footer */
.cc-footer {{ border-top: 2.5px solid #1a1a1a; margin-top: 2.5rem; padding: 1rem 0; display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: #aaa; flex-wrap: wrap; gap: 8px; text-align: left; line-height: 1.4; }}
.cc-footer-name {{ font-family: 'Lora', Georgia, serif; font-weight: 600; font-size: 15px; color: #1a1a1a; }}
.cc-footer-nav {{ display: flex; gap: 12px; }}
.cc-footer-nav a {{ font-size: 11px; color: #888; text-decoration: none; font-weight: 600; }}
.cc-footer-nav a:hover {{ color: #2C4A2E; }}
.cc-footer-tagline {{ font-size: 11px; color: #aaa; }}
"""


def build_topic_index_html(current_slug: str) -> str:
    """Return the full topic-index grid, with the current topic highlighted."""
    by_cat: dict[str, list] = defaultdict(list)
    for t in TOPICS:
        by_cat[t["category"]].append(t)
    # Stable category order matching homepage convention
    category_order = ["Core Theology", "Church Life", "Spiritual Formation", "Culture & Society"]
    cats = [c for c in category_order if c in by_cat] + [c for c in by_cat if c not in category_order]

    parts = [IDX_START, '<nav class="cc-topic-index" aria-label="All topics">']
    parts.append('<div class="cc-topic-index-header">')
    parts.append(f'<div class="cc-topic-index-label">Explore all {len(TOPICS)} topics</div>')
    parts.append('<div class="cc-topic-index-meta"><a href="/digest/">Today\u2019s digest \u2192</a></div>')
    parts.append('</div>')
    parts.append('<div class="cc-topic-index-grid">')
    for cat in cats:
        parts.append('<div class="cc-topic-index-col">')
        parts.append(f'<div class="cc-topic-index-cat">{cat}</div>')
        for t in by_cat[cat]:
            cls = "cc-topic-index-link active" if t["slug"] == current_slug else "cc-topic-index-link"
            parts.append(f'<a href="/topics/{t["slug"]}/" class="{cls}">{t["name"]}</a>')
        parts.append('</div>')
    parts.append('</div>')
    parts.append('</nav>')
    parts.append(IDX_END)
    return "\n".join(parts)


def inject_or_replace_css(html: str) -> tuple[str, bool]:
    """Insert the unified-chrome CSS block before </style>. On re-runs,
    replace the existing marker-bounded block in place."""
    if CSS_MARKER in html:
        # Replace the existing unified block (from marker to just before </style>).
        # Use a lambda for replacement so backslashes (\25BE etc.) aren't parsed as group refs.
        new_html = re.sub(
            re.escape(CSS_MARKER) + r"[\s\S]*?(?=</style>)",
            lambda _m: UNIFIED_CSS.strip() + "\n",
            html,
            count=1,
        )
        return new_html, new_html != html
    # Fresh inject — place right before </style>
    if "</style>" not in html:
        return html, False
    new_html = html.replace("</style>", UNIFIED_CSS + "\n</style>", 1)
    return new_html, True


def replace_header(html: str) -> tuple[str, bool]:
    """Replace <header class="cc-header">...</header> with SHARED_HEADER (wrapped in markers)."""
    # Re-run path: replace marker-bounded block
    if HDR_START in html and HDR_END in html:
        new_html = re.sub(
            re.escape(HDR_START) + r"[\s\S]*?" + re.escape(HDR_END),
            lambda _m: SHARED_HEADER,
            html,
            count=1,
        )
        return new_html, new_html != html
    # Fresh: find the minimal existing header and replace it
    pattern = re.compile(r'<header class="cc-header">[\s\S]*?</header>', re.IGNORECASE)
    if not pattern.search(html):
        return html, False
    new_html = pattern.sub(lambda _m: SHARED_HEADER, html, count=1)
    return new_html, new_html != html


def replace_footer(html: str) -> tuple[str, bool]:
    """Replace <footer class="cc-footer">...</footer> with SHARED_FOOTER (wrapped in markers)."""
    if FTR_START in html and FTR_END in html:
        new_html = re.sub(
            re.escape(FTR_START) + r"[\s\S]*?" + re.escape(FTR_END),
            lambda _m: SHARED_FOOTER,
            html,
            count=1,
        )
        return new_html, new_html != html
    pattern = re.compile(r'<footer class="cc-footer">[\s\S]*?</footer>', re.IGNORECASE)
    if not pattern.search(html):
        return html, False
    new_html = pattern.sub(lambda _m: SHARED_FOOTER, html, count=1)
    return new_html, new_html != html


def replace_pills_with_index(html: str, slug: str) -> tuple[str, bool]:
    """Remove the existing <nav class="cc-topics-strip">...</nav> pills section
    and inject the cc-topic-index grid (wrapped in markers) just before </main>.
    On re-run, replace the marker-bounded block in place."""
    index_html = build_topic_index_html(slug)

    # If marker block already present, replace it in place
    if IDX_START in html and IDX_END in html:
        new_html = re.sub(
            re.escape(IDX_START) + r"[\s\S]*?" + re.escape(IDX_END),
            lambda _m: index_html,
            html,
            count=1,
        )
        return new_html, new_html != html

    # Remove old pills strip (nav or section form)
    new_html = re.sub(
        r'<(nav|section)[^>]*class="cc-topics-strip"[\s\S]*?</\1>',
        "",
        html,
        count=1,
    )

    # Inject before </main>
    if "</main>" not in new_html:
        return new_html, new_html != html
    new_html = new_html.replace("</main>", index_html + "\n</main>", 1)
    return new_html, new_html != html


def add_prose_class_to_main(html: str) -> tuple[str, bool]:
    """Ensure the <main> element has the cc-prose class so the 740px narrowing applies."""
    if re.search(r'<main[^>]*class="[^"]*cc-prose[^"]*"', html):
        return html, False
    # Handle <main> with no attributes
    new_html, n = re.subn(r'<main(\s*)>', r'<main\1 class="cc-prose">', html, count=1)
    if n:
        return new_html, True
    # Handle <main class="..."> (no cc-prose yet)
    new_html, n = re.subn(r'<main([^>]*)class="([^"]*)"', r'<main\1class="\2 cc-prose"', html, count=1)
    return new_html, bool(n)


def process_topic_page(slug: str) -> str:
    path = TOPICS_DIR / slug / "index.html"
    if not path.exists():
        return f"{slug}: skipped (no index.html)"
    html = path.read_text(encoding="utf-8")
    original = html

    changes = []
    html, ch = inject_or_replace_css(html)
    if ch: changes.append("css")
    html, ch = replace_header(html)
    if ch: changes.append("header")
    html, ch = add_prose_class_to_main(html)
    if ch: changes.append("main-class")
    html, ch = replace_pills_with_index(html, slug)
    if ch: changes.append("topic-index")
    html, ch = replace_footer(html)
    if ch: changes.append("footer")

    if html == original:
        return f"{slug}: no change"
    path.write_text(html, encoding="utf-8")
    return f"{slug}: {', '.join(changes)}"


def main():
    slugs = sorted({t["slug"] for t in TOPICS})
    updated = 0
    for slug in slugs:
        status = process_topic_page(slug)
        print(f"  {status}")
        if "no change" not in status and "skipped" not in status:
            updated += 1
    print(f"\nDone: {updated}/{len(slugs)} topic pages updated.")


if __name__ == "__main__":
    main()
