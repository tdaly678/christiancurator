"""
update_voice_backlinks.py — Add a "Featured in" section to voice pages listing
the topic pages where that voice has been featured.

Data sources (to maximize coverage):
  1. docs/featured_topic_log.json — historical daily featured-topic entries
     (topic slug + articles with author strings)
  2. docs/index.html + docs/digest/index.html — current rendered voice/topic
     co-occurrences (by proximity within same article container)

Voice names matched to slugs via docs/voices_data.json (exact name match + a
slugified fallback to catch minor punctuation differences).

Output: rewrites docs/voices/<slug>/index.html for every voice that has at least
one topic appearance, inserting a <section class="cc-voice-topics"> block with
links to the matching /topics/<slug>/ pages.

Idempotent: the section is wrapped in AEO-TOPIC-BACKLINKS marker comments and
replaced in-place on each run. Safe to re-run anytime — intended to be called
from the daily pipeline so new appearances propagate automatically.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
VOICES_DIR = DOCS_DIR / "voices"

MARKER_START = "<!-- AEO-TOPIC-BACKLINKS:START -->"
MARKER_END = "<!-- AEO-TOPIC-BACKLINKS:END -->"


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s


def build_voice_topic_map() -> dict[str, list[str]]:
    """Return {voice_slug: [topic_slug, ...]}, merged from all available sources."""
    voices = json.load(open(DOCS_DIR / "voices_data.json"))
    name_to_slug = {v["name"]: v["slug"] for v in voices}
    known_slugs = {v["slug"] for v in voices}

    mapping: dict[str, set[str]] = defaultdict(set)

    # Source 1: featured_topic_log.json
    log_path = DOCS_DIR / "featured_topic_log.json"
    if log_path.exists():
        log = json.load(open(log_path))
        for _date, topics in log.items():
            for topic in topics:
                tslug = topic.get("slug")
                if not tslug:
                    continue
                for art in topic.get("articles", []):
                    author_str = (art.get("author") or "").strip()
                    if not author_str:
                        continue
                    # Split multi-author strings: commas, " & ", " and "
                    parts = re.split(r",| & | and ", author_str)
                    for p in parts:
                        p = p.strip()
                        if not p:
                            continue
                        vslug = name_to_slug.get(p)
                        if not vslug:
                            cand = slugify(p)
                            if cand in known_slugs:
                                vslug = cand
                        if vslug:
                            mapping[vslug].add(tslug)

    # Source 2: proximity scan of homepage + digest (for currently-featured voices)
    for p in [DOCS_DIR / "index.html", DOCS_DIR / "digest" / "index.html"]:
        if not p.exists():
            continue
        html = p.read_text(encoding="utf-8")
        for m in re.finditer(r'href="/voices/([^/"]+)/"', html):
            vslug = m.group(1)
            if vslug not in known_slugs:
                continue
            ctx = html[max(0, m.start() - 400): m.end() + 400]
            for tslug in re.findall(r'href="/topics/([^/"]+)/"', ctx):
                mapping[vslug].add(tslug)

    return {v: sorted(ts) for v, ts in mapping.items() if ts}


def load_topic_names() -> dict[str, str]:
    """Return {topic_slug: display_name} from frontend.topics_data."""
    sys.path.insert(0, str(REPO_ROOT))
    from frontend.topics_data import TOPICS  # noqa: E402
    return {t["slug"]: t["name"] for t in TOPICS}


def build_section_html(topic_slugs: list[str], topic_names: dict[str, str]) -> str:
    """Return the HTML block for the 'Featured in' section."""
    links = []
    for tslug in topic_slugs:
        tname = topic_names.get(tslug, tslug.replace("-", " ").title())
        # Strip "On " prefix for cleaner display
        display = tname[3:] if tname.lower().startswith("on ") else tname
        links.append(
            f'<a class="cc-voice-topic-link" href="/topics/{tslug}/">{display}</a>'
        )
    inner = "\n      ".join(links)
    return f"""{MARKER_START}
<section class="cc-voice-topics">
  <div class="cc-section-label">Featured in Deep-Dive Topics</div>
  <div class="cc-voice-topics-list">
      {inner}
  </div>
</section>
{MARKER_END}"""


SECTION_CSS = """
    .cc-voice-topics{margin:2rem 0 2.5rem;padding:1.25rem 1.5rem;background:#fff;border:1px solid #e0ddd8;border-radius:5px;}
    .cc-voice-topics-list{display:flex;flex-wrap:wrap;gap:0.5rem 0.9rem;}
    .cc-voice-topic-link{display:inline-block;font-size:13px;color:#2C4A2E;text-decoration:none;padding:4px 10px;background:#f0f4f0;border-radius:3px;font-weight:600;letter-spacing:0.02em;}
    .cc-voice-topic-link:hover{background:#2C4A2E;color:#fff;}
"""
CSS_MARKER = ".cc-voice-topics{"  # simple dedupe marker


def inject_css(html: str) -> tuple[str, bool]:
    if CSS_MARKER in html:
        return html, False
    # Insert immediately after the .cc-voice-bio{} rule (every voice page has it)
    m = re.search(r"(\.cc-voice-bio\s*\{[^}]*\})", html)
    if not m:
        return html, False
    at = m.end()
    return html[:at] + SECTION_CSS + html[at:], True


def insert_or_replace_section(html: str, section_html: str) -> tuple[str, bool]:
    """Put the section between <p class="cc-voice-bio">...</p> and the <div class="cc-voice-meta">
    (or before the 'Notable Books' section if meta absent)."""
    # Replace existing marker-bounded section if present
    if MARKER_START in html and MARKER_END in html:
        new_html = re.sub(
            re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
            section_html,
            html,
            count=1,
            flags=re.DOTALL,
        )
        return new_html, new_html != html

    # Fresh insertion: after </p> that closes cc-voice-bio
    m = re.search(r'(<p class="cc-voice-bio">.*?</p>)', html, re.DOTALL)
    if not m:
        return html, False
    at = m.end()
    return html[:at] + "\n    " + section_html + html[at:], True


def process_voice(slug: str, topic_slugs: list[str], topic_names: dict[str, str]) -> str:
    path = VOICES_DIR / slug / "index.html"
    if not path.exists():
        return f"{slug}: skipped (no index.html)"
    html = path.read_text(encoding="utf-8")

    section = build_section_html(topic_slugs, topic_names)
    new_html = html
    css_changed = False
    section_changed = False

    new_html, css_changed = inject_css(new_html)
    new_html, section_changed = insert_or_replace_section(new_html, section)

    if not (css_changed or section_changed):
        return f"{slug}: no change"

    path.write_text(new_html, encoding="utf-8")
    parts = []
    if css_changed:
        parts.append("css")
    if section_changed:
        parts.append(f"section({len(topic_slugs)} topics)")
    return f"{slug}: {', '.join(parts)}"


def main():
    mapping = build_voice_topic_map()
    topic_names = load_topic_names()

    print(f"Voice→topic mapping: {len(mapping)} voices with topic links")
    if not mapping:
        print("  (nothing to do)")
        return

    updated = 0
    for slug in sorted(mapping.keys()):
        status = process_voice(slug, mapping[slug], topic_names)
        print(f"  {status}")
        if "section" in status or "css" in status:
            updated += 1

    print(f"\nDone: {updated}/{len(mapping)} voice pages updated.")


if __name__ == "__main__":
    main()
