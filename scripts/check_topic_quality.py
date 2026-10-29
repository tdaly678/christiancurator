"""
check_topic_quality.py — Block placeholder / template-filler entries in the
curated article lists on docs/topics/<slug>/index.html.

Why this exists
---------------
In October 2026 a live review found that /topics/faith-deconstruction/ (one of
the two pages carrying most Search Console impressions) was showing entries
like "Article on On Deconstruction & Faith #1" with href="#", "The Biblical
Basis for On Deconstruction & Faith", and annotations such as "A pastoral
reflection on how Biblical Literacy connects to the gospel…". No script in
this repo generates those strings. They came from an early bulk template and
then survived every later pass because topic pages are hand-curated HTML. This
check stops that kind of filler from shipping again.

What it flags (inside each <article class="cc-article-entry">)
---------------------------------------------------------------
  missing-url        href absent, empty, "#", or not http(s)
  placeholder-title  title contains "Article on"
  template-title     title contains "On <Topic Name>" (the topic name pasted
                     into a stock title) or a stock title stem
  filler-annotation  annotation matches a known boilerplate sentence
  dup-annotation     identical annotation text on 3+ different topic pages

A byline with only an outlet and no author is allowed; many hand-curated pages
use that format on purpose.

Ratchet, not a cliff
--------------------
Some older pages still contain filler (see the baseline file). Failing on
every one of them would block the whole daily commit, so this check uses a
ratchet. `scripts/topic_quality_baseline.json` records the known violation
count per slug. The check fails if any page has MORE violations than its
baseline, and a page with no baseline entry is allowed none. When you clean a
page, run with --update-baseline so the lower count is locked in.

Where it runs
-------------
`.github/workflows/daily_run.yml` runs it *before* the commit step, so a
regression keeps the run from publishing. `topic_quality.yml` also runs it on
every push that touches docs/topics/, to catch hand edits.

Usage
-----
    python scripts/check_topic_quality.py                  # gate (exit 1 on regression)
    python scripts/check_topic_quality.py --report         # list every violation
    python scripts/check_topic_quality.py --update-baseline

The script never modifies topic pages.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOPICS_DIR = ROOT / "docs" / "topics"
BASELINE = Path(__file__).resolve().parent / "topic_quality_baseline.json"

sys.path.insert(0, str(ROOT))
try:
    from frontend.topics_data import TOPICS  # type: ignore
    TOPIC_NAMES = {t["slug"]: t["name"] for t in TOPICS}
except Exception:  # topics_data shape changed — fall back to the H1 only
    TOPIC_NAMES = {}

ENTRY_RE = re.compile(r'<article class="cc-article-entry">(.*?)</article>', re.S)
TITLE_RE = re.compile(r'<(div|h[2-4]) class="cc-article-title">\s*(?:<a\b([^>]*)>(.*?)</a>|(.*?))\s*</\1>', re.S)
HREF_RE = re.compile(r'\bhref="([^"]*)"')
ANNOT_RE = re.compile(r'<(div|p) class="cc-article-annotation">(.*?)</\1>', re.S)
H1_RE = re.compile(r'<h1 class="cc-topic-title">(.*?)</h1>', re.S)

# Stock title stems from the original bulk template. "{t}" is the topic name.
TEMPLATE_TITLE_STEMS = [
    r"^The Biblical Basis for\b",
    r"^Historical Development of On\b",
    r"^Rethinking .* for a New Generation$",
    r"^Defending Traditional Views on On\b",
    r"^Pastoral Care and On\b",
    r"^Unity and Disagreement: On\b",
    r"\bin Evangelical Thought$",
    r"^Contemporary Evangelical [A-Z][\w ]+: A Crisis of Authority$",
]

# Boilerplate annotations. Matched as prefixes after whitespace is collapsed.
FILLER_ANNOTATIONS = [
    r"A pastoral reflection on how ",
    r"A contemporary reflection on how ",
    r"A foundational evangelical perspective on this topic",
    r"An accessible theological survey helping readers understand the major positions",
    r"A collection of essays representing multiple evangelical perspectives",
    r"A careful exegetical study of key biblical passages that inform",
    r"Exploring the practical implications: how pastors should think about",
    r"Tracing how evangelical theology on this topic has evolved",
    r"An analysis of how current cultural pressures are reshaping",
    r"A sophisticated theological defense of classical evangelical teaching",
    r"How younger evangelicals are re-examining inherited positions",
    r"A call for charity and deeper engagement as evangelicals",
]
FILLER_RE = re.compile("|".join(f"(?:^{p})" for p in FILLER_ANNOTATIONS))
STEM_RES = [re.compile(p) for p in TEMPLATE_TITLE_STEMS]


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _topic_names(slug: str, page: str) -> list[str]:
    names = []
    if slug in TOPIC_NAMES:
        names.append(TOPIC_NAMES[slug])
    m = H1_RE.search(page)
    if m:
        h1 = _text(m.group(1))
        names.append(h1[3:] if h1.startswith("On ") else h1)
    return [n for n in dict.fromkeys(names) if n]


def scan_page(slug: str, page: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (violations, annotations). Each violation is (code, detail)."""
    out: list[tuple[str, str]] = []
    annotations: list[str] = []
    names = _topic_names(slug, page)
    for i, m in enumerate(ENTRY_RE.finditer(page), 1):
        body = m.group(1)
        t = TITLE_RE.search(body)
        _, attrs, linked, bare = (t.groups() if t else ("", "", "", ""))
        title = _text(linked or bare or "")
        href_m = HREF_RE.search(attrs or "")
        href = (href_m.group(1).strip() if href_m else "")
        label = f"#{i} {title[:70]!r}"

        if not href or href == "#" or not re.match(r"https?://", href):
            out.append(("missing-url", label))
        if re.search(r"\bArticle on\b", title):
            out.append(("placeholder-title", label))
        elif any(f"On {n}" in title and title != f"On {n}" for n in names) or any(r.search(title) for r in STEM_RES):
            out.append(("template-title", label))

        a = ANNOT_RE.search(body)
        ann = _text(a.group(2)) if a else ""
        if ann:
            annotations.append(ann)
            if FILLER_RE.search(ann):
                out.append(("filler-annotation", f"{label}: {ann[:70]!r}"))
    return out, annotations


def scan_all() -> dict[str, list[tuple[str, str]]]:
    results: dict[str, list[tuple[str, str]]] = {}
    ann_pages: dict[str, set[str]] = defaultdict(set)
    ann_by_slug: dict[str, list[str]] = {}
    for path in sorted(TOPICS_DIR.glob("*/index.html")):
        slug = path.parent.name
        page = path.read_text(encoding="utf-8")
        v, anns = scan_page(slug, page)
        results[slug] = v
        ann_by_slug[slug] = anns
        for a in anns:
            ann_pages[a].add(slug)
    for slug, anns in ann_by_slug.items():
        for a in anns:
            if len(ann_pages[a]) >= 3 and not FILLER_RE.search(a):
                results[slug].append(("dup-annotation", f"on {len(ann_pages[a])} pages: {a[:70]!r}"))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", action="store_true", help="print every violation, not just regressions")
    ap.add_argument("--update-baseline", action="store_true", help="rewrite the baseline to current counts")
    args = ap.parse_args()

    results = scan_all()
    counts = {s: len(v) for s, v in results.items() if v}

    if args.update_baseline:
        BASELINE.write_text(json.dumps(dict(sorted(counts.items())), indent=2) + "\n", encoding="utf-8")
        print(f"Baseline written: {len(counts)} page(s), {sum(counts.values())} known violation(s).")
        return 0

    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    regressions = {s: c for s, c in counts.items() if c > baseline.get(s, 0)}
    improved = {s: (b, counts.get(s, 0)) for s, b in baseline.items() if counts.get(s, 0) < b}

    if args.report:
        for slug, v in results.items():
            for code, detail in v:
                print(f"{slug}: {code}: {detail}")
        print()

    for slug in sorted(regressions):
        print(f"::error title=Topic quality::{slug} has {counts[slug]} curated-list violation(s) (baseline {baseline.get(slug, 0)})")
        for code, detail in results[slug]:
            print(f"    {code}: {detail}")
    for slug, (b, c) in sorted(improved.items()):
        print(f"{slug}: improved {b} → {c}; run with --update-baseline to lock it in.")

    print(f"Topic quality: {len(counts)} page(s) with known filler, {sum(counts.values())} violation(s); "
          f"{len(regressions)} regression(s).")
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
