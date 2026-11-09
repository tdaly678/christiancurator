#!/usr/bin/env python3
"""run_data_watch.py: the daily topic data watch (see curator/data_watch.py).

Runs in .github/workflows/daily_run.yml after the pipeline and before
build_recent_articles.py. Reads today's scored pool (output/articles.json) and
recent digest rows (docs/article_history.json), keeps its state in
docs/data_watch.json, updates topic pages in place, and writes a
"Topic data to review" section to the job summary.

It never fails the run: any error becomes a ::warning and exit 0, unless
--strict. A source page that 403s is a warning and a "link only" action.

Usage:
    python scripts/run_data_watch.py              # normal daily run
    python scripts/run_data_watch.py --dry-run    # report only, write nothing
    python scripts/run_data_watch.py --date 2026-11-09
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curator import data_watch  # noqa: E402

POOL = REPO_ROOT / "output" / "articles.json"
HISTORY = REPO_ROOT / "docs" / "article_history.json"
STATE = REPO_ROOT / "docs" / "data_watch.json"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _summary(text: str) -> None:
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", type=date.fromisoformat, default=None)
    ap.add_argument("--dry-run", action="store_true", help="report only; write no file")
    ap.add_argument("--strict", action="store_true", help="exit 1 on an internal error")
    args = ap.parse_args(argv)
    today = args.date or datetime.now(ZoneInfo("America/New_York")).date()

    try:
        pool = _load(POOL, {})
        pool = pool.get("articles", []) if isinstance(pool, dict) else pool
        history = _load(HISTORY, [])
        state = _load(STATE, {})
        state = data_watch.run_watch(pool, history, state, today, write=not args.dry_run)
        if not args.dry_run:
            STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for s in state["last_run"]["stories"]:
            if s.get("warning"):
                print(f"::warning::{s['warning']}")
        for p in state["last_run"]["pages"]:
            if p.get("warning"):
                print(f"::warning::data watch {p['slug']}: {p['note']}")
        _summary(data_watch.summary_markdown(state))
    except Exception as exc:
        traceback.print_exc()
        print(f"::warning::data watch skipped: {type(exc).__name__}: {exc}")
        _summary(f"## Topic data to review\n\nData watch skipped after an error: `{type(exc).__name__}: {exc}`\n")
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
