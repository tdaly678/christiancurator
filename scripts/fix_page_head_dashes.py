#!/usr/bin/env python3
"""Remove the template-produced em dashes from archive and daily page heads.

The archive, digest and daily templates used to write "Christian Curator —
Daily Digest, <date>", "<date> — Christian Curator Daily Pulse" and similar
strings into <title>, meta tags and JSON-LD. The templates now use " | ".
This script rewrites only those exact template strings in pages already
published, so their heads match a fresh render. It never touches Pulse text
written by the model (descriptions, paragraphs, previews).

Only the <head> is edited, plus the archive footer line the template wrote.
Idempotent. Dry run by default; --apply writes.

    python scripts/fix_page_head_dashes.py            # count changes
    python scripts/fix_page_head_dashes.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

DATE = r"((?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4})"

HEAD_RULES = [
    # archive and digest
    (re.compile(r"Christian Curator — Daily Digest, " + DATE), r"Daily Digest, \1 | Christian Curator"),
    (re.compile(r"curated for " + DATE + r" — theology, culture"), r"curated for \1: theology, culture"),
    (re.compile(r"church life, and world news — from The Gospel Coalition"),
     "church life, and world news, from The Gospel Coalition"),
    (re.compile(r"Christian Curator — " + DATE), r"\1 | Christian Curator"),
    # daily
    (re.compile(DATE + r" — Christian Curator Daily Pulse"), r"\1 | Christian Curator Daily Pulse"),
    (re.compile(DATE + r" — What the Christian World Is Talking About"),
     r"\1 | What the Christian World Is Talking About"),
]

BODY_RULES = [
    ('<a href="/">Christian Curator</a> &mdash; Curated perspectives, updated daily.',
     '<a href="/">Christian Curator</a> &middot; Curated perspectives, updated daily.'),
]


def fix_html(html: str) -> str:
    end = html.find("</head>")
    if end < 0:
        return html
    head, rest = html[:end], html[end:]
    for pattern, repl in HEAD_RULES:
        head = pattern.sub(repl, head)
    for old, new in BODY_RULES:
        rest = rest.replace(old, new)
    return head + rest


def pages() -> list[Path]:
    out = []
    for sub in ("archive", "daily"):
        out += sorted((DOCS / sub).glob("*/index.html"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    changed = 0
    for path in pages():
        html = path.read_text(encoding="utf-8")
        new = fix_html(html)
        if new != html:
            changed += 1
            if args.apply:
                path.write_text(new, encoding="utf-8")
    verb = "Rewrote" if args.apply else "Would rewrite"
    print(f"{verb} {changed} page(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
