#!/usr/bin/env python3
"""One-time backfill: mark the Anthropic credit-outage rows in article_history.

From 2026-09-06 through 2026-10-25 every Claude scoring call failed (empty
credit balance; see .christian-orchestrator/anthropic-pulse-diagnosis-2026-10-26.md),
so each article got the fallback score of 5 plus mechanical boosts and no
tags. The data confirms the window: every row in it has empty tags, and the
days on either side have none. Those rows get scored_by "fallback" with
scored_by_backfilled true so tuning can exclude them. Rows outside the window
are left alone; new runs write scored_by directly (curator/scorer.py).

Idempotent. Usage: python scripts/backfill_scored_by.py [--dry-run]
"""
import json
import sys
from pathlib import Path

HISTORY = Path(__file__).parent.parent / "docs" / "article_history.json"
START, END = "2026-09-06", "2026-10-25"


def main() -> int:
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    changed = 0
    for row in history:
        if START <= row.get("date_shown", "") <= END and "scored_by" not in row:
            row["scored_by"] = "fallback"
            row["scored_by_backfilled"] = True
            changed += 1
    print(f"Marked {changed} rows from {START} to {END} as scored_by=fallback.")
    if changed and "--dry-run" not in sys.argv:
        HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
