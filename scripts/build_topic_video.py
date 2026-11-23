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

Shorts per view (optional "shorts" object, keyed by debate card id such as
"position-1"): each Short is written inside its card, after Key Reads, between
<!-- CC-TOPIC-SHORT:<card id>:START --> and <!-- CC-TOPIC-SHORT:<card id>:END -->.
It is collapsed by default: a small button (9:16 WebP thumbnail plus "Watch the
N-second version") with aria-expanded. The click injects a vertical 9:16
youtube-nocookie iframe (max 320px wide) with a "Watch on YouTube" link
(data-pos "topic-short") and "Hide video", which removes the iframe. The CSS and
one delegated click script for every Short live in the main CC-TOPIC-VIDEO block,
so the cards carry only markup plus a VideoObject JSON-LD
(data-cc-marker="CC-SHORT-SCHEMA") per Short. A card with no entry gets nothing,
and a block whose key leaves the mapping is removed on the next run. To add a
Short: verify the id (channel RSS plus oEmbed title), save a 180x320 WebP
thumbnail under docs/assets/, add the entry, rerun.

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
  "shorts": {                                    # optional
    "position-1": {
      "youtube_id": "0-sH-7oJMSU",
      "name": "Title as published on YouTube",
      "view": "Dispensational Premillennialism",   # used in the button's aria-label
      "description": "Plain summary for the schema",
      "duration_seconds": 37,
      "duration_iso": "PT37S",
      "upload_date": "2026-11-19",
      "thumbnail_path": "/assets/short-eschatology-position-1-thumb.webp"
    }
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
SHORT_START = "<!-- CC-TOPIC-SHORT:{key}:START -->"
SHORT_END = "<!-- CC-TOPIC-SHORT:{key}:END -->"
SHORT_BLOCK_RE = re.compile(r"<!-- CC-TOPIC-SHORT:([\w-]+):START -->.*?<!-- CC-TOPIC-SHORT:\1:END -->\n?", re.DOTALL)
SHORT_KEY_RE = re.compile(r"^position-[1-9]$")
SHORT_REQUIRED = ("youtube_id", "name", "view", "description", "duration_seconds", "duration_iso",
                  "upload_date", "thumbnail_path")
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

SHORT_CSS = """
.cc-short { margin-top: .9rem; padding-top: .75rem; border-top: 1px solid #eeebe5; }
.cc-short-open { display: flex; align-items: center; gap: 10px; width: 100%; margin: 0; padding: 6px 10px 6px 6px;
  background: #f4f1ea; border: 1px solid #e0ddd8; border-radius: 4px; cursor: pointer; text-align: left; font: inherit; color: #1a1a1a;
  transition: border-color .15s ease, background-color .15s ease; }
.cc-short-open:hover { border-color: #b9c4b3; background: #f0ede4; }
.cc-short-open:focus-visible { outline: 2px solid #2C4A2E; outline-offset: 2px; }
.cc-short-thumb { position: relative; flex: 0 0 34px; width: 34px; aspect-ratio: 9 / 16; border-radius: 2px; overflow: hidden; background: #2C4A2E; }
.cc-short-thumb img { display: block; width: 100%; height: 100%; object-fit: cover; }
.cc-short-thumb .cc-video-play { width: 20px; height: 20px; margin: -10px 0 0 -10px; }
.cc-short-thumb .cc-video-play::after { left: 8px; top: 6px; border-width: 4px 0 4px 6px; }
.cc-short-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.cc-short-label { font-family: 'Source Sans 3', sans-serif; font-size: 13px; font-weight: 600; color: #2C4A2E; }
.cc-short-meta { font-family: 'Source Sans 3', sans-serif; font-size: 11.5px; color: #6b6b6b; }
.cc-short-open[hidden], .cc-short-player[hidden] { display: none; }
.cc-short-player { max-width: 320px; }
.cc-short-frame { position: relative; width: 100%; aspect-ratio: 9 / 16; background: #1a1a1a; border-radius: 4px 4px 0 0; overflow: hidden; }
.cc-short-frame iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
.cc-short-player .cc-video-bar { padding: 6px 10px; font-size: 12px; }
@media print { .cc-short { display: none; } }
""".strip()

# One delegated listener serves every Short on the page, wherever the cards sit.
SHORT_JS = """
(function () {
  document.addEventListener('click', function (e) {
    var open = e.target.closest && e.target.closest('.cc-short-open');
    var hide = e.target.closest && e.target.closest('.cc-short-hide');
    var box = (open || hide) && (open || hide).closest('.cc-short');
    if (!box) return;
    var btn = box.querySelector('.cc-short-open');
    var player = box.querySelector('.cc-short-player');
    var frame = box.querySelector('.cc-short-frame');
    if (open) {
      var f = document.createElement('iframe');
      f.src = box.getAttribute('data-embed');
      f.title = box.getAttribute('data-title');
      f.setAttribute('allow', 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture');
      f.setAttribute('allowfullscreen', '');
      frame.appendChild(f);
      btn.setAttribute('aria-expanded', 'true');
      btn.hidden = true;
      player.hidden = false;
      f.focus();
      if (typeof window.gtag === 'function') {
        var m = location.pathname.match(/\\/topics\\/([^\\/]+)\\//);
        window.gtag('event', 'video_play', { topic: m ? m[1] : '', video_id: box.getAttribute('data-video'), video_kind: 'short' });
      }
    } else {
      frame.innerHTML = '';
      player.hidden = true;
      btn.hidden = false;
      btn.setAttribute('aria-expanded', 'false');
      btn.focus();
    }
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
    errors.extend(validate_shorts(data.get("shorts") or {}))
    return errors


def validate_shorts(shorts: dict) -> list[str]:
    errors: list[str] = []
    ids = set()
    for key, sh in shorts.items():
        where = f"shorts.{key}"
        if not SHORT_KEY_RE.match(key):
            errors.append(f"{where}: key must be a debate card id like position-1")
        missing = [k for k in SHORT_REQUIRED if sh.get(k) in (None, "")]
        if missing:
            errors.append(f"{where}: missing {', '.join(missing)}")
            continue
        for k in ("name", "view", "description"):
            text = str(sh[k])
            if "\u2014" in text or "\u2013" in text:
                errors.append(f"{where}.{k} has an em or en dash")
            if re.search(r"(^|\s)#\w", text):
                errors.append(f"{where}.{k} has a hashtag")
            if re.search(r"\bpastor\b", text, re.IGNORECASE):
                errors.append(f'{where}.{k} uses the word "Pastor"')
        if not ID_RE.match(sh["youtube_id"]):
            errors.append(f"{where}.youtube_id is not an 11 character YouTube id")
        if sh["youtube_id"] in ids:
            errors.append(f"{where}.youtube_id is used twice")
        ids.add(sh["youtube_id"])
        secs = iso_seconds(sh["duration_iso"])
        if secs is None:
            errors.append(f"{where}.duration_iso is not an ISO 8601 duration")
        elif abs(secs - float(sh["duration_seconds"])) > 0.05:
            errors.append(f"{where}.duration_iso does not match duration_seconds")
        try:
            date.fromisoformat(sh["upload_date"])
        except ValueError:
            errors.append(f"{where}.upload_date is not an ISO date")
        thumb = sh["thumbnail_path"]
        if not thumb.startswith("/") or not (DOCS_DIR / thumb.lstrip("/")).is_file():
            errors.append(f"{where}.thumbnail_path {thumb} is not a file under docs/")
    return errors


def schema(v: dict, marker: str = "CC-VIDEO-SCHEMA") -> str:
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
    return f'<script type="application/ld+json" data-cc-marker="{marker}">\n{body}\n</script>'


def render_block(data: dict) -> str:
    v = data["video"]
    vid = v["youtube_id"]
    embed = f"https://www.youtube-nocookie.com/embed/{vid}?autoplay=1&rel=0&cc_load_policy=0"
    watch = f"https://youtu.be/{vid}"
    kicker = f"Video overview · {v['duration_label']}"
    label = f"Play video: {v['headline']} ({spoken_length(float(v['duration_seconds']))})"
    has_shorts = bool(data.get("shorts"))
    css = CSS + ("\n" + SHORT_CSS if has_shorts else "")
    return "\n".join([
        START,
        f"<style>\n{css}\n</style>",
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
        *([f"<script>\n{SHORT_JS}\n</script>"] if has_shorts else []),
        schema(v),
        END,
    ])


def render_short(key: str, sh: dict) -> str:
    vid = sh["youtube_id"]
    secs = int(round(float(sh["duration_seconds"])))
    embed = f"https://www.youtube-nocookie.com/embed/{vid}?autoplay=1&rel=0&cc_load_policy=0"
    player_id = f"cc-short-player-{key}"
    label = f"Watch the {secs}-second version"
    aria = f"Play video: {sh['view']}, the {spoken_length(secs)} version"
    meta = f"Short video · {secs // 60}:{secs % 60:02d}"
    return "\n".join([
        SHORT_START.format(key=key),
        f'<div class="cc-short" data-video="{esc(vid)}" data-embed="{esc(embed)}" data-title="{esc(sh["name"])}">',
        f'<button type="button" class="cc-short-open" aria-expanded="false" aria-controls="{player_id}" aria-label="{esc(aria)}">'
        f'<span class="cc-short-thumb"><img src="{esc(sh["thumbnail_path"])}" alt="" width="180" height="320" loading="lazy" decoding="async">'
        '<span class="cc-video-play" aria-hidden="true"></span></span>'
        f'<span class="cc-short-text"><span class="cc-short-label">{esc(label)}</span>'
        f'<span class="cc-short-meta">{esc(meta)}</span></span></button>',
        f'<div class="cc-short-player" id="{player_id}" hidden>',
        '<div class="cc-short-frame"></div>',
        f'<div class="cc-video-bar"><span class="cc-video-links"><a href="https://www.youtube.com/shorts/{esc(vid)}" '
        'target="_blank" rel="noopener" data-pos="topic-short" data-src="YouTube">Watch on YouTube</a>'
        f'<button type="button" class="cc-video-hide cc-short-hide" aria-controls="{player_id}">Hide video</button></span></div>',
        "</div>",
        "</div>",
        schema(sh, "CC-SHORT-SCHEMA"),
        SHORT_END.format(key=key),
    ])


def card_insert_at(page_html: str, key: str) -> int:
    """Index right after the Key Reads list of the debate card with id=key."""
    start = page_html.find(f'id="{key}"')
    if start < 0:
        raise ValueError(f"no debate card with id={key!r} on the page")
    nxt = page_html.find('<div class="cc-debate-side', start)
    stop = nxt if nxt >= 0 else len(page_html)
    reads = page_html.find('<div class="cc-debate-reads">', start, stop)
    if reads < 0:
        raise ValueError(f"debate card {key!r} has no Key Reads list to place the Short after")
    close = page_html.find("</div>", reads)
    if close < 0 or close > stop:
        raise ValueError(f"debate card {key!r} Key Reads list is not closed")
    at = close + len("</div>")
    return at + 1 if page_html[at:at + 1] == "\n" else at


def apply_shorts(page_html: str, shorts: dict) -> str:
    # Drop blocks whose key left the mapping.
    page_html = SHORT_BLOCK_RE.sub(lambda m: m.group(0) if m.group(1) in shorts else "", page_html)
    for key in sorted(shorts):
        block = render_short(key, shorts[key])
        pat = re.compile(re.escape(SHORT_START.format(key=key)) + r".*?" + re.escape(SHORT_END.format(key=key)), re.DOTALL)
        if pat.search(page_html):
            page_html = pat.sub(lambda _m: block, page_html, count=1)
        else:
            at = card_insert_at(page_html, key)
            page_html = page_html[:at] + block + "\n" + page_html[at:]
    return page_html


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
            new = apply_shorts(apply(current, render_block(data)), data.get("shorts") or {})
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
