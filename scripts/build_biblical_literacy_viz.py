"""
build_biblical_literacy_viz.py: render the biblical literacy page's survey visuals.

Reads data/biblical-literacy/surveys.json (one row per published figure) and rewrites
only three marker blocks in docs/topics/biblical-literacy/index.html:

    <!-- CC-BL-VIZ-GAP:START -->      ... <!-- CC-BL-VIZ-GAP:END -->       reverence gap + grade strip
    <!-- CC-BL-VIZ-QUIZ:START -->     ... <!-- CC-BL-VIZ-QUIZ:END -->      By the Numbers: quiz + chart
    <!-- CC-BL-VIZ-TRACKER:START -->  ... <!-- CC-BL-VIZ-TRACKER:END -->   survey tracker + Dataset JSON-LD

Charts are server-rendered SVG (no chart library, no JavaScript). The quiz is the only
piece with a script, and its questions and answers still show without it.

The visible "Last updated" line and the Article `dateModified` move only when the data
file changed (a hash of it is stored in the tracker block). The build fails when any row
lacks a URL or license status, and rows marked ask-first or cite-only are never charted.

Run by hand after editing the data file. The daily data watch (scripts/run_data_watch.py)
also runs it after adding a quoted figure to the file's "watch" list; those rows are shown
as a cited table and never charted.

Usage:
    python scripts/build_biblical_literacy_viz.py            # rewrite the page
    python scripts/build_biblical_literacy_viz.py --check    # exit 1 if the page is stale
    python scripts/build_biblical_literacy_viz.py --date 2026-11-09
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "biblical-literacy" / "surveys.json"
PAGE_PATH = REPO_ROOT / "docs" / "topics" / "biblical-literacy" / "index.html"

PAGE_URL = "https://www.christiancurator.com/topics/biblical-literacy/"
PAGE_TITLE = "What Is Biblical Literacy?"
DATA_URL = "https://github.com/tdaly678/christiancurator/blob/main/data/biblical-literacy/surveys.json"
DATA_RAW_URL = "https://raw.githubusercontent.com/tdaly678/christiancurator/main/data/biblical-literacy/surveys.json"

BLOCKS = ("GAP", "QUIZ", "TRACKER")
LICENSE_STATUSES = {"reuse", "cite-only", "ask-first", "permission-granted"}
CHARTABLE = {"reuse", "permission-granted"}
# Rows the daily data watch (curator/data_watch.py) adds under "watch": a quoted
# sentence checked against its source page. Shown as cited text, never charted.
WATCH_FIELDS = ("id", "quote", "figure", "publisher", "license_status", "url", "verified_date")
REQUIRED_ROW_FIELDS = (
    "source", "study_title", "url", "field_dates", "publication_date", "sample", "population",
    "question_wording", "measure", "subgroup", "value", "margin_of_error", "license_status",
    "verified_date",
)

PEW_DISCLAIMER = (
    "Pew Research Center bears no responsibility for the analyses or interpretations of the data "
    "presented here. The opinions expressed herein, including any implications for policy, are those "
    "of the author and not of Pew Research Center."
)

GREEN = "#2C4A2E"
GAP_RED = "#8B1A1A"
BROWN = "#8B4513"
TRACK = "#ece9e4"
MUTED = "#8fa48f"
INK = "#1a1a1a"
GREY = "#666"
FONT = "'Source Sans 3', sans-serif"

# SVG geometry: a narrow viewBox keeps labels readable when the chart shrinks on a phone.
VB_W = 480
PAD_X = 4
BAR_W = VB_W - 2 * PAD_X - 44  # leaves room for the value label at the bar's end


class BuildError(Exception):
    pass


# --------------------------------------------------------------------------- data


def load_data(path: Path = DATA_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def merged_rows(data: dict) -> list[dict]:
    """Rows with their study's fields filled in (row values win)."""
    studies = data.get("studies", {})
    out = []
    for row in data.get("rows", []):
        study = studies.get(row.get("study"), {})
        merged = {
            "source": study.get("publisher"),
            "study_title": study.get("study_title"),
            "url": study.get("url"),
            "field_dates": study.get("field_dates"),
            "publication_date": study.get("publication_date"),
            "sample": study.get("sample"),
            "population": study.get("population"),
            "margin_of_error": study.get("margin_of_error"),
            "license_status": study.get("license_status"),
            "verified_date": study.get("verified_date"),
        }
        merged.update({k: v for k, v in row.items() if v is not None})
        out.append(merged)
    return out


def validate(data: dict) -> list[str]:
    """Every problem with the data file, as readable strings. Empty means valid."""
    errors: list[str] = []
    studies = data.get("studies", {})
    seen: set[str] = set()
    for row in data.get("rows", []):
        rid = row.get("id") or "(row without id)"
        if rid in seen:
            errors.append(f"{rid}: duplicate id")
        seen.add(rid)
        if row.get("study") not in studies:
            errors.append(f"{rid}: unknown study {row.get('study')!r}")
    for row in merged_rows(data):
        rid = row.get("id") or "(row without id)"
        for field in REQUIRED_ROW_FIELDS:
            value = row.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{rid}: missing {field}")
        url = row.get("url") or ""
        if url and not url.startswith("https://"):
            errors.append(f"{rid}: url must be https: {url}")
        status = row.get("license_status")
        if status and status not in LICENSE_STATUSES:
            errors.append(f"{rid}: license_status {status!r} not in {sorted(LICENSE_STATUSES)}")
        value = row.get("value")
        if value is not None and not (isinstance(value, (int, float)) and 0 <= value <= 100):
            errors.append(f"{rid}: value must be a number from 0 to 100")
        for field in ("verified_date", "publication_date"):
            if row.get(field):
                try:
                    date.fromisoformat(row[field])
                except ValueError:
                    errors.append(f"{rid}: {field} is not YYYY-MM-DD")
    for w in data.get("watch", []):
        wid = w.get("id") or "(watch row without id)"
        if wid in seen:
            errors.append(f"{wid}: duplicate id")
        seen.add(wid)
        for field in WATCH_FIELDS:
            if not str(w.get(field) or "").strip():
                errors.append(f"{wid}: missing {field}")
        if w.get("url") and not str(w["url"]).startswith("https://"):
            errors.append(f"{wid}: url must be https: {w['url']}")
        if w.get("license_status") and w["license_status"] not in LICENSE_STATUSES:
            errors.append(f"{wid}: license_status {w['license_status']!r} not in {sorted(LICENSE_STATUSES)}")
        if w.get("figure") and w.get("quote") and w["figure"] not in w["quote"]:
            errors.append(f"{wid}: figure {w['figure']!r} is not in its quote")
        if w.get("verified_date"):
            try:
                date.fromisoformat(w["verified_date"])
            except ValueError:
                errors.append(f"{wid}: verified_date is not YYYY-MM-DD")
    for entry in data.get("changelog", []):
        try:
            date.fromisoformat(entry.get("date", ""))
        except ValueError:
            errors.append(f"changelog entry has a bad date: {entry!r}")
    return errors


def figure_rows(data: dict, figure: str, chart: bool = True) -> list[dict]:
    rows = [r for r in merged_rows(data) if r.get("figure") == figure]
    if chart:
        blocked = [r["id"] for r in rows if r.get("license_status") not in CHARTABLE]
        if blocked:
            raise BuildError(f"rows not cleared for charting in {figure}: {', '.join(blocked)}")
    if not rows:
        raise BuildError(f"no rows for figure {figure}")
    return rows


def row_by_id(data: dict, rid: str) -> dict:
    for r in merged_rows(data):
        if r["id"] == rid:
            return r
    raise BuildError(f"missing row {rid}")


def data_hash(data: dict) -> str:
    canon = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- helpers


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def pct(value) -> str:
    return f"{value:g}%"


def long_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def svg_open(height: float, title: str, desc: str, ident: str) -> str:
    return (
        f'<svg class="cc-viz-svg" viewBox="0 0 {VB_W} {height:.0f}" role="img" '
        f'aria-labelledby="{ident}-t {ident}-d" font-family="{FONT}">'
        f'<title id="{ident}-t">{esc(title)}</title><desc id="{ident}-d">{esc(desc)}</desc>'
    )


def text(x, y, s, size=13, fill=INK, weight=None, anchor=None) -> str:
    attrs = f'x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}"'
    if weight:
        attrs += f' font-weight="{weight}"'
    if anchor:
        attrs += f' text-anchor="{anchor}"'
    return f"<text {attrs}>{esc(s)}</text>"


def scale(value) -> float:
    return BAR_W * value / 100.0


def hbar_rows(items: list[tuple[str, float, str]], top: float = 0) -> tuple[str, float]:
    """Horizontal bars, label above each bar, on a 0-100 track. items: (label, value, color)."""
    parts, y = [], top
    for label, value, color in items:
        parts.append(text(PAD_X, y + 13, label, size=13))
        parts.append(f'<rect x="{PAD_X}" y="{y + 18:.1f}" width="{BAR_W}" height="12" rx="2" fill="{TRACK}"/>')
        parts.append(f'<rect x="{PAD_X}" y="{y + 18:.1f}" width="{scale(value):.1f}" height="12" rx="2" fill="{color}"/>')
        parts.append(text(PAD_X + scale(value) + 5, y + 29, pct(value), size=13, weight="600"))
        y += 40
    return "".join(parts), y


def data_table(caption: str, headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th scope=\"col\">{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return (
        f'<details class="cc-viz-data"><summary>Data table</summary>'
        f'<table><caption>{esc(caption)}</caption><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></details>"
    )


def link(url: str, label: str) -> str:
    ext = ' rel="noopener" target="_blank"' if url.startswith("http") else ""
    return f'<a href="{esc(url)}"{ext}>{esc(label)}</a>'


def source_line(rows: list[dict], extra: str = "") -> str:
    seen, bits = set(), []
    for r in rows:
        key = r["url"]
        if key in seen:
            continue
        seen.add(key)
        bits.append(
            f"{esc(r['source'])}, {link(r['url'], r['study_title'])}. "
            f"Fielded {esc(r['field_dates'])}; {esc(r['sample'])}; "
            f"margin of error {esc(r['margin_of_error'])}."
        )
    tail = f" {extra}" if extra else ""
    return f'<p class="cc-viz-source">Source: {" ".join(bits)}{tail}</p>'


# --------------------------------------------------------------------------- piece 1


def render_gap(data: dict) -> str:
    rows = figure_rows(data, "gap")
    imp = {r["subgroup"]: r for r in rows if r["id"].startswith("pew-importance-")}
    rd = {r["subgroup"]: r for r in rows if r["id"].startswith("pew-weekly-")}
    groups = [g for g in imp if g in rd]
    if len(groups) != len(imp) or len(groups) != len(rd):
        raise BuildError("gap chart needs an importance and a weekly-reading row for every group")

    y = 30
    parts = [
        f'<circle cx="{PAD_X + 6}" cy="12" r="5" fill="{GREEN}"/>',
        text(PAD_X + 16, 16, "Says the Bible is extremely or very important", size=12, fill=GREY),
        f'<circle cx="{PAD_X + 296}" cy="12" r="5" fill="#fff" stroke="{GAP_RED}" stroke-width="2"/>',
        text(PAD_X + 306, 16, "Reads scripture weekly", size=12, fill=GREY),
    ]
    for g in groups:
        a, b = rd[g]["value"], imp[g]["value"]
        xa, xb = PAD_X + 6 + scale(a), PAD_X + 6 + scale(b)
        weight = "600" if g == "All U.S. adults" else None
        parts.append(text(PAD_X, y + 13, g, size=13, weight=weight))
        parts.append(f'<line x1="{PAD_X + 6}" y1="{y + 25}" x2="{PAD_X + 6 + BAR_W}" y2="{y + 25}" stroke="{TRACK}" stroke-width="2"/>')
        parts.append(f'<line x1="{xa:.1f}" y1="{y + 25}" x2="{xb:.1f}" y2="{y + 25}" stroke="{GAP_RED}" stroke-width="4"/>')
        parts.append(f'<circle cx="{xa:.1f}" cy="{y + 25}" r="5.5" fill="#fff" stroke="{GAP_RED}" stroke-width="2"/>')
        parts.append(f'<circle cx="{xb:.1f}" cy="{y + 25}" r="5.5" fill="{GREEN}"/>')
        # Value labels sit outside the pair so they never collide; near the left edge both go right.
        if xa - 9 > 34:
            parts.append(text(xa - 9, y + 29, pct(a), size=12, fill=GAP_RED, anchor="end"))
            parts.append(text(xb + 9, y + 29, pct(b), size=12, fill=GREEN, weight="600"))
        else:
            parts.append(text(xb + 9, y + 29, pct(b), size=12, fill=GREEN, weight="600"))
            parts.append(text(xb + 44, y + 29, f"{pct(a)} weekly", size=12, fill=GAP_RED))
        y += 42
    lead = "Evangelical Protestant"
    desc = "; ".join(f"{g}: {pct(imp[g]['value'])} important, {pct(rd[g]['value'])} read weekly" for g in groups)
    svg = svg_open(y + 4, "The reverence gap, by religious tradition", desc, "bl-gap") + "".join(parts) + "</svg>"

    caption = (
        f"Most Christian traditions rate the Bible far more important than they read it: "
        f"{pct(imp[lead]['value'])} of evangelical Protestants call it extremely or very important, "
        f"but {pct(rd[lead]['value'])} read scripture weekly; among mainline Protestants it is "
        f"{pct(imp['Mainline Protestant']['value'])} and {pct(rd['Mainline Protestant']['value'])}."
    )
    table = data_table(
        "Importance of the Bible and weekly scripture reading, Pew Religious Landscape Study 2023-24",
        ["Group", "Bible extremely or very important", "Reads scripture at least weekly", "Gap (points)"],
        [[esc(g), pct(imp[g]["value"]), pct(rd[g]["value"]), f"{imp[g]['value'] - rd[g]['value']:g}"] for g in groups],
    )
    questions = (
        f'<p class="cc-viz-note">Questions: "{esc(imp[groups[0]]["question_wording"])}" and '
        f'"{esc(rd[groups[0]]["question_wording"])}" (at least once a week).</p>'
    )
    pew = source_line([imp[groups[0]], rd[groups[0]]], extra=f"Chart by Christian Curator. {esc(PEW_DISCLAIMER)}")

    grades = render_grades(data)
    return (
        '<figure class="cc-viz" id="reverence-gap">\n'
        '<div class="cc-viz-kicker">The reverence gap</div>\n'
        f"{svg}\n<figcaption>{esc(caption)}</figcaption>\n{questions}\n{table}\n{pew}\n</figure>\n{grades}"
    )


def render_grades(data: dict) -> str:
    rows = figure_rows(data, "grades")
    avg = next(r for r in rows if r["id"] == "lifeway-quiz-average")
    grades = [r for r in rows if r["id"].startswith("lifeway-quiz-grade-")]
    f_row = next(r for r in grades if r["label"] == "F")
    if abs(sum(r["value"] for r in grades) - 100) > 1:
        raise BuildError("grade shares must add up to 100")

    colors = {"F": GAP_RED, "D": "#b77b6f", "C": "#a9b5a9", "B": MUTED, "A": GREEN}
    parts, x = [], PAD_X
    full = VB_W - 2 * PAD_X
    for r in grades:
        w = full * r["value"] / 100.0
        parts.append(f'<rect x="{x:.1f}" y="6" width="{w:.1f}" height="30" fill="{colors.get(r["label"], MUTED)}"/>')
        label = f"{r['label']} {pct(r['value'])}"
        if w > 52:
            parts.append(text(x + w / 2, 26, label, size=13, fill="#fff", weight="600", anchor="middle"))
        else:
            parts.append(text(x + w / 2, 54, label, size=12, fill=INK, anchor="middle"))
        x += w
    desc = "; ".join(f"grade {r['label']}: {pct(r['value'])}" for r in grades)
    svg = svg_open(62, "Lifeway Bible literacy quiz grades", desc, "bl-grades") + "".join(parts) + "</svg>"
    caption = f"Average score {avg['value']:g}; {pct(f_row['value'])} of churchgoers scored an F."
    table = data_table(
        "Lifeway Research Bible literacy quiz, grade distribution, 2026",
        ["Grade", "Score range", "Share of churchgoers"],
        [[esc(r["label"]), esc(r["measure"].split("(")[-1].rstrip(")")), pct(r["value"])] for r in grades]
        + [["Average", "", f"{avg['value']:g} out of 100"]],
    )
    return (
        '<figure class="cc-viz cc-viz-grades" id="quiz-grades">\n'
        '<div class="cc-viz-kicker">What churchgoers know</div>\n'
        f"{svg}\n<figcaption>{esc(caption)} Lifeway Research graded {esc(avg['sample'])} on a Bible "
        f'knowledge quiz; F is below 60. <a href="#by-the-numbers">See the questions</a>.</figcaption>\n'
        f"{table}\n{source_line([avg], extra='Chart by Christian Curator.')}\n</figure>"
    )


# --------------------------------------------------------------------------- piece 2

QUIZ_JS = """<script>
(function(){
  var q=document.getElementById('bl-quiz'); if(!q) return;
  q.className+=' cc-quiz-js';
  q.addEventListener('click',function(e){
    var b=e.target.closest('button[data-opt]'); if(!b) return;
    var item=b.closest('.cc-quiz-item'); if(item.getAttribute('data-done')) return;
    item.setAttribute('data-done','1');
    var ok=b.getAttribute('data-opt')===item.getAttribute('data-answer');
    b.className+=ok?' is-right':' is-wrong';
    item.querySelector('.cc-quiz-verdict').textContent=ok?'Correct.':'Not quite.';
    var bs=item.querySelectorAll('button[data-opt]');
    for(var i=0;i<bs.length;i++){bs[i].disabled=true;
      if(bs[i].getAttribute('data-opt')===item.getAttribute('data-answer')) bs[i].className+=' is-answer';}
    if(window.gtag) gtag('event','bl_quiz_answer',{quiz_item:item.id,correct:ok});
  });
})();
</script>"""


def render_quiz(data: dict) -> str:
    rows = figure_rows(data, "quiz")
    groups = data.get("quiz_groups", [])
    known = {g["key"] for g in groups}
    stray = [r["id"] for r in rows if r.get("group") not in known]
    if stray:
        raise BuildError(f"quiz rows with unknown group: {', '.join(stray)}")
    study = rows[0]

    # Five tap-to-answer questions (our paraphrases), then the full chart.
    taps = [r for r in rows if r.get("tap")]
    items = []
    for n, r in enumerate(taps, 1):
        tap = r["tap"]
        if tap["answer"] not in tap["options"]:
            raise BuildError(f"{r['id']}: tap answer is not one of its options")
        opts = "".join(
            f'<button type="button" data-opt="{esc(o)}">{esc(o)}</button>' for o in tap["options"]
        )
        items.append(
            f'<li class="cc-quiz-item" id="bl-q{n}" data-answer="{esc(tap["answer"])}">'
            f'<p class="cc-quiz-q">{esc(tap["prompt"])}</p>'
            f'<div class="cc-quiz-opts">{opts}</div>'
            f'<p class="cc-quiz-a"><span class="cc-quiz-verdict"></span> Answer: <strong>{esc(tap["answer"])}</strong>. '
            f'{esc(tap["note"])} <span class="cc-quiz-stat">{pct(r["value"])} of churchgoers got this right.</span></p>'
            "</li>"
        )

    chart_parts, y = [], 0
    for g in groups:
        g_rows = sorted((r for r in rows if r["group"] == g["key"]), key=lambda r: -r["value"])
        if not g_rows:
            continue
        chart_parts.append(text(PAD_X, y + 16, g["label"].upper(), size=11, fill=GREEN, weight="600"))
        y += 24
        bars, y = hbar_rows([(r["label"], r["value"], GAP_RED if r["value"] < 50 else GREEN) for r in g_rows], top=y)
        chart_parts.append(bars)
        y += 6
    desc = "; ".join(f"{r['label']}: {pct(r['value'])} correct" for r in rows)
    svg = svg_open(y, "Share of churchgoers who answered each quiz question correctly", desc, "bl-quiz-chart")
    svg += "".join(chart_parts) + "</svg>"

    moses = row_by_id(data, "lifeway-quiz-q25")
    order = row_by_id(data, "lifeway-quiz-q38")
    hezekiah = row_by_id(data, "lifeway-quiz-q54_5")
    caption = (
        f"Churchgoers know the Bible's famous people and verses better than its order and shape: "
        f"{pct(moses['value'])} knew Moses received the Ten Commandments, but {pct(order['value'])} could put "
        f"Deborah, Goliath, Jonah and Esther in order, and {pct(hezekiah['value'])} knew Hezekiah is not a book of the Bible."
    )

    reads = []
    for g in groups:
        if g.get("links"):
            links = " and ".join(link(u, t) for t, u in g["links"])
            reads.append(f"<li><strong>{esc(g['label'].split(':')[0])}:</strong> {links}</li>")

    table_rows = []
    for g in groups:
        for r in (r for r in rows if r["group"] == g["key"]):
            table_rows.append([esc(g["label"].split(":")[0]), esc(r["label"]), esc(r["correct_answer"]), pct(r["value"])])
    table = data_table(
        "Lifeway Research Bible literacy quiz, share answering correctly, 2026",
        ["Skill", "Question", "Correct answer", "Answered correctly"],
        table_rows,
    )
    side = sorted({r["url"] for r in rows if r["url"] != study["url"]})
    quiz_extra = "".join(
        f"Figures for {esc(', '.join(r['label'] for r in rows if r['url'] == u))} are from Lifeway's {link(u, 'frequencies report')}. "
        for u in side
    ) + "Questions in the five-question check are our paraphrases. Chart by Christian Curator."
    omitted = (
        '<p class="cc-viz-note">The chart shows every question Lifeway reported in its release. One item, '
        "which miracle the Gospels do not record, is left out because the release and Lifeway's frequencies "
        "report give different figures for it.</p>"
    )

    return (
        '<section class="cc-viz-section" id="by-the-numbers">\n'
        '<h2 class="cc-viz-label">By the Numbers</h2>\n'
        '<div class="cc-viz-title">What Churchgoers Got Right</div>\n'
        f'<p class="cc-viz-intro">In August 2026 Lifeway Research quizzed {esc(study["sample"])} on the Bible. '
        "Try five of the questions, reworded here, then see how churchgoers did on each skill.</p>\n"
        f'<ol class="cc-quiz" id="bl-quiz">{"".join(items)}</ol>\n'
        '<figure class="cc-viz" id="quiz-results">\n'
        f"{svg}\n<figcaption>{esc(caption)}</figcaption>\n{omitted}\n{table}\n"
        f"{source_line([study], extra=quiz_extra)}\n"
        "</figure>\n"
        f'<div class="cc-viz-reads"><div class="cc-viz-reads-label">Where to go next</div><ul>{"".join(reads)}</ul></div>\n'
        f"{QUIZ_JS}\n</section>"
    )


# --------------------------------------------------------------------------- piece 3


def panel(title: str, rows: list[dict], measures_line: str, svg: str, caption: str, table: str,
          extra_source: str = "", meta: dict | None = None) -> str:
    """One tracker panel. `meta` (default: the first row) supplies question, sample and dates."""
    r0 = meta or rows[0]
    return (
        '<figure class="cc-viz cc-viz-panel">\n'
        f'<div class="cc-viz-kicker">{esc(title)}</div>\n'
        f"{svg}\n<figcaption>{esc(caption)}</figcaption>\n"
        f'<dl class="cc-viz-meta"><dt>Question</dt><dd>{esc(r0["question_wording"])}</dd>'
        f'<dt>Sample</dt><dd>{esc(r0["sample"])}; {esc(r0["population"])}</dd>'
        f'<dt>Field dates</dt><dd>{esc(r0["field_dates"])}</dd>'
        f'<dt>What this measures</dt><dd>{esc(measures_line)}</dd></dl>\n'
        f"{table}\n{source_line([r0], extra=extra_source)}\n</figure>"
    )


def render_pew_panel(data: dict) -> str:
    rows = figure_rows(data, "tracker-pew")
    colors = [GREEN, MUTED, "#c9d2c9", TRACK]
    parts, x, full = [], PAD_X, VB_W - 2 * PAD_X
    for r, c in zip(rows, colors):
        w = full * r["value"] / 100.0
        parts.append(f'<rect x="{x:.1f}" y="6" width="{w:.1f}" height="30" fill="{c}"/>')
        if w > 40:
            parts.append(text(x + w / 2, 26, pct(r["value"]), size=13, fill="#fff" if c == GREEN else INK, weight="600", anchor="middle"))
        x += w
    for i, (r, c) in enumerate(zip(rows, colors)):
        lx, ly = PAD_X + (i % 2) * 220, 56 + (i // 2) * 18
        parts.append(f'<rect x="{lx}" y="{ly - 10}" width="10" height="10" fill="{c}" stroke="#bbb" stroke-width="0.5"/>')
        parts.append(text(lx + 14, ly, f"{r['label']} ({pct(r['value'])})", size=12, fill=GREY))
    desc = "; ".join(f"{r['label']}: {pct(r['value'])}" for r in rows)
    svg = svg_open(82, "Pew: how often U.S. adults read scripture", desc, "bl-pew") + "".join(parts) + "</svg>"
    weekly = rows[0]
    caption = f"{pct(weekly['value'])} of U.S. adults read scripture outside of religious services at least weekly in 2023-24."
    table = data_table("Pew Religious Landscape Study 2023-24, scripture reading", ["Frequency", "U.S. adults"],
                       [[esc(r["label"]), pct(r["value"])] for r in rows])
    return panel(
        "Pew Research Center: reading, all U.S. adults", rows,
        "How often people say they read scripture of any religion on their own. One point in time: Pew says its "
        "2007 and 2014 results are not comparable because the survey moved from phone to online and mail.",
        svg, caption, table, extra_source=f"Chart by Christian Curator. {esc(PEW_DISCLAIMER)}",
    )


def render_lifeway_panel(data: dict) -> str:
    rows = figure_rows(data, "tracker-lifeway")
    daily = [r for r in rows if r["id"].startswith("lifeway-genz-daily-")]
    nodiff = next(r for r in rows if r["id"] == "lifeway-genz-no-difference")
    bars, y = hbar_rows([(r["subgroup"], r["value"], GREEN) for r in daily], top=4)
    sep = f'<line x1="{PAD_X}" y1="{y + 6}" x2="{VB_W - PAD_X}" y2="{y + 6}" stroke="{TRACK}"/>'
    y += 14
    note = text(PAD_X, y + 12, "Gen Z: Bible reading and study has not made", size=13)
    note += text(PAD_X, y + 28, "a significant difference in how they live", size=13)
    y += 18
    bar2, y = hbar_rows([("", nodiff["value"], GAP_RED)], top=y)
    desc = "; ".join(f"{r['subgroup']}: {pct(r['value'])} study daily" for r in daily)
    desc += f"; Gen Z saying it has not made a significant difference: {pct(nodiff['value'])}"
    svg = svg_open(y + 2, "Lifeway: daily Bible study by generation, and the Gen Z application gap", desc, "bl-lw")
    svg += bars + sep + note + bar2 + "</svg>"
    genz = daily[0]
    caption = (
        f"Gen Z churchgoers read more but report less change: {pct(genz['value'])} study the Bible every day, "
        f"the most of any generation, yet {pct(nodiff['value'])} say it has not made a significant difference in how they live."
    )
    extra = figure_rows(data, "tracker-lifeway-table", chart=False)
    table = data_table(
        "Lifeway Research, U.S. Protestant churchgoers by generation, 2025",
        ["Group", "Measure", "Value"],
        [[esc(r["subgroup"]), esc(r["measure"]), pct(r["value"])] for r in daily + [nodiff] + extra],
    )
    return panel(
        "Lifeway Research: reading and application, churchgoers by generation", rows,
        "Churchgoers only (Protestants attending at least monthly), not all Americans. Daily Bible study is "
        "reported practice; the second bar is self-reported effect. Only the Gen Z value of the second measure is published.",
        svg, caption, table, extra_source="Chart by Christian Curator.",
    )


def render_gallup_panel(data: dict) -> str:
    rows = figure_rows(data, "tracker-gallup")
    periods: list[str] = []
    by: dict[tuple[str, str], dict] = {}
    for r in rows:
        if r["period"] not in periods:
            periods.append(r["period"])
        by[(r["period"], r["series"])] = r
    series = [("literal", "Literal word of God", GREEN), ("inspired", "Inspired, not all literal", MUTED),
              ("fables", "Fables, legends, history", BROWN)]
    label_w, full = 64, VB_W - 2 * PAD_X - 64
    parts, lx = [], PAD_X
    for _, lab, c in series:
        parts.append(f'<rect x="{lx}" y="4" width="10" height="10" fill="{c}"/>')
        parts.append(text(lx + 14, 13, lab, size=11, fill=GREY))
        lx += 14 + len(lab) * 5.6 + 14
    y = 24
    for p in reversed(periods):  # newest first
        parts.append(text(PAD_X, y + 12, p, size=12, fill=INK, weight="600" if p == periods[-1] else None))
        x = PAD_X + label_w
        for key, _, c in series:
            v = by[(p, key)]["value"]
            w = full * v / 100.0
            parts.append(f'<rect x="{x:.1f}" y="{y + 1}" width="{w:.1f}" height="14" fill="{c}"/>')
            if w > 22:
                parts.append(text(x + w / 2, y + 12, f"{v:g}", size=10.5, fill="#fff" if c != MUTED else INK, anchor="middle"))
            x += w
        y += 18
    desc = "; ".join(
        f"{p}: literal {by[(p, 'literal')]['value']:g}%, inspired {by[(p, 'inspired')]['value']:g}%, fables {by[(p, 'fables')]['value']:g}%"
        for p in periods
    )
    svg = svg_open(y + 4, "Gallup: Americans' views of the Bible, 1976 to 2022", desc, "bl-gallup") + "".join(parts) + "</svg>"
    first, last = periods[0], periods[-1]
    caption = (
        f"The share of Americans who call the Bible the literal word of God fell from "
        f"{by[(first, 'literal')]['value']:g}% in {first} to {by[(last, 'literal')]['value']:g}% in {last}, while the "
        f"share calling it a book of fables and legends rose from {by[(first, 'fables')]['value']:g}% to "
        f"{by[(last, 'fables')]['value']:g}%."
    )
    table = data_table(
        "Gallup, Americans' views of the Bible, every published wave",
        ["Survey", "Field dates", "Literal", "Inspired", "Fables", ],
        [[esc(p), esc(by[(p, "literal")]["field_dates"])] + [pct(by[(p, k)]["value"]) for k, _, _ in series] for p in reversed(periods)],
    )
    latest = dict(by[(last, "literal")])
    latest["field_dates"] = f"{len(periods)} surveys, {first} to {last}; latest fielded {latest['field_dates']}"
    return panel(
        "Gallup: views of the Bible, all U.S. adults", rows,
        "What people believe the Bible is, not whether they read or know it. Remaining shares had no opinion.",
        svg, caption, table, meta=latest,
        extra_source="Chart by Christian Curator from the figures Gallup publishes; no Gallup graphic is reproduced.",
    )


def render_cited_table(data: dict) -> str:
    rows = figure_rows(data, "table-cited", chart=False)
    out = [[esc(r["source"]), esc(r["measure"]), esc(r["subgroup"]), esc(r["period"]), pct(r["value"])] for r in rows]
    head = "".join(f'<th scope="col">{h}</th>' for h in ("Survey", "Measure", "Group", "Year", "Value"))
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in out)
    seen: list[str] = []
    for r in rows:
        if r["study"] not in seen:
            seen.append(r["study"])
    notes = "".join(
        source_line([next(r for r in rows if r["study"] == sid)],
                    extra="Question wording: " + esc(next(r for r in rows if r["study"] == sid)["question_wording"]) + ".")
        for sid in seen
    )
    return (
        '<div class="cc-viz-cited">\n'
        '<div class="cc-viz-kicker">Barna and American Bible Society: cited figures</div>\n'
        '<p class="cc-viz-note">These surveys are quoted as text, not charted, until their publishers grant '
        "permission. Barna asks whether people read the Bible weekly; ABS sorts people into Scripture "
        "engagement segments built from several questions. They are different measures.</p>\n"
        f'<div class="cc-viz-scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>\n'
        f"{notes}\n</div>"
    )


def render_watch_table(data: dict) -> str:
    """Figures the data watch found in new stories: quoted text with links, newest first.

    Never charted, whatever the license status. A row joins a chart only after a
    person adds question wording, sample and field dates to `rows`.
    """
    rows = sorted(data.get("watch") or [], key=lambda w: (w["verified_date"], w["id"]), reverse=True)
    if not rows:
        return ""
    body = "".join(
        "<tr>"
        f"<td>\u201c{esc(w['quote'])}\u201d</td>"
        f"<td>{esc(w['publisher'])}</td>"
        f"<td>{link(w['url'], w.get('title') or w.get('reported_by') or w['publisher'])}"
        f"{', ' + esc(w['reported_by']) if w.get('reported_by') else ''}</td>"
        f"<td><time datetime=\"{esc(w['verified_date'])}\">{esc(w['verified_date'])}</time></td>"
        "</tr>"
        for w in rows
    )
    head = "".join(f'<th scope="col">{h}</th>' for h in ("Figure as reported", "Survey by", "Source", "Checked"))
    return (
        '<div class="cc-viz-cited cc-viz-watch" id="data-watch">\n'
        '<div class="cc-viz-kicker">New figures from the data watch</div>\n'
        '<p class="cc-viz-note">Figures from recent stories, quoted as published and checked against the '
        "linked page on the date shown. They are cited, not charted, until we confirm the question, sample "
        "and field dates.</p>\n"
        f'<div class="cc-viz-scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>\n'
        "</div>"
    )


def render_dataset_jsonld(data: dict, page_date: date) -> str:
    studies = data["studies"]
    based_on = [
        {
            "@type": "CreativeWork",
            "name": s["study_title"],
            "url": s["url"],
            "datePublished": s["publication_date"],
            "publisher": {"@type": "Organization", "name": s["publisher"]},
        }
        for s in studies.values()
    ]
    measures = sorted({r["measure"] for r in merged_rows(data) if not r["id"].startswith("gallup-")})
    measures += ["Views of the Bible (literal, inspired, fables)"]
    years = [int(r["period"][-4:]) for r in merged_rows(data) if re.search(r"\d{4}$", str(r["period"]))]
    doc = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": data["title"],
        "description": data["description"],
        "url": PAGE_URL + "#survey-tracker",
        "sameAs": DATA_URL,
        "creator": {"@type": "Organization", "name": "Christian Curator", "url": "https://www.christiancurator.com"},
        "dateModified": page_date.isoformat(),
        "temporalCoverage": f"{min(years)}/{max(years)}",
        "spatialCoverage": {"@type": "Place", "name": "United States"},
        "isAccessibleForFree": True,
        "variableMeasured": measures,
        "isBasedOn": based_on,
        "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": DATA_RAW_URL}],
    }
    body = json.dumps(doc, indent=2, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{body}\n</script>'


def render_tracker(data: dict, page_date: date, digest: str) -> str:
    barna = {(r["subgroup"], r["period"]): r for r in figure_rows(data, "table-cited", chart=False) if r["source"] == "Barna Group"}
    abs_row = next(r for r in figure_rows(data, "table-cited", chart=False) if r["source"] == "American Bible Society")
    genz = row_by_id(data, "lifeway-genz-daily-genz")
    nodiff = row_by_id(data, "lifeway-genz-no-difference")
    top = (
        "Engagement measures disagree, so the honest answer depends on the survey and the measure. "
        f"Barna shows a 2025 rise in weekly Bible reading ({pct(barna[('U.S. adults', '2024')]['value'])} in 2024 to "
        f"{pct(barna[('U.S. adults', '2025')]['value'])} in 2025), led by Gen Z and Millennials. "
        f"American Bible Society shows its Scripture Engaged segment down in 2026, at {pct(abs_row['value'])}. "
        f"Lifeway finds Gen Z churchgoers reading more ({pct(genz['value'])} study the Bible daily) but applying less "
        f"({pct(nodiff['value'])} say it has not made a significant difference in how they live)."
    )
    changelog = "".join(
        f"<li><time datetime=\"{esc(e['date'])}\">{esc(e['date'])}</time>: {esc(e['note'])}</li>"
        for e in sorted(data.get("changelog", []), key=lambda e: e["date"], reverse=True)
    )
    watch = render_watch_table(data)
    watch = f"{watch}\n" if watch else ""
    cite = (
        f'Cite this page: "{PAGE_TITLE}" Christian Curator, {PAGE_URL}, last updated {long_date(page_date)}. '
        f'Data: {link(DATA_URL, "surveys.json")}.'
    )
    return (
        f"<!-- CC-BL-VIZ-DATA-HASH:{digest} -->\n"
        '<section class="cc-viz-section cc-tracker" id="survey-tracker">\n'
        '<h2 class="cc-viz-label">Survey Tracker</h2>\n'
        '<div class="cc-viz-title">Is Bible Reading Rising or Falling?</div>\n'
        f'<p class="cc-viz-intro">{esc(top)}</p>\n'
        f"{render_pew_panel(data)}\n{render_lifeway_panel(data)}\n{render_gallup_panel(data)}\n{render_cited_table(data)}\n"
        f"{watch}"
        '<div class="cc-viz-methods">\n'
        '<p><strong>Methods.</strong> We do not merge surveys; each panel is one survey\'s own measure, with its own '
        "question, sample and field dates, and panels do not share an axis. Figures are copied from each publisher's "
        "release or report and checked against the source page on the date in the data file. Charts are ours; no "
        "publisher's chart or image is reproduced.</p>\n"
        f'<div class="cc-viz-reads-label">Changelog</div><ul class="cc-viz-changelog">{changelog}</ul>\n'
        f'<p class="cc-viz-cite">{cite}</p>\n'
        "</div>\n"
        f"{render_dataset_jsonld(data, page_date)}\n"
        "</section>"
    )


# --------------------------------------------------------------------------- page


def marker_re(name: str) -> re.Pattern:
    return re.compile(
        rf"(<!-- CC-BL-VIZ-{name}:START -->\n?)(.*?)(\n?<!-- CC-BL-VIZ-{name}:END -->)", re.S
    )


def replace_block(page: str, name: str, content: str) -> str:
    pattern = marker_re(name)
    found = pattern.findall(page)
    if len(found) != 1:
        raise BuildError(f"expected exactly one CC-BL-VIZ-{name} marker pair, found {len(found)}")
    return pattern.sub(lambda m: m.group(1) + content + m.group(3), page, count=1)


LAST_UPDATED_RE = re.compile(r'(<p class="cc-last-updated">Last updated: )([A-Z][a-z]+ \d{1,2}, \d{4})(</p>)')
DATE_MODIFIED_RE = re.compile(r'("@type": "Article".*?"dateModified": ")(\d{4}-\d{2}-\d{2})(")', re.S)
HASH_RE = re.compile(r"<!-- CC-BL-VIZ-DATA-HASH:([0-9a-f]+) -->")


def page_last_updated(page: str) -> date:
    m = LAST_UPDATED_RE.search(page)
    if not m:
        raise BuildError("page has no 'Last updated' line")
    return datetime.strptime(m.group(2), "%B %d, %Y").date()


def set_dates(page: str, new_date: date) -> str:
    page, n1 = LAST_UPDATED_RE.subn(lambda m: m.group(1) + long_date(new_date) + m.group(3), page, count=1)
    page, n2 = DATE_MODIFIED_RE.subn(lambda m: m.group(1) + new_date.isoformat() + m.group(3), page, count=1)
    if not (n1 and n2):
        raise BuildError("could not update Last updated and dateModified")
    return page


def build_page(page: str, data: dict, today: date) -> str:
    errors = validate(data)
    if errors:
        raise BuildError("invalid data file:\n  " + "\n  ".join(errors))
    digest = data_hash(data)
    old = HASH_RE.search(page)
    page_date = page_last_updated(page)
    if not old or old.group(1) != digest:
        page_date = today
        page = set_dates(page, today)
    page = replace_block(page, "GAP", render_gap(data))
    page = replace_block(page, "QUIZ", render_quiz(data))
    page = replace_block(page, "TRACKER", render_tracker(data, page_date, digest))
    return page


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", type=Path, default=DATA_PATH)
    ap.add_argument("--page", type=Path, default=PAGE_PATH)
    ap.add_argument("--date", type=date.fromisoformat, default=None, help="date to stamp if the data changed")
    ap.add_argument("--check", action="store_true", help="exit 1 if the page is out of date; write nothing")
    args = ap.parse_args(argv)

    today = args.date or datetime.now(ZoneInfo("America/New_York")).date()
    original = args.page.read_text(encoding="utf-8")
    try:
        updated = build_page(original, load_data(args.data), today)
    except BuildError as exc:
        print(f"build_biblical_literacy_viz: {exc}", file=sys.stderr)
        return 2
    if updated == original:
        print("biblical literacy visuals: up to date")
        return 0
    if args.check:
        print("biblical literacy visuals: page is out of date; run scripts/build_biblical_literacy_viz.py", file=sys.stderr)
        return 1
    args.page.write_text(updated, encoding="utf-8")
    print(f"biblical literacy visuals: wrote {args.page.relative_to(REPO_ROOT) if args.page.is_relative_to(REPO_ROOT) else args.page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
