#!/usr/bin/env python3
"""Write a markdown review list of voice pages that look like junk.

Read-only: nothing is deleted. The output is for Tom to approve before any
voice page is removed (removal must also drop the slug from voices_data.json
and sitemap-voices.xml).

Usage:
    python scripts/report_junk_voices.py .christian-orchestrator/junk-voices-review.md
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from curator.voice_filters import HUB_SLUGS, junk_reason  # noqa: E402

VOICES_DIR = REPO_ROOT / "docs" / "voices"
DATA = REPO_ROOT / "docs" / "voices_data.json"

SECULAR = re.compile(r"https?://(?:www\.)?(nytimes\.com|theguardian\.com|bbc\.(?:co\.uk|com)|apnews\.com|"
                     r"wsj\.com|washingtonpost\.com|reuters\.com)/")
ARTICLE_LINK = re.compile(r'href="(https?://[^"]+)"')
OWN_OR_NOISE = re.compile(r"christiancurator\.com|fonts\.g|googletagmanager|amazon\.com|schema\.org|"
                          r"twitter\.com|x\.com|facebook\.com|wikipedia\.org")


def outbound(html: str) -> list[str]:
    return [u for u in ARTICLE_LINK.findall(html) if not OWN_OR_NOISE.search(u)]


def dedupe_key(slug: str) -> str:
    """Drop single-letter middle initials and honorifics: brian-g-najapfour -> brian-najapfour."""
    tokens = [t for t in slug.split("-") if len(t) > 1]
    if tokens and tokens[0] in {"dr", "rev", "pastor", "prof"}:
        tokens = tokens[1:]
    return "-".join(tokens)


def main(out_path: str) -> int:
    slugs = sorted(d.name for d in VOICES_DIR.iterdir()
                   if d.is_dir() and (d / "index.html").exists() and d.name not in HUB_SLUGS)
    names = {v["slug"]: v["name"] for v in json.loads(DATA.read_text(encoding="utf-8"))}

    flagged: dict[str, list[str]] = defaultdict(list)
    flagged_set = set()
    for s in slugs:
        r = junk_reason(s)
        if r:
            flagged[r.split(" (")[0]].append(s)
            flagged_set.add(s)

    secular = []
    for s in slugs:
        if s in flagged_set:
            continue
        links = outbound((VOICES_DIR / s / "index.html").read_text(encoding="utf-8"))
        hits = [u for u in links if SECULAR.match(u)]
        if hits and len(hits) == len(links):
            secular.append((s, SECULAR.match(hits[0]).group(1), len(hits)))

    groups = defaultdict(list)
    for s in slugs:
        groups[dedupe_key(s)].append(s)
    dupes = [sorted(v, key=len) for v in groups.values() if len(v) > 1]

    total = sum(map(len, flagged.values()))
    lines = [
        f"# Junk voice pages — proposed for deletion ({date.today().isoformat()})",
        "",
        "**Status: awaiting Tom's approval. Nothing has been deleted.**",
        "",
        f"Scanned {len(slugs)} person pages under `docs/voices/` (the 8 category hubs are excluded).",
        "",
        "Deleting a page also requires removing its entry from `docs/voices_data.json`; the sitemap",
        "and `/voices/` hubs rebuild from those on the next daily run. Consider a 301-style redirect",
        "stub (or a link to the surviving page) for the duplicate pairs rather than a hard 404.",
        "",
        "New pages matching sections A are now blocked at creation time by",
        "`curator/voice_filters.py` (wired into `curator/voice_generator.py` and",
        "`scripts/backfill_voices_data.py`).",
        "",
        f"## A. High confidence — denylist matches ({total})",
        "",
    ]
    for reason, items in sorted(flagged.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"### {reason} ({len(items)})")
        lines.append("")
        for s in items:
            lines.append(f"- [ ] `{s}` — {names.get(s, '(not in voices_data)')}")
        lines.append("")

    lines += [
        f"## B. Probable secular journalists ({len(secular)})",
        "",
        "Every outbound article link on the page points at a mainstream outlet. These predate the",
        "2026-07-14 `world_news` skip. Medium confidence — spot-check a few before approving.",
        "",
    ]
    for s, dom, n in secular:
        lines.append(f"- [ ] `{s}` — {names.get(s, '')} ({n} link(s), {dom})")
    lines.append("")

    lines += [
        f"## C. Likely duplicates ({len(dupes)} groups)",
        "",
        "Slugs that collapse to the same name once middle initials/honorifics are removed. Lower",
        "confidence: confirm it is the same person first (e.g. `michael-brown` vs `michael-g-brown`",
        "may be two people), then keep whichever page has the better bio and inbound links — the",
        "shorter slug is listed first only for convenience. Merge unique bio content into the survivor.",
        "",
    ]
    for g in dupes:
        lines.append(f"- [ ] {' / '.join(f'`{x}`' for x in g)}")
    lines.append("")

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"A={total}  B={len(secular)}  C={len(dupes)} groups  -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "junk-voices-review.md"))
