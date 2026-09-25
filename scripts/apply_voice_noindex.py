#!/usr/bin/env python3
"""WP-1 — noindex thin /voices/ pages.

Most voice pages are stubs. They stay live and navigable (so internal links keep
flowing to the topic pages) but drop out of the index. A page keeps its index
slot only if it clears ALL of:

    body word count >= --min-words (default 200)
    at least one cc-qf-item  (Quick Facts)
    at least one cc-faq-item (FAQ)

Usage
    python3 scripts/apply_voice_noindex.py --dry-run
    python3 scripts/apply_voice_noindex.py --dry-run --csv wp1-manifest.csv
    python3 scripts/apply_voice_noindex.py --apply
    python3 scripts/apply_voice_noindex.py --revert

Two traps this script exists to avoid, both hit during the August build:

1.  ATTRIBUTE ORDER IS NOT STABLE IN THIS REPO. 931 voice pages carry
    `<link rel="canonical" href="...">` and 262 carry `<link href="..."
    rel="canonical"/>`, because a prettifier alphabetized them. A regex that
    assumes `rel` comes first silently skips a fifth of the site while the run
    still looks successful. The canonical match below uses a lookahead so
    either order works.

2.  THE SENTINEL REGEX MUST CONSUME ITS OWN LEADING INDENTATION. If it does
    not, strip() leaves orphaned spaces behind, every run re-inserts, and
    idempotency breaks quietly. Do not "tidy" whitespace anywhere in the strip
    path either.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import date, timezone, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from curator.slug_guard import is_junk_slug, needs_split  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VOICES_DIR = ROOT / "docs" / "voices"
STATUS_PATH = ROOT / "docs" / "voice_index_status.json"
OVERRIDES_PATH = ROOT / "scripts" / "voice_index_overrides.txt"

SENTINEL = "<!-- CC-NOINDEX-AUTO -->"
ROBOTS_TAG = '<meta name="robots" content="noindex, follow" />'

# Category hub pages built by scripts/build_voice_hubs.py. Always indexed.
HUB_SLUGS = {
    "pastors", "theologians-scholars", "apologists", "bible-teachers",
    "journalists", "ministry-leaders", "writers", "speakers-creators",
}

# Either attribute order. The lookahead is the whole point — see the docstring.
CANONICAL_LINE_RE = re.compile(
    r'(?m)^([ \t]*)(<link\b(?=[^>]*\brel=["\']canonical["\'])[^>]*>)[ \t]*(\r?\n)'
)
# Consumes its own leading indentation and its own newline. See the docstring.
SENTINEL_LINE_RE = re.compile(r'(?m)^[ \t]*' + re.escape(SENTINEL) + r'[^\n]*\r?\n')
ANY_ROBOTS_RE = re.compile(r'<meta\b(?=[^>]*\bname=["\']robots["\'])[^>]*>', re.I)
HEAD_CLOSE_RE = re.compile(r'(?m)^([ \t]*)</head>')

SCRIPT_STYLE_RE = re.compile(r'<(script|style)\b.*?</\1>', re.S | re.I)
COMMENT_RE = re.compile(r'<!--.*?-->', re.S)
MAIN_RE = re.compile(r'<main\b[^>]*>(.*?)</main>', re.S | re.I)
TAG_RE = re.compile(r'<[^>]+>')


def body_word_count(html: str) -> int:
    """Words of visible prose. Head, scripts, styles and comments excluded."""
    text = SCRIPT_STYLE_RE.sub(" ", html)
    text = COMMENT_RE.sub(" ", text)
    m = MAIN_RE.search(text)
    if m:
        text = m.group(1)
    text = TAG_RE.sub(" ", text)
    return len(text.split())


def load_overrides() -> tuple[set[str], set[str]]:
    """`slug` forces keep, `-slug` forces noindex. Blank lines and # ignored."""
    keep, drop = set(), set()
    if not OVERRIDES_PATH.exists():
        return keep, drop
    for line in OVERRIDES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        (drop if line.startswith("-") else keep).add(line.lstrip("-"))
    return keep, drop


def add_tag(html: str) -> tuple[str, str]:
    """Insert the sentinel line. Returns (html, how) — how is 'canonical',
    'head' or 'none'."""
    if SENTINEL in html:
        return html, "already"
    m = CANONICAL_LINE_RE.search(html)
    if m:
        indent = m.group(1)
        insert = f"{indent}{SENTINEL}{ROBOTS_TAG}{m.group(3)}"
        return html[:m.end()] + insert + html[m.end():], "canonical"
    m = HEAD_CLOSE_RE.search(html)
    if m:
        indent = m.group(1)
        insert = f"{indent}  {SENTINEL}{ROBOTS_TAG}\n"
        return html[:m.start()] + insert + html[m.start():], "head"
    return html, "none"


def strip_tag(html: str) -> str:
    return SENTINEL_LINE_RE.sub("", html)


def classify(slug: str, html: str, min_words: int,
             keep_over: set[str], drop_over: set[str]) -> dict:
    words = body_word_count(html)
    qf = html.count("cc-qf-item")
    faq = html.count("cc-faq-item")
    has_sentinel = SENTINEL in html
    other_robots = bool(ANY_ROBOTS_RE.search(strip_tag(html)))

    rec = {
        "slug": slug, "words": words, "quick_facts": qf, "faq_items": faq,
        "has_auto_noindex": has_sentinel,
        "preexisting_noindex": other_robots,
        "junk": is_junk_slug(slug),
        "split_into": "|".join(needs_split(slug)),
    }

    if other_robots:
        rec.update(decision="skip", reason="hand-placed robots tag already on page")
    elif slug in HUB_SLUGS:
        rec.update(decision="keep", reason="category hub")
    elif slug in keep_over:
        rec.update(decision="keep", reason="override: force keep")
    elif slug in drop_over:
        rec.update(decision="noindex", reason="override: force noindex")
    elif rec["junk"]:
        rec.update(decision="noindex", reason="junk byline slug")
    elif words >= min_words and qf > 0 and faq > 0:
        rec.update(decision="keep", reason=f"{words}w + quick facts + faq")
    else:
        missing = []
        if words < min_words:
            missing.append(f"{words}w < {min_words}")
        if qf == 0:
            missing.append("no quick facts")
        if faq == 0:
            missing.append("no faq")
        rec.update(decision="noindex", reason="; ".join(missing))
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    g.add_argument("--apply", action="store_true", help="write the noindex tags")
    g.add_argument("--revert", action="store_true", help="remove every tag this script added")
    ap.add_argument("--min-words", type=int, default=200)
    ap.add_argument("--csv", metavar="PATH", help="write the full per-page manifest")
    args = ap.parse_args()

    if not VOICES_DIR.exists():
        print(f"no such directory: {VOICES_DIR}", file=sys.stderr)
        return 1

    keep_over, drop_over = load_overrides()
    records, changed = [], 0

    for d in sorted(VOICES_DIR.iterdir()):
        idx = d / "index.html"
        if not d.is_dir() or not idx.exists():
            continue
        html = idx.read_text(encoding="utf-8")

        if args.revert:
            new = strip_tag(html)
            if new != html:
                idx.write_text(new, encoding="utf-8")
                changed += 1
            continue

        rec = classify(d.name, html, args.min_words, keep_over, drop_over)
        records.append(rec)

        if args.apply and rec["decision"] == "noindex" and not rec["has_auto_noindex"]:
            new, how = add_tag(html)
            rec["inserted_at"] = how
            if how == "none":
                print(f"  WARN no canonical and no </head>: {d.name}", file=sys.stderr)
            elif new != html:
                idx.write_text(new, encoding="utf-8")
                changed += 1
        elif args.apply and rec["decision"] == "keep" and rec["has_auto_noindex"]:
            idx.write_text(strip_tag(html), encoding="utf-8")   # promoted since last run
            changed += 1

    if args.revert:
        print(f"reverted {changed} pages")
        if STATUS_PATH.exists():
            STATUS_PATH.unlink()
        return 0

    keep = [r["slug"] for r in records if r["decision"] == "keep"]
    drop = [r["slug"] for r in records if r["decision"] == "noindex"]
    skip = [r["slug"] for r in records if r["decision"] == "skip"]

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "min_words": args.min_words,
        "total": len(records),
        "indexed": sorted(keep),
        "noindexed": sorted(drop),
        "skipped": sorted(skip),
    }, indent=2) + "\n", encoding="utf-8")

    if args.csv:
        cols = ["slug", "words", "quick_facts", "faq_items", "decision", "reason",
                "junk", "split_into", "preexisting_noindex", "has_auto_noindex"]
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(records, key=lambda r: (-r["words"], r["slug"])))
        print(f"manifest: {args.csv}")

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[{mode}] {len(records)} voice pages, min-words={args.min_words}")
    print(f"  keep indexed : {len(keep)}")
    print(f"  noindex      : {len(drop)}")
    print(f"  left alone   : {len(skip)}  (hand-placed robots tag)")
    print(f"  junk slugs   : {sum(1 for r in records if r['junk'])}")
    if args.apply:
        print(f"  files written: {changed}")
    print(f"  status file  : {STATUS_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
