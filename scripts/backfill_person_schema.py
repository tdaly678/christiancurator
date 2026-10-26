#!/usr/bin/env python3
"""Add Person JSON-LD to voice pages that lack it.

Uses curator.voice_generator.render_jsonld() — the same function new voice
pages are rendered with — but injects only the schema block before </head>
instead of re-rendering the page. A full re-render would drop hand-curated
book lists and affiliation sections (54 pages) and the hub-category
breadcrumb that later scripts add, so the page body is left untouched.

Idempotent: pages that already carry the CC-PERSON-SCHEMA marker or any
Person JSON-LD are skipped. Category hubs and denylisted junk slugs
(curator/voice_filters.py) are skipped too.

Usage:
    python scripts/backfill_person_schema.py            # apply
    python scripts/backfill_person_schema.py --dry-run  # counts only
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from curator.voice_filters import HUB_SLUGS, junk_reason  # noqa: E402
from curator.voice_generator import FAQ_MARKER, PERSON_MARKER, render_jsonld  # noqa: E402

VOICES_DIR = REPO_ROOT / "docs" / "voices"
DATA = REPO_ROOT / "docs" / "voices_data.json"
LD_RE = re.compile(r'<script\b[^>]*\btype="application/ld\+json"[^>]*>(.*?)</script>', re.S)


def ld_types(html: str) -> set[str]:
    """@types of every JSON-LD block. Raises ValueError on a block that won't parse."""
    types = set()
    for blk in LD_RE.findall(html):
        data = json.loads(blk.replace("/* AEO-FAQPAGE-SCHEMA */", ""))
        items = data if isinstance(data, list) else data.get("@graph", [data])
        types.update(x.get("@type") for x in items if isinstance(x, dict))
    return types


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    authors = {a["slug"]: a for a in json.loads(DATA.read_text(encoding="utf-8"))}
    counts = {"already": 0, "added": 0, "skipped_junk": 0, "skipped_no_data": 0}
    for d in sorted(VOICES_DIR.iterdir()):
        page = d / "index.html"
        if not d.is_dir() or not page.exists() or d.name in HUB_SLUGS:
            continue
        html = page.read_text(encoding="utf-8")
        if PERSON_MARKER in html or "Person" in ld_types(html):
            counts["already"] += 1
            continue
        if junk_reason(d.name):
            counts["skipped_junk"] += 1
            continue
        author = authors.get(d.name)
        if not author:
            counts["skipped_no_data"] += 1
            continue
        if FAQ_MARKER in html:
            author = {**author, "faqs": []}  # page already has its FAQPage block
        block = render_jsonld(author)
        idx = html.find("</head>")
        if idx == -1:
            counts["skipped_no_data"] += 1
            continue
        new = html[:idx].rstrip("\n") + block + "\n" + html[idx:]
        assert "Person" in ld_types(new)
        counts["added"] += 1
        if not dry:
            page.write_text(new, encoding="utf-8")
    print(("DRY RUN " if dry else "") + "  ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
