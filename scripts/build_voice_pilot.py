#!/usr/bin/env python3
"""build_voice_pilot.py: render the Voices pilot pages and their topic back-links.

Reads data/voices/pilot.json (drafts carry "reviewed": false until Tom signs
off) and, for each writer:
  - writes docs/voices/<slug>/index.html from curator.voice_pilot, with the
    recent pieces from our archive bylines rendered as static HTML in the
    CC-RECENT-ARTICLES block (scripts/build_recent_articles.py refreshes that
    block in place each day);
  - keeps frontend/voices_noindex.json and docs/sitemap-voices.xml in step
    with the page's robots tag (an unreviewed page that is only an auto list
    is noindexed and left out of the sitemap).
Then it writes a "Writers on this topic" CC-TOPIC-VOICES block on each topic
hub a pilot writer returns to, and removes the block from hubs no longer listed.

Run by hand after editing the data file. Idempotent.

    python scripts/build_voice_pilot.py                    # write pages
    python scripts/build_voice_pilot.py --preview-dir DIR  # also copy pages to DIR/<slug>.html
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_recent_articles as recent  # noqa: E402
from curator import voice_pilot as vp  # noqa: E402
from frontend.topics_data import TOPICS  # noqa: E402

DOCS = REPO_ROOT / "docs"
VOICES_DIR = DOCS / "voices"
TOPICS_DIR = DOCS / "topics"
NOINDEX_PATH = REPO_ROOT / "frontend" / "voices_noindex.json"
SITEMAP_VOICES = DOCS / "sitemap-voices.xml"


def topic_names() -> dict[str, str]:
    out = {}
    for t in TOPICS:
        name = t["name"]
        out[t["slug"]] = name[3:] if name.lower().startswith("on ") else name
    return {s: n for s, n in out.items() if (TOPICS_DIR / s / "index.html").exists()}


def voice_names() -> dict[str, str]:
    data = json.loads((DOCS / "voices_data.json").read_text(encoding="utf-8"))
    noindex = set(json.loads(NOINDEX_PATH.read_text(encoding="utf-8"))) if NOINDEX_PATH.exists() else set()
    return {
        v["slug"]: v["name"] for v in data
        if v["slug"] not in noindex and (VOICES_DIR / v["slug"] / "index.html").exists()
    }


def recent_html(entry: dict, by_voice: dict[str, list[dict]]) -> str:
    items = by_voice.get(entry["slug"]) or []
    if not items:
        return ""
    return recent.render_section(
        "From Our Daily Digest", f"Recent Articles by {entry['name']}", items,
        limit=recent.VOICE_MAX_ITEMS,
    )


def sync_noindex(slug: str, noindex: bool) -> bool:
    current = json.loads(NOINDEX_PATH.read_text(encoding="utf-8")) if NOINDEX_PATH.exists() else []
    want = sorted(set(current) | {slug}) if noindex else sorted(set(current) - {slug})
    if want == sorted(current):
        return False
    NOINDEX_PATH.write_text(json.dumps(want, indent=2) + "\n", encoding="utf-8")
    return True


def drop_from_sitemap(slug: str) -> bool:
    if not SITEMAP_VOICES.exists():
        return False
    xml = SITEMAP_VOICES.read_text(encoding="utf-8")
    out = re.sub(
        r"[ \t]*<url>\s*<loc>[^<]*/voices/" + re.escape(slug) + r"/</loc>.*?</url>\n?",
        "", xml, flags=re.DOTALL,
    )
    if out == xml:
        return False
    SITEMAP_VOICES.write_text(out, encoding="utf-8")
    return True


def update_topic_hubs(writers: list[dict], names: dict[str, str]) -> list[str]:
    mapping = {s: pairs for s, pairs in vp.topic_voice_map(writers).items() if s in names}
    changed = []
    for page in sorted(TOPICS_DIR.glob("*/index.html")):
        slug = page.parent.name
        html = page.read_text(encoding="utf-8")
        if slug not in mapping and vp.TOPIC_START not in html:
            continue
        block = vp.render_topic_voices_block(mapping[slug]) if slug in mapping else ""
        out = vp.inject_topic_voices(html, block)
        if out is None:
            print(f"  ! {slug}: no AEO-RELATED-TOPICS anchor, back-link not added")
            continue
        if out != html:
            page.write_text(out, encoding="utf-8")
            changed.append(slug)
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--preview-dir", type=Path, help="also write each page to DIR/<slug>.html")
    args = ap.parse_args(argv)

    pilot = vp.load_pilot()
    last_updated = pilot.get("last_updated", "")
    writers = pilot["writers"]
    tnames, vnames = topic_names(), voice_names()
    by_voice = recent.collect_by_voice()

    for entry in writers:
        slug = entry["slug"]
        html = vp.render_pilot_page(
            entry, recent_html=recent_html(entry, by_voice), voice_names=vnames,
            topic_names=tnames, last_updated=entry.get("last_updated") or last_updated,
        )
        path = VOICES_DIR / slug / "index.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        noindex = vp.needs_noindex(entry)
        sync_noindex(slug, noindex)
        if noindex:
            drop_from_sitemap(slug)
        if args.preview_dir:
            args.preview_dir.mkdir(parents=True, exist_ok=True)
            (args.preview_dir / f"{slug}.html").write_text(html, encoding="utf-8")
        status = "noindex" if noindex else "index"
        print(f"  /voices/{slug}/  {status}  reviewed={bool(entry.get('reviewed'))}")

    changed = update_topic_hubs(writers, tnames)
    print(f"topic hubs with voice back-links updated: {len(changed)} {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
