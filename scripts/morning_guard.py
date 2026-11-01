"""Decide whether this Daily Curator Run arrival should publish.

The workflow fires more than once each morning (a 5:07 AM America/New_York
schedule, later catch-up schedules, and an optional Cloudflare ping). The
second arrival must no-op. A late arrival must still publish when today's
Eastern archive is not on origin/main yet, so a delayed GitHub schedule does
not drop the day.

Clock rules use America/New_York, including the DST transitions. The runner's
TZ is irrelevant.

Exit 0 for both "run" and "skip". Exit 2 when the decision cannot be made
(git fetch failed, unknown event). A skip is a successful no-op.

Not for production: CC_SKIP_FETCH=1 and CC_ALREADY_PUBLISHED skip the network.
The workflow does not set them.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

# Automatic arrivals before this minute-of-day do not publish. 4:50 AM leaves
# room for a ping that starts a few seconds early and still rejects a UTC
# misfire of the 8:37 UTC slot (4:37 AM EDT).
EARLIEST_MINUTE = 4 * 60 + 50
# 4:50–5:59 AM ET is the on-time window. 6:00 AM onward is a catch-up.
ON_TIME_UNTIL_MINUTE = 6 * 60

RUN = "run"
SKIP = "skip"

REASON_ON_TIME = "on_time"
REASON_LATE_CATCHUP = "late_catchup"
REASON_ALREADY_PUBLISHED = "already_published"
REASON_TOO_EARLY = "too_early"
REASON_MANUAL = "manual"
REASON_MANUAL_OVERRIDE = "manual_override"

ALLOWED_EVENTS = {"schedule", "workflow_dispatch"}
ARCHIVE_REF = "origin/main"


@dataclass(frozen=True)
class Decision:
    decision: str
    reason: str
    pipeline_args: str
    eastern_date: str


def as_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def pipeline_args(*, morning: bool, no_email: bool, force_email: bool) -> str:
    """Flags passed to main.py.

    A morning ping always takes the normal path, which sends email. It cannot
    force a second send or suppress the send. On a manual dispatch, no_email
    wins over force_email, matching the workflow's previous behavior.
    """
    if morning:
        return ""
    if no_email:
        return "--no-email"
    if force_email:
        return "--force-email"
    return ""


def to_eastern(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return now.astimezone(EASTERN)


def decide(
    now: datetime,
    *,
    already_published: bool,
    event_name: str,
    morning: bool = False,
    force_email: bool = False,
    no_email: bool = False,
) -> Decision:
    """Return run/skip for one workflow arrival.

    `now` is any timezone-aware instant. The Eastern calendar date is the day
    the archive is named for.
    """
    if event_name not in ALLOWED_EVENTS:
        raise ValueError(f"unexpected event {event_name!r}")

    et = to_eastern(now)
    args = pipeline_args(morning=morning, no_email=no_email, force_email=force_email)
    manual_override = event_name == "workflow_dispatch" and not morning and (force_email or no_email)
    if manual_override:
        return Decision(RUN, REASON_MANUAL_OVERRIDE, args, et.date().isoformat())

    if already_published:
        return Decision(SKIP, REASON_ALREADY_PUBLISHED, args, et.date().isoformat())

    automatic = event_name == "schedule" or morning
    minute_of_day = et.hour * 60 + et.minute
    if automatic and minute_of_day < EARLIEST_MINUTE:
        return Decision(SKIP, REASON_TOO_EARLY, args, et.date().isoformat())

    if automatic and minute_of_day >= ON_TIME_UNTIL_MINUTE:
        reason = REASON_LATE_CATCHUP
    elif automatic:
        reason = REASON_ON_TIME
    else:
        reason = REASON_MANUAL
    return Decision(RUN, reason, args, et.date().isoformat())


def archive_rel(day: date) -> str:
    return f"docs/archive/{day.isoformat()}/index.html"


def archive_published(repo: Path, day: date, ref: str = ARCHIVE_REF) -> bool:
    """True when that Eastern day's archive is already committed on `ref`."""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{archive_rel(day)}"],
        cwd=repo,
        capture_output=True,
    )
    return result.returncode == 0


def fetch_origin_main(repo: Path) -> None:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(
        [
            "git", "fetch", "--no-tags", "--depth=1", "origin",
            "+refs/heads/main:refs/remotes/origin/main",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"git fetch origin main failed: {detail}")


def parse_at(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _emit(decision: Decision, *, clock: str = "", schedule: str = "") -> None:
    lines = "\n".join([
        f"decision={decision.decision}",
        f"reason={decision.reason}",
        f"eastern_date={decision.eastern_date}",
        f"pipeline_args={decision.pipeline_args}",
    ]) + "\n"
    sys.stdout.write(lines)
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(lines)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        rows = [
            "### Morning guard",
            "",
            f"- Decision: `{decision.decision}`",
            f"- Reason: `{decision.reason}`",
            f"- Eastern: {clock or decision.eastern_date}",
        ]
        if schedule:
            rows.append(f"- Schedule: `{schedule}`")
        rows.append(f"- Pipeline args: `{decision.pipeline_args or '(none, sends email)'}`")
        rows.append("")
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(rows))
    print(
        f"Morning guard: {decision.decision} ({decision.reason}) "
        f"eastern={clock or decision.eastern_date} schedule={schedule or '-'} "
        f"args={decision.pipeline_args!r}",
        file=sys.stderr,
    )


def _already_published(repo: Path, day: date) -> bool:
    if "CC_ALREADY_PUBLISHED" in os.environ:
        return as_bool(os.environ["CC_ALREADY_PUBLISHED"])
    if os.environ.get("CC_SKIP_FETCH") != "1":
        fetch_origin_main(repo)
    return archive_published(repo, day)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily Curator Run morning guard")
    parser.add_argument(
        "--at",
        help="ISO-8601 instant to evaluate instead of now (tests and the operator doc)",
    )
    args = parser.parse_args(argv)

    event_name = os.environ.get("CC_EVENT_NAME", "schedule")
    morning = as_bool(os.environ.get("CC_MORNING"))
    force_email = as_bool(os.environ.get("CC_FORCE_EMAIL"))
    no_email = as_bool(os.environ.get("CC_NO_EMAIL"))
    now = parse_at(args.at) if args.at else datetime.now(timezone.utc)
    repo = Path(os.environ.get("CC_REPO", Path(__file__).resolve().parent.parent))
    schedule = os.environ.get("CC_SCHEDULE", "")

    try:
        et = to_eastern(now)
        published = _already_published(repo, et.date())
        decision = decide(
            now,
            already_published=published,
            event_name=event_name,
            morning=morning,
            force_email=force_email,
            no_email=no_email,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"Morning guard failed: {exc}", file=sys.stderr)
        return 2

    _emit(decision, clock=et.strftime("%Y-%m-%d %H:%M %Z"), schedule=schedule)
    return 0


if __name__ == "__main__":
    sys.exit(main())
