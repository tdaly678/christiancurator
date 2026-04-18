"""
add_related_topics.py — Insert a "Related topics" cross-link block into every
topic page, positioned between the closing </section> of the synthesis and
the opening of the "Curated" article list.

For each topic:
  1. Compute the 4 most related other topics by scoring:
       - same category: +5
       - per shared keyword: +2
       - per shared name-word (>3 chars): +3
  2. Inject a <nav class="cc-related-topics"> block with links to those 4 topics.
  3. Add .cc-related-topics CSS (once, idempotent by marker).

Content-additive: does not touch editorial, debate cards, synthesis copy, or
article annotations. Hand-curated body content is preserved exactly.

Idempotent: wrapped in AEO-RELATED-TOPICS marker comments; re-run replaces
the block in place (so the mapping can be recomputed after topics_data
changes).

Run:
    cd christiancurator
    python scripts/add_related_topics.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"

MARKER_START = "<!-- AEO-RELATED-TOPICS:START -->"
MARKER_END = "<!-- AEO-RELATED-TOPICS:END -->"

SECTION_CSS = """
    /* Related topics */
    .cc-related-topics { margin: 2.25rem 0; padding: 1.1rem 1.25rem 1.25rem; background: #f7f5f2; border-radius: 5px; border: 1px solid #e0ddd8; }
    .cc-related-topics-label { font-size: 10px; font-weight: 600; letter-spacing: 0.16em; text-transform: uppercase; color: #2C4A2E; margin-bottom: 0.8rem; }
    .cc-related-topics-list { display: flex; flex-wrap: wrap; gap: 0.45rem 0.7rem; }
    .cc-related-topic-link { display: inline-block; font-size: 13px; color: #2C4A2E; text-decoration: none; padding: 5px 11px; background: #fff; border: 1px solid #d0d9d0; border-radius: 3px; font-weight: 600; letter-spacing: 0.02em; }
    .cc-related-topic-link:hover { background: #2C4A2E; color: #fff; border-color: #2C4A2E; }
"""
CSS_MARKER = ".cc-related-topics {"


def load_topics():
    sys.path.insert(0, str(REPO_ROOT))
    from frontend.topics_data import TOPICS  # noqa: E402
    return TOPICS


def compute_related(topics: list, top_n: int = 4) -> dict[str, list[str]]:
    """{slug: [related_slug, ...top_n]} ordered by score desc."""
    related_map: dict[str, list[str]] = {}

    def score(a, b):
        s = 0
        if a["category"] == b["category"]:
            s += 5
        akw = {k.lower() for k in a.get("keywords", [])}
        bkw = {k.lower() for k in b.get("keywords", [])}
        s += 2 * len(akw & bkw)
        a_words = {w.lower() for w in a["name"].split() if len(w) > 3}
        b_words = {w.lower() for w in b["name"].split() if len(w) > 3}
        s += 3 * len(a_words & b_words)
        return s

    for t in topics:
        scored = [
            (other["slug"], score(t, other))
            for other in topics
            if other["slug"] != t["slug"]
        ]
        scored.sort(key=lambda x: -x[1])
        related_map[t["slug"]] = [slug for slug, sc in scored[:top_n] if sc > 0]

    return related_map


def build_section_html(related_slugs: list[str], by_slug: dict) -> str:
    links = []
    for s in related_slugs:
        t = by_slug[s]
        display = t["name"]
        if display.lower().startswith("on "):
            display = display[3:]
        links.append(
            f'<a class="cc-related-topic-link" href="/topics/{s}/">{display}</a>'
        )
    inner = "\n    ".join(links)
    return f"""{MARKER_START}
<nav aria-label="Related topics" class="cc-related-topics">
  <div class="cc-related-topics-label">Related Deep-Dive Topics</div>
  <div class="cc-related-topics-list">
    {inner}
  </div>
</nav>
{MARKER_END}"""


def inject_css(html: str) -> tuple[str, bool]:
    if CSS_MARKER in html:
        return html, False
    # Insert after .cc-synthesis p rule (it's near the end of the per-page styles)
    m = re.search(r"(\.cc-synthesis\s+p\s*\{[^}]*\})", html)
    if not m:
        # fallback: after .cc-synthesis {} itself
        m = re.search(r"(\.cc-synthesis\s*\{[^}]*\})", html)
    if not m:
        return html, False
    at = m.end()
    return html[:at] + SECTION_CSS + html[at:], True


def insert_or_replace_section(html: str, section_html: str) -> tuple[str, bool]:
    """Place section between </section> closing the synthesis and the next
    opening tag (div/main holding the Curated article list)."""
    # Replace existing marker block if present
    if MARKER_START in html and MARKER_END in html:
        new_html = re.sub(
            re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
            section_html,
            html,
            count=1,
            flags=re.DOTALL,
        )
        return new_html, new_html != html

    # Locate the synthesis section's closing tag.
    m_start = re.search(r'<section[^>]*class="cc-synthesis"[^>]*>', html)
    if not m_start:
        return html, False
    # Find matching </section> — synthesis doesn't contain nested <section>s
    end_m = re.search(r"</section>", html[m_start.end():])
    if not end_m:
        return html, False
    insert_at = m_start.end() + end_m.end()
    return html[:insert_at] + "\n" + section_html + html[insert_at:], True


def process_topic_page(slug: str, related_slugs: list[str], by_slug: dict) -> str:
    path = TOPICS_DIR / slug / "index.html"
    if not path.exists():
        return f"{slug}: skipped (no index.html)"
    if not related_slugs:
        return f"{slug}: skipped (no related topics computed)"
    html = path.read_text(encoding="utf-8")

    section = build_section_html(related_slugs, by_slug)
    new_html, css_added = inject_css(html)
    new_html, section_added = insert_or_replace_section(new_html, section)

    if not (css_added or section_added):
        return f"{slug}: no change"

    path.write_text(new_html, encoding="utf-8")
    parts = []
    if css_added:
        parts.append("css")
    if section_added:
        parts.append(f"section({len(related_slugs)} links)")
    return f"{slug}: {', '.join(parts)}"


def main():
    topics = load_topics()
    by_slug = {t["slug"]: t for t in topics}
    related_map = compute_related(topics, top_n=4)

    updated = 0
    for slug in sorted(related_map.keys()):
        status = process_topic_page(slug, related_map[slug], by_slug)
        print(f"  {status}")
        if "section" in status or "css" in status:
            updated += 1

    print(f"\nDone: {updated}/{len(related_map)} topic pages updated.")


if __name__ == "__main__":
    main()
