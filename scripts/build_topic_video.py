#!/usr/bin/env python3
"""build_topic_video.py: compact expandable video strip on a topic page.

For a topic page that has data/topic_video/<slug>.json, writes, idempotently,
one block between <!-- CC-TOPIC-VIDEO:START --> and <!-- CC-TOPIC-VIDEO:END -->:

1. Its own small <style> (the shared docs/assets/topic.css is left alone so its
   hash, and every other page, stays put).
2. <section class="cc-video" id="video">: a compact strip (a <button> with
   aria-expanded) showing a self-hosted WebP thumbnail with a play mark, a
   "Video overview" kicker with the length, the headline, the narrator line and
   a quiet "Watch" pill. Clicking it swaps the strip for a fixed 16:9 player.
   The youtube-nocookie iframe is created only on that click, so the page makes
   no YouTube request before the reader asks for the video. Under the player a
   one-row bar shows the narrator line, "Watch on YouTube" (data-pos
   "topic-video", tracked by topic.js like every topic link) and "Hide video",
   which removes the iframe (stopping playback) and brings the strip back.
   A GA4 "video_play" event {topic, video_id} fires on the click when gtag exists.
3. A VideoObject JSON-LD (<script ... data-cc-marker="CC-VIDEO-SCHEMA">): name,
   description, thumbnailUrl (absolute), uploadDate, duration, embedUrl and the
   publisher. No contentUrl: Google keeps that for direct media files.

First insert goes right before <section class="cc-editorial"> (after the TL;DR
and the CC-TOPIC-TOP jump nav); later runs replace the block in place.

Schema of data/topic_video/<slug>.json:

{
  "slug": "eschatology",
  "video": {
    "youtube_id": "L3IzTHCC_mo",
    "name": "Title as published on YouTube (iframe title, schema name)",
    "headline": "Short headline shown on the strip",
    "description": "Plain summary for the schema",
    "narrator": "Narrated by Tom Daly, editor of Christian Curator",
    "duration_seconds": 202,
    "duration_iso": "PT3M22S",
    "duration_label": "3 MIN",
    "upload_date": "2026-11-19",
    "thumbnail_path": "/assets/video-eschatology-thumb.webp"   # under docs/
  },
  "notes": "editor notes; never rendered"
}

Rules (validate()): no em or en dashes, no hashtags, never the word "Pastor";
the YouTube id is 11 safe characters; duration_iso matches duration_seconds;
the thumbnail file exists under docs/; upload_date is an ISO date.

Usage:
  python scripts/build_topic_video.py                 # every slug with a data file
  python scripts/build_topic_video.py --slug eschatology
  python scripts/build_topic_video.py --check         # validate, and fail on a stale page
  python scripts/build_topic_video.py --dry-run       # report, write nothing
Tests: tests/test_build_topic_video.py
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "topic_video"
DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"
SITE = "https://www.christiancurator.com"

START = "<!-- CC-TOPIC-VIDEO:START -->"
END = "<!-- CC-TOPIC-VIDEO:END -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
ANCHOR = '<section class="cc-editorial"'

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
ISO_DUR_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")
REQUIRED = ("youtube_id", "name", "headline", "description", "narrator",
            "duration_seconds", "duration_iso", "duration_label", "upload_date",
            "thumbnail_path")

CSS = """
.cc-video { margin: 0 0 2rem; }
.cc-video-strip { display: flex; align-items: center; gap: 14px; width: 100%; margin: 0; padding: 10px 14px 10px 10px;
  background: #f4f1ea; border: 1px solid #e0ddd8; border-radius: 4px; cursor: pointer; text-align: left;
  font: inherit; color: #1a1a1a; transition: border-color .15s ease, background-color .15s ease; }
.cc-video-strip:hover { border-color: #b9c4b3; background: #f0ede4; }
.cc-video-strip:focus-visible { outline: 2px solid #2C4A2E; outline-offset: 2px; }
.cc-video-thumb { position: relative; flex: 0 0 144px; width: 144px; aspect-ratio: 16 / 9; border-radius: 3px; overflow: hidden; background: #2C4A2E; }
.cc-video-thumb img { display: block; width: 100%; height: 100%; object-fit: cover; }
.cc-video-play { position: absolute; left: 50%; top: 50%; width: 34px; height: 34px; margin: -17px 0 0 -17px; border-radius: 50%;
  background: rgba(26, 26, 26, .62); box-shadow: 0 0 0 1px rgba(255, 255, 255, .35); }
.cc-video-play::after { content: ""; position: absolute; left: 13px; top: 10px; border-style: solid; border-width: 7px 0 7px 11px;
  border-color: transparent transparent transparent #fff; }
.cc-video-text { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.cc-video-kicker { font-family: 'Source Sans 3', sans-serif; font-size: 10.5px; font-weight: 600; letter-spacing: .14em;
  text-transform: uppercase; color: #2C4A2E; }
.cc-video-title { font-family: 'Lora', Georgia, serif; font-size: 16.5px; font-weight: 600; line-height: 1.3; color: #1a1a1a; }
.cc-video-credit { font-family: 'Source Sans 3', sans-serif; font-size: 12.5px; color: #6b6b6b; }
.cc-video-cta { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 6px; padding: 6px 13px; border: 1px solid #2C4A2E;
  border-radius: 999px; font-family: 'Source Sans 3', sans-serif; font-size: 13px; font-weight: 600; color: #2C4A2E; background: transparent; }
.cc-video-strip:hover .cc-video-cta { background: #2C4A2E; color: #faf9f7; }
.cc-video-cta svg { width: 9px; height: 10px; fill: currentColor; }
.cc-video-strip[hidden], .cc-video-player[hidden] { display: none; }
.cc-video-frame { position: relative; width: 100%; aspect-ratio: 16 / 9; background: #1a1a1a; border-radius: 4px 4px 0 0; overflow: hidden; }
.cc-video-frame iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
.cc-video-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px;
  background: #f4f1ea; border: 1px solid #e0ddd8; border-top: 0; border-radius: 0 0 4px 4px;
  font-family: 'Source Sans 3', sans-serif; font-size: 12.5px; color: #6b6b6b; }
.cc-video-links { display: inline-flex; align-items: center; gap: 14px; white-space: nowrap; }
.cc-video-links a { color: #2C4A2E; text-decoration: underline; text-underline-offset: 2px; }
.cc-video-hide { padding: 0; border: 0; background: none; font: inherit; color: #6b6b6b; cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
.cc-video-hide:hover { color: #1a1a1a; }
@media (max-width: 560px) {
  .cc-video-strip { gap: 11px; padding: 8px 10px 8px 8px; }
  .cc-video-thumb { flex-basis: 104px; width: 104px; }
  .cc-video-play { width: 28px; height: 28px; margin: -14px 0 0 -14px; }
  .cc-video-play::after { left: 11px; top: 8px; border-width: 6px 0 6px 9px; }
  .cc-video-title { font-size: 14.5px; }
  .cc-video-credit { font-size: 11.5px; }
  .cc-video-cta { display: none; }
  .cc-video-bar { flex-wrap: wrap; row-gap: 4px; }
}
@media print { .cc-video { display: none; } }
""".strip()

# The script reads everything from data attributes on its own section, so one
# copy works for any page and the iframe exists only after the click.
JS = """
(function () {
  var box = document.currentScript && document.currentScript.previousElementSibling;
  if (!box || !box.classList.contains('cc-video')) return;
  var strip = box.querySelector('.cc-video-strip');
  var player = box.querySelector('.cc-video-player');
  var frame = box.querySelector('.cc-video-frame');
  var hide = box.querySelector('.cc-video-hide');
  strip.addEventListener('click', function () {
    var f = document.createElement('iframe');
    f.src = box.getAttribute('data-embed');
    f.title = box.getAttribute('data-title');
    f.setAttribute('allow', 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture');
    f.setAttribute('allowfullscreen', '');
    frame.appendChild(f);
    strip.setAttribute('aria-expanded', 'true');
    strip.hidden = true;
    player.hidden = false;
    f.focus();
    if (typeof window.gtag === 'function') {
      var m = location.pathname.match(/\\/topics\\/([^\\/]+)\\//);
      window.gtag('event', 'video_play', { topic: m ? m[1] : '', video_id: box.getAttribute('data-video') });
    }
  });
  hide.addEventListener('click', function () {
    frame.innerHTML = '';
    player.hidden = true;
    strip.hidden = false;
    strip.setAttribute('aria-expanded', 'false');
    strip.focus();
  });
})();
""".strip()

PLAY_SVG = '<svg viewBox="0 0 9 10" aria-hidden="true" focusable="false"><path d="M0 0L9 5L0 10Z"/></svg>'


def esc(s: str) -> str:
    return html_mod.escape(s, quote=True)


def iso_seconds(iso: str) -> float | None:
    m = ISO_DUR_RE.match(iso or "")
    if not m or iso == "PT":
        return None
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)


def spoken_length(seconds: float) -> str:
    total = int(round(seconds))
    m, s = divmod(total, 60)
    parts = []
    if m:
        parts.append(f"{m} minute" + ("s" if m != 1 else ""))
    if s:
        parts.append(f"{s} second" + ("s" if s != 1 else ""))
    return " ".join(parts) or "under a second"


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    v = data.get("video") or {}
    for key in REQUIRED:
        if v.get(key) in (None, ""):
            errors.append(f"video.{key} is missing")
    if errors:
        return errors
    for key in ("name", "headline", "description", "narrator", "duration_label"):
        text = str(v[key])
        if "—" in text or "–" in text:
            errors.append(f"video.{key} has an em or en dash")
        if re.search(r"(^|\s)#\w", text):
            errors.append(f"video.{key} has a hashtag")
        if re.search(r"\bpastor\b", text, re.IGNORECASE):
            errors.append(f'video.{key} uses the word "Pastor"')
    if not ID_RE.match(v["youtube_id"]):
        errors.append("video.youtube_id is not an 11 character YouTube id")
    secs = iso_seconds(v["duration_iso"])
    if secs is None:
        errors.append("video.duration_iso is not an ISO 8601 duration (PTnMnS)")
    elif abs(secs - float(v["duration_seconds"])) > 0.05:
        errors.append(f"video.duration_iso ({secs}s) does not match duration_seconds ({v['duration_seconds']})")
    try:
        date.fromisoformat(v["upload_date"])
    except ValueError:
        errors.append("video.upload_date is not an ISO date")
    thumb = v["thumbnail_path"]
    if not thumb.startswith("/") or not (DOCS_DIR / thumb.lstrip("/")).is_file():
        errors.append(f"video.thumbnail_path {thumb} is not a file under docs/")
    return errors


def schema(v: dict) -> str:
    obj = {
        "@context": "https://schema.org",
        "@type": "VideoObject",
        "name": v["name"],
        "description": v["description"],
        "thumbnailUrl": SITE + v["thumbnail_path"],
        "uploadDate": v["upload_date"],
        "duration": v["duration_iso"],
        "embedUrl": f"https://www.youtube-nocookie.com/embed/{v['youtube_id']}",
        "publisher": {"@type": "Organization", "name": "Christian Curator", "url": SITE},
    }
    body = json.dumps(obj, indent=2, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json" data-cc-marker="CC-VIDEO-SCHEMA">\n{body}\n</script>'


def render_block(data: dict) -> str:
    v = data["video"]
    vid = v["youtube_id"]
    embed = f"https://www.youtube-nocookie.com/embed/{vid}?autoplay=1&rel=0&cc_load_policy=0"
    watch = f"https://youtu.be/{vid}"
    kicker = f"Video overview · {v['duration_label']}"
    label = f"Play video: {v['headline']} ({spoken_length(float(v['duration_seconds']))})"
    return "\n".join([
        START,
        f"<style>\n{CSS}\n</style>",
        f'<section class="cc-video" id="video" aria-label="Video overview" data-video="{esc(vid)}" '
        f'data-embed="{esc(embed)}" data-title="{esc(v["name"])}">',
        f'<button type="button" class="cc-video-strip" aria-expanded="false" aria-controls="cc-video-player" aria-label="{esc(label)}">',
        f'<span class="cc-video-thumb"><img src="{esc(v["thumbnail_path"])}" alt="" width="960" height="540" decoding="async">'
        '<span class="cc-video-play" aria-hidden="true"></span></span>',
        '<span class="cc-video-text">'
        f'<span class="cc-video-kicker">{esc(kicker)}</span>'
        f'<span class="cc-video-title">{esc(v["headline"])}</span>'
        f'<span class="cc-video-credit">{esc(v["narrator"])}</span></span>',
        f'<span class="cc-video-cta" aria-hidden="true">{PLAY_SVG}Watch</span>',
        "</button>",
        '<div class="cc-video-player" id="cc-video-player" hidden>',
        '<div class="cc-video-frame"></div>',
        f'<div class="cc-video-bar"><span class="cc-video-credit-bar">{esc(v["narrator"])}</span>'
        f'<span class="cc-video-links"><a href="{esc(watch)}" target="_blank" rel="noopener" data-pos="topic-video" '
        'data-src="YouTube">Watch on YouTube</a>'
        '<button type="button" class="cc-video-hide" aria-controls="cc-video-player">Hide video</button></span></div>',
        "</div>",
        "</section>",
        f"<script>\n{JS}\n</script>",
        schema(v),
        END,
    ])


def apply(page_html: str, block: str) -> str:
    if START in page_html:
        return BLOCK_RE.sub(lambda _m: block, page_html, count=1)
    idx = page_html.find(ANCHOR)
    if idx < 0:
        raise ValueError(f"no {ANCHOR!r} anchor on the page for the first insert")
    return page_html[:idx] + block + "\n" + page_html[idx:]


def load(slug: str) -> dict:
    return json.loads((DATA_DIR / f"{slug}.json").read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    slugs = [args.slug] if args.slug else sorted(p.stem for p in DATA_DIR.glob("*.json"))
    failed = False
    for slug in slugs:
        data = load(slug)
        errors = validate(data)
        if data.get("slug") != slug:
            errors.append(f"slug field {data.get('slug')!r} does not match the file name")
        page = TOPICS_DIR / slug / "index.html"
        if not page.is_file():
            errors.append(f"no page at {page.relative_to(REPO_ROOT)}")
        if errors:
            failed = True
            for e in errors:
                print(f"{slug}: {e}")
            continue
        current = page.read_text(encoding="utf-8")
        try:
            new = apply(current, render_block(data))
        except ValueError as exc:
            failed = True
            print(f"{slug}: {exc}")
            continue
        if new == current:
            print(f"{slug}: up to date")
        elif args.check:
            failed = True
            print(f"{slug}: page is stale, rerun scripts/build_topic_video.py --slug {slug}")
        elif args.dry_run:
            print(f"{slug}: would update")
        else:
            page.write_text(new, encoding="utf-8")
            print(f"{slug}: updated")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
