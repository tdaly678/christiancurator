"""
prune_sources.py: quarterly prune of quiet independent feeds (P2.4, 2026-10-30).

An independent source (`independent: True`, role primary) leaves the daily
feed list when BOTH hold:
  * 0 placements in the last WINDOW_DAYS (90). A placement is an
    article_history.json row (top 20, Worth Your Time) or an appearance on a
    docs/archive/YYYY-MM-DD/ page (`'article_source':'<name>'`) in the window.
  * fewer than MIN_POSTS_PER_MONTH (2) posts a month, measured from the live
    feed: items published in the window divided by window months.
Sources first added to sources.py less than WINDOW_DAYS ago (per git history)
are never pruned.

Pruned sources move to the "Voices watchlist (NOT fetched)" comment block at
the bottom of fetcher/sources.py. That list is not fetched; it exists for
topic-page curation (hand-picked reads for the 70 topic pages).

Usage:
  python scripts/prune_sources.py                 # dry run: print what would move
  python scripts/prune_sources.py --report PATH   # dry run, also write a markdown report
  python scripts/prune_sources.py --apply         # edit fetcher/sources.py

Run quarterly (early Jan / Apr / Jul / Oct), review the dry run, then --apply
and commit. Nothing is removed without --apply.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SOURCES_PATH = ROOT / "fetcher" / "sources.py"
HISTORY_PATH = ROOT / "docs" / "article_history.json"
ARCHIVE_DIR = ROOT / "docs" / "archive"
WINDOW_DAYS = 90
MIN_POSTS_PER_MONTH = 2.0
WATCHLIST_ANCHOR = "# ── Media candidates rejected"


# ---------------------------------------------------------------- pure helpers

def independents(sources: list[dict]) -> list[dict]:
    return [s for s in sources if s.get("independent") and s.get("role", "primary") == "primary"]


def count_history_placements(history: list[dict], cutoff: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in history:
        if row.get("date_shown", "") >= cutoff and row.get("scored_by") != "media":
            name = row.get("source_name", "")
            counts[name] = counts.get(name, 0) + 1
    return counts


def count_archive_placements(pages: dict[str, str], cutoff: str) -> dict[str, int]:
    """pages: {YYYY-MM-DD: html}. Counts days each source appears on."""
    counts: dict[str, int] = {}
    for day, html in pages.items():
        if day < cutoff:
            continue
        names = set(re.findall(r"'article_source':'([^']*)'", html))
        names |= set(re.findall(r'data-src="([^"]*)"', html))
        for name in names:
            counts[name] = counts.get(name, 0) + 1
    return counts


def posts_per_month(published: list[str], today: date, window_days: int = WINDOW_DAYS) -> float:
    cutoff = today - timedelta(days=window_days)
    n = 0
    for p in published:
        try:
            if parsedate_to_datetime(p).date() >= cutoff:
                n += 1
        except (TypeError, ValueError):
            continue
    return round(n / (window_days / 30.0), 2)


def decide(sources: list[dict], placements: dict[str, int], rates: dict[str, float],
           added_on: dict[str, str], today: date) -> list[dict]:
    """One row per independent: name, placements, posts_per_month, added_on, prune, reason."""
    grace_cutoff = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    rows = []
    for s in independents(sources):
        name = s["name"]
        placed, rate, added = placements.get(name, 0), rates.get(name, 0.0), added_on.get(name, "")
        if added and added > grace_cutoff:
            prune, reason = False, f"added {added}, inside the {WINDOW_DAYS}-day grace period"
        elif placed == 0 and rate < MIN_POSTS_PER_MONTH:
            prune, reason = True, f"0 placements in {WINDOW_DAYS} days, {rate:g} posts/month"
        else:
            prune, reason = False, ""
        rows.append({"name": name, "url": s["url"], "placements": placed, "posts_per_month": rate,
                     "added_on": added, "prune": prune, "reason": reason})
    return sorted(rows, key=lambda r: (not r["prune"], r["placements"], r["posts_per_month"]))


def remove_source_block(text: str, name: str) -> tuple[str, bool]:
    """Remove the `{ ... },` dict for `name` from sources.py text."""
    lines = text.split("\n")
    target = f'"name": {json.dumps(name, ensure_ascii=False)},'
    idx = next((i for i, l in enumerate(lines) if l.strip() == target), None)
    if idx is None:
        return text, False
    start = idx
    while start > 0 and lines[start].strip() != "{":
        start -= 1
    end = idx
    while end < len(lines) - 1 and lines[end].strip() != "},":
        end += 1
    if lines[start].strip() != "{" or lines[end].strip() != "},":
        return text, False
    del lines[start:end + 1]
    return "\n".join(lines), True


def add_to_watchlist(text: str, name: str, url: str, reason: str) -> str:
    """Append a line to the Voices watchlist comment block (before the media block)."""
    entry = f"#   {name:<22} {url}: pruned {date.today().isoformat()} ({reason})"
    pos = text.find(WATCHLIST_ANCHOR)
    if pos == -1:
        return text.rstrip("\n") + "\n" + entry + "\n"
    # Insert before the "#" spacer line that precedes the media header.
    spacer = text.rfind("#\n", 0, pos)
    at = spacer if spacer != -1 else pos
    return text[:at] + entry + "\n" + text[at:]


# ------------------------------------------------------------------- live data

def _archive_pages(cutoff: str) -> dict[str, str]:
    pages = {}
    if ARCHIVE_DIR.exists():
        for d in ARCHIVE_DIR.iterdir():
            f = d / "index.html"
            if d.is_dir() and d.name >= cutoff and f.exists():
                pages[d.name] = f.read_text(encoding="utf-8", errors="ignore")
    return pages


def _added_on(name: str) -> str:
    """Date of the oldest commit that added this source's name line, or ''."""
    try:
        out = subprocess.run(
            ["git", "log", "--format=%ad", "--date=short", "-S", f'"name": "{name}"', "--",
             "fetcher/sources.py"],
            cwd=ROOT, capture_output=True, text=True, timeout=60).stdout.split()
        return out[-1] if out else ""
    except Exception:
        return ""


def _feed_rate(source: dict, today: date) -> tuple[str, float, str]:
    from fetcher.rss_fetcher import fetch_feed
    articles, health = fetch_feed(source)
    rate = posts_per_month([a.get("published", "") for a in articles], today)
    return source["name"], rate, health.get("error", "")


def main() -> int:
    ap = argparse.ArgumentParser(description="Quarterly prune of quiet independent feeds.")
    ap.add_argument("--apply", action="store_true", help="edit fetcher/sources.py")
    ap.add_argument("--report", help="write a markdown report to this path")
    args = ap.parse_args()

    from fetcher.sources import SOURCES
    today = date.today()
    cutoff = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    candidates = independents(SOURCES)

    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else []
    placements = count_history_placements(history, cutoff)
    for name, n in count_archive_placements(_archive_pages(cutoff), cutoff).items():
        placements[name] = placements.get(name, 0) + n

    with ThreadPoolExecutor(max_workers=8) as pool:
        feed = list(pool.map(lambda s: _feed_rate(s, today), candidates))
        added = list(pool.map(lambda s: (s["name"], _added_on(s["name"])), candidates))
    rates = {name: rate for name, rate, _ in feed}
    errors = {name: err for name, _, err in feed if err}
    rows = decide(SOURCES, placements, rates, dict(added), today)

    lines = [f"# Source prune {'APPLY' if args.apply else 'dry run'}, {today.isoformat()}", "",
             f"Rule: independent, 0 placements in {WINDOW_DAYS} days AND < {MIN_POSTS_PER_MONTH:g} "
             f"posts/month. {len(rows)} independents checked.", "",
             "| Source | Placements | Posts/month | Added | Decision |", "|---|---|---|---|---|"]
    for r in rows:
        note = r["reason"] + (f"; feed error: {errors[r['name']]}" if r["name"] in errors else "")
        lines.append(f"| {r['name']} | {r['placements']} | {r['posts_per_month']:g} | "
                     f"{r['added_on'] or '?'} | {'MOVE to watchlist' if r['prune'] else 'keep'}"
                     f"{': ' + note if note else ''} |")
    movers = [r for r in rows if r["prune"]]
    lines += ["", f"{len(movers)} source(s) would move: {', '.join(r['name'] for r in movers) or 'none'}."]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")

    if args.apply and movers:
        text = SOURCES_PATH.read_text(encoding="utf-8")
        for r in movers:
            text, ok = remove_source_block(text, r["name"])
            if ok:
                text = add_to_watchlist(text, r["name"], r["url"], r["reason"])
            else:
                print(f"  Could not locate the block for {r['name']}; left in place.")
        SOURCES_PATH.write_text(text, encoding="utf-8")
        print(f"Edited {SOURCES_PATH.relative_to(ROOT)}. Review the diff, then commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
