#!/usr/bin/env python3
"""Exit non-zero if any configured feed has returned 0 items for 7+ run days.

Reads docs/feed_health.json, written by fetcher/rss_fetcher.py on every run.
Runs near the end of the daily workflow (after the commit), so the site still
publishes but the run is marked failed and GitHub sends its failure email.
Fix by correcting the URL in fetcher/sources.py or removing the source.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from fetcher.rss_fetcher import FEED_HEALTH_PATH, ZERO_STREAK_FAIL_DAYS  # noqa: E402


def main() -> int:
    if not FEED_HEALTH_PATH.exists():
        print("::error title=Feed health::docs/feed_health.json missing; the fetcher did not run.")
        return 1
    report = json.loads(FEED_HEALTH_PATH.read_text(encoding="utf-8"))
    by_name = {s["source"]: s for s in report.get("sources", [])}
    dead = {name: s for name, s in report.get("zero_streaks", {}).items()
            if s.get("days", 0) >= ZERO_STREAK_FAIL_DAYS and name in by_name}
    empty_today = [s for s in report.get("sources", []) if not s.get("n_entries")]
    stale = [s for s in report.get("sources", []) if s.get("stale")]

    lines = [f"Feed health for run {report.get('run_at')}: "
             f"{len(by_name) - len(empty_today)}/{len(by_name)} feeds returned items."]
    for s in empty_today:
        streak = report["zero_streaks"].get(s["source"], {}).get("days", 1)
        lines.append(f"- EMPTY {s['source']} ({s.get('error') or 'no items'}; {streak} day(s) in a row)")
    for s in stale:
        lines.append(f"- STALE {s['source']} (newest item {s.get('newest_date')})")
    print("\n".join(lines))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## Feed health\n\n" + "\n".join(lines) + "\n")

    if dead:
        names = ", ".join(f"{n} ({s['days']} days)" for n, s in dead.items())
        print(f"::error title=Feed health::Feeds empty for {ZERO_STREAK_FAIL_DAYS}+ days: {names}. "
              "Fix or remove them in fetcher/sources.py.")
        return 1
    print("Feed health OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
