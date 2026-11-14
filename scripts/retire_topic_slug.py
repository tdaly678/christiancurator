#!/usr/bin/env python3
"""retire_topic_slug.py: fold a topic page into another and keep the old URL working.

For every retired slug in frontend/topics_redirects.json ({old: {"to": new, "name": ...}}):

1. Rewrites internal links site-wide (docs/**/*.html, the Jinja templates and
   frontend/__init__.py): href="/topics/<old>/" (also with the full site URL)
   becomes href="/topics/<new>/", and the anchor text, when it is the old
   topic name, becomes the new topic name from frontend/topics_data.py. The
   homepage's gtag topic_click label moves too. Nothing else on a page changes.
2. Writes docs/topics/<old>/index.html as a redirect stub, the same pattern as
   merged voice pages: meta refresh to the new page, canonical to the new
   page, robots noindex, follow. GitHub Pages cannot send a real 301.

The sitemap, the /topics/ hub, the quality gate and the topic builders skip
retired slugs (frontend/topic_redirects.py), and build_recent_articles.py
moves data-watch Fresh stories filed under the old slug to the new page.

Usage:
  python scripts/retire_topic_slug.py            # dry run: counts only
  python scripts/retire_topic_slug.py --apply    # write
Idempotent: a second --apply changes nothing.
Tests: tests/test_ai_topic_page.py
"""
from __future__ import annotations

import argparse
import html as html_mod
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from frontend.topic_redirects import SITE, load_topic_redirects, render_stub  # noqa: E402

DOCS = REPO_ROOT / "docs"
CODE_FILES = [
    REPO_ROOT / "frontend" / name
    for name in ("template.html", "digest_template.html", "archive_template.html",
                 "daily_template.html", "__init__.py")
]


def topic_names() -> dict[str, str]:
    from frontend.topics_data import TOPICS
    return {t["slug"]: t["name"] for t in TOPICS}


def rewrite_links(text: str, old: str, new: str, old_name: str, new_name: str) -> str:
    """Point every link at /topics/<old>/ to /topics/<new>/ and rename its text."""
    href = re.compile(r'href="(' + re.escape(SITE) + r')?/topics/' + re.escape(old) + r'/"')
    if not href.search(text) and f"'topic':'{old}'" not in text:
        return text
    escaped_old = html_mod.escape(old_name, quote=False)

    def fix_anchor(m: re.Match) -> str:
        tag, body = m.group(1), m.group(2)
        tag = href.sub(lambda h: f'href="{h.group(1) or ""}/topics/{new}/"', tag)
        tag = tag.replace(f"'topic':'{old}'", f"'topic':'{new}'")
        stripped = body.strip()
        if old_name and stripped == old_name:
            body = body.replace(stripped, new_name)
        elif old_name and stripped == escaped_old:
            body = body.replace(stripped, html_mod.escape(new_name, quote=False))
        return tag + body

    anchor = re.compile(r'(<a\b[^>]*?href="(?:' + re.escape(SITE) + r')?/topics/'
                        + re.escape(old) + r'/"[^>]*>)([^<]*)', re.S)
    text = anchor.sub(fix_anchor, text)
    # hrefs outside an <a> (link rel, JSON, Python strings) and leftover labels
    text = href.sub(lambda h: f'href="{h.group(1) or ""}/topics/{new}/"', text)
    return text.replace(f"'topic':'{old}'", f"'topic':'{new}'")


def targets(skip: set[Path]) -> list[Path]:
    files = [p for p in DOCS.rglob("*.html") if p not in skip]
    return sorted(files) + [p for p in CODE_FILES if p.exists()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    args = ap.parse_args(argv)

    redirects = load_topic_redirects()
    names = topic_names()
    stubs = {DOCS / "topics" / old / "index.html" for old in redirects}
    total = 0
    for old, rec in redirects.items():
        new = rec["to"]
        if new not in names:
            print(f"! {old}: target {new} is not in topics_data.py")
            return 1
        if not (DOCS / "topics" / new / "index.html").exists():
            print(f"! {old}: /topics/{new}/ does not exist yet")
            return 1
        changed = 0
        for path in targets(stubs):
            text = path.read_text(encoding="utf-8")
            out = rewrite_links(text, old, new, rec.get("name", ""), names[new])
            if out != text:
                changed += 1
                if args.apply:
                    path.write_text(out, encoding="utf-8")
        stub_path = DOCS / "topics" / old / "index.html"
        stub = render_stub(old, new, rec.get("name", old), names[new])
        stub_changed = not stub_path.exists() or stub_path.read_text(encoding="utf-8") != stub
        if stub_changed and args.apply:
            stub_path.parent.mkdir(parents=True, exist_ok=True)
            stub_path.write_text(stub, encoding="utf-8")
        print(f"{old} -> {new}: {changed} file(s) with links to rewrite; "
              f"stub {'written' if stub_changed and args.apply else 'needs writing' if stub_changed else 'current'}")
        total += changed + int(stub_changed)
    if not args.apply:
        print("dry run: nothing written (use --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
