#!/usr/bin/env python3
"""fix_voice_titles.py: one-off pass that takes em dashes out of Voices titles.

Voice profile pages were titled "Name — Voices — Christian Curator". The Voices
pilot (Nov 2026) changes that to the pronoun-free, dash-free form from
curator.voice_generator.voice_page_title():

    Name: Articles, Bio, and Where They Write | Christian Curator

Per page it rewrites <title> and og:title. Merged-duplicate stubs (meta refresh
to the survivor) become "Name | Christian Curator". It also collapses runs of
blank lines left behind by the old recent-articles injector, and fixes the
/voices/ index title, description and count line. Category hubs are rebuilt by
scripts/build_voice_hubs.py and are skipped here. Voices pilot pages
(data-cc-voice-pilot) own their titles via curator.voice_pilot.page_title(), so
their titles are left alone: rewrapping "Where to Start with X: Articles and Bio"
doubled the suffix on /voices/david-powlison/ (Nov 12 2026).

Idempotent. Default is a dry run; pass --apply to write.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curator.voice_generator import voice_page_title  # noqa: E402

VOICES_DIR = REPO_ROOT / "docs" / "voices"
HUBS = {"apologists", "bible-teachers", "journalists", "ministry-leaders", "pastors",
        "speakers-creators", "theologians-scholars", "writers"}

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
# Either attribute order: older pages were written by BeautifulSoup as
# <meta content="..." property="og:title"/>.
OG_TITLE_RE = re.compile(
    r'<meta property="og:title" content="[^"]*" />|<meta content="[^"]*" property="og:title"\s*/>'
)
SUFFIX_RE = re.compile(
    r"\s*(?:—\s*Voices\s*—|:\s*Articles, Bio, and Where They Write\s*\||—|\|)\s*Christian Curator\s*$"
)
PILOT_MARK = "data-cc-voice-pilot="
BLANK_RUN_RE = re.compile(r"\n(?:[ \t]*\n){2,}")


def page_name(html: str) -> str | None:
    m = TITLE_RE.search(html)
    if not m:
        return None
    name = SUFFIX_RE.sub("", m.group(1).strip()).strip()
    return name or None


def fix_page(html: str) -> str:
    name = None if PILOT_MARK in html else page_name(html)
    if name:
        is_stub = 'http-equiv="refresh"' in html
        title = f"{name} | Christian Curator" if is_stub else voice_page_title(name)
        html = TITLE_RE.sub(lambda _: f"<title>{title}</title>", html, count=1)
        html = OG_TITLE_RE.sub(lambda _: f'<meta property="og:title" content="{title}" />', html, count=1)
    return BLANK_RUN_RE.sub("\n\n", html)


def fix_index(html: str) -> str:
    html = html.replace("<title>Voices — Christian Curator</title>", "<title>Voices | Christian Curator</title>")
    html = html.replace('content="Voices — Christian Curator"', 'content="Voices | Christian Curator"')
    html = html.replace("curate most often — the voices shaping", "curate most often: the voices shaping")
    return re.sub(r"curate most often — (\d+) voices worth following\.",
                  r"curate most often: \1 voices worth following.", html)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args(argv)

    changed = 0
    targets = [(VOICES_DIR / "index.html", fix_index)]
    for d in sorted(VOICES_DIR.iterdir()):
        if d.is_dir() and d.name not in HUBS and (d / "index.html").exists():
            targets.append((d / "index.html", fix_page))
    for path, fn in targets:
        html = path.read_text(encoding="utf-8")
        out = fn(html)
        if out != html:
            changed += 1
            if args.apply:
                path.write_text(out, encoding="utf-8")
    verb = "updated" if args.apply else "would update"
    print(f"fix_voice_titles: {verb} {changed} of {len(targets)} pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
