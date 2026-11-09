#!/usr/bin/env python3
"""Report feeds that have returned 0 items for 7+ run days, without failing the run.

Reads docs/feed_health.json, written by fetcher/rss_fetcher.py on every run.
Runs near the end of the daily workflow (after the commit). Long zero streaks
become ::warning annotations and a "Feed health" section in the job summary, so
they stay visible without marking the whole run failed. Pass --strict to exit 1
on any such streak (the old behavior).

Exit 1 only when docs/feed_health.json is missing (the fetcher did not run), or
with --strict when a streak reaches ZERO_STREAK_FAIL_DAYS.

Substack feeds (*.substack.com) return HTTP 403 to GitHub's runner IPs while the
same URL and headers return 200 from a home connection (first seen 2026-10-31),
so those streaks are listed under "Blocked on runner" rather than as dead feeds.
Fix a truly dead feed by correcting the URL in fetcher/sources.py; removing a
source is Tom's call.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from fetcher.rss_fetcher import FEED_HEALTH_PATH, ZERO_STREAK_FAIL_DAYS  # noqa: E402


def is_blocked(source: dict) -> bool:
    """True when the host refused us (401/403/429) rather than serving an empty feed."""
    return source.get("http_status") in (401, 403, 429)


def build_report(report: dict, fail_days: int = ZERO_STREAK_FAIL_DAYS) -> tuple[list[str], dict]:
    """(summary lines, {name: streak}) for every configured feed empty fail_days+ days."""
    sources = report.get("sources", [])
    by_name = {s["source"]: s for s in sources}
    streaks = report.get("zero_streaks", {})
    long_streaks = {name: s for name, s in streaks.items()
                    if s.get("days", 0) >= fail_days and name in by_name}
    empty_today = [s for s in sources if not s.get("n_entries")]
    stale = [s for s in sources if s.get("stale")]

    lines = [f"Feed health for run {report.get('run_at')}: "
             f"{len(by_name) - len(empty_today)}/{len(by_name)} feeds returned items."]
    blocked = [n for n in long_streaks if is_blocked(by_name[n])]
    empty = [n for n in long_streaks if not is_blocked(by_name[n])]
    if blocked:
        lines.append(f"\n**Blocked on runner, {fail_days}+ days ({len(blocked)}):** "
                     "the host refuses GitHub's IPs; check the feed from a home connection "
                     "before treating it as dead.")
        for n in blocked:
            s = by_name[n]
            lines.append(f"- {n}: {s.get('error') or s.get('http_status')} "
                         f"for {long_streaks[n]['days']} days ({s['url']})")
    if empty:
        lines.append(f"\n**Empty {fail_days}+ days ({len(empty)}):** fix the URL in "
                     "fetcher/sources.py or list it for Tom to review.")
        for n in empty:
            s = by_name[n]
            lines.append(f"- {n}: {s.get('error') or 'no items'} "
                         f"for {long_streaks[n]['days']} days ({s['url']})")
    recent = [s for s in empty_today if s["source"] not in long_streaks]
    if recent:
        lines.append(f"\n**Empty today, under {fail_days} days ({len(recent)}):**")
        for s in recent:
            streak = streaks.get(s["source"], {}).get("days", 1)
            lines.append(f"- {s['source']} ({s.get('error') or 'no items'}; {streak} day(s) in a row)")
    if stale:
        lines.append(f"\n**Stale ({len(stale)}):** newest item over 60 days old.")
        for s in stale:
            lines.append(f"- {s['source']} (newest item {s.get('newest_date')})")
    return lines, long_streaks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true",
                        help=f"exit 1 when any feed has been empty {ZERO_STREAK_FAIL_DAYS}+ days")
    args = parser.parse_args(argv)

    if not FEED_HEALTH_PATH.exists():
        print("::error title=Feed health::docs/feed_health.json missing; the fetcher did not run.")
        return 1
    report = json.loads(FEED_HEALTH_PATH.read_text(encoding="utf-8"))
    lines, long_streaks = build_report(report)
    print("\n".join(lines))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Feed health\n\n" + "\n".join(lines) + "\n")

    if not long_streaks:
        print("Feed health OK.")
        return 0
    names = ", ".join(f"{n} ({s['days']} days)" for n, s in long_streaks.items())
    level = "error" if args.strict else "warning"
    print(f"::{level} title=Feed health::{len(long_streaks)} feeds empty for "
          f"{ZERO_STREAK_FAIL_DAYS}+ days: {names}. See the Feed health section of the job summary.")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
