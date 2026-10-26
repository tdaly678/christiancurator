"""
ai_health.py — records Anthropic API failures that the pipeline deliberately
swallows (so the site still publishes) and makes them visible afterwards.

Every AI step catches its own exceptions and falls back to a degraded result.
That keeps the daily run alive, but it also meant a dead API key or an empty
credit balance went unnoticed for weeks (Daily Pulse stopped on 2026-09-05
because the account ran out of credit). Each fallback now calls
record_failure(); main.py calls write_report() at the end of the run, and the
workflow's final step runs scripts/check_ai_health.py, which fails the job
(after the site has been committed) so GitHub emails the repo owner.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPORT_PATH = Path(__file__).parent.parent / "output" / "ai_health.json"

_failures: dict[str, dict] = {}


def _classify(message: str) -> str:
    m = message.lower()
    if "credit balance is too low" in m:
        return "billing"
    if "authentication_error" in m or "invalid x-api-key" in m:
        return "auth"
    if "not_found_error" in m:
        return "model"
    if "overloaded" in m or "529" in m:
        return "overloaded"
    return "other"


def record_failure(step: str, exc: BaseException | str) -> None:
    """Note that an AI step fell back to a degraded result. Cheap; call freely."""
    message = str(exc)
    entry = _failures.setdefault(step, {"count": 0, "kind": _classify(message), "first_error": message[:400]})
    entry["count"] += 1


def failures() -> dict[str, dict]:
    return dict(_failures)


HINTS = {
    "billing": "Anthropic account is out of credit. Add credits or enable auto-reload at "
               "console.anthropic.com → Plans & Billing (the org that owns the ANTHROPIC_API_KEY secret).",
    "auth": "ANTHROPIC_API_KEY is invalid or revoked. Create a new key and update the repo secret "
            "(Settings → Secrets and variables → Actions → ANTHROPIC_API_KEY).",
    "model": "A configured model ID was rejected. Check the model= strings in curator/*.py.",
    "overloaded": "Anthropic API was overloaded through all retries. Usually transient.",
    "other": "See the run log for the full error.",
}


def write_report(daily_summary_ok: bool) -> dict:
    """Persist the run's AI health and emit GitHub Actions annotations."""
    report = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "daily_summary_ok": daily_summary_ok,
        "failures": _failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if not _failures and daily_summary_ok:
        return report

    lines = []
    if not daily_summary_ok:
        lines.append("Daily Pulse summary was NOT generated — no /daily/ page today.")
    for step, f in _failures.items():
        lines.append(f"{step}: {f['count']} failure(s) [{f['kind']}] — {HINTS[f['kind']]}")

    print("\n=== AI HEALTH: DEGRADED ===")
    for line in lines:
        print(f"  {line}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for line in lines:
            print(f"::error title=AI step degraded::{line}")
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as fh:
                fh.write("## ⚠️ AI steps degraded\n\n")
                for line in lines:
                    fh.write(f"- {line}\n")
    return report
