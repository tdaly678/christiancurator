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
                           "work": "title of the piece", "source": "<source id>",
                           "also": ["optional further source ids, linked after the work"]}}],
  "differ": ["3 to 5 bullets"],
  "method": "...", "method_source": "<source id>",
  "sources": [{"id": "...", "publisher": "...", "title": "...", "year": 2013, "url": "https://...",
               "fetched": "YYYY-MM-DD", "quote": "words found verbatim on the page", "notes": "..."}],
  "place": {"before": "literal string on the page"}   # first insert only
}
Other types ("type", default "timeline"); both share every key above except
stations / common / lanes:
  "spectrum": "axis": {"left": "...", "right": "...", "label": "optional"},
              "axis_y": {"label": "...", "bottom": "...", "top": "..."}   # optional: two axes
              "bands": [{"from": 0, "to": 35, "label": "..."}]           # optional, one axis only
              "positions": [{"id", "name", "short", "color", "at": 0..100, "y": 0..100 (two axes),
                             "text", "short_text", "placement": "optional words",
                             "outside": true, "outside_label": "...", "proponent": {...}}]
              One axis: a line with numbered dots and a row of cards (stacked on phones).
              Two axes: a plot with numbered dots beside the cards.
  "matrix":   "columns": [{"id", "name", "short", "color", "outside", "outside_label", "proponent"}],
              "rows": [{"id", "label", "short", "cells": [{"text", "short", "mark": "yes|partly|no"}]}]
              Views across, questions down; on phones each question becomes a block.
  "orgchart": "tiers": [{"id", "label"}]  (2 to 5 levels, top first),
              "charts": [{"id", "name", "short", "tag", "color", "proponent",
                          "boxes": [{"tier", "text", "sub", "loose": true}]   # one per tier, in order
                          "links": [{"between": [upper tier, lower tier],
                                     "down": "authority label", "up": "elects or consents label"}
                                    | {"between": [...], "loose": "cooperation label"}]}]
              2 to 4 side-by-side org diagrams; on phones they stack.
  "chronology": "events": [{"id", "date": "c. 1098", "year": 1098 (whole number, for order), "name",
                            "short", "who", "text", "short_text", "color", "outside", "proponent"}]
              3 to 8 events in date order: cards alternate above and below one line
              (one column with a rail on phones).
  "outside": a view beyond evangelical bounds, drawn dashed and labelled "Shown for contrast".
  Optional on any type: "voices_label", "note" (footer sentence), "image_source" (footer line on the
  image), "table_view_label", "png_name" (share image file name, default the id).
Rules (validate()): 2 to 5 lanes; every lane covers every station exactly once, in
order, with contiguous spans; "shared" segments sit only on common stations;
every proponent and the common/method sources resolve, with URL, fetched date
and a quote; no em or en dashes, tracking parameters or Quiet Revival.
Spectrum: 2 to 7 positions, at (and y with axis_y) from 0 to 100. Matrix: 2 to 5
columns, 2 to 8 rows, one cell with text per column. Every view needs a proponent.
Several data files may target one page (each with its own id).
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
MIN_SHARE_H = 630
KINDS = {"period", "event", "shared"}
TYPES = ("timeline", "spectrum", "matrix", "orgchart", "chronology")
TYPE_KEYS = {"timeline": ("stations", "common", "lanes"), "spectrum": ("axis", "positions"),
             "matrix": ("columns", "rows"), "orgchart": ("tiers", "charts"), "chronology": ("events",)}
MARKS = ("yes", "partly", "no")
MARK_LABELS = {"yes": "Yes", "partly": "In part", "no": "No"}
OUTSIDE_LABEL = "Shown for contrast"

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


def vtype(d: dict) -> str:
    return d.get("type") or "timeline"


def views(d: dict) -> list[dict]:
    """The views a visual compares: timeline lanes, spectrum positions or matrix columns."""
    return d.get({"timeline": "lanes", "spectrum": "positions", "matrix": "columns", "orgchart": "charts",
                  "chronology": "events"}.get(vtype(d), "lanes")) or []


def outside_label(view: dict) -> str:
    return view.get("outside_label") or OUTSIDE_LABEL if view.get("outside") else ""


# ---------------------------------------------------------------- loading and validation

def data_files(data_dir: Path = DATA_DIR) -> list[Path]:
    """Every data file; a file placed next to another visual's block comes after it."""
    def key(path: Path):
        try:
            place = json.dumps(load(path).get("place") or {})
        except (OSError, ValueError):
            place = ""
        return ("CC-TIMELINE:" in place, path.name)
    return sorted(data_dir.glob("*.json"), key=key)


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
    kind = vtype(d)
    if kind not in TYPES:
        return [f"type must be one of {sorted(TYPES)}"]
    for key in ("id", "slug", "label", "title", "image_title", "caption", "differ", "sources") + TYPE_KEYS[kind]:
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

    if kind == "timeline":
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
    elif kind == "spectrum":
        errs += validate_spectrum(d)
    elif kind == "orgchart":
        errs += validate_orgchart(d)
    elif kind == "chronology":
        errs += validate_chronology(d)
    else:
        errs += validate_matrix(d)
    for view in views(d):
        vid = view.get("id", "?")
        if not view.get("name"):
            errs.append(f"view {vid}: missing name")
        if view.get("color") and view["color"] not in COLORS:
            errs.append(f"view {vid}: unknown color {view['color']}")
        prop = view.get("proponent") or {}
        if not prop.get("name") or not prop.get("work"):
            errs.append(f"view {vid}: proponent needs name and work")
        if prop.get("source") not in sources:
            errs.append(f"view {vid}: proponent source {prop.get('source')!r} is not in sources")
        for extra in prop.get("also") or []:
            if extra not in sources:
                errs.append(f"view {vid}: also source {extra!r} is not in sources")

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


def _unique_ids(items: list[dict], what: str) -> list[str]:
    ids = [x.get("id") for x in items]
    if not all(ids) or len(set(ids)) != len(ids):
        return [f"{what} ids must be unique and present"]
    return [f"{what} id {i!r} must be kebab case" for i in ids if not ID_RE.match(str(i))]


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 100


def validate_spectrum(d: dict) -> list[str]:
    errs: list[str] = []
    axis, axis_y = d["axis"], d.get("axis_y")
    if not axis.get("left") or not axis.get("right"):
        errs.append("axis needs left and right")
    if axis_y is not None and (not axis_y.get("bottom") or not axis_y.get("top") or not axis_y.get("label")):
        errs.append("axis_y needs label, bottom and top")
    if not 2 <= len(d["positions"]) <= 7:
        errs.append("2 to 7 positions")
    errs += _unique_ids(d["positions"], "position")
    for pos in d["positions"]:
        pid = pos.get("id", "?")
        if not _num(pos.get("at")):
            errs.append(f"position {pid}: at must be a number from 0 to 100")
        if axis_y is not None and not _num(pos.get("y")):
            errs.append(f"position {pid}: y must be a number from 0 to 100 on a two-axis spectrum")
        if axis_y is None and "y" in pos:
            errs.append(f"position {pid}: y needs axis_y")
        if not pos.get("text"):
            errs.append(f"position {pid}: missing text")
    for band in d.get("bands") or []:
        if not (_num(band.get("from")) and _num(band.get("to")) and band["from"] < band["to"] and band.get("label")):
            errs.append(f"band {band.get('label')!r}: needs label and from < to, 0 to 100")
    return errs


def validate_matrix(d: dict) -> list[str]:
    errs: list[str] = []
    cols, rows = d["columns"], d["rows"]
    if not 2 <= len(cols) <= 5:
        errs.append("2 to 5 columns")
    if not 2 <= len(rows) <= 8:
        errs.append("2 to 8 rows")
    errs += _unique_ids(cols, "column") + _unique_ids(rows, "row")
    for row in rows:
        rid = row.get("id", "?")
        if not row.get("label"):
            errs.append(f"row {rid}: missing label")
        cells = row.get("cells") or []
        if len(cells) != len(cols):
            errs.append(f"row {rid}: needs one cell per column ({len(cols)})")
            continue
        for k, cell in enumerate(cells):
            if not cell.get("text"):
                errs.append(f"row {rid}: cell {k + 1} needs text")
            if cell.get("mark") not in (None, "") + MARKS:
                errs.append(f"row {rid}: mark must be one of {MARKS}")
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
    for view in views(d):
        p = view["proponent"].get("image_name") or view["proponent"]["name"]
        if p not in pubs:
            pubs.append(p)
    src = {s["id"]: s for s in d["sources"]}
    line = d.get("image_source") or "Voices: " + "; ".join(pubs)
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
            f'<desc id="{tid}-d">{esc(describe(d))}</desc><rect width="{w}" height="{h:.0f}" fill="#fff"/>')


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
    if vtype(d) == "spectrum":
        return render_spectrum(d, False)
    if vtype(d) == "matrix":
        return render_matrix(d, False)
    if vtype(d) == "orgchart":
        return render_orgchart(d, False)
    if vtype(d) == "chronology":
        return render_chronology(d, False)
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
    if vtype(d) == "spectrum":
        return render_spectrum(d, True)
    if vtype(d) == "matrix":
        return render_matrix(d, True)
    if vtype(d) == "orgchart":
        return render_orgchart(d, True)
    if vtype(d) == "chronology":
        return render_chronology(d, True)
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


# ---------------------------------------------------------------- spectrum and matrix

def describe(d: dict) -> str:
    """The whole visual in words, for the SVG <desc>."""
    kind = vtype(d)
    if kind == "timeline":
        return lane_desc(d)
    if kind == "orgchart":
        return orgchart_desc(d)
    if kind == "chronology":
        return chronology_desc(d)
    if kind == "spectrum":
        axis, axis_y = d["axis"], d.get("axis_y")
        out = [f"{axis.get('label') or 'Axis'}: from {axis['left']} to {axis['right']}."]
        if axis_y:
            out.append(f"{axis_y['label']}: from {axis_y['bottom']} to {axis_y['top']}.")
        for n, pos in enumerate(ordered(d), 1):
            where = placement(d, pos)
            tag = f" ({outside_label(pos)})" if pos.get("outside") else ""
            out.append(f"{n}. {pos['name']}{tag}: {where}. {pos['text']}")
        return " ".join(out)
    out = []
    for k, col in enumerate(d["columns"]):
        tag = f" ({outside_label(col)})" if col.get("outside") else ""
        bits = [f"{row['label']}: {row['cells'][k]['text']}" for row in d["rows"]]
        out.append(f"{col['name']}{tag}. " + "; ".join(bits) + ".")
    return " ".join(out)


def ordered(d: dict) -> list[dict]:
    """Spectrum positions left to right (then top to bottom), which is also their number order."""
    return sorted(d["positions"], key=lambda p: (p["at"], -p.get("y", 0)))


def _toward(label: str) -> str:
    return label[:1].lower() + label[1:]


def _where(at: float, low: str, high: str) -> str:
    if at <= 15:
        return f"at the {_toward(low)} end"
    if at < 40:
        return f"toward {_toward(low)}"
    if at <= 60:
        return "near the middle"
    if at < 85:
        return f"toward {_toward(high)}"
    return f"at the {_toward(high)} end"


def placement(d: dict, pos: dict) -> str:
    if pos.get("placement"):
        return pos["placement"]
    where = _where(pos["at"], d["axis"]["left"], d["axis"]["right"])
    if d.get("axis_y"):
        ay = d["axis_y"]
        where += f"; {_toward(ay['label'])}: " + _where(pos["y"], ay["bottom"], ay["top"]).replace("the ", "", 1)
    return where[:1].upper() + where[1:]


def mark_svg(mark: str | None, cx: float, cy: float, r: float, col: str) -> str:
    if mark == "yes":
        return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{col}"/>'
    if mark == "partly":
        return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="#fff" stroke="{col}" stroke-width="1.5"/>'
                f'<path d="M{cx:.1f},{cy - r:.1f} A{r},{r} 0 0 1 {cx:.1f},{cy + r:.1f} Z" fill="{col}"/>')
    if mark == "no":
        return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="#fff" stroke="{col}" stroke-width="1.5"/>'
    return ""


def badge(n: int, cx: float, cy: float, col: str, outside: bool, r: float = 10) -> str:
    if outside:
        return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="#fff" stroke="{col}" stroke-width="1.6" '
                f'stroke-dasharray="3 2"/>' + tx(cx, cy + 4, str(n), 11.5, col, "700", "middle"))
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{col}"/>'
            + tx(cx, cy + 4, str(n), 11.5, "#fff", "700", "middle"))


def card(pos: dict, n: int, x: float, y: float, w: float, h: float | None = None,
         size: float = 11.5, short: bool = False) -> tuple[str, float]:
    """A numbered card for one position; returns (svg, height). Pass h to stretch it."""
    col = color(pos.get("color"))
    inner = w - 34
    name_lines, ns = fit(pos.get("short") if short and pos.get("short") else pos["name"], inner, 13, True,
                         max_lines=2, floor=10.5)
    text = pos.get("short_text") if short and pos.get("short_text") else pos["text"]
    body = wrap(text, w - 18, size)
    prop = pos["proponent"].get("image_name") or pos["proponent"]["name"]
    eg = wrap(f"e.g. {prop}", w - 18, 10.5)
    tag = outside_label(pos)
    need = 12 + len(name_lines) * 15 + (13 if tag else 0) + 4 + len(body) * size * 1.25 + len(eg) * 13 + 8
    hh = h or need
    dash = ' stroke-dasharray="4 3"' if pos.get("outside") else ""
    parts = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{hh:.1f}" rx="6" fill="#fff" '
             f'stroke="{col if pos.get("outside") else GRID}" stroke-width="1.2"{dash}/>',
             f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="4" rx="2" fill="{col}"/>',
             badge(n, x + 15, y + 20, col, bool(pos.get("outside")), 9)]
    ty = y + 24
    for ln in name_lines:
        parts.append(tx(x + 29, ty, ln, ns, col, "700"))
        ty += 15
    if tag:
        parts.append(tx(x + 29, ty - 1, tag, 10.5, GREY, "600"))
        ty += 13
    ty += 4
    for ln in body:
        parts.append(tx(x + 9, ty, ln, size, INK))
        ty += size * 1.25
    for ln in eg:
        parts.append(tx(x + 9, ty, ln, 10.5, GREY))
        ty += 13
    return "".join(parts), need


def axis_strip(d: dict, x0: float, x1: float, y: float, narrow: bool) -> tuple[list[str], float]:
    """The one-axis line with bands, end labels and numbered dots; returns (parts, bottom y)."""
    axis = d["axis"]
    parts = []
    pos_sorted = ordered(d)
    # stagger dots that would touch, upward in rows
    rows, last = [], {}
    for p in pos_sorted:
        px = x0 + 16 + p["at"] / 100 * (x1 - x0 - 32)
        row = 0
        while row in last and px - last[row] < 23:
            row += 1
        last[row] = px
        rows.append((p, px, row))
    lift = max((r for _, _, r in rows), default=0) * 23
    bands = d.get("bands") or []
    top = y + lift + (22 if bands else 0)
    line_y = top + 12
    for b in bands:
        bx0, bx1 = x0 + b["from"] / 100 * (x1 - x0), x0 + b["to"] / 100 * (x1 - x0)
        parts.append(f'<rect x="{bx0:.1f}" y="{line_y - 9:.1f}" width="{bx1 - bx0:.1f}" height="18" rx="4" fill="{SHADE}"/>')
        lines, s = fit(b["label"], bx1 - bx0 - 4, 10.5, True, max_lines=1, floor=8.5)
        parts.append(tx((bx0 + bx1) / 2, y + 10, lines[0], s, "#2C4A2E", "700", "middle"))
    parts.append(f'<line x1="{x0:.1f}" x2="{x1:.1f}" y1="{line_y:.1f}" y2="{line_y:.1f}" stroke="{GREY}" '
                 f'stroke-width="2"/>')
    for xx, sgn in ((x0, 1), (x1, -1)):
        parts.append(f'<path d="M{xx:.1f},{line_y:.1f} l{8 * sgn},-5 v10 Z" fill="{GREY}"/>')
    for n, (p, px, row) in enumerate(rows, 1):
        col = color(p.get("color"))
        cy = line_y - row * 23
        if row:
            parts.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{cy:.1f}" y2="{line_y:.1f}" stroke="{col}" '
                         f'stroke-width="1.5"/>')
        parts.append(badge(n, px, cy, col, bool(p.get("outside"))))
    ly = line_y + 26
    size = 11.5 if narrow else 12.5
    parts.append(tx(x0, ly, axis["left"], size, INK, "700"))
    parts.append(tx(x1, ly, axis["right"], size, INK, "700", "end"))
    if axis.get("label") and not narrow:
        parts.append(tx((x0 + x1) / 2, ly, axis["label"], 11, GREY, None, "middle"))
    return parts, ly + 10


def plot_2d(d: dict, x: float, y: float, w: float, h: float) -> list[str]:
    """Two-axis spectrum: a plot with labelled ends and numbered dots."""
    axis, ay = d["axis"], d["axis_y"]
    margin = 22
    px0, px1, py0, py1 = x + margin, x + w, y, y + h - 30
    parts = [f'<rect x="{px0:.1f}" y="{py0:.1f}" width="{px1 - px0:.1f}" height="{py1 - py0:.1f}" rx="6" '
             f'fill="#faf9f7" stroke="{GRID}"/>',
             f'<line x1="{(px0 + px1) / 2:.1f}" x2="{(px0 + px1) / 2:.1f}" y1="{py0:.1f}" y2="{py1:.1f}" '
             f'stroke="{GRID}" stroke-dasharray="3 3"/>',
             f'<line x1="{px0:.1f}" x2="{px1:.1f}" y1="{(py0 + py1) / 2:.1f}" y2="{(py0 + py1) / 2:.1f}" '
             f'stroke="{GRID}" stroke-dasharray="3 3"/>']
    cy = (py0 + py1) / 2
    lx = x + 8
    parts.append(f'<text x="{lx:.1f}" y="{cy:.1f}" font-size="11" fill="{GREY}" font-weight="700" '
                 f'text-anchor="middle" transform="rotate(-90 {lx:.1f} {cy:.1f})">{esc(ay["label"])}</text>')
    parts.append(tx(px0 + 6, py0 + 14, ay["top"], 11, INK, "700"))
    parts.append(tx(px0 + 6, py1 - 7, ay["bottom"], 11, INK, "700"))
    parts.append(tx(px0, py1 + 16, axis["left"], 11.5, INK, "700"))
    parts.append(tx(px1, py1 + 16, axis["right"], 11.5, INK, "700", "end"))
    if axis.get("label"):
        parts.append(tx((px0 + px1) / 2, py1 + 28, axis["label"], 11, GREY, "700", "middle"))
    inset = 22
    dots = []
    for n, p in enumerate(ordered(d), 1):
        cx = px0 + inset + p["at"] / 100 * (px1 - px0 - 2 * inset)
        cyy = py1 - 26 - p["y"] / 100 * (py1 - py0 - 52)
        dots.append((n, p, cx, cyy))
    taken = [(cx - 12, cyy - 12, cx + 12, cyy + 12) for _, _, cx, cyy in dots]
    for n, p, cx, cyy in dots:
        col = color(p.get("color"))
        parts.append(badge(n, cx, cyy, col, bool(p.get("outside")), 11))
        name = p.get("short") or p["name"]
        tw = text_w(name, 11.5, True)
        cands = [(cx + 15, cyy + 4, None), (cx - 15, cyy + 4, "end"),
                 (cx, cyy - 17, "middle"), (cx, cyy + 26, "middle")]
        best = None
        for lx, ly, anchor in cands:
            bx0 = lx if anchor is None else (lx - tw if anchor == "end" else lx - tw / 2)
            box = (bx0, ly - 11, bx0 + tw, ly + 3)
            inside = px0 + 2 <= box[0] and box[2] <= px1 - 2 and py0 <= box[1] and box[3] <= py1
            clash = any(not (box[2] < t[0] or box[0] > t[2] or box[3] < t[1] or box[1] > t[3]) for t in taken)
            if inside and not clash:
                best = (lx, ly, anchor, box)
                break
        if best is None:
            lx, ly, anchor = cands[0]
            best = (lx, ly, anchor, (lx, ly - 11, lx + tw, ly + 3))
        lx, ly, anchor, box = best
        taken.append(box)
        parts.append(tx(lx, ly, name, 11.5, col, "700", anchor))
    return parts


def render_spectrum(d: dict, narrow: bool) -> str:
    w = W_NARROW if narrow else W_WIDE
    sub = (d.get("image_subtitle_narrow") if narrow else None) or d.get("image_subtitle", "")
    parts, y = header(d, w, sub)
    pos = ordered(d)
    if d.get("axis_y"):
        if narrow:
            ph = 250
            parts += plot_2d(d, PAD, y, w - 2 * PAD, ph)
            y += ph + 10
            for n, p in enumerate(pos, 1):
                svg, h = card(p, n, PAD, y, w - 2 * PAD, short=True)
                parts.append(svg)
                y += h + 8
        else:
            plot_w = 400
            ph = 330
            parts += plot_2d(d, PAD, y, plot_w, ph)
            cx0 = PAD + plot_w + 16
            cy = y
            heights = [card(p, n, 0, 0, w - PAD - cx0, size=11)[1] for n, p in enumerate(pos, 1)]
            gap = max(6.0, (ph - sum(heights)) / max(1, len(pos) - 1)) if sum(heights) < ph else 6.0
            for n, p in enumerate(pos, 1):
                svg, h = card(p, n, cx0, cy, w - PAD - cx0, size=11)
                parts.append(svg)
                cy += h + min(gap, 14)
            y = max(y + ph, cy)
    else:
        strip, y = axis_strip(d, PAD + 4, w - PAD - 4, y, narrow)
        parts += strip
        y += 8
        if narrow:
            for n, p in enumerate(pos, 1):
                svg, h = card(p, n, PAD, y, w - 2 * PAD, short=True)
                parts.append(svg)
                y += h + 8
        else:
            gap = 8
            cw = (w - 2 * PAD - gap * (len(pos) - 1)) / len(pos)
            size = 11.5 if cw >= 130 else 11
            h = max(card(p, n, 0, 0, cw, size=size)[1] for n, p in enumerate(pos, 1))
            for n, p in enumerate(pos, 1):
                parts.append(card(p, n, PAD + (n - 1) * (cw + gap), y, cw, h, size=size)[0])
            y += h
    foot, y = footer(d, y + 12, w, 11)
    return svg_open(d, w, y, narrow) + "".join(parts) + foot + "</svg>"


def col_head(col: dict, x: float, y: float, w: float, h: float, size: float, short: bool) -> str:
    c = color(col.get("color"))
    lines, s = fit(col.get("short") if short and col.get("short") else col["name"], w - 8, size, True,
                   max_lines=3, floor=9.5)
    tag = outside_label(col)
    parts = []
    if col.get("outside"):
        parts.append(f'<rect x="{x + 2:.1f}" y="{y:.1f}" width="{w - 4:.1f}" height="{h:.1f}" rx="5" fill="#fff" '
                     f'stroke="{c}" stroke-dasharray="4 3"/>')
    body_h = len(lines) * s * 1.18 + (12 if tag else 0)
    cy = y + (h - 4) / 2 - (6 if tag else 0)
    parts.append(block_text(lines, x + w / 2, cy, s, c, "700"))
    if tag:
        parts.append(tx(x + w / 2, cy + body_h / 2 + 6, tag, 9.5, GREY, "600", "middle"))
    parts.append(f'<rect x="{x + 6:.1f}" y="{y + h - 4:.1f}" width="{w - 12:.1f}" height="3" rx="1.5" fill="{c}"/>')
    return "".join(parts)


def mark_legend(d: dict, x: float, y: float) -> tuple[str, float]:
    used = [m for m in MARKS if any(c.get("mark") == m for r in d["rows"] for c in r["cells"])]
    if not used:
        return "", y
    labels = {**MARK_LABELS, **(d.get("mark_labels") or {})}
    parts, xx = [], x
    for m in used:
        parts.append(mark_svg(m, xx + 6, y - 4, 5.5, INK))
        parts.append(tx(xx + 16, y, labels[m], 11, GREY))
        xx += 26 + text_w(labels[m], 11)
    return "".join(parts), y + 14


def render_matrix(d: dict, narrow: bool) -> str:
    w = W_NARROW if narrow else W_WIDE
    sub = (d.get("image_subtitle_narrow") if narrow else None) or d.get("image_subtitle", "")
    parts, y = header(d, w, sub)
    cols, rows = d["columns"], d["rows"]
    legend, y = mark_legend(d, PAD, y + 2)
    parts.append(legend)
    if narrow:
        name_w = 96
        for row in rows:
            lines, s = fit(row.get("short") or row["label"], w - 2 * PAD - 12, 12.5, True, max_lines=2)
            hh = len(lines) * s * 1.2 + 10
            parts.append(f'<rect x="{PAD:.1f}" y="{y:.1f}" width="{w - 2 * PAD:.1f}" height="{hh:.1f}" rx="4" '
                         f'fill="{SHADE}"/>')
            for k, ln in enumerate(lines):
                parts.append(tx(PAD + 6, y + 5 + s + k * s * 1.2, ln, s, "#2C4A2E", "700"))
            y += hh + 4
            for k, col in enumerate(cols):
                c = color(col.get("color"))
                cell = row["cells"][k]
                nlines, ns = fit(col.get("short") or col["name"], name_w - 4, 11.5, True, max_lines=2, floor=9.5)
                mark = cell.get("mark")
                tx0 = PAD + name_w + (18 if mark else 4)
                body = wrap(cell.get("short") or cell["text"], w - PAD - tx0, 11.5)
                hh = max(len(nlines) * ns * 1.18, len(body) * 14.5) + 8
                for j, ln in enumerate(nlines):
                    parts.append(tx(PAD + 2, y + 4 + ns + j * ns * 1.18, ln, ns, c, "700"))
                if mark:
                    parts.append(mark_svg(mark, PAD + name_w + 8, y + 4 + 7, 5.5, c))
                for j, ln in enumerate(body):
                    parts.append(tx(tx0, y + 4 + 11.5 + j * 14.5, ln, 11.5, INK))
                y += hh
                if k < len(cols) - 1:
                    parts.append(f'<line x1="{PAD + 2:.1f}" x2="{w - PAD:.1f}" y1="{y - 3:.1f}" y2="{y - 3:.1f}" '
                                 f'stroke="{GRID}" stroke-opacity="0.6"/>')
            y += 8
    else:
        label_w = 128
        cw = (w - 2 * PAD - label_w) / len(cols)
        head_h = max(40.0, max(len(fit(c["name"], cw - 8, 12.5, True, max_lines=3, floor=9.5)[0]) * 15
                               + (14 if c.get("outside") else 0) + 12 for c in cols))
        for k, col in enumerate(cols):
            parts.append(col_head(col, PAD + label_w + k * cw, y, cw, head_h, 12.5, False))
        y += head_h + 4
        for i, row in enumerate(rows):
            rl, rs = fit(row["label"], label_w - 10, 12, True, max_lines=4)
            cells = []
            hh = len(rl) * rs * 1.2 + 14
            for k, col in enumerate(cols):
                cell = row["cells"][k]
                indent = 16 if cell.get("mark") else 0
                body = wrap(cell["text"], cw - 12 - indent, 11)
                cells.append((cell, body, indent))
                hh = max(hh, len(body) * 13.8 + 14)
            if i % 2 == 0:
                parts.append(f'<rect x="{PAD:.1f}" y="{y:.1f}" width="{w - 2 * PAD:.1f}" height="{hh:.1f}" rx="4" '
                             f'fill="#faf9f7"/>')
            for j, ln in enumerate(rl):
                parts.append(tx(PAD + 6, y + 7 + rs + j * rs * 1.2, ln, rs, INK, "700"))
            for k, (cell, body, indent) in enumerate(cells):
                c = color(cols[k].get("color"))
                x0 = PAD + label_w + k * cw + 6
                if cell.get("mark"):
                    parts.append(mark_svg(cell["mark"], x0 + 6, y + 14, 5.5, c))
                for j, ln in enumerate(body):
                    parts.append(tx(x0 + indent, y + 18 + j * 13.8, ln, 11, INK))
            y += hh
            parts.append(f'<line x1="{PAD:.1f}" x2="{w - PAD:.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>')
    foot, y = footer(d, y + 12, w, 11)
    return svg_open(d, w, y, narrow) + "".join(parts) + foot + "</svg>"


# ---------------------------------------------------------------- org charts and chronologies

ARROW_KINDS = ("down", "up", "loose")
ARROW_LABELS = {"down": "Authority or oversight", "up": "Elects or consents", "loose": "Cooperation, no authority"}


def validate_orgchart(d: dict) -> list[str]:
    errs: list[str] = []
    tiers, charts = d["tiers"], d["charts"]
    if not 2 <= len(tiers) <= 5:
        errs.append("2 to 5 tiers")
    if not 2 <= len(charts) <= 4:
        errs.append("2 to 4 charts")
    errs += _unique_ids(tiers, "tier") + _unique_ids(charts, "chart")
    tier_ids = [t.get("id") for t in tiers]
    for t in tiers:
        if not t.get("label"):
            errs.append(f"tier {t.get('id')}: missing label")
    for ch in charts:
        cid = ch.get("id", "?")
        boxes = ch.get("boxes") or []
        if [b.get("tier") for b in boxes] != tier_ids:
            errs.append(f"chart {cid}: needs one box per tier, in tier order")
        for b in boxes:
            if not b.get("text"):
                errs.append(f"chart {cid}: box {b.get('tier')} needs text")
        for link in ch.get("links") or []:
            pair = link.get("between") or []
            if len(pair) != 2 or any(x not in tier_ids for x in pair) or \
                    tier_ids.index(pair[1]) != tier_ids.index(pair[0]) + 1:
                errs.append(f"chart {cid}: link {pair} must join two neighbouring tiers, top first")
                continue
            kinds = [k for k in ARROW_KINDS if link.get(k)]
            if not kinds:
                errs.append(f"chart {cid}: link {pair} needs down, up or loose")
            if link.get("loose") and len(kinds) > 1:
                errs.append(f"chart {cid}: a loose link stands alone")
    return errs


def validate_chronology(d: dict) -> list[str]:
    errs: list[str] = []
    events = d["events"]
    if not 3 <= len(events) <= 8:
        errs.append("3 to 8 events")
    errs += _unique_ids(events, "event")
    years = []
    for ev in events:
        eid = ev.get("id", "?")
        for key in ("date", "text"):
            if not ev.get(key):
                errs.append(f"event {eid}: missing {key}")
        if not isinstance(ev.get("year"), int) or isinstance(ev.get("year"), bool):
            errs.append(f"event {eid}: year must be a whole number (for order)")
        else:
            years.append(ev["year"])
    if years != sorted(years):
        errs.append("events must run in date order")
    return errs


def arrow(kind: str, x: float, y0: float, y1: float, col: str) -> str:
    """A vertical connector from y0 (upper box) to y1 (lower box)."""
    if kind == "loose":
        return (f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y0:.1f}" y2="{y1:.1f}" stroke="{GREY}" '
                f'stroke-width="1.6" stroke-dasharray="2 3"/>')
    dash = ' stroke-dasharray="5 3"' if kind == "up" else ""
    if kind == "down":
        tip, back = y1, y1 - 7
        line = (y0, back)
    else:
        tip, back = y0, y0 + 7
        line = (back, y1)
    return (f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{line[0]:.1f}" y2="{line[1]:.1f}" stroke="{col}" '
            f'stroke-width="1.6"{dash}/>'
            f'<path d="M{x - 4.5:.1f},{back:.1f} L{x + 4.5:.1f},{back:.1f} L{x:.1f},{tip:.1f} Z" fill="{col}"/>')


def arrow_legend(kinds: list[str], x: float, y: float, w: float) -> tuple[str, float]:
    parts, xx = [], x
    for k in kinds:
        label = ARROW_LABELS[k]
        lw = 30 + text_w(label, 11)
        if xx + lw > x + w:
            xx, y = x, y + 16
        col = GREY if k == "loose" else INK
        dash = {"down": "", "up": ' stroke-dasharray="5 3"', "loose": ' stroke-dasharray="2 3"'}[k]
        parts.append(f'<line x1="{xx:.1f}" x2="{xx + 18:.1f}" y1="{y - 4:.1f}" y2="{y - 4:.1f}" stroke="{col}" '
                     f'stroke-width="1.6"{dash}/>')
        if k == "down":
            parts.append(f'<path d="M{xx + 18:.1f},{y - 8:.1f} L{xx + 18:.1f},{y:.1f} L{xx + 24:.1f},{y - 4:.1f} Z" fill="{INK}"/>')
        elif k == "up":
            parts.append(f'<path d="M{xx:.1f},{y - 8:.1f} L{xx:.1f},{y:.1f} L{xx - 6:.1f},{y - 4:.1f} Z" fill="{INK}"/>')
        parts.append(tx(xx + 30, y, label, 11, GREY))
        xx += lw + 14
    return "".join(parts), y + 16


def _links(ch: dict) -> dict:
    return {tuple(l["between"]): l for l in ch.get("links") or []}


def org_box(b: dict, x: float, y: float, w: float, col: str, h: float | None = None,
            size: float = 11.5) -> tuple[str, float]:
    lines = wrap(b["text"], w - 14, size, True)
    sub = wrap(b["sub"], w - 14, 10.5) if b.get("sub") else []
    need = 10 + len(lines) * size * 1.2 + len(sub) * 12.6 + 6
    hh = h or need
    if b.get("loose"):
        shape = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{hh:.1f}" rx="6" fill="#fff" '
                 f'stroke="{GREY}" stroke-width="1.2" stroke-dasharray="2 3"/>')
    else:
        shape = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{hh:.1f}" rx="6" fill="#fff"/>'
                 f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{hh:.1f}" rx="6" fill="{col}" '
                 f'fill-opacity="0.11" stroke="{col}" stroke-width="1.2"/>')
    parts = [shape]
    ty = y + (hh - need) / 2 + 6 + size
    for ln in lines:
        parts.append(tx(x + w / 2, ty, ln, size, INK if b.get("loose") else col, "700", "middle"))
        ty += size * 1.2
    for ln in sub:
        parts.append(tx(x + w / 2, ty, ln, 10.5, GREY, None, "middle"))
        ty += 12.6
    return "".join(parts), need


def gap_parts(link: dict | None, x: float, w: float, y0: float, col: str, label_w: float,
              gh: float | None = None) -> tuple[list[str], float]:
    """Arrows and their labels between two boxes of one chart; returns (parts, gap height).
    Pass gh to draw at a set height, so the arrows in one row share a length."""
    if not link:
        return [], gh or 18.0
    kinds = [k for k in ARROW_KINDS if link.get(k)]
    slots = [x + w * ((0.2, 0.6)[i] if len(kinds) > 1 else 0.4) for i in range(len(kinds))]
    labelled = [(k, sx, wrap(link[k], label_w, 10)) for k, sx in zip(kinds, slots)]
    gh = gh or max(26.0, max(len(lines) * 11.5 for _, _, lines in labelled) + 12)
    parts = []
    for k, sx, lines in labelled:
        parts.append(arrow(k, sx, y0 + 2, y0 + gh - 2, col))
        ty = y0 + gh / 2 - (len(lines) - 1) * 5.75 + 3.5
        for j, ln in enumerate(lines):
            parts.append(tx(sx + 8, ty + j * 11.5, ln, 10, GREY))
    return parts, gh


def render_orgchart(d: dict, narrow: bool) -> str:
    w = W_NARROW if narrow else W_WIDE
    sub = (d.get("image_subtitle_narrow") if narrow else None) or d.get("image_subtitle", "")
    parts, y = header(d, w, sub)
    tiers, charts = d["tiers"], d["charts"]
    used = [k for k in ARROW_KINDS if any(l.get(k) for ch in charts for l in ch.get("links") or [])]
    legend, y = arrow_legend(used, PAD, y + 2, w - 2 * PAD)
    parts.append(legend)
    y += 4
    if narrow:
        bw = w - 2 * PAD
        for ch in charts:
            col = color(ch.get("color"))
            parts.append(col_head(ch, PAD, y, bw, 30, 13, True))
            y += 34
            if ch.get("tag"):
                for ln in wrap(ch["tag"], bw, 10.5):
                    parts.append(tx(PAD + bw / 2, y + 8, ln, 10.5, GREY, None, "middle"))
                    y += 13
                y += 4
            links = _links(ch)
            for i, b in enumerate(ch["boxes"]):
                svg, h = org_box(b, PAD + 20, y, bw - 40, col)
                parts.append(svg)
                y += h
                if i < len(tiers) - 1:
                    g, gh = gap_parts(links.get((tiers[i]["id"], tiers[i + 1]["id"])), PAD + 20, bw - 40, y, col,
                                      (bw - 40) * 0.36)
                    parts += g
                    y += gh
            y += 18
    else:
        label_w = 86
        n = len(charts)
        pw = (w - 2 * PAD - label_w) / n
        bw = pw - 16
        head_h = max(36.0, max(len(fit(c["name"], pw - 8, 12.5, True, max_lines=3, floor=9.5)[0]) * 15 + 12
                               for c in charts))
        for k, ch in enumerate(charts):
            parts.append(col_head(ch, PAD + label_w + k * pw, y, pw, head_h, 12.5, False))
        y += head_h + 4
        if any(c.get("tag") for c in charts):
            tag_lines = [wrap(c.get("tag", ""), pw - 12, 10.5) for c in charts]
            for k, lines in enumerate(tag_lines):
                for j, ln in enumerate(lines):
                    parts.append(tx(PAD + label_w + k * pw + pw / 2, y + 10 + j * 12.5, ln, 10.5, GREY, None, "middle"))
            y += max(len(l) for l in tag_lines) * 12.5 + 8
        for i, t in enumerate(tiers):
            h = max(org_box(ch["boxes"][i], 0, 0, bw, INK)[1] for ch in charts)
            tl, ts = fit(t["label"], label_w - 8, 11, True, max_lines=3)
            lh = ts * 1.18
            ty = y + h / 2 - lh * (len(tl) - 1) / 2 + ts * 0.35
            for j, ln in enumerate(tl):
                parts.append(tx(PAD, ty + j * lh, ln, ts, GREY, "700"))
            for k, ch in enumerate(charts):
                parts.append(org_box(ch["boxes"][i], PAD + label_w + k * pw + 8, y, bw, color(ch.get("color")), h)[0])
            y += h
            if i < len(tiers) - 1:
                args = [(_links(ch).get((t["id"], tiers[i + 1]["id"])), PAD + label_w + k * pw + 8, bw, y,
                         color(ch.get("color")), bw * 0.4) for k, ch in enumerate(charts)]
                gh = max(gap_parts(*a)[1] for a in args)
                for a in args:
                    parts += gap_parts(*a, gh=gh)[0]
                y += gh
    foot, y = footer(d, y + 12, w, 11)
    return svg_open(d, w, y, narrow) + "".join(parts) + foot + "</svg>"


def orgchart_desc(d: dict) -> str:
    tiers = d["tiers"]
    out = []
    for ch in d["charts"]:
        links = _links(ch)
        bits = []
        for i, b in enumerate(ch["boxes"]):
            box = b["text"] + (f" ({b['sub']})" if b.get("sub") else "")
            if b.get("loose"):
                box += ", cooperative only"
            bits.append(f"{tiers[i]['label']}: {box}")
            if i < len(tiers) - 1:
                link = links.get((tiers[i]["id"], tiers[i + 1]["id"])) or {}
                for k in ARROW_KINDS:
                    if link.get(k):
                        arrow_word = {"down": "downward, authority", "up": "upward, elects or consents",
                                      "loose": "cooperation only"}[k]
                        bits.append(f"link {arrow_word}: {link[k]}")
        out.append(f"{ch['name']}. " + "; ".join(bits) + ".")
    return " ".join(out)


def orgchart_table(d: dict) -> str:
    charts, tiers = d["charts"], d["tiers"]
    head = (f'<th scope="col">{esc(d.get("table_view_label") or "Level")}</th>'
            + "".join(f'<th scope="col">{esc(c["name"])}</th>' for c in charts))
    rows = []
    for i, t in enumerate(tiers):
        cells = []
        for c in charts:
            b = c["boxes"][i]
            text = b["text"] + (f": {b['sub']}" if b.get("sub") else "")
            if b.get("loose"):
                text += " (cooperation, no authority)"
            cells.append(f'<td data-label="{esc(c["name"])}">{esc(text)}</td>')
        rows.append(f'<tr><th scope="row">{esc(t["label"])}</th>{"".join(cells)}</tr>')
    links_cells = []
    for c in charts:
        bits = []
        for l in c.get("links") or []:
            for k in ARROW_KINDS:
                if l.get(k):
                    bits.append(l[k])
        links_cells.append(f'<td data-label="{esc(c["name"])}">{esc("; ".join(bits))}</td>')
    rows.append(f'<tr><th scope="row">Lines of authority</th>{"".join(links_cells)}</tr>')
    return _table(d, head, rows)


def event_card(ev: dict, x: float, y: float, w: float, h: float | None = None, short: bool = False,
               size: float = 11) -> tuple[str, float]:
    col = color(ev.get("color"))
    name = ev.get("short") if short and ev.get("short") else ev["name"]
    name_lines = wrap(name, w - 18, 12.5, True)
    who = wrap(ev["who"], w - 18, 10.5) if ev.get("who") else []
    body = wrap(ev.get("short_text") if short and ev.get("short_text") else ev["text"], w - 18, size)
    tag = outside_label(ev)
    need = 10 + 13 + len(name_lines) * 15 + (13 if tag else 0) + len(who) * 13 + 3 + len(body) * size * 1.25 + 6
    hh = h or need
    dash = ' stroke-dasharray="4 3"' if ev.get("outside") else ""
    parts = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{hh:.1f}" rx="6" fill="#fff" '
             f'stroke="{col if ev.get("outside") else GRID}" stroke-width="1.2"{dash}/>',
             f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="4" rx="2" fill="{col}"/>']
    ty = y + 19
    parts.append(tx(x + 9, ty, ev["date"], 11, col, "700"))
    ty += 15
    for ln in name_lines:
        parts.append(tx(x + 9, ty, ln, 12.5, INK, "700"))
        ty += 15
    if tag:
        parts.append(tx(x + 9, ty - 1, tag, 10.5, GREY, "600"))
        ty += 13
    for ln in who:
        parts.append(tx(x + 9, ty, ln, 10.5, GREY))
        ty += 13
    ty += 3
    for ln in body:
        parts.append(tx(x + 9, ty, ln, size, INK))
        ty += size * 1.25
    return "".join(parts), need


def render_chronology(d: dict, narrow: bool) -> str:
    w = W_NARROW if narrow else W_WIDE
    sub = (d.get("image_subtitle_narrow") if narrow else None) or d.get("image_subtitle", "")
    parts, y = header(d, w, sub)
    events = d["events"]
    if narrow:
        lx = PAD + 8
        cx0, cw = PAD + 24, w - 2 * PAD - 24
        y0 = y
        cards = []
        for ev in events:
            svg, h = event_card(ev, cx0, y, cw, short=True)
            cards.append((ev, y, svg))
            y += h + 10
        parts.append(f'<line x1="{lx:.1f}" x2="{lx:.1f}" y1="{y0 + 10:.1f}" y2="{y - 20:.1f}" stroke="{GRID}" '
                     f'stroke-width="3"/>')
        for ev, cy, svg in cards:
            col = color(ev.get("color"))
            parts.append(f'<line x1="{lx:.1f}" x2="{cx0:.1f}" y1="{cy + 19:.1f}" y2="{cy + 19:.1f}" stroke="{col}"/>')
            parts.append(_dot(lx, cy + 19, col, ev.get("outside")))
            parts.append(svg)
    else:
        n = len(events)
        s = (w - 2 * PAD) / n
        gap = 12.0
        above = [i for i in range(n) if i % 2 == 0]
        below = [i for i in range(n) if i % 2 == 1]
        # Cards alternate above and below the line; each row is spread evenly across the width
        # (a shorter lower row is offset by half a card), so every dot sits under its own card.
        cw = (w - 2 * PAD - (len(above) - 1) * gap) / len(above)
        offset = {i: k * (cw + gap) for k, i in enumerate(above)}
        shift = (cw + gap) / 2 if len(below) < len(above) else 0.0
        offset.update({i: shift + k * (cw + gap) for k, i in enumerate(below)})
        heights = [event_card(ev, 0, 0, cw)[1] for ev in events]
        ha = max(heights[i] for i in above)
        hb = max((heights[i] for i in below), default=0)
        line_y = y + ha + 20
        parts.append(f'<line x1="{PAD:.1f}" x2="{w - PAD:.1f}" y1="{line_y:.1f}" y2="{line_y:.1f}" stroke="{GRID}" '
                     f'stroke-width="3"/>')
        parts.append(f'<path d="M{w - PAD:.1f},{line_y - 6:.1f} L{w - PAD + 8:.1f},{line_y:.1f} '
                     f'L{w - PAD:.1f},{line_y + 6:.1f} Z" fill="{GRID}"/>')
        for i, ev in enumerate(events):
            col = color(ev.get("color"))
            cx = PAD + s * (i + 0.5)
            x = PAD + offset[i]
            if i in above:
                cy = line_y - 20 - ha
                parts.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{cy + ha:.1f}" y2="{line_y:.1f}" stroke="{col}"/>')
                parts.append(event_card(ev, x, cy, cw, ha)[0])
            else:
                cy = line_y + 20
                parts.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{line_y:.1f}" y2="{cy:.1f}" stroke="{col}"/>')
                parts.append(event_card(ev, x, cy, cw, hb)[0])
            parts.append(_dot(cx, line_y, col, ev.get("outside")))
        y = line_y + 20 + hb
    foot, y = footer(d, y + 12, w, 11)
    return svg_open(d, w, y, narrow) + "".join(parts) + foot + "</svg>"


def _dot(cx: float, cy: float, col: str, outside: bool | None) -> str:
    if outside:
        return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6.5" fill="#fff" stroke="{col}" stroke-width="1.8" '
                f'stroke-dasharray="3 2"/>')
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6.5" fill="{col}" stroke="#fff" stroke-width="2"/>'


def chronology_desc(d: dict) -> str:
    out = ["In date order."]
    for n, ev in enumerate(d["events"], 1):
        tag = f" ({outside_label(ev)})" if ev.get("outside") else ""
        who = f", {ev['who']}" if ev.get("who") else ""
        out.append(f"{n}. {ev['date']}: {ev['name']}{tag}{who}. {ev['text']}")
    return " ".join(out)


def chronology_table(d: dict) -> str:
    head = ('<th scope="col">When</th>'
            f'<th scope="col">{esc(d.get("table_view_label") or "View")}</th>'
            '<th scope="col">Who and where</th><th scope="col">In short</th>')
    rows = []
    for ev in d["events"]:
        tag = f" ({esc(outside_label(ev))})" if ev.get("outside") else ""
        rows.append(f'<tr><th scope="row">{esc(ev["date"])}</th>'
                    f'<td data-label="{esc(d.get("table_view_label") or "View")}">{esc(ev["name"])}{tag}</td>'
                    f'<td data-label="Who and where">{esc(ev.get("who", ""))}</td>'
                    f'<td data-label="In short">{esc(ev["text"])}</td></tr>')
    return _table(d, head, rows)


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


def _table(d: dict, head: str, rows: list[str]) -> str:
    return (f'<details class="cc-chart-data"><summary>Table version</summary><div class="cc-chart-scroll">'
            f'<table class="cc-timeline-table cc-chart-stack"><caption>{esc(d["image_title"])}</caption>'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div></details>')


def table_html(d: dict) -> str:
    if vtype(d) == "orgchart":
        return orgchart_table(d)
    if vtype(d) == "chronology":
        return chronology_table(d)
    if vtype(d) == "spectrum":
        where = d["axis"].get("label") or "Where it sits"
        if d.get("axis_y"):
            where = "Where it sits"
        head = (f'<th scope="col">{esc(d.get("table_view_label") or "View")}</th>'
                f'<th scope="col">{esc(where)}</th><th scope="col">In short</th>')
        rows = []
        for n, p in enumerate(ordered(d), 1):
            tag = f" ({esc(outside_label(p))})" if p.get("outside") else ""
            rows.append(f'<tr><th scope="row">{n}. {esc(p["name"])}{tag}</th>'
                        f'<td data-label="{esc(where)}">{esc(placement(d, p))}</td>'
                        f'<td data-label="In short">{esc(p["text"])}</td></tr>')
        return _table(d, head, rows)
    if vtype(d) == "matrix":
        cols = d["columns"]
        head = (f'<th scope="col">{esc(d.get("table_view_label") or "Question")}</th>'
                + "".join(f'<th scope="col">{esc(c["name"])}'
                          + (f" ({esc(outside_label(c))})" if c.get("outside") else "") + "</th>" for c in cols))
        rows = []
        for row in d["rows"]:
            cells = "".join(f'<td data-label="{esc(c["name"])}">{esc(row["cells"][k]["text"])}</td>'
                            for k, c in enumerate(cols))
            rows.append(f'<tr><th scope="row">{esc(row["label"])}</th>{cells}</tr>')
        return _table(d, head, rows)
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
    for view in views(d):
        p = view["proponent"]
        s = src[p["source"]]
        who = voice_html(p, voices)
        pub = "" if s["publisher"] == p["name"] else f'{esc(s["publisher"])}, '
        tag = f" ({esc(outside_label(view))})" if view.get("outside") else ""
        more = "".join(f"; {link(src[x])}{year(src[x])}" for x in p.get("also") or [])
        voices_li.append(
            f'<li><span class="cc-timeline-swatch" style="background:{color(view.get("color"))}"></span>'
            f'<strong>{esc(view["name"])}{tag}:</strong> {who}, {pub}{link(s, p["work"])}{year(s)}{more}</li>')
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
        f'<div class="cc-timeline-voices"><div class="cc-timeline-sub">{esc(d.get("voices_label") or "One voice for each view")}</div>'
        f'<ul>{"".join(voices_li)}</ul></div>\n'
        f'<p class="cc-chart-source">{method}{esc(d.get("note") or "No view is presented here as the answer.")} '
        f'Chart by Christian Curator.</p>\n'
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
    inner = int(round((width - 2 * pad) * vh / vw))
    height = max(inner + 2 * pad, MIN_SHARE_H)   # X crops a short card; keep it near 1200 x 630 or taller
    top = (height - inner) // 2
    fonts = (f"@font-face{{font-family:'Source Sans 3';src:url('{(FONTS / 'SourceSans3-Variable.ttf').as_uri()}');"
             f"font-weight:200 900;}}@font-face{{font-family:'Lora';src:url('{(FONTS / 'Lora-Variable.ttf').as_uri()}');"
             f"font-weight:400 700;}}")
    page = (f"<!doctype html><html><head><meta charset='utf-8'><style>{fonts}html,body{{margin:0;background:#fff;}}"
            f"svg{{display:block;width:{width - 2 * pad}px;height:auto;margin:{top}px {pad}px;}}</style></head>"
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
            png = write_png(d, PNG_DIR / f"{slug}-{d.get('png_name') or d['id']}.png")
            print(f"  wrote {png.relative_to(REPO_ROOT)}")
    if errors:
        print(f"{errors} problem(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
