#!/usr/bin/env python3
"""WP-1 — remove junk byline pages from /voices/.

Deletes the page directory, unlinks every reference to it across docs/, and
drops its record from docs/voices_data.json.

Two-person mashups of REAL people (curator.slug_guard.SPLIT_NOT_DELETE) are
reported and left alone. They need splitting into separate pages, which is
editorial work, not a delete.

    python3 scripts/prune_junk_voices.py --dry-run
    python3 scripts/prune_junk_voices.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from curator.slug_guard import is_junk_slug, needs_split, SPLIT_NOT_DELETE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
VOICES_DIR = DOCS / "voices"
VOICES_DATA = DOCS / "voices_data.json"


def unlink_refs(slug: str, apply: bool) -> int:
    """Replace <a href="/voices/<slug>/">Label</a> with the bare label."""
    anchor = re.compile(
        r'<a\b[^>]*href=["\']/voices/' + re.escape(slug) + r'/["\'][^>]*>(.*?)</a>',
        re.S | re.I,
    )
    touched = 0
    for path in DOCS.rglob("*.html"):
        try:
            html = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if f"/voices/{slug}/" not in html:
            continue
        new = anchor.sub(lambda m: m.group(1), html)
        if new != html:
            touched += 1
            if apply:
                path.write_text(new, encoding="utf-8")
    return touched


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    apply = args.apply

    present = sorted(d.name for d in VOICES_DIR.iterdir()
                     if d.is_dir() and (d / "index.html").exists())
    junk = [s for s in present if is_junk_slug(s)]
    splits = [s for s in present if needs_split(s)]

    print(f"{'APPLY' if apply else 'DRY RUN'} — {len(present)} voice pages scanned\n")
    print(f"To delete ({len(junk)}):")
    for s in junk:
        refs = unlink_refs(s, apply)
        if apply:
            shutil.rmtree(VOICES_DIR / s, ignore_errors=True)
        print(f"  {s:56} refs in {refs} file(s)")

    if splits:
        print(f"\nLEFT ALONE — split these by hand, do not delete ({len(splits)}):")
        for s in splits:
            print(f"  {s}  ->  {', '.join(SPLIT_NOT_DELETE[s])}")

    if VOICES_DATA.exists():
        data = json.loads(VOICES_DATA.read_text(encoding="utf-8"))
        kept = [v for v in data if v.get("slug") not in set(junk)]
        removed = len(data) - len(kept)
        print(f"\nvoices_data.json: {len(data)} -> {len(kept)} ({removed} removed)")
        if apply and removed:
            VOICES_DATA.write_text(json.dumps(kept, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")

    stray = [s for s in present if s not in junk and s not in splits
             and re.search(r'-and-[a-z]', s) and s.count('-') >= 4]
    if stray:
        print(f"\nWARNING — long ' and ' slugs the guard did NOT match. Eyeball these:")
        for s in stray[:20]:
            print(f"  {s}")

    if not apply:
        print("\nNothing was changed. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
