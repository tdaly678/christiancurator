#!/usr/bin/env python3
"""Backfill docs/voices_data.json with any voice pages present on disk but missing
from the JSON. Without this, those pages render correctly but are not linked from
/voices/ index, leaving them orphaned for crawlers.

Reads each orphan page's <title> and <meta name="description"> as the bio source.
Adds a minimal entry; downstream pipeline will enrich on its next pass.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
VOICES_DIR = DOCS_DIR / "voices"
VOICES_DATA_PATH = DOCS_DIR / "voices_data.json"


def parse_meta(html: str, attr: str, name_value: str) -> str:
    m = re.search(
        rf'<meta\s+{attr}="{re.escape(name_value)}"\s+content="([^"]*)"',
        html, re.IGNORECASE,
    )
    return m.group(1) if m else ""


def parse_title_name(html: str) -> str:
    m = re.search(r"<title>([^<]+)</title>", html)
    if not m:
        return ""
    title = m.group(1)
    return title.split(" — ")[0].strip()


def initials(name: str) -> str:
    parts = [p for p in name.split() if p and p[0].isalpha()]
    if not parts:
        return name[:2].upper()
    return "".join(p[0].upper() for p in parts[:3]) or name[:2].upper()


def main() -> int:
    if not VOICES_DATA_PATH.exists():
        print("voices_data.json missing", file=sys.stderr)
        return 1

    data = json.loads(VOICES_DATA_PATH.read_text(encoding="utf-8"))
    known_slugs = {v["slug"] for v in data}

    on_disk = sorted(
        d.name for d in VOICES_DIR.iterdir()
        if d.is_dir() and (d / "index.html").exists()
    )
    orphans = [s for s in on_disk if s not in known_slugs]

    if not orphans:
        print("backfill: no orphan voice pages — nothing to do")
        return 0

    added = 0
    for slug in orphans:
        html = (VOICES_DIR / slug / "index.html").read_text(encoding="utf-8")
        name = parse_title_name(html) or slug.replace("-", " ").title()
        bio = parse_meta(html, "name", "description")
        entry = {
            "name": name,
            "slug": slug,
            "bio": bio,
            "affiliation": "",
            "role": "Contributor",
            "education": "",
            "website": "",
            "books": [],
            "initials": initials(name),
        }
        data.append(entry)
        added += 1
        print(f"  + {slug}  ({name})")

    VOICES_DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"backfill: added {added} voice(s) to voices_data.json (now {len(data)} total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
