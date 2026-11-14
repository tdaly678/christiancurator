#!/usr/bin/env python3
"""build_topic_charts.py: sourced, accessible static charts on topic pages.

Convention (for every topic page except biblical-literacy, which keeps its own
builder, scripts/build_biblical_literacy_viz.py):

  data/topic_charts/<slug>/<chart-id>.json   one file per chart
  data/topic_charts/<slug>/section.json      optional: groups charts in a section

Each chart renders as a <figure class="cc-chart" id="<chart-id>"> holding an
inline SVG (or an HTML table for type "table") between
<!-- CC-CHART:<chart-id>:START --> and <!-- CC-CHART:<chart-id>:END -->.
The SVG carries its own title, population line, source line with publisher and
year, and a small "christiancurator.com" mark in the corner, so a screenshot
keeps its meaning and its credit. Screen readers get <title>/<desc> (every
value) and a data table in a <details>. Styles live in docs/assets/topic.css.
Re-running replaces each block in place; a block not yet on the page is
inserted at the chart's (or the section's) "place".

Chart file schema:

{
  "id": "why-left",                       # = file name; kebab case; becomes the anchor
  "type": "hbar" | "column" | "line" | "table",
  "kicker": "Why people leave",           # small red label above the chart
  "title": "Why people say they left",    # a question or claim; drawn on the image
  "subtitle": "U.S. adults raised Christian who no longer identify as Christian",
                                          # the population; drawn on the image
  "caption": "One or two sentences saying what the chart shows.",
  "note": "Question wording, caveats.",   # optional
  "unit": "%",                            # "%" or "" (or any suffix)
  "max": 100,                             # optional axis maximum
  "categories": [{"id": "belief", "label": "Stopped believing", "color": "green"}],
                                          # hbar only, optional: colors bars, adds a legend
  "series": [{"id": "yes", "label": "Yes votes", "color": "green"}],
                                          # column and line: one entry per series
  "reference": {"value": 66.67, "label": "Two-thirds needed"},   # column/line, optional
  "columns": ["Body", "Women as senior pastors", "Document"],    # table only
  "rows": [
    # hbar:   {"label": "...", "value": 42, "as_published": "42%", "source": "pew2025", "category": "belief"}
    # column/line: {"label": "2024", "values": {"yes": 60.74}, "as_published": {"yes": "60.74%"}, "source": "sbc2024"}
    # table:  {"cells": ["...", "...", "..."], "source": "pca-bco"}
  ],
  "sources": [
    {"id": "pew2025", "publisher": "Pew Research Center", "study": "Study or page title",
     "year": 2025, "url": "https://...", "fetched": "2026-11-14",
     "license": "reuse" | "own-chart-cite" | "credit",
     "field_dates": "optional", "sample": "optional"}
  ],
  "place": {"before": "<!-- AEO-RELATED-TOPICS:START -->"}   # or {"after": "..."}; not needed inside a section
}

section.json schema:
{"id": "by-the-numbers", "label": "By the Numbers", "title": "What the surveys show",
 "intro": "optional sentence", "charts": ["why-left", "leaving-returning"],
 "place": {"before": "<!-- AEO-RELATED-TOPICS:START -->"}}
The section renders <section class="cc-viz-section" id="..."> between
<!-- CC-CHART-SECTION:<id>:START/END --> with its charts inside, in order.

Rules (validate()): every row cites a source in "sources"; every source has a
URL, publisher, study, year and the date it was opened ("fetched"); license is
reuse, own-chart-cite, or credit (Tom, Nov 14 2026: Barna and PRRI are drawn
from published figures and credited clearly; never copy their graphics);
"as_published" records the exact figure as printed and must match the value;
no em or en dashes; no tracking parameters; no Quiet Revival.

Usage:
  python scripts/build_topic_charts.py                    # every slug with charts
  python scripts/build_topic_charts.py --slug faith-deconstruction
  python scripts/build_topic_charts.py --check            # validate only
Tests: tests/test_build_topic_charts.py
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

DATA_DIR = REPO_ROOT / "data" / "topic_charts"
TOPICS_DIR = REPO_ROOT / "docs" / "topics"

TYPES = {"hbar", "column", "line", "table"}
LICENSES = {"reuse", "own-chart-cite", "credit"}
COLORS = {
    "green": "#2C4A2E", "brown": "#8B4513", "blue": "#4A4A8B", "red": "#8B1A1A",
    "gold": "#b08a2e", "sage": "#8fa48f", "grey": "#8a8a8a", "rose": "#b77b6f",
}
INK, GREY, TRACK, GRID = "#1a1a1a", "#666", "#ece9e4", "#e0ddd8"
FONT = "'Source Sans 3', sans-serif"
SERIF = "'Lora', Georgia, serif"
W, PAD = 640, 16
W_NARROW = 360   # second image for phones; topic.css swaps them below 560px
BRAND = "christiancurator.com"

DASH_RE = re.compile("[–—]")
BANNED_RE = re.compile(r"quiet revival", re.I)
TRACKING_RE = re.compile(r"[?&](?:utm_[a-z]+|fbclid|gclid|mc_eid)=", re.I)
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def esc(s) -> str:
    return html_mod.escape(str(s if s is not None else ""), quote=True)


def chart_marker(cid: str) -> tuple[str, str]:
    return f"<!-- CC-CHART:{cid}:START -->", f"<!-- CC-CHART:{cid}:END -->"


def section_marker(sid: str) -> tuple[str, str]:
    return f"<!-- CC-CHART-SECTION:{sid}:START -->", f"<!-- CC-CHART-SECTION:{sid}:END -->"


def fmt(v: float, unit: str = "") -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return f"{s}{unit}"


def wrap(text: str, max_chars: int) -> list[str]:
    lines, line = [], ""
    for word in str(text).split():
        if line and len(line) + 1 + len(word) > max_chars:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


def t(x, y, s, size=14, fill=INK, weight=None, anchor=None, family=None) -> str:
    a = f'x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}"'
    if weight:
        a += f' font-weight="{weight}"'
    if anchor:
        a += f' text-anchor="{anchor}"'
    if family:
        a += f' font-family="{family}"'
    return f"<text {a}>{esc(s)}</text>"


# ---------------------------------------------------------------- loading

def load_slug(slug: str, data_dir: Path = DATA_DIR) -> tuple[list[dict], dict | None]:
    folder = data_dir / slug
    charts, section = [], None
    for path in sorted(folder.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if path.name == "section.json":
            section = data
        else:
            data.setdefault("_file", path.stem)
            charts.append(data)
    return charts, section


def chart_slugs(data_dir: Path = DATA_DIR) -> list[str]:
    return sorted(p.name for p in data_dir.glob("*") if p.is_dir() and any(p.glob("*.json")))


# ---------------------------------------------------------------- validation

def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in ("place", "_file"):
                yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _matches(value, published) -> bool:
    m = NUM_RE.search(str(published).replace(",", ""))
    return bool(m) and abs(float(m.group(0)) - float(value)) <= 0.051


def validate_chart(c: dict) -> list[str]:
    cid = c.get("id", "?")
    errs: list[str] = []

    def e(msg):
        errs.append(f"{cid}: {msg}")

    if not ID_RE.match(str(c.get("id", ""))):
        e("id must be kebab case")
    if c.get("_file") and c.get("id") != c["_file"]:
        e(f"id must match the file name ({c['_file']}.json)")
    if c.get("type") not in TYPES:
        e(f"type must be one of {sorted(TYPES)}")
    for f in ("title", "subtitle", "caption"):
        if not str(c.get(f, "")).strip():
            e(f"{f} is required")
    for s in _strings(c):
        if DASH_RE.search(s):
            e(f"em or en dash in {s[:60]!r}")
        if BANNED_RE.search(s):
            e("Quiet Revival is withdrawn and may not be cited")
        if TRACKING_RE.search(s):
            e(f"tracking parameter in {s[:80]!r}")

    sources = {s.get("id"): s for s in c.get("sources") or []}
    if not sources:
        e("at least one source is required")
    for sid, s in sources.items():
        for f in ("id", "publisher", "study", "year", "url", "fetched", "license"):
            if not str(s.get(f, "")).strip():
                e(f"source {sid}: {f} is required")
        if s.get("url") and not str(s["url"]).startswith(("https://", "http://")):
            e(f"source {sid}: url must be a full URL")
        if s.get("fetched") and not ISO_RE.match(str(s["fetched"])):
            e(f"source {sid}: fetched must be YYYY-MM-DD (the day it was opened)")
        if s.get("license") and s["license"] not in LICENSES:
            e(f"source {sid}: license {s['license']!r} may not be charted (use {sorted(LICENSES)})")

    rows = c.get("rows") or []
    if not rows:
        e("rows are required")
    series = [s.get("id") for s in c.get("series") or []]
    for s in c.get("series") or []:
        if s.get("color", "green") not in COLORS:
            e(f"series {s.get('id')}: unknown color {s.get('color')!r}")
    cats = {k.get("id"): k for k in c.get("categories") or []}
    for k in cats.values():
        if k.get("color", "green") not in COLORS:
            e(f"category {k.get('id')}: unknown color {k.get('color')!r}")
    if c.get("type") in ("column", "line") and not series:
        e("column and line charts need series")
    if c.get("type") == "table" and not c.get("columns"):
        e("table charts need columns")

    for n, r in enumerate(rows, 1):
        if r.get("source") not in sources:
            e(f"row {n}: source {r.get('source')!r} is not in sources")
        typ = c.get("type")
        if typ == "hbar":
            if not isinstance(r.get("value"), (int, float)):
                e(f"row {n}: value must be a number")
            elif not _matches(r["value"], r.get("as_published", "")):
                e(f"row {n}: as_published {r.get('as_published')!r} does not match value {r['value']}")
            if cats and r.get("category") not in cats:
                e(f"row {n}: category {r.get('category')!r} is not in categories")
        elif typ in ("column", "line"):
            vals, pub = r.get("values") or {}, r.get("as_published") or {}
            for sid, v in vals.items():
                if sid not in series:
                    e(f"row {n}: series {sid!r} is not in series")
                elif not isinstance(v, (int, float)):
                    e(f"row {n}: {sid} must be a number")
                elif not _matches(v, pub.get(sid, "")):
                    e(f"row {n}: as_published[{sid}] {pub.get(sid)!r} does not match {v}")
        elif typ == "table":
            if len(r.get("cells") or []) != len(c.get("columns") or []):
                e(f"row {n}: cells must match columns")
    ref = c.get("reference")
    if ref is not None and not isinstance(ref.get("value"), (int, float)):
        e("reference.value must be a number")
    return errs


def validate_slug(slug: str, charts: list[dict], section: dict | None, page_html: str) -> list[str]:
    errs: list[str] = []
    ids = [c.get("id") for c in charts]
    if len(ids) != len(set(ids)):
        errs.append("duplicate chart ids")
    for c in charts:
        errs += validate_chart(c)
    in_section = set((section or {}).get("charts") or [])
    if section:
        if not ID_RE.match(str(section.get("id", ""))):
            errs.append("section: id must be kebab case")
        for f in ("label", "title"):
            if not str(section.get(f, "")).strip():
                errs.append(f"section: {f} is required")
        for s in _strings(section):
            if DASH_RE.search(s):
                errs.append(f"section: em or en dash in {s[:60]!r}")
        for cid in in_section:
            if cid not in ids:
                errs.append(f"section: chart {cid!r} has no data file")
        if section_marker(section["id"])[0] not in page_html:
            errs += _place_errors("section", section.get("place"), page_html)
    for c in charts:
        if c.get("id") in in_section or chart_marker(c.get("id", ""))[0] in page_html:
            continue
        errs += _place_errors(c.get("id", "?"), c.get("place"), page_html)
    return errs


def _place_errors(who: str, place, page_html: str) -> list[str]:
    if not isinstance(place, dict) or not (place.get("before") or place.get("after")):
        return [f"{who}: place {{'before': ...}} or {{'after': ...}} is required for the first build"]
    anchor = place.get("before") or place.get("after")
    if anchor not in page_html:
        return [f"{who}: place anchor {anchor[:60]!r} is not on the page"]
    return []


# ---------------------------------------------------------------- rendering

def color(name: str | None) -> str:
    return COLORS.get(name or "green", COLORS["green"])


def axis_max(c: dict, values: list[float]) -> float:
    if c.get("max"):
        return float(c["max"])
    if c.get("unit") == "%":
        return 100.0
    top = max(values + [c.get("reference", {}).get("value", 0)] + [1])
    return top * 1.1


def narrow(w: float) -> bool:
    return w < W


def small(w: float) -> float:
    """Size of axis, source and brand text: larger on the narrow image so it stays legible on a phone."""
    return 12.5 if narrow(w) else 11.5


def header(c: dict, w: float = W) -> tuple[list[str], float]:
    parts, y = [], 24
    for line in wrap(c["title"], int((w - 2 * PAD) / 11)):
        parts.append(t(PAD, y, line, size=20, weight="700", family=SERIF))
        y += 25
    for line in wrap(c["subtitle"], int((w - 2 * PAD) / 7.2)):
        parts.append(t(PAD, y - 2, line, size=13, fill=GREY))
        y += 17
    return parts, y + 8


def legend(items: list[tuple], y: float, w: float = W) -> tuple[str, float]:
    """items: (label, color) or (label, color, "ref") for a dashed reference-line swatch."""
    parts, x = [], PAD
    for item in items:
        label, col = item[0], item[1]
        dashed = len(item) > 2 and item[2] == "ref"
        width = (26 if dashed else 18) + 7.2 * len(label) + 16
        if x + width > w - PAD and x > PAD:
            x, y = PAD, y + 20
        if dashed:
            parts.append(f'<line x1="{x:.1f}" x2="{x + 20:.1f}" y1="{y - 4.5:.1f}" y2="{y - 4.5:.1f}" '
                         f'stroke="{col}" stroke-width="1.5" stroke-dasharray="5 4"/>')
            parts.append(t(x + 25, y, label, size=13, fill=col, weight="600"))
        else:
            parts.append(f'<rect x="{x:.1f}" y="{y - 10:.1f}" width="11" height="11" rx="2" fill="{col}"/>')
            parts.append(t(x + 16, y, label, size=13, fill="#444"))
        x += width
    return "".join(parts), y + 18


def legend_items(c: dict, series: bool) -> list[tuple]:
    items = [(s["label"], color(s.get("color"))) for s in c.get("series", [])] if series else []
    ref = c.get("reference")
    if ref:
        # The reference line is named in the legend, never on the plot, so its
        # label can never sit on a bar (the SBC 74.6% bar crossed it).
        items.append((f'{ref.get("label", "")} ({fmt(ref["value"], c.get("unit", ""))})'.strip(),
                      COLORS["red"], "ref"))
    return items


def footer(c: dict, y: float, w: float = W) -> tuple[str, float]:
    srcs = []
    for s in c["sources"]:
        bit = f'{s["publisher"]}, {s["year"]}'
        if bit not in srcs:
            srcs.append(bit)
    size = small(w)
    lines = wrap("Source: " + "; ".join(srcs), int((w - 2 * PAD) / (size * 0.62)))
    parts = [f'<line x1="{PAD}" x2="{w - PAD}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}"/>']
    y += 17
    for i, line in enumerate(lines):
        parts.append(t(PAD, y, line, size=size, fill=GREY))
        if i < len(lines) - 1:
            y += 15
    if narrow(w):
        y += 17  # the mark gets its own line on the narrow image
    parts.append(t(w - PAD, y, BRAND, size=size - 0.5, fill="#2C4A2E", weight="600", anchor="end"))
    return "".join(parts), y + 10


def desc_text(c: dict) -> str:
    unit = c.get("unit", "")
    if c["type"] == "hbar":
        return "; ".join(f'{r["label"]}: {fmt(r["value"], unit)}' for r in c["rows"])
    if c["type"] in ("column", "line"):
        names = {s["id"]: s["label"] for s in c["series"]}
        bits = []
        for r in c["rows"]:
            vals = ", ".join(f"{names[k]} {fmt(v, unit)}" for k, v in r["values"].items())
            bits.append(f'{r["label"]}: {vals}')
        ref = c.get("reference")
        if ref:
            bits.append(f'{ref.get("label", "Reference")}: {fmt(ref["value"], unit)}')
        return "; ".join(bits)
    return ""


def svg_wrap(c: dict, body: str, height: float, w: float = W) -> str:
    # The wide image shows above 560px, the narrow one below it (topic.css);
    # the hidden one is display:none, so screen readers meet the chart once.
    cid = c["id"] + ("-n" if narrow(w) else "")
    cls = "cc-chart-svg " + ("cc-chart-narrow" if narrow(w) else "cc-chart-wide")
    return (
        f'<svg class="{cls}" viewBox="0 0 {w} {height:.0f}" role="img" '
        f'aria-labelledby="{cid}-t {cid}-d" font-family="{FONT}">'
        f'<title id="{cid}-t">{esc(c["title"])}</title><desc id="{cid}-d">{esc(c.get("alt") or desc_text(c))}</desc>'
        f'<rect width="{w}" height="{height:.0f}" fill="#fff"/>{body}</svg>'
    )


def _bar_row(parts: list[str], label_lines: list[str], y: float, bars: list[tuple[float, str]],
             top: float, unit: str, w: float) -> float:
    """One labeled row of horizontal bars (one bar per (value, color)); returns the next y."""
    bar_w = w - 2 * PAD - 60
    for k, line in enumerate(label_lines):
        parts.append(t(PAD, y + 13 + 17 * k, line, size=14))
    y += 17 * (len(label_lines) - 1)
    if not bars:
        parts.append(f'<rect x="{PAD}" y="{y + 19:.1f}" width="{bar_w}" height="15" rx="2" fill="{TRACK}"/>')
        return y + 46
    for v, col in bars:
        bw = bar_w * v / top
        parts.append(f'<rect x="{PAD}" y="{y + 19:.1f}" width="{bar_w}" height="15" rx="2" fill="{TRACK}"/>')
        parts.append(f'<rect x="{PAD}" y="{y + 19:.1f}" width="{bw:.1f}" height="15" rx="2" fill="{col}"/>')
        parts.append(t(PAD + bw + 6, y + 32, fmt(v, unit), size=14, weight="700"))
        y += 21
    return y + 25


def render_hbar(c: dict, w: float = W) -> str:
    parts, y = header(c, w)
    cats = {k["id"]: k for k in c.get("categories") or []}
    if cats:
        leg, y = legend([(k["label"], color(k.get("color"))) for k in cats.values()], y + 4, w)
        parts.append(leg)
    unit = c.get("unit", "")
    top = axis_max(c, [r["value"] for r in c["rows"]])
    for r in c["rows"]:
        col = color(cats[r["category"]].get("color")) if cats and r.get("category") in cats else color(r.get("color"))
        y = _bar_row(parts, wrap(r["label"], int((w - 2 * PAD) / 7.4)), y, [(r["value"], col)], top, unit, w)
    foot, y = footer(c, y + 6, w)
    return svg_wrap(c, "".join(parts) + foot, y, w)


def _plot_frame(c: dict, top: float, y0: float, plot_h: float, left: float, w: float = W) -> list[str]:
    unit = c.get("unit", "")
    parts = []
    for i in range(5):
        v = top * i / 4
        yy = y0 + plot_h - plot_h * i / 4
        parts.append(f'<line x1="{left}" x2="{w - PAD}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{GRID}"/>')
        parts.append(t(left - 6, yy + 4, fmt(round(v, 1), unit), size=small(w), fill=GREY, anchor="end"))
    ref = c.get("reference")
    if ref:
        yy = y0 + plot_h - plot_h * ref["value"] / top
        parts.append(f'<line x1="{left}" x2="{w - PAD}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{COLORS["red"]}" '
                     f'stroke-width="1.5" stroke-dasharray="5 4"/>')
    return parts


def render_column(c: dict, w: float = W) -> str:
    if narrow(w):
        return render_column_narrow(c, w)
    parts, y = header(c, w)
    series = c["series"]
    items = legend_items(c, series=len(series) > 1)
    if items:
        leg, y = legend(items, y + 4, w)
        parts.append(leg)
    unit = c.get("unit", "")
    vals = [v for r in c["rows"] for v in r["values"].values()]
    top = axis_max(c, vals)
    left, plot_h, y0 = PAD + 40, 220, y + 14
    parts += _plot_frame(c, top, y0, plot_h, left, w)
    n = len(c["rows"])
    group_w = (w - PAD - left) / n
    bar_w = min(56, (group_w - 16) / len(series))
    for i, r in enumerate(c["rows"]):
        gx = left + group_w * i + (group_w - bar_w * len(series)) / 2
        for j, s in enumerate(series):
            if s["id"] not in r["values"]:
                continue
            v = r["values"][s["id"]]
            h = plot_h * v / top
            x = gx + j * bar_w
            parts.append(f'<rect x="{x + 2:.1f}" y="{y0 + plot_h - h:.1f}" width="{bar_w - 4:.1f}" height="{h:.1f}" '
                         f'fill="{color(s.get("color"))}"/>')
            # Value inside the bar top when it fits, so it never collides with a reference line.
            if h >= 24:
                parts.append(t(x + bar_w / 2, y0 + plot_h - h + 17, fmt(v, unit), size=13, weight="700",
                               anchor="middle", fill="#fff"))
            else:
                parts.append(t(x + bar_w / 2, y0 + plot_h - h - 6, fmt(v, unit), size=13, weight="700",
                               anchor="middle"))
        for k, line in enumerate(wrap(r["label"], max(8, int(group_w / 7.5)))):
            parts.append(t(left + group_w * i + group_w / 2, y0 + plot_h + 18 + 15 * k, line, size=13, anchor="middle"))
    y = y0 + plot_h + 18 + 15 * max(len(wrap(r["label"], max(8, int(group_w / 7.5)))) for r in c["rows"]) + 8
    foot, y = footer(c, y, w)
    return svg_wrap(c, "".join(parts) + foot, y, w)


def render_column_narrow(c: dict, w: float) -> str:
    """Column charts on a phone: the same data as grouped horizontal bars, so labels and values stay full size."""
    parts, y = header(c, w)
    series = c["series"]
    items = legend_items(c, series=len(series) > 1)
    if items:
        leg, y = legend(items, y + 4, w)
        parts.append(leg)
    unit = c.get("unit", "")
    top = axis_max(c, [v for r in c["rows"] for v in r["values"].values()])
    y_start = y
    for r in c["rows"]:
        bars = [(r["values"][s["id"]], color(s.get("color"))) for s in series if s["id"] in r["values"]]
        y = _bar_row(parts, wrap(r["label"], int((w - 2 * PAD) / 7.4)), y, bars, top, unit, w)
    ref = c.get("reference")
    if ref:
        x = PAD + (w - 2 * PAD - 60) * ref["value"] / top
        parts.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y_start + 16:.1f}" y2="{y - 8:.1f}" '
                     f'stroke="{COLORS["red"]}" stroke-width="1.5" stroke-dasharray="5 4"/>')
    foot, y = footer(c, y + 6, w)
    return svg_wrap(c, "".join(parts) + foot, y, w)


def render_line(c: dict, w: float = W) -> str:
    parts, y = header(c, w)
    series = c["series"]
    leg, y = legend(legend_items(c, series=True), y + 4, w)
    parts.append(leg)
    unit = c.get("unit", "")
    vals = [v for r in c["rows"] for v in r["values"].values()]
    top = axis_max(c, vals)
    left, plot_h, y0 = PAD + 40, 200, y + 14
    parts += _plot_frame(c, top, y0, plot_h, left, w)
    n = len(c["rows"])
    span = w - PAD - 30 - left
    xs = [left + 24 + (span * i / (n - 1) if n > 1 else span / 2) for i in range(n)]
    def ypos(v):
        return y0 + plot_h - plot_h * v / top

    labels = []
    for s in series:
        pts = [(xs[i], ypos(r["values"][s["id"]]), r["values"][s["id"]], i)
               for i, r in enumerate(c["rows"]) if s["id"] in r["values"]]
        col = color(s.get("color"))
        if len(pts) > 1:
            path = " ".join(f"{x:.1f},{yy:.1f}" for x, yy, _, _ in pts)
            parts.append(f'<polyline points="{path}" fill="none" stroke="{col}" stroke-width="2.5"/>')
        for x, yy, v, i in pts:
            parts.append(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="4" fill="{col}"/>')
            # A point with a higher neighbor within 20px puts its label below.
            row_vals = c["rows"][i]["values"]
            others = [row_vals[o["id"]] for o in series if o is not s and o["id"] in row_vals]
            below = any(o > v and ypos(v) - ypos(o) < 20 for o in others)
            labels.append(t(x, yy + 19 if below else yy - 9, fmt(v, unit), size=13, weight="700",
                            anchor="middle", fill=col))
    parts += labels
    for i, r in enumerate(c["rows"]):
        parts.append(t(xs[i], y0 + plot_h + 18, r["label"], size=13, anchor="middle"))
    foot, y = footer(c, y0 + plot_h + 30, w)
    return svg_wrap(c, "".join(parts) + foot, y, w)


def render_table_body(c: dict) -> str:
    sources = {s["id"]: s for s in c["sources"]}
    head = "".join(f'<th scope="col">{esc(h)}</th>' for h in c["columns"]) + '<th scope="col">Source</th>'
    rows = []
    for r in c["rows"]:
        s = sources[r["source"]]
        cells = "".join(f"<td>{esc(x)}</td>" for x in r["cells"])
        rows.append(f'<tr>{cells}<td><a href="{esc(s["url"])}" target="_blank" rel="noopener">'
                    f'{esc(s["publisher"])}, {esc(s["year"])}</a></td></tr>')
    return (f'<div class="cc-chart-scroll"><table class="cc-chart-table"><caption>{esc(c["title"])}. '
            f'{esc(c["subtitle"])}</caption><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody>'
            f"</table></div>")


def data_table(c: dict) -> str:
    unit = c.get("unit", "")
    sources = {s["id"]: s for s in c["sources"]}
    if c["type"] == "hbar":
        head = ["Group", "Value", "As published", "Source"]
        body = [[r["label"], fmt(r["value"], unit), r.get("as_published", ""), sources[r["source"]]["publisher"]]
                for r in c["rows"]]
    else:
        names = [s["label"] for s in c["series"]]
        head = [""] + names + ["Source"]
        body = [[r["label"]] + [fmt(r["values"][s["id"]], unit) if s["id"] in r["values"] else ""
                                for s in c["series"]] + [sources[r["source"]]["publisher"]] for r in c["rows"]]
    th = "".join(f'<th scope="col">{esc(h)}</th>' for h in head)
    tb = "".join("<tr>" + "".join(f"<td>{esc(x)}</td>" for x in row) + "</tr>" for row in body)
    return (f'<details class="cc-chart-data"><summary>Data table</summary><table><caption>{esc(c["title"])}'
            f"</caption><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></details>")


def source_par(c: dict) -> str:
    bits = []
    for s in c["sources"]:
        extra = "; ".join(x for x in (s.get("field_dates"), s.get("sample")) if x)
        bits.append(f'{esc(s["publisher"])}, <a href="{esc(s["url"])}" target="_blank" rel="noopener">'
                    f'{esc(s["study"])}</a> ({esc(s["year"])})' + (f". {esc(extra)}" if extra else ""))
    return f'<p class="cc-chart-source">Source: {". ".join(bits)}. Chart by Christian Curator.</p>'


RENDERERS = {"hbar": render_hbar, "column": render_column, "line": render_line}


def render_chart(c: dict) -> str:
    start, end = chart_marker(c["id"])
    if c["type"] == "table":
        visual = render_table_body(c)
    else:
        visual = RENDERERS[c["type"]](c) + "\n" + RENDERERS[c["type"]](c, W_NARROW)
    kicker = f'<div class="cc-chart-kicker">{esc(c["kicker"])}</div>' if c.get("kicker") else ""
    note = f'<p class="cc-chart-note">{esc(c["note"])}</p>' if c.get("note") else ""
    table = "" if c["type"] == "table" else data_table(c)
    return (f'{start}\n<figure class="cc-chart cc-chart-{c["type"]}" id="{esc(c["id"])}">{kicker}\n{visual}\n'
            f'<figcaption>{esc(c["caption"])}</figcaption>{note}{table}\n{source_par(c)}\n</figure>\n{end}')


def render_section(section: dict, charts: list[dict]) -> str:
    start, end = section_marker(section["id"])
    by_id = {c["id"]: c for c in charts}
    inner = "\n".join(render_chart(by_id[cid]) for cid in section["charts"])
    intro = f'<p class="cc-viz-intro">{esc(section["intro"])}</p>' if section.get("intro") else ""
    return (f'{start}\n<section class="cc-viz-section cc-chart-section" id="{esc(section["id"])}">\n'
            f'<h2 class="cc-viz-label">{esc(section["label"])}</h2>\n'
            f'<h3 class="cc-viz-title">{esc(section["title"])}</h3>{intro}\n{inner}\n</section>\n{end}')


def put(page_html: str, start: str, end: str, block: str, place: dict | None) -> str:
    block_re = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if block_re.search(page_html):
        return block_re.sub(lambda _: block, page_html, count=1)
    place = place or {}
    if place.get("before"):
        i = page_html.index(place["before"])
        return page_html[:i] + block + "\n" + page_html[i:]
    anchor = place["after"]
    i = page_html.index(anchor) + len(anchor)
    return page_html[:i] + "\n" + block + page_html[i:]


def build_page(page_html: str, charts: list[dict], section: dict | None) -> str:
    out = page_html
    in_section = set((section or {}).get("charts") or [])
    if section:
        # A chart that moved into the section loses any standalone block; the
        # section block (markers kept) is then rewritten with every chart inside.
        for cid in in_section:
            s, e = chart_marker(cid)
            out = re.sub(r"\n?" + re.escape(s) + r".*?" + re.escape(e), "", out, flags=re.DOTALL)
        s, e = section_marker(section["id"])
        out = put(out, s, e, render_section(section, charts), section.get("place"))
    for c in charts:
        if c["id"] in in_section:
            continue
        s, e = chart_marker(c["id"])
        out = put(out, s, e, render_chart(c), c.get("place"))
    try:
        from build_topic_top import ensure_assets
        out = ensure_assets(out)
    except ImportError:  # pragma: no cover
        pass
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug", action="append")
    ap.add_argument("--check", action="store_true", help="validate only")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    slugs = args.slug or chart_slugs()
    errors = 0
    for slug in slugs:
        page = TOPICS_DIR / slug / "index.html"
        if not page.exists():
            print(f"::error::data/topic_charts/{slug}: no topic page")
            errors += 1
            continue
        charts, section = load_slug(slug)
        html = page.read_text(encoding="utf-8")
        problems = validate_slug(slug, charts, section, html)
        for p in problems:
            print(f"::error::data/topic_charts/{slug}: {p}")
        if problems:
            errors += len(problems)
            continue
        if args.check:
            continue
        out = build_page(html, charts, section)
        if out != html and not args.dry_run:
            page.write_text(out, encoding="utf-8")
        print(f"{slug}: {len(charts)} chart(s){' (changed)' if out != html else ''}")
    if errors:
        print(f"{errors} problem(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
