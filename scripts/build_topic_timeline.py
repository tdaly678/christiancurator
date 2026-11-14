#!/usr/bin/env python3
"""build_topic_timeline.py: parallel-timeline explainer visuals on topic pages.

A concept visual, not survey data: one horizontal lane per view, all lanes on a
shared row of "stations" (events and periods in order), so what every view
affirms lines up in shaded columns and the differences show as gaps and spans.

  data/topic_timelines/<slug>.json   one visual per topic page

It renders between <!-- CC-TIMELINE:<id>:START --> and <!-- CC-TIMELINE:<id>:END -->
as <section class="cc-timeline" id="<id>"> holding:
  - a wide SVG (lanes across) and a phone SVG (lanes down, stations as rows),
    swapped below 560px by the shared cc-chart-wide / cc-chart-narrow rules in
    docs/assets/topic.css; each has <title> and a <desc> spelling out every lane;
  - common ground, "Where they differ" (3 to 5 bullets), a table version with the
    same content, one sourced voice per view, and a source line.
Styles specific to the block are inline in it, so the shared topic assets (and
every page's asset hash) do not change.

File schema:
{
  "id": "timelines", "slug": "<slug>", "label": "Small caps section label",
  "title": "Section title", "intro": "One or two sentences.",
  "image_title": "Title drawn on the image", "image_subtitle": "...", "image_subtitle_narrow": "...",
  "caption": "What the visual shows.",
  "stations": [{"id": "cross", "label": "Cross, resurrection, ascension", "short": "phone label", "weight": 1}],
  "common": ["cross", ...],            # station ids every view affirms (shaded)
  "common_text": "...", "common_source": "<source id>",
  "lanes": [{"id": "...", "name": "...", "short": "phone header", "tag": "optional", "color": "green",
             "segments": [{"span": ["church", "trib"], "kind": "period" | "event" | "shared",
                           "text": "wide label", "short": "phone label"}],
             "proponent": {"name": "...", "slug": "optional voice slug", "image_name": "...",
                           "work": "title of the piece", "source": "<source id>"}}],
  "differ": ["3 to 5 bullets"],
  "method": "...", "method_source": "<source id>",
  "sources": [{"id": "...", "publisher": "...", "title": "...", "year": 2013, "url": "https://...",
               "fetched": "YYYY-MM-DD", "quote": "words found verbatim on the page", "notes": "..."}],
  "place": {"before": "literal string on the page"}   # first insert only
}
Rules (validate()): 2 to 5 lanes; every lane covers every station exactly once, in
order, with contiguous spans; "shared" segments sit only on common stations;
every proponent and the common/method sources resolve, with URL, fetched date
and a quote; no em or en dashes, tracking parameters or Quiet Revival.
Voice links render only for linkable /voices/ pages (build_topic_top.VoiceIndex).

Usage:
  python scripts/build_topic_timeline.py                  # every data file
  python scripts/build_topic_timeline.py --slug eschatology
  python scripts/build_topic_timeline.py --check          # validate, and fail on a stale page
  python scripts/build_topic_timeline.py --png            # also write docs/og/charts/<slug>-<id>.png
                                                          # (needs Google Chrome; not in the daily run)
Tests: tests/test_build_topic_timeline.py
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_topic_charts import COLORS, put  # noqa: E402
from build_topic_top import VoiceIndex, ensure_assets  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "topic_timelines"
TOPICS_DIR = REPO_ROOT / "docs" / "topics"
PNG_DIR = REPO_ROOT / "docs" / "og" / "charts"
FONTS = REPO_ROOT / "data" / "fonts"

INK, GREY, GRID, SHADE = "#1a1a1a", "#666", "#e0ddd8", "#eef2ec"
FONT = "'Source Sans 3', sans-serif"
SERIF = "'Lora', Georgia, serif"
BRAND = "christiancurator.com"
W_WIDE, W_NARROW, PAD = 740, 360, 14
KINDS = {"period", "event", "shared"}

DASH_RE = re.compile("[–—]")
BANNED_RE = re.compile(r"quiet revival", re.I)
TRACKING_RE = re.compile(r"[?&](?:utm_[a-z]+|fbclid|gclid|mc_eid)=", re.I)
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def esc(s) -> str:
    return html_mod.escape(str(s if s is not None else ""), quote=True)


def markers(tid: str) -> tuple[str, str]:
    return f"<!-- CC-TIMELINE:{tid}:START -->", f"<!-- CC-TIMELINE:{tid}:END -->"


def color(name: str | None) -> str:
    return COLORS.get(name or "green", COLORS["green"])


# ---------------------------------------------------------------- loading and validation

def data_files(data_dir: Path = DATA_DIR) -> list[Path]:
    return sorted(data_dir.glob("*.json"))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def validate(d: dict, page_html: str | None = None) -> list[str]:
    errs: list[str] = []
    for key in ("id", "slug", "label", "title", "image_title", "caption", "stations", "common",
                "lanes", "differ", "sources"):
        if not d.get(key):
            errs.append(f"missing {key}")
    if errs:
        return errs
    if not ID_RE.match(d["id"]):
        errs.append(f"id {d['id']!r} must be kebab case")
    for s in _strings(d):
        if DASH_RE.search(s):
            errs.append(f"em or en dash in {s[:50]!r}")
        if BANNED_RE.search(s):
            errs.append("Quiet Revival is not cited")
        if TRACKING_RE.search(s):
            errs.append(f"tracking parameter in {s[:60]!r}")

    sources = {}
    for s in d["sources"]:
        sid = s.get("id", "?")
        for key in ("id", "publisher", "title", "url", "fetched", "quote"):  # year is optional (undated statements)
            if not s.get(key):
                errs.append(f"source {sid}: missing {key}")
        if s.get("url") and not str(s["url"]).startswith("https://"):
            errs.append(f"source {sid}: url must be https")
        if s.get("fetched") and not ISO_RE.match(str(s["fetched"])):
            errs.append(f"source {sid}: fetched must be YYYY-MM-DD")
        sources[sid] = s

    station_ids = [st.get("id") for st in d["stations"]]
    if len(set(station_ids)) != len(station_ids) or not all(station_ids):
        errs.append("station ids must be unique and present")
    for st in d["stations"]:
        if not st.get("label"):
            errs.append(f"station {st.get('id')}: missing label")
    common = set(d["common"])
    if not common <= set(station_ids):
        errs.append(f"common lists unknown stations: {sorted(common - set(station_ids))}")

    if not 2 <= len(d["lanes"]) <= 5:
        errs.append("2 to 5 lanes")
    for lane in d["lanes"]:
        lid = lane.get("id", "?")
        if not lane.get("name"):
            errs.append(f"lane {lid}: missing name")
        if lane.get("color") and lane["color"] not in COLORS:
            errs.append(f"lane {lid}: unknown color {lane['color']}")
        pos = 0
        for seg in lane.get("segments") or []:
            span = seg.get("span") or []
            if seg.get("kind") not in KINDS:
                errs.append(f"lane {lid}: kind must be one of {sorted(KINDS)}")
            if not 1 <= len(span) <= 2 or any(x not in station_ids for x in span):
                errs.append(f"lane {lid}: bad span {span}")
                break
            a, b = station_ids.index(span[0]), station_ids.index(span[-1])
            if a != pos or b < a:
                errs.append(f"lane {lid}: span {span} is out of order or leaves a gap")
                break
            if seg["kind"] == "shared":
                if a != b or span[0] not in common:
                    errs.append(f"lane {lid}: a shared mark sits on one common station")
            elif not seg.get("text"):
                errs.append(f"lane {lid}: segment {span} needs text")
            pos = b + 1
        else:
            if pos != len(station_ids):
                errs.append(f"lane {lid}: segments must cover every station")
        prop = lane.get("proponent") or {}
        if not prop.get("name") or not prop.get("work"):
            errs.append(f"lane {lid}: proponent needs name and work")
        if prop.get("source") not in sources:
            errs.append(f"lane {lid}: proponent source {prop.get('source')!r} is not in sources")

    for key in ("common_source", "method_source"):
        if d.get(key) and d[key] not in sources:
            errs.append(f"{key} {d[key]!r} is not in sources")
    if not 3 <= len(d["differ"]) <= 5:
        errs.append("differ takes 3 to 5 bullets")

    if page_html is not None:
        start, _ = markers(d["id"])
        anchor = (d.get("place") or {}).get("before") or (d.get("place") or {}).get("after")
        if start not in page_html and (not anchor or anchor not in page_html):
            errs.append("place anchor is not on the page")
    return errs


# ---------------------------------------------------------------- SVG helpers

def text_w(s: str, size: float, bold: bool = False) -> float:
    """Rough rendered width in Source Sans 3."""
    return len(s) * size * (0.51 if bold else 0.48)


def wrap(text: str, width: float, size: float, bold: bool = False) -> list[str]:
    lines, line = [], ""
    for word in str(text).split():
        cand = f"{line} {word}".strip()
        if line and text_w(cand, size, bold) > width:
            lines.append(line)
            line = word
        else:
            line = cand
    if line:
        lines.append(line)
    return lines


def fit(text: str, width: float, size: float, bold: bool = False, max_lines: int = 9,
        floor: float = 9.0) -> tuple[list[str], float]:
    """Wrap, shrinking the size until every word fits the width and lines <= max_lines."""
    while True:
        lines = wrap(text, width, size, bold)
        longest = max((text_w(w, size, bold) for w in str(text).split()), default=0)
        if (longest <= width and len(lines) <= max_lines) or size <= floor:
            return lines, size
        size -= 0.5


def tx(x, y, s, size=12, fill=INK, weight=None, anchor=None, family=None) -> str:
    a = f'x="{x:.1f}" y="{y:.1f}" font-size="{size:g}" fill="{fill}"'
    if weight:
        a += f' font-weight="{weight}"'
    if anchor:
        a += f' text-anchor="{anchor}"'
    if family:
        a += f' font-family="{family}"'
    return f"<text {a}>{esc(s)}</text>"


def block_text(lines: list[str], cx: float, cy: float, size: float, fill: str, weight=None) -> str:
    lh = size * 1.18
    y0 = cy - lh * (len(lines) - 1) / 2 + size * 0.35
    return "".join(tx(cx, y0 + i * lh, ln, size, fill, weight, "middle") for i, ln in enumerate(lines))


def segment_shape(seg: dict, x: float, y: float, w: float, h: float, col: str, text: str,
                  size: float) -> str:
    if seg["kind"] == "shared":
        return f'<circle cx="{x + w / 2:.1f}" cy="{y + h / 2:.1f}" r="7" fill="{col}"/>'
    inner = w - 10
    lines, s = fit(text, inner, size, bold=seg["kind"] == "event", max_lines=max(1, int((h - 4) / (size * 1.18))))
    if seg["kind"] == "event":
        shape = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="7" fill="{col}"/>'
        return shape + block_text(lines, x + w / 2, y + h / 2, s, "#fff", "600")
    shape = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="7" fill="#fff"/>'
             f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="7" fill="{col}" '
             f'fill-opacity="0.13" stroke="{col}" stroke-width="1.2"/>')
    return shape + block_text(lines, x + w / 2, y + h / 2, s, INK)


def lane_desc(d: dict) -> str:
    """Every lane in words, for the SVG <desc>."""
    names = {st["id"]: st["label"] for st in d["stations"]}
    out = []
    for lane in d["lanes"]:
        bits = []
        for seg in lane["segments"]:
            where = " to ".join(names[x] for x in dict.fromkeys(seg["span"]))
            bits.append(f"{where}: {seg['text']}" if seg.get("text") else where)
        out.append(f"{lane['name']}: " + "; ".join(bits) + ".")
    common = [st["label"] for st in d["stations"] if st["id"] in set(d["common"])]
    if common:
        out.append("All views affirm: " + ", ".join(common) + ".")
    return " ".join(out)


def footer(d: dict, y: float, w: float, size: float) -> tuple[str, float]:
    pubs = []
    for lane in d["lanes"]:
        p = lane["proponent"].get("image_name") or lane["proponent"]["name"]
        if p not in pubs:
            pubs.append(p)
    src = {s["id"]: s for s in d["sources"]}
    line = "Voices: " + "; ".join(pubs)
    if d.get("method_source"):
        m = src[d["method_source"]]
        line += ". Sequences after " + ", ".join(str(x) for x in (m["title"], m["publisher"], m.get("year")) if x) + "."
    parts = [f'<line x1="{PAD}" x2="{w - PAD}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>']
    y += 16
    for i, ln in enumerate(wrap(line, w - 2 * PAD, size)):
        parts.append(tx(PAD, y, ln, size, GREY))
        y += 14
    if w < W_WIDE:
        y += 3
    else:
        y -= 14
    parts.append(tx(w - PAD, y, BRAND, size - 0.5, "#2C4A2E", "600", "end"))
    return "".join(parts), y + 10


def svg_open(d: dict, w: float, h: float, narrow: bool) -> str:
    tid = d["id"] + ("-n" if narrow else "")
    cls = "cc-chart-svg cc-timeline-svg " + ("cc-chart-narrow" if narrow else "cc-chart-wide")
    return (f'<svg class="{cls}" viewBox="0 0 {w} {h:.0f}" role="img" aria-labelledby="{tid}-t {tid}-d" '
            f'font-family="{FONT}"><title id="{tid}-t">{esc(d["image_title"])}</title>'
            f'<desc id="{tid}-d">{esc(lane_desc(d))}</desc><rect width="{w}" height="{h:.0f}" fill="#fff"/>')


def header(d: dict, w: float, subtitle: str) -> tuple[list[str], float]:
    parts, y = [], 26
    size = 19 if w < W_WIDE else 21
    for ln in wrap(d["image_title"], w - 2 * PAD, size, True):
        parts.append(tx(PAD, y, ln, size, INK, "700", family=SERIF))
        y += size * 1.25
    for ln in wrap(subtitle, w - 2 * PAD, 12.5):
        parts.append(tx(PAD, y - 3, ln, 12.5, GREY))
        y += 16
    return parts, y + 6


def render_wide(d: dict) -> str:
    w = W_WIDE
    parts, y = header(d, w, d.get("image_subtitle", ""))
    label_w = 136
    total = sum(st.get("weight", 1) for st in d["stations"])
    unit = (w - 2 * PAD - label_w) / total
    xs, x = {}, PAD + label_w
    for st in d["stations"]:
        cw = unit * st.get("weight", 1)
        xs[st["id"]] = (x, cw)
        x += cw
    head_h, lane_h, gap = 34, 66, 8
    body_h = head_h + len(d["lanes"]) * lane_h
    common = set(d["common"])
    for st in d["stations"]:
        x0, cw = xs[st["id"]]
        if st["id"] in common:
            parts.append(f'<rect x="{x0 + 1:.1f}" y="{y:.1f}" width="{cw - 2:.1f}" height="{body_h:.1f}" '
                         f'rx="4" fill="{SHADE}"/>')
        lines, s = fit(st["label"], cw - 8, 11.5, True, max_lines=2)
        fill = "#2C4A2E" if st["id"] in common else GREY
        parts.append(block_text(lines, x0 + cw / 2, y + head_h / 2, s, fill, "700"))
    y += head_h
    for lane in d["lanes"]:
        col = color(lane.get("color"))
        name_lines, ns = fit(lane["name"], label_w - 8, 13, True, max_lines=2)
        prop = lane["proponent"].get("image_name") or lane["proponent"]["name"]
        n_lines = len(name_lines) + 1
        ty = y + lane_h / 2 - (n_lines - 1) * 7.5 + 4
        for i, ln in enumerate(name_lines):
            parts.append(tx(PAD, ty + i * 15, ln, ns, col, "700"))
        parts.append(tx(PAD, ty + len(name_lines) * 15, f"e.g. {prop}", 11, GREY))
        mid = y + lane_h / 2
        parts.append(f'<line x1="{PAD + label_w:.1f}" x2="{w - PAD:.1f}" y1="{mid:.1f}" y2="{mid:.1f}" '
                     f'stroke="{col}" stroke-opacity="0.35" stroke-width="2"/>')
        for seg in lane["segments"]:
            x0 = xs[seg["span"][0]][0]
            x1 = xs[seg["span"][-1]][0] + xs[seg["span"][-1]][1]
            parts.append(segment_shape(seg, x0 + 3, y + gap, x1 - x0 - 6, lane_h - 2 * gap, col,
                                       seg.get("text", ""), 11.5))
        y += lane_h
    foot, y = footer(d, y + 12, w, 11)
    return svg_open(d, w, y, False) + "".join(parts) + foot + "</svg>"


def render_narrow(d: dict) -> str:
    w = W_NARROW
    parts, y = header(d, w, d.get("image_subtitle_narrow") or d.get("image_subtitle", ""))
    label_w = 70
    n = len(d["lanes"])
    lane_w = (w - 2 * PAD - label_w) / n
    head_h = 40
    heights = {}
    for st in d["stations"]:
        base = 38 if st.get("weight", 1) < 0.9 else (66 if st.get("weight", 1) > 1 else 54)
        lines, s = fit(st.get("short") or st["label"], label_w - 6, 11, True, max_lines=3)
        heights[st["id"]] = max(base, len(lines) * s * 1.18 + 12)
    head_size = min(fit(ln.get("short") or ln["name"], lane_w - 4, 11.5, True, max_lines=2)[1]
                    for ln in d["lanes"])
    for i, lane in enumerate(d["lanes"]):
        col = color(lane.get("color"))
        x0 = PAD + label_w + i * lane_w
        lines, s = fit(lane.get("short") or lane["name"], lane_w - 4, head_size, True, max_lines=2)
        parts.append(block_text(lines, x0 + lane_w / 2, y + head_h / 2 - 2, s, col, "700"))
        parts.append(f'<rect x="{x0 + 6:.1f}" y="{y + head_h - 5:.1f}" width="{lane_w - 12:.1f}" height="3" '
                     f'rx="1.5" fill="{col}"/>')
    y += head_h
    ys, yy = {}, y
    for st in d["stations"]:
        ys[st["id"]] = (yy, heights[st["id"]])
        yy += heights[st["id"]]
    common = set(d["common"])
    for st in d["stations"]:
        y0, h = ys[st["id"]]
        if st["id"] in common:
            parts.append(f'<rect x="{PAD:.1f}" y="{y0 + 1:.1f}" width="{w - 2 * PAD:.1f}" height="{h - 2:.1f}" '
                         f'rx="4" fill="{SHADE}"/>')
        lines, s = fit(st.get("short") or st["label"], label_w - 6, 11, True, max_lines=3)
        fill = "#2C4A2E" if st["id"] in common else GREY
        lh = s * 1.18
        ty = y0 + h / 2 - lh * (len(lines) - 1) / 2 + s * 0.35
        for k, ln in enumerate(lines):
            parts.append(tx(PAD + 4, ty + k * lh, ln, s, fill, "700"))
    for i, lane in enumerate(d["lanes"]):
        col = color(lane.get("color"))
        x0 = PAD + label_w + i * lane_w
        cx = x0 + lane_w / 2
        parts.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y:.1f}" y2="{yy:.1f}" stroke="{col}" '
                     f'stroke-opacity="0.35" stroke-width="2"/>')
        for seg in lane["segments"]:
            y0 = ys[seg["span"][0]][0]
            y1 = ys[seg["span"][-1]][0] + ys[seg["span"][-1]][1]
            parts.append(segment_shape(seg, x0 + 2.5, y0 + 3, lane_w - 5, y1 - y0 - 6, col,
                                       seg.get("short") or seg.get("text", ""), 10.5))
    foot, yy = footer(d, yy + 12, w, 11)
    return svg_open(d, w, yy, True) + "".join(parts) + foot + "</svg>"


# ---------------------------------------------------------------- HTML

STYLE = (
    "<style>"
    ".cc-timeline{margin:2rem 0;}"
    ".cc-timeline-label{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#8B1A1A;margin-bottom:0.4rem;}"
    ".cc-timeline-title{font-family:'Lora',Georgia,serif;font-size:22px;line-height:1.3;color:#1a1a1a;margin-bottom:0.4rem;}"
    ".cc-timeline-intro{font-size:15px;line-height:1.6;color:#444;margin-bottom:0.6rem;}"
    ".cc-timeline .cc-chart-svg.cc-chart-wide{max-width:740px;}"
    ".cc-timeline .cc-chart-svg.cc-chart-narrow{max-width:420px;}"
    ".cc-timeline-common{margin:0.8rem 0;padding:0.7rem 0.9rem;background:#eef2ec;border-radius:4px;font-size:14.5px;line-height:1.55;}"
    ".cc-timeline-sub{font-size:10px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:#2C4A2E;margin:1rem 0 0.4rem;}"
    ".cc-timeline-key ul,.cc-timeline-voices ul{list-style:none;padding:0;margin:0;}"
    ".cc-timeline-key li{position:relative;padding:0.3rem 0 0.3rem 1rem;font-size:14.5px;line-height:1.5;}"
    ".cc-timeline-key li::before{content:'';position:absolute;left:0;top:0.75rem;width:6px;height:6px;border-radius:50%;background:#8B1A1A;}"
    ".cc-timeline-voices li{padding:0.3rem 0;font-size:14px;line-height:1.5;color:#444;}"
    ".cc-timeline-swatch{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:baseline;}"
    ".cc-timeline-table th[scope=row]{font-weight:600;}"
    "</style>"
)


def voice_html(prop: dict, voices: VoiceIndex) -> str:
    if prop.get("slug") and voices.linkable(prop["slug"]):
        return (f'<a href="/voices/{esc(prop["slug"])}/" data-pos="topic-voices">'
                f'{esc(prop["name"])}</a>')
    return esc(prop["name"])


def table_html(d: dict) -> str:
    stations = d["stations"]
    head = '<th scope="col">View</th>' + "".join(f'<th scope="col">{esc(st["label"])}</th>' for st in stations)
    common = set(d["common"])
    rows = []
    for lane in d["lanes"]:
        cells = []
        for seg in lane["segments"]:
            span = len(range([s["id"] for s in stations].index(seg["span"][0]),
                             [s["id"] for s in stations].index(seg["span"][-1]) + 1))
            text = seg.get("text") or ("Affirmed" if seg["span"][0] in common else "")
            labels = [st["label"] for st in stations if st["id"] in seg["span"]]
            cs = f' colspan="{span}"' if span > 1 else ""
            cells.append(f'<td{cs} data-label="{esc(" to ".join(labels))}">{esc(text)}</td>')
        rows.append(f'<tr><th scope="row">{esc(lane["name"])}</th>{"".join(cells)}</tr>')
    return (f'<details class="cc-chart-data"><summary>Table version</summary><div class="cc-chart-scroll">'
            f'<table class="cc-timeline-table cc-chart-stack"><caption>{esc(d["image_title"])}</caption>'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div></details>')


def render_block(d: dict, voices: VoiceIndex | None = None) -> str:
    voices = voices or VoiceIndex()
    src = {s["id"]: s for s in d["sources"]}
    start, end = markers(d["id"])

    def link(s: dict, text: str | None = None) -> str:
        return (f'<a href="{esc(s["url"])}" target="_blank" rel="noopener" data-pos="topic-timeline">'
                f'{esc(text or s["title"])}</a>')

    def year(s: dict) -> str:
        return f' ({esc(s["year"])})' if s.get("year") else ""

    common = ""
    if d.get("common_text"):
        cite = ""
        if d.get("common_source"):
            s = src[d["common_source"]]
            cite = f' ({link(s, ", ".join(str(x) for x in (s["publisher"], s.get("year")) if x))})'
        common = (f'<p class="cc-timeline-common"><strong>Common ground.</strong> '
                  f'{esc(d["common_text"])}{cite}</p>')
    differ = "".join(f"<li>{esc(b)}</li>" for b in d["differ"])
    voices_li = []
    for lane in d["lanes"]:
        p = lane["proponent"]
        s = src[p["source"]]
        who = voice_html(p, voices)
        pub = "" if s["publisher"] == p["name"] else f'{esc(s["publisher"])}, '
        voices_li.append(
            f'<li><span class="cc-timeline-swatch" style="background:{color(lane.get("color"))}"></span>'
            f'<strong>{esc(lane["name"])}:</strong> {who}, {pub}{link(s, p["work"])}{year(s)}</li>')
    method = ""
    if d.get("method"):
        method = esc(d["method"]) + " "
        if d.get("method_source"):
            s = src[d["method_source"]]
            method = (f'{esc(d["method"].rstrip("."))}: {esc(s["publisher"])}, '
                      f'{link(s)}{year(s)}. ')
    intro = f'<p class="cc-timeline-intro">{esc(d["intro"])}</p>' if d.get("intro") else ""
    return (
        f'{start}\n<section class="cc-timeline" id="{esc(d["id"])}">{STYLE}\n'
        f'<h2 class="cc-timeline-label">{esc(d["label"])}</h2>\n'
        f'<h3 class="cc-timeline-title">{esc(d["title"])}</h3>{intro}\n'
        f'<figure class="cc-chart cc-timeline-fig">\n{render_wide(d)}\n{render_narrow(d)}\n'
        f'<figcaption>{esc(d["caption"])}</figcaption>\n{common}\n'
        f'<div class="cc-timeline-key"><div class="cc-timeline-sub">Where they differ</div><ul>{differ}</ul></div>\n'
        f'{table_html(d)}\n'
        f'<div class="cc-timeline-voices"><div class="cc-timeline-sub">One voice for each view</div>'
        f'<ul>{"".join(voices_li)}</ul></div>\n'
        f'<p class="cc-chart-source">{method}No view is presented here as the answer. Chart by Christian Curator.</p>\n'
        f'</figure>\n</section>\n{end}'
    )


def build_page(page_html: str, d: dict, voices: VoiceIndex | None = None) -> str:
    start, end = markers(d["id"])
    out = put(page_html, start, end, render_block(d, voices), d.get("place"))
    return ensure_assets(out)


# ---------------------------------------------------------------- PNG

def chrome_binary() -> str | None:
    for cand in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 shutil.which("google-chrome") or "", shutil.which("chromium") or ""):
        if cand and Path(cand).exists():
            return cand
    return None


def share_html(d: dict, width: int = 1200) -> tuple[str, int]:
    svg = render_wide(d)
    vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    vw, vh = int(vb.group(1)), int(vb.group(2))
    pad = 36
    height = int(round((width - 2 * pad) * vh / vw)) + 2 * pad
    fonts = (f"@font-face{{font-family:'Source Sans 3';src:url('{(FONTS / 'SourceSans3-Variable.ttf').as_uri()}');"
             f"font-weight:200 900;}}@font-face{{font-family:'Lora';src:url('{(FONTS / 'Lora-Variable.ttf').as_uri()}');"
             f"font-weight:400 700;}}")
    page = (f"<!doctype html><html><head><meta charset='utf-8'><style>{fonts}html,body{{margin:0;background:#fff;}}"
            f"svg{{display:block;width:{width - 2 * pad}px;height:auto;margin:{pad}px;}}</style></head>"
            f"<body>{svg}</body></html>")
    return page, height


def write_png(d: dict, out: Path, width: int = 1200) -> Path:
    chrome = chrome_binary()
    if not chrome:
        raise RuntimeError("Google Chrome not found; --png needs it")
    page, height = share_html(d, width)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "share.html"
        src.write_text(page, encoding="utf-8")
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", f"--window-size={width},{height}",
                        f"--screenshot={out}", src.as_uri()],
                       check=True, capture_output=True, timeout=60)
    return out


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug", action="append")
    ap.add_argument("--check", action="store_true", help="validate, and fail when a page is stale")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--png", action="store_true", help="also render the share image")
    args = ap.parse_args(argv)
    errors = 0
    voices = VoiceIndex()
    for path in data_files():
        d = load(path)
        slug = d.get("slug") or path.stem
        if args.slug and slug not in args.slug:
            continue
        page = TOPICS_DIR / slug / "index.html"
        if not page.exists():
            print(f"::error::{path.relative_to(REPO_ROOT)}: no topic page {slug}")
            errors += 1
            continue
        html = page.read_text(encoding="utf-8")
        problems = validate(d, html)
        for p in problems:
            print(f"::error::{path.relative_to(REPO_ROOT)}: {p}")
        if problems:
            errors += len(problems)
            continue
        out = build_page(html, d, voices)
        if args.check:
            if out != html:
                print(f"::error::{slug}: timeline block is stale; run scripts/build_topic_timeline.py --slug {slug}")
                errors += 1
            continue
        if out != html and not args.dry_run:
            page.write_text(out, encoding="utf-8")
        print(f"{slug}: timeline {d['id']}{' (changed)' if out != html else ''}")
        if args.png and not args.dry_run:
            png = write_png(d, PNG_DIR / f"{slug}-{d['id']}.png")
            print(f"  wrote {png.relative_to(REPO_ROOT)}")
    if errors:
        print(f"{errors} problem(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
