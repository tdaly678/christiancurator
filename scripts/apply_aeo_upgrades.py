"""
apply_aeo_upgrades.py

Applies AEO improvements to every topic page under docs/topics/<slug>/index.html:

  1. Upgrade section labels to semantic <h2>:
       .cc-key-questions-label, .cc-synthesis-label, .cc-article-list-label, .cc-debate-label
     (CSS targets these by class, so visual styling is preserved.)
  2. Insert a TL;DR block immediately after the topic hero, using the
     tldr field from output/aeo_enrichment.json.
  3. Insert a visible "Last updated: <date>" line inside the hero.
  4. Add FAQPage JSON-LD built from the page's existing Key Questions +
     the faq_answers generated in aeo_enrichment.json.
  5. Enrich (or replace) the existing Article JSON-LD so it includes:
       author, datePublished, dateModified, description (updated to the
       new meta_description).
  6. Overwrite <meta name="description">, <meta property="og:description">,
     and <meta name="twitter:description"> with the AEO meta_description.

The script is idempotent: running it twice produces the same output.

Run:
    cd christiancurator
    python scripts/apply_aeo_upgrades.py           # applies to all pages
    python scripts/apply_aeo_upgrades.py abortion  # applies to one page
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from frontend.topics_data import TOPICS_BY_SLUG  # noqa: E402

DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"
ENRICHMENT_PATH = REPO_ROOT / "output" / "aeo_enrichment.json"

AUTHOR_NAME = "Christian Curator Editorial"
PUBLISHER_NAME = "Christian Curator"
SITE_URL = "https://www.christiancurator.com"

# Fixed publication date for topic pages (they were created in April 2026)
DEFAULT_PUBLISHED = "2026-04-01"
TODAY_ISO = dt.date.today().isoformat()


TLDR_CSS = """
    .cc-tldr { margin-bottom: 2rem; padding: 1.1rem 1.25rem; background: #fef9f0; border-left: 3px solid #c9a144; border-radius: 0 4px 4px 0; }
    .cc-tldr-label { font-size: 10px; font-weight: 600; letter-spacing: 0.16em; text-transform: uppercase; color: #8b6f1e; margin-bottom: 0.45rem; }
    .cc-tldr p { font-size: 15px; line-height: 1.6; color: #2a2a2a; margin: 0; }
    .cc-last-updated { font-size: 12px; color: #999; margin-top: 0.6rem; }
""".strip()


def pretty_date(iso: str) -> str:
    """Turn 2026-04-17 into 'April 17, 2026'."""
    return dt.date.fromisoformat(iso).strftime("%B %-d, %Y")


# ──────────────────────────────────────────────────────────────────────────────
# Individual upgrades — each returns True if it modified the soup.
# ──────────────────────────────────────────────────────────────────────────────

# Classes that mark a real section heading and should be <h2>.
# Styling is by class, so visual appearance is unchanged.
LABEL_CLASSES_TO_H2 = [
    "cc-key-questions-label",    # "Key Questions This Topic Addresses"
    "cc-synthesis-label",        # "What the Conversation Adds Up To"
    "cc-article-list-label",     # "The Evangelical Conversation, Curated"
    "cc-debate-label",           # "The Evangelical Debate" (34 pages)
    "cc-controversy-label",      # "The Evangelical Debate" (35 pages, alt markup)
    "cc-controversy-title",      # Section title for controversy-style pages
]


def upgrade_section_labels_to_h2(soup: BeautifulSoup) -> bool:
    changed = False
    for cls in LABEL_CLASSES_TO_H2:
        for tag in soup.select(f"div.{cls}"):
            tag.name = "h2"
            changed = True
    return changed


def ensure_tldr_css(soup: BeautifulSoup) -> bool:
    """Append the TL;DR CSS to the first <style> block if not already there."""
    style = soup.find("style")
    if not style or not style.string:
        return False
    if ".cc-tldr {" in style.string:
        return False
    style.string = style.string.rstrip() + "\n" + TLDR_CSS + "\n"
    return True


def insert_tldr_block(soup: BeautifulSoup, tldr: str) -> bool:
    """Insert a TL;DR block right after the cc-topic-hero div. Idempotent."""
    hero = soup.select_one(".cc-topic-hero")
    if not hero:
        return False

    # Remove any existing tldr block so we refresh content on re-run
    existing = soup.select_one(".cc-tldr")
    if existing:
        existing.decompose()

    block = soup.new_tag("div", attrs={"class": "cc-tldr"})
    label = soup.new_tag("div", attrs={"class": "cc-tldr-label"})
    label.string = "TL;DR"
    block.append(label)
    p = soup.new_tag("p")
    p.string = tldr
    block.append(p)
    hero.insert_after(block)
    return True


def insert_last_updated(soup: BeautifulSoup, when: str) -> bool:
    """Insert 'Last updated: April 17, 2026' inside .cc-topic-hero. Idempotent."""
    hero = soup.select_one(".cc-topic-hero")
    if not hero:
        return False
    # Remove any previous cc-last-updated so we refresh
    for el in hero.select(".cc-last-updated"):
        el.decompose()
    p = soup.new_tag("p", attrs={"class": "cc-last-updated"})
    p.string = f"Last updated: {pretty_date(when)}"
    hero.append(p)
    return True


def _jsonld_scripts(soup: BeautifulSoup):
    return soup.find_all("script", attrs={"type": "application/ld+json"})


def upgrade_article_schema(soup: BeautifulSoup, meta_description: str, url: str) -> bool:
    """Enrich the existing Article schema (or add one if missing)."""
    scripts = _jsonld_scripts(soup)
    article_script = None
    article_data = None
    for s in scripts:
        if not s.string:
            continue
        try:
            data = json.loads(s.string)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Article":
            article_script = s
            article_data = data
            break

    if article_data is None:
        # Build fresh Article schema
        article_data = {
            "@context": "https://schema.org",
            "@type": "Article",
            "url": url,
            "mainEntityOfPage": url,
        }

    article_data["description"] = meta_description
    article_data["author"] = {"@type": "Organization", "name": AUTHOR_NAME, "url": SITE_URL}
    article_data["publisher"] = {
        "@type": "Organization",
        "name": PUBLISHER_NAME,
        "url": SITE_URL,
    }
    article_data.setdefault("datePublished", DEFAULT_PUBLISHED)
    article_data["dateModified"] = TODAY_ISO
    article_data.setdefault("@context", "https://schema.org")
    article_data["@type"] = "Article"
    article_data.setdefault("url", url)
    article_data.setdefault("mainEntityOfPage", url)

    new_json = json.dumps(article_data, ensure_ascii=False, indent=2)
    if article_script is not None:
        article_script.string = "\n" + new_json + "\n"
    else:
        tag = soup.new_tag("script", attrs={"type": "application/ld+json"})
        tag.string = "\n" + new_json + "\n"
        head = soup.find("head")
        head.append(tag)
    return True


FAQ_MARKER_COMMENT = "AEO-FAQPAGE-SCHEMA"


def _normalize(s: str) -> str:
    """Normalize for fuzzy key matching: strip all quote/apostrophe variants.
    LLMs sometimes swap straight doubles for straight singles or vice versa,
    and the page may render curly quotes. Stripping them is safe because we
    keep the original question text for the final schema key."""
    drop = {
        "'", '"',
        "\u2018", "\u2019", "\u201c", "\u201d",  # curly quotes
    }
    return "".join(ch for ch in s if ch not in drop).strip().lower()


def upgrade_faq_schema(soup: BeautifulSoup, questions: list[str], answers: dict) -> bool:
    """Add (or refresh) a FAQPage JSON-LD using the page's questions and provided answers."""
    # Remove any prior block we inserted
    for s in _jsonld_scripts(soup):
        if s.string and FAQ_MARKER_COMMENT in s.string:
            s.decompose()

    # Build a normalized lookup so smart-quote/curly-apostrophe mismatches don't drop answers
    norm_answers = {_normalize(k): v for k, v in answers.items()}

    faq_items = []
    for q in questions:
        a = answers.get(q) or norm_answers.get(_normalize(q))
        if not a:
            continue
        faq_items.append(
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
        )
    if not faq_items:
        return False

    faq_data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_items,
    }
    body = json.dumps(faq_data, ensure_ascii=False, indent=2)
    # Marker comment lets us find and refresh this block on re-runs
    wrapped = f"\n/* {FAQ_MARKER_COMMENT} */\n{body}\n"
    tag = soup.new_tag("script", attrs={"type": "application/ld+json"})
    tag.string = wrapped
    soup.find("head").append(tag)
    return True


def update_meta_descriptions(soup: BeautifulSoup, meta_description: str) -> bool:
    """Ensure description / og:description / twitter:description exist with content."""
    head = soup.find("head")
    if head is None:
        return False
    changed = False
    targets = [
        {"name": "description"},
        {"property": "og:description"},
        {"name": "twitter:description"},
    ]
    for attrs in targets:
        tag = soup.find("meta", attrs=attrs)
        if tag is None:
            tag = soup.new_tag("meta", attrs={**attrs, "content": meta_description})
            head.append(tag)
            changed = True
        elif tag.get("content") != meta_description:
            tag["content"] = meta_description
            changed = True
    return changed


def ensure_head_metadata(soup: BeautifulSoup, slug: str, topic_name: str, url: str) -> bool:
    """Make sure canonical, og:type, og:site_name, og:title, og:url, twitter:card,
    twitter:title exist. Page-specific titles are derived from the <title> tag."""
    head = soup.find("head")
    if head is None:
        return False
    title_tag = soup.find("title")
    page_title = title_tag.get_text(strip=True) if title_tag else f"On {topic_name} — Christian Curator"

    changed = False

    def ensure(selector_attrs: dict, default_content: str):
        nonlocal changed
        tag = soup.find("meta", attrs=selector_attrs)
        if tag is None:
            tag = soup.new_tag("meta", attrs={**selector_attrs, "content": default_content})
            head.append(tag)
            changed = True

    # canonical
    if soup.find("link", attrs={"rel": "canonical"}) is None:
        link = soup.new_tag("link", attrs={"rel": "canonical", "href": url})
        head.append(link)
        changed = True

    ensure({"property": "og:type"}, "article")
    ensure({"property": "og:site_name"}, PUBLISHER_NAME)
    ensure({"property": "og:title"}, page_title)
    ensure({"property": "og:url"}, url)
    ensure({"name": "twitter:card"}, "summary")
    ensure({"name": "twitter:title"}, page_title)
    return changed


# ──────────────────────────────────────────────────────────────────────────────
# Page-level orchestration
# ──────────────────────────────────────────────────────────────────────────────


def process_page(slug: str, enrichment: dict) -> str:
    topic_dir = TOPICS_DIR / slug
    html_path = topic_dir / "index.html"
    if not html_path.exists():
        return f"skip (no index.html): {slug}"

    data = enrichment.get(slug)
    if not data or "error" in data:
        return f"skip (no enrichment): {slug}"

    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    tldr = data["tldr"]
    meta = data["meta_description"]
    questions = data.get("_questions_on_page", [])
    answers = data.get("faq_answers", {})

    url = f"{SITE_URL}/topics/{slug}/"

    topic = TOPICS_BY_SLUG.get(slug, {})
    upgrade_section_labels_to_h2(soup)
    ensure_tldr_css(soup)
    insert_tldr_block(soup, tldr)
    insert_last_updated(soup, TODAY_ISO)
    update_meta_descriptions(soup, meta)
    ensure_head_metadata(soup, slug, topic.get("name", slug), url)
    upgrade_article_schema(soup, meta, url)
    upgrade_faq_schema(soup, questions, answers)

    # Write back — preserve existing encoding and newline style
    new_html = str(soup)
    if new_html != html:
        html_path.write_text(new_html, encoding="utf-8")
        return f"updated: {slug}"
    return f"unchanged: {slug}"


def main(argv: list[str]):
    if not ENRICHMENT_PATH.exists():
        sys.exit(f"Missing {ENRICHMENT_PATH}. Run generate_aeo_content.py first.")
    enrichment = json.loads(ENRICHMENT_PATH.read_text())

    if len(argv) > 1:
        slugs = argv[1:]
    else:
        slugs = sorted(p.name for p in TOPICS_DIR.iterdir() if p.is_dir())

    for slug in slugs:
        print(process_page(slug, enrichment))


if __name__ == "__main__":
    main(sys.argv)
