"""
apply_semantic_html.py

Replaces generic <div class="cc-*"> containers with semantic HTML5 tags
on every topic page under docs/topics/<slug>/index.html.

Transformations (all preserve existing class attributes and content, so
CSS targeting .cc-* classes continues to work unchanged):

  <div class="cc-header">         → <header class="cc-header">
  <div class="cc-footer">         → <footer class="cc-footer">
  <div class="cc-tldr">           → <section class="cc-tldr">
  <div class="cc-editorial">      → <section class="cc-editorial">
  <div class="cc-key-questions">  → <section class="cc-key-questions">
  <div class="cc-controversy">    → <section class="cc-controversy">
  <div class="cc-synthesis">      → <section class="cc-synthesis">
  <div class="cc-article-entry">  → <article class="cc-article-entry">
  <div class="cc-topics-strip">   → <nav class="cc-topics-strip">

Also wraps the page's primary content in a single <main> landmark,
positioned between </header> and <footer>.

Idempotent: running twice is a no-op. Safe to re-run after any content
edits that don't re-introduce the old div wrappers.

Run:
    cd christiancurator
    python scripts/apply_semantic_html.py           # all pages
    python scripts/apply_semantic_html.py baptism   # one page
"""

from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from frontend.topics_data import TOPICS  # noqa: E402

DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"

# class name → new tag name. All existing attributes (including class) are preserved.
TAG_RENAMES: dict[str, str] = {
    "cc-header": "header",
    "cc-footer": "footer",
    "cc-tldr": "section",
    "cc-editorial": "section",
    "cc-key-questions": "section",
    "cc-controversy": "section",
    "cc-synthesis": "section",
    "cc-article-entry": "article",
    "cc-topics-strip": "nav",
}


def rename_divs_by_class(soup: BeautifulSoup) -> int:
    """Rename every <div class="X"> to the configured semantic tag. Returns count."""
    count = 0
    for class_name, new_tag in TAG_RENAMES.items():
        for el in soup.find_all("div", class_=class_name):
            el.name = new_tag
            count += 1
    return count


def wrap_main(soup: BeautifulSoup) -> bool:
    """
    Wrap the page's primary content in a single <main>.

    The <main> opens right after </header> (the site header) and closes
    right before <footer> (the site footer). Returns True if a new
    <main> was inserted, False if one already existed.
    """
    if soup.find("main") is not None:
        return False

    header = soup.find("header", class_="cc-header")
    footer = soup.find("footer", class_="cc-footer")
    if header is None or footer is None:
        return False

    # header and footer must share a parent (cc-root) for a clean wrap
    if header.parent is not footer.parent:
        return False

    main_tag = soup.new_tag("main")

    # Collect everything strictly between header and footer, then move
    # them inside the new main element in order.
    cursor = header.next_sibling
    to_move = []
    while cursor is not None and cursor is not footer:
        to_move.append(cursor)
        cursor = cursor.next_sibling

    header.insert_after(main_tag)
    for node in to_move:
        main_tag.append(node.extract())

    return True


def process_page(slug: str) -> str:
    """Apply semantic upgrades to one topic page. Returns a status string."""
    html_path = TOPICS_DIR / slug / "index.html"
    if not html_path.exists():
        return f"{slug}: skipped (no index.html)"

    original = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(original, "html.parser")

    renamed = rename_divs_by_class(soup)
    main_added = wrap_main(soup)

    new_html = str(soup)
    if new_html == original:
        return f"{slug}: no change (already upgraded)"

    html_path.write_text(new_html, encoding="utf-8")
    parts = []
    if renamed:
        parts.append(f"{renamed} tag renames")
    if main_added:
        parts.append("wrapped in <main>")
    return f"{slug}: {', '.join(parts) if parts else 'updated'}"


def main():
    slugs_arg = sys.argv[1:]
    if slugs_arg:
        slugs = slugs_arg
    else:
        slugs = [t["slug"] for t in TOPICS]

    total = len(slugs)
    changed = 0
    skipped = 0
    for slug in slugs:
        status = process_page(slug)
        print(f"  {status}")
        if "skipped" in status:
            skipped += 1
        elif "no change" not in status:
            changed += 1

    print(f"\nDone: {changed}/{total} changed, {skipped} skipped.")


if __name__ == "__main__":
    main()
