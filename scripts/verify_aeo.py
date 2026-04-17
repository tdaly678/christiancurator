"""
verify_aeo.py — Sanity checks the AEO upgrades.

Checks every topic page for:
  * 1 <h1> + at least 4 <h2> tags
  * <meta name="description"> present and non-empty
  * One Article JSON-LD with author, datePublished, dateModified
  * One FAQPage JSON-LD with >= 1 mainEntity
  * TL;DR block present
  * 'Last updated:' line present
  * All JSON-LD blocks parse as valid JSON

Also renders digest_template.html against minimal mock data to confirm
the new Article schema block parses as valid JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"
FRONTEND_DIR = REPO_ROOT / "frontend"


def check_page(slug: str) -> list[str]:
    """Return list of problems found (empty list = pass)."""
    problems = []
    html_path = TOPICS_DIR / slug / "index.html"
    if not html_path.exists():
        return ["no index.html"]

    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    h1s = soup.find_all("h1")
    h2s = soup.find_all("h2")
    if len(h1s) != 1:
        problems.append(f"expected 1 <h1>, found {len(h1s)}")
    if len(h2s) < 4:
        problems.append(f"expected >= 4 <h2>, found {len(h2s)}")

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc or not meta_desc.get("content", "").strip():
        problems.append("missing/empty meta description")

    tldr = soup.select_one(".cc-tldr")
    if tldr is None:
        problems.append("missing TL;DR block")

    last_updated = soup.select_one(".cc-last-updated")
    if last_updated is None:
        problems.append("missing last-updated line")

    jsonld_scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    article_found = False
    faq_found = False
    for s in jsonld_scripts:
        body = (s.string or "").strip()
        # Strip leading marker comment if present
        if body.startswith("/*"):
            body = body.split("*/", 1)[1].strip()
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            problems.append(f"JSON-LD did not parse: {e}")
            continue
        if isinstance(data, dict):
            t = data.get("@type")
            if t == "Article":
                article_found = True
                for key in ("author", "datePublished", "dateModified"):
                    if key not in data:
                        problems.append(f"Article schema missing {key}")
            elif t == "FAQPage":
                faq_found = True
                entities = data.get("mainEntity", [])
                if not entities:
                    problems.append("FAQPage has no questions")

    if not article_found:
        problems.append("no Article schema")
    if not faq_found:
        problems.append("no FAQPage schema")

    return problems


def check_digest_template() -> list[str]:
    problems = []
    env = Environment(loader=FileSystemLoader(str(FRONTEND_DIR)))
    try:
        tpl = env.get_template("digest_template.html")
    except Exception as e:
        return [f"digest template failed to load: {e}"]

    # Minimal mock context sufficient to render just enough to validate schema
    mock_ctx = {
        "articles": [],
        "yesterday_articles": [],
        "world_news_articles": [],
        "date": "April 17, 2026",
        "iso_date": "2026-04-17",
        "featured_topics": [],
        "topics_by_category": {},
        "categories": [],
        "archive_dates": [],
        "voices_by_name": {},
    }
    try:
        html = tpl.render(**mock_ctx)
    except Exception as e:
        return [f"digest render failed: {e}"]

    soup = BeautifulSoup(html, "html.parser")
    jsonld_scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    article_found = False
    for s in jsonld_scripts:
        body = (s.string or "").strip()
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            problems.append(f"digest JSON-LD invalid: {e}")
            continue
        if isinstance(data, dict) and data.get("@type") == "Article":
            article_found = True
            for key in ("author", "datePublished", "dateModified", "headline"):
                if key not in data:
                    problems.append(f"digest Article schema missing {key}")
    if not article_found:
        problems.append("digest template has no Article schema")
    return problems


def main():
    print("== Daily Digest template ==")
    digest_problems = check_digest_template()
    if digest_problems:
        for p in digest_problems:
            print(f"  FAIL: {p}")
    else:
        print("  OK")

    print("\n== Topic pages ==")
    slugs = sorted(p.name for p in TOPICS_DIR.iterdir() if p.is_dir())
    total = 0
    failing = 0
    all_problems = {}
    for slug in slugs:
        problems = check_page(slug)
        total += 1
        if problems and problems != ["no index.html"]:
            failing += 1
            all_problems[slug] = problems

    print(f"  Checked {total} topic pages, {failing} with problems.")
    for slug, problems in sorted(all_problems.items()):
        print(f"  {slug}:")
        for p in problems:
            print(f"    - {p}")

    exit_code = 0 if not failing and not digest_problems else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
