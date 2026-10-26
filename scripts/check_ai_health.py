#!/usr/bin/env python3
"""Exit non-zero if the day's run degraded any AI step.

Runs as the last workflow step (after the commit), so the site still publishes
but the run is marked failed and GitHub sends its failure email.
"""
import json
import sys
from pathlib import Path

REPORT = Path(__file__).parent.parent / "output" / "ai_health.json"


def main() -> int:
    if not REPORT.exists():
        print("::error title=AI health::output/ai_health.json missing — main.py did not finish.")
        return 1
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    bad = not report.get("daily_summary_ok") or bool(report.get("failures"))
    print(json.dumps(report, indent=2))
    if bad:
        print("::error title=AI health::One or more AI steps fell back to degraded output. See the job summary.")
        return 1
    print("AI health OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
