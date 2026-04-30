"""
apply_semantic_to_file.py

Applies semantic-tag upgrades to a Jinja-flavored HTML file WITHOUT
re-serializing the DOM (which BeautifulSoup does, mangling whitespace
and attribute order). Works by regex + balanced-div counting, so Jinja
{% ... %} and {{ ... }} blocks survive untouched.

Given a mapping of {class-name: new-tag}, for each class it:
  1. Finds every <div ... class="X" ...>.
  2. Counts <div>/</div> depth forward from that opening tag until it
     returns to zero — that's the matching close.
  3. Renames the opening tag and the matching close tag to the new tag.
  4. Preserves every attribute (including class) on the opening tag.

Also inserts a single <main>...</main> wrapper between the closing
</header> and the opening <footer> on the page, if not already present.

Idempotent: runs are stable after the first pass.

Run:
    cd christiancurator
    python scripts/apply_semantic_to_file.py frontend/digest_template.html
    python scripts/apply_semantic_to_file.py docs/index.html
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# class name → new tag. Order matters: outer containers first so that
# inner renames don't confuse the div-balance walker (we always scan
# only over remaining <div>/</div> tags, so order doesn't strictly
# matter for correctness, but outer-first reads more naturally in diffs).
DEFAULT_TAG_RENAMES: dict[str, str] = {
    # Page-level landmarks
    "cc-header": "header",
    "cc-footer": "footer",
    # Top-level sections
    "cc-welcome": "section",
    "cc-featured": "section",
    "cc-headlines": "section",
    "cc-world-news": "section",
    "cc-yesterday": "section",
    "cc-front": "section",
    "cc-archive-list": "section",
    # Topic-page sections (harmless on digest, no-op if absent)
    "cc-tldr": "section",
    "cc-editorial": "section",
    "cc-key-questions": "section",
    "cc-controversy": "section",
    "cc-synthesis": "section",
    # Independent content blocks
    "cc-featured-card": "article",
    "cc-headline-lead": "article",
    "cc-headline-item": "article",
    "cc-world-news-item": "article",
    "cc-article-entry": "article",
    "cc-card-large": "article",
    "cc-card-medium": "article",
    "cc-card-small": "article",
    "cc-lead": "article",
    "cc-article": "article",
    "cc-related-item": "article",
    # Navigation
    "cc-topics-strip": "nav",
    "cc-topic-index": "nav",
}

DIV_TAG_RE = re.compile(r"<(/?)div\b[^>]*>", re.IGNORECASE)


def rename_class_block(html: str, cls: str, new_tag: str) -> tuple[str, int]:
    """Replace every <div class="...cls..."> ... matching </div> pair with
    <new_tag ...> ... </new_tag>. Returns (new_html, replacement_count)."""
    # Match <div ...> where class attribute contains our class as a whole
    # word (so cc-header doesn't match cc-header-nav).
    open_re = re.compile(
        r'<div(\s+[^>]*?\bclass="(?:[^"]*\s)?'
        + re.escape(cls)
        + r'(?:\s[^"]*)?"[^>]*?)>',
    )

    # Collect all matches first, then apply replacements from the end so
    # positions in the source string don't shift as we edit.
    matches = list(open_re.finditer(html))
    out = html
    count = 0
    for m in reversed(matches):
        open_start, open_end = m.start(), m.end()
        attrs = m.group(1)

        # Walk forward from open_end, counting div depth.
        depth = 1
        pos = open_end
        close_start = close_end = None
        while True:
            tm = DIV_TAG_RE.search(out, pos)
            if not tm:
                break
            if tm.group(1):  # closing tag
                depth -= 1
                if depth == 0:
                    close_start, close_end = tm.start(), tm.end()
                    break
            else:
                depth += 1
            pos = tm.end()

        if close_start is None:
            # Unbalanced — skip this one rather than corrupt the file.
            continue

        # Replace close first (later in string → safe), then open.
        out = out[:close_start] + f"</{new_tag}>" + out[close_end:]
        out = out[:open_start] + f"<{new_tag}{attrs}>" + out[open_end:]
        count += 1

    return out, count


def insert_main_wrapper(html: str) -> tuple[str, bool]:
    """Insert <main>...</main> between </header> and <footer>, once.

    The <main> opens immediately after the first </header> and closes
    immediately before the last <footer class="cc-footer">. Assumes the
    header→footer rename has already been applied by rename_class_block.

    No-op if a <main> tag already exists anywhere in the file.
    """
    if re.search(r"<main\b", html, re.IGNORECASE):
        return html, False

    header_close = re.search(r"</header>", html, re.IGNORECASE)
    footer_open = re.search(r'<footer\b[^>]*class="[^"]*\bcc-footer\b', html, re.IGNORECASE)
    if not header_close or not footer_open:
        return html, False

    # Insert </main> just before <footer>. We do this first because
    # the insertion point is AFTER </header>, so positions ≤ header_close.end()
    # remain valid when we subsequently insert <main> after </header>.
    fo_start = footer_open.start()
    out = html[:fo_start] + "</main>\n" + html[fo_start:]
    hc_end = header_close.end()
    out = out[:hc_end] + "\n<main>\n" + out[hc_end:]

    return out, True


def apply_to_file(path: Path, tag_renames: dict[str, str] = DEFAULT_TAG_RENAMES) -> None:
    original = path.read_text(encoding="utf-8")
    html = original
    total_renamed = 0
    for cls, new_tag in tag_renames.items():
        html, n = rename_class_block(html, cls, new_tag)
        if n:
            total_renamed += n
            print(f"  {cls} → <{new_tag}>: {n} block(s)")

    html, main_added = insert_main_wrapper(html)
    if main_added:
        print("  wrapped content in <main>")

    if html != original:
        path.write_text(html, encoding="utf-8")
        print(f"  Wrote {path} ({total_renamed} renames)")
    else:
        print(f"  {path}: no change")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/apply_semantic_to_file.py <path> [path...]")
        sys.exit(2)

    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"  {path}: skipped (not found)")
            continue
        print(f"\n== {path} ==")
        apply_to_file(path)


if __name__ == "__main__":
    main()
