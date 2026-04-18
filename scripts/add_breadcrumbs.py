"""
add_breadcrumbs.py — Insert Home > Topics > [Name] breadcrumbs into the 70
topic pages at docs/topics/<slug>/index.html.

Three edits per page:
  1. Inject `.cc-breadcrumb` CSS block into the <style> section (once).
  2. Insert <nav class="cc-breadcrumb"> between </header> and <main>
     (or after <main> if the layout nests it that way).
  3. Add BreadcrumbList JSON-LD alongside the Article JSON-LD.

Also adds id="topics" to <nav class="cc-topic-index"> on the homepage so
the "Topics" link in the breadcrumb has somewhere to land.

Idempotent: runs are stable. Hand-curated body content is untouched.

Run:
    cd christiancurator
    python scripts/add_breadcrumbs.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"

BREADCRUMB_CSS = """
    /* Breadcrumb */
    .cc-breadcrumb { font-size: 11px; color: #aaa; margin-bottom: 1.5rem; letter-spacing: 0.02em; }
    .cc-breadcrumb a { color: #2C4A2E; text-decoration: none; }
    .cc-breadcrumb a:hover { text-decoration: underline; }
    .cc-breadcrumb-sep { margin: 0 6px; color: #ccc; }
"""

# Marker comment so the idempotency check is unambiguous.
BREADCRUMB_CSS_MARKER = "/* Breadcrumb */"


def extract_topic_meta(html: str) -> tuple[str, str] | None:
    """Pull (topic_name, canonical_url) from the page; return None if not found."""
    name_m = re.search(
        r'<h1\s+class="cc-topic-title">([^<]+)</h1>', html, re.IGNORECASE
    )
    # Canonical link — attributes may be in either order (href before rel, or vice versa)
    canonical_m = re.search(
        r'<link\s+[^>]*rel="canonical"[^>]*?href="([^"]+)"', html, re.IGNORECASE
    )
    if not canonical_m:
        canonical_m = re.search(
            r'<link\s+[^>]*href="([^"]+)"[^>]*?rel="canonical"', html, re.IGNORECASE
        )
    if not name_m or not canonical_m:
        return None
    return name_m.group(1).strip(), canonical_m.group(1).strip()


def inject_breadcrumb_css(html: str) -> tuple[str, bool]:
    """Insert the breadcrumb CSS into the <style> block if not already present."""
    if BREADCRUMB_CSS_MARKER in html:
        return html, False

    # Insert right after the .cc-back:hover rule — that's near the top of the
    # style block on every topic page.
    anchor = re.search(r"(\.cc-back:hover\s*\{[^}]*\})", html)
    if not anchor:
        return html, False

    insert_at = anchor.end()
    new_html = html[:insert_at] + BREADCRUMB_CSS + html[insert_at:]
    return new_html, True


def build_breadcrumb_html(topic_name: str) -> str:
    """Return the breadcrumb <nav> markup."""
    # Keep topic name without the leading "On " prefix for cleaner breadcrumb text
    display = topic_name
    if display.lower().startswith("on "):
        display = display[3:]

    return (
        '<nav aria-label="Breadcrumb" class="cc-breadcrumb">'
        '<a href="/">Home</a>'
        '<span class="cc-breadcrumb-sep">\u203A</span>'
        '<a href="/#topics">Topics</a>'
        '<span class="cc-breadcrumb-sep">\u203A</span>'
        f"<span aria-current=\"page\">{display}</span>"
        "</nav>"
    )


def insert_breadcrumb_element(html: str, topic_name: str) -> tuple[str, bool]:
    """Insert <nav class="cc-breadcrumb"> between </header> and the topic hero."""
    if 'class="cc-breadcrumb"' in html:
        return html, False

    bc = build_breadcrumb_html(topic_name)

    # Pattern 1: </header><main>  (compact semantic output from apply_semantic_to_file)
    m = re.search(r"(</header>\s*<main>)", html, re.IGNORECASE)
    if m:
        new_html = html[: m.end()] + "\n" + bc + html[m.end():]
        return new_html, True

    # Pattern 2: </header>\n<main>
    m = re.search(r"(</header>\s*\n\s*<main[^>]*>)", html, re.IGNORECASE)
    if m:
        new_html = html[: m.end()] + "\n" + bc + html[m.end():]
        return new_html, True

    return html, False


def insert_breadcrumb_jsonld(html: str, topic_name: str, canonical: str) -> tuple[str, bool]:
    """Append a BreadcrumbList JSON-LD script right after the Article JSON-LD."""
    if '"@type": "BreadcrumbList"' in html or "'@type': 'BreadcrumbList'" in html:
        return html, False

    # Clean display name (strip "On " prefix)
    display = topic_name
    if display.lower().startswith("on "):
        display = display[3:]

    site_root = "https://www.christiancurator.com"
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Home",
                "item": f"{site_root}/",
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Topics",
                "item": f"{site_root}/#topics",
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": display,
                "item": canonical,
            },
        ],
    }
    jsonld = (
        '<script type="application/ld+json">\n'
        + json.dumps(data, indent=2, ensure_ascii=False)
        + "\n</script>"
    )

    # Insert right after the first closing </script> that follows an Article schema.
    article_m = re.search(
        r'"@type"\s*:\s*"Article"', html
    )
    if not article_m:
        return html, False
    # Find the </script> that closes that block
    close_m = re.search(r"</script>", html[article_m.end():])
    if not close_m:
        return html, False
    insert_at = article_m.end() + close_m.end()
    new_html = html[:insert_at] + "\n" + jsonld + html[insert_at:]
    return new_html, True


def process_topic_page(path: Path) -> str:
    """Apply all three edits to one topic page. Returns a status string."""
    html = path.read_text(encoding="utf-8")
    meta = extract_topic_meta(html)
    if not meta:
        return f"{path.parent.name}: skipped (couldn't extract topic meta)"
    topic_name, canonical = meta

    changed = False
    html, css_added = inject_breadcrumb_css(html)
    changed |= css_added

    html, el_added = insert_breadcrumb_element(html, topic_name)
    changed |= el_added

    html, jsonld_added = insert_breadcrumb_jsonld(html, topic_name, canonical)
    changed |= jsonld_added

    if not changed:
        return f"{path.parent.name}: no change (already has breadcrumb)"

    path.write_text(html, encoding="utf-8")
    parts = []
    if css_added:
        parts.append("css")
    if el_added:
        parts.append("nav")
    if jsonld_added:
        parts.append("json-ld")
    return f"{path.parent.name}: added {', '.join(parts)}"


def ensure_topics_anchor_on_homepage(template_path: Path, rendered_path: Path) -> list[str]:
    """Add id="topics" to <nav class="cc-topic-index"> on homepage template + rendered."""
    out = []
    for p in (template_path, rendered_path):
        if not p.exists():
            out.append(f"{p.name}: not found")
            continue
        html = p.read_text(encoding="utf-8")
        if re.search(r'<nav[^>]*\bid="topics"[^>]*class="cc-topic-index"', html) or re.search(
            r'<nav[^>]*class="cc-topic-index"[^>]*\bid="topics"', html
        ):
            out.append(f"{p.name}: already has id=topics")
            continue
        # Match the opening <nav class="cc-topic-index"> tag and insert id="topics"
        new_html, n = re.subn(
            r'<nav(\s+)class="cc-topic-index"',
            r'<nav\1id="topics" class="cc-topic-index"',
            html,
            count=1,
        )
        if n:
            p.write_text(new_html, encoding="utf-8")
            out.append(f"{p.name}: added id=topics")
        else:
            out.append(f"{p.name}: nav not found")
    return out


def main():
    print("== Homepage anchor ==")
    for line in ensure_topics_anchor_on_homepage(
        REPO_ROOT / "frontend" / "template.html",
        DOCS_DIR / "index.html",
    ):
        print(f"  {line}")

    print("\n== Topic pages ==")
    slugs = sorted(p for p in TOPICS_DIR.iterdir() if p.is_dir())
    total = len(slugs)
    added = 0
    skipped = 0
    for slug_dir in slugs:
        html_path = slug_dir / "index.html"
        if not html_path.exists():
            skipped += 1
            continue
        status = process_topic_page(html_path)
        print(f"  {status}")
        if "added" in status:
            added += 1
        elif "no change" in status or "skipped" in status:
            skipped += 1
    print(f"\nDone: {added}/{total} updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
