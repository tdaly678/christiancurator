"""Clock and idempotency decisions for the 5:00 AM ET daily run.

Run: python3 -m unittest tests.test_morning_guard
"""

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.morning_guard import (  # noqa: E402
    ARCHIVE_REF,
    RUN,
    SKIP,
    archive_published,
    decide,
    pipeline_args,
)


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)


WORKFLOW = (ROOT / ".github" / "workflows" / "daily_run.yml").read_text(encoding="utf-8")


class PipelineArgs(unittest.TestCase):
    def test_morning_ping_cannot_force_or_suppress_email(self):
        self.assertEqual(pipeline_args(morning=True, no_email=True, force_email=True), "")

    def test_manual_no_email_wins_over_force_email(self):
        self.assertEqual(pipeline_args(morning=False, no_email=True, force_email=True), "--no-email")

    def test_manual_force_email(self):
        self.assertEqual(pipeline_args(morning=False, no_email=False, force_email=True), "--force-email")


class EasternClock(unittest.TestCase):
    def test_winter_10_07_utc_is_5_07_est_and_runs(self):
        # 2026-11-15 is EST. 10:07 UTC is the on-time instant.
        decision = decide(at("2026-11-15T10:07:00Z"), already_published=False, event_name="schedule")
        self.assertEqual(decision.decision, RUN)
        self.assertEqual(decision.reason, "on_time")
        self.assertEqual(decision.eastern_date, "2026-11-15")
        self.assertEqual(decision.pipeline_args, "")

    def test_summer_09_07_utc_is_5_07_edt_and_runs(self):
        decision = decide(at("2026-07-15T09:07:00Z"), already_published=False, event_name="schedule")
        self.assertEqual(decision.decision, RUN)
        self.assertEqual(decision.reason, "on_time")
        self.assertEqual(decision.eastern_date, "2026-07-15")

    def test_day_after_fall_back_2026_is_5_07_est(self):
        # Clocks fell back at 2:00 AM on 2026-11-01. 10:07 UTC is 5:07 AM EST.
        decision = decide(at("2026-11-01T10:07:00Z"), already_published=False, event_name="schedule")
        self.assertEqual((decision.decision, decision.reason, decision.eastern_date),
                         (RUN, "on_time", "2026-11-01"))

    def test_spring_forward_2027_is_5_07_edt(self):
        # DST starts at 2:00 AM on 2027-03-14. 09:07 UTC is 5:07 AM EDT.
        decision = decide(at("2027-03-14T09:07:00Z"), already_published=False, event_name="schedule")
        self.assertEqual((decision.decision, decision.reason, decision.eastern_date),
                         (RUN, "on_time", "2027-03-14"))

    def test_winter_09_utc_cron_misfire_is_too_early(self):
        # 09:07 UTC in November is 4:07 AM EST, before the 4:50 AM floor.
        decision = decide(at("2026-11-15T09:07:00Z"), already_published=False, event_name="schedule")
        self.assertEqual((decision.decision, decision.reason), (SKIP, "too_early"))

    def test_summer_08_37_utc_misfire_does_not_publish_at_4_37_am(self):
        decision = decide(at("2026-07-15T08:37:00Z"), already_published=False, event_name="schedule")
        self.assertEqual((decision.decision, decision.reason), (SKIP, "too_early"))
        self.assertEqual(decision.eastern_date, "2026-07-15")

    def test_utc_date_and_eastern_date_diverge_after_8_pm_est(self):
        # 01:30 UTC Nov 15 is 8:30 PM EST on Nov 14. The archive day is Nov 14.
        decision = decide(at("2026-11-15T01:30:00Z"), already_published=False, event_name="schedule")
        self.assertEqual(decision.eastern_date, "2026-11-14")
        self.assertEqual(decision.reason, "late_catchup")


class Idempotency(unittest.TestCase):
    def test_second_arrival_at_5_07_noops(self):
        decision = decide(at("2026-11-15T10:07:00Z"), already_published=True, event_name="schedule")
        self.assertEqual((decision.decision, decision.reason), (SKIP, "already_published"))

    def test_late_schedule_does_not_email_again_when_morning_ran(self):
        # Oct 31 2026 shape: GitHub delivered around 10:35 AM ET, still EDT.
        decision = decide(at("2026-10-31T14:35:00Z"), already_published=True, event_name="schedule")
        self.assertEqual(decision.eastern_date, "2026-10-31")
        self.assertEqual((decision.decision, decision.reason), (SKIP, "already_published"))

    def test_late_schedule_still_publishes_when_nothing_has_run(self):
        decision = decide(at("2026-10-31T14:35:00Z"), already_published=False, event_name="schedule")
        self.assertEqual((decision.decision, decision.reason), (RUN, "late_catchup"))
        self.assertEqual(decision.pipeline_args, "")

    def test_summer_6_07_am_catchup_runs_only_if_5_am_missed(self):
        missed = decide(at("2026-07-15T10:07:00Z"), already_published=False, event_name="schedule")
        done = decide(at("2026-07-15T10:07:00Z"), already_published=True, event_name="schedule")
        self.assertEqual((missed.decision, missed.reason), (RUN, "late_catchup"))
        self.assertEqual((done.decision, done.reason), (SKIP, "already_published"))

    def test_morning_ping_ignores_force_email_when_already_published(self):
        decision = decide(
            at("2026-07-15T09:02:00Z"),
            already_published=True,
            event_name="workflow_dispatch",
            morning=True,
            force_email=True,
        )
        self.assertEqual((decision.decision, decision.reason), (SKIP, "already_published"))
        self.assertEqual(decision.pipeline_args, "")

    def test_morning_ping_ignores_no_email_and_sends(self):
        decision = decide(
            at("2026-07-15T09:00:00Z"),
            already_published=False,
            event_name="workflow_dispatch",
            morning=True,
            no_email=True,
        )
        self.assertEqual((decision.decision, decision.reason, decision.pipeline_args),
                         (RUN, "on_time", ""))

    def test_morning_ping_before_4_50_does_not_start_the_day(self):
        # 4:00 AM EST. The winter 09:00 UTC Cloudflare slot must not dispatch,
        # and the guard would refuse it if it did.
        decision = decide(
            at("2026-11-15T09:00:00Z"),
            already_published=False,
            event_name="workflow_dispatch",
            morning=True,
        )
        self.assertEqual((decision.decision, decision.reason), (SKIP, "too_early"))

    def test_ping_a_few_seconds_before_5_still_runs(self):
        # 4:59 AM EDT, the summer 09:00 UTC cron if it starts slightly early.
        decision = decide(
            at("2026-07-15T08:59:30Z"),
            already_published=False,
            event_name="workflow_dispatch",
            morning=True,
        )
        self.assertEqual((decision.decision, decision.reason), (RUN, "on_time"))

    def test_manual_force_email_runs_even_when_published(self):
        decision = decide(
            at("2026-11-15T15:00:00Z"),
            already_published=True,
            event_name="workflow_dispatch",
            force_email=True,
        )
        self.assertEqual((decision.decision, decision.reason, decision.pipeline_args),
                         (RUN, "manual_override", "--force-email"))

    def test_manual_no_email_republishes(self):
        decision = decide(
            at("2026-11-15T15:00:00Z"),
            already_published=True,
            event_name="workflow_dispatch",
            no_email=True,
            force_email=True,
        )
        self.assertEqual(decision.pipeline_args, "--no-email")
        self.assertEqual(decision.reason, "manual_override")

    def test_plain_dispatch_noops_when_the_day_already_published(self):
        decision = decide(
            at("2026-11-15T16:00:00Z"),
            already_published=True,
            event_name="workflow_dispatch",
        )
        self.assertEqual((decision.decision, decision.reason), (SKIP, "already_published"))

    def test_plain_dispatch_runs_when_the_day_has_not_published(self):
        decision = decide(
            at("2026-11-15T16:12:00Z"),
            already_published=False,
            event_name="workflow_dispatch",
        )
        self.assertEqual((decision.decision, decision.reason), (RUN, "manual"))

    def test_unknown_event_is_rejected(self):
        with self.assertRaises(ValueError):
            decide(at("2026-11-15T10:07:00Z"), already_published=False, event_name="pull_request")


class ArchiveRef(unittest.TestCase):
    def _repo(self, day: str | None) -> Path:
        path = Path(self.enterContext(tempfile.TemporaryDirectory()))
        subprocess.check_call(["git", "init", "-b", "main"], cwd=path, stdout=subprocess.DEVNULL)
        subprocess.check_call(["git", "config", "user.email", "t@example.com"], cwd=path)
        subprocess.check_call(["git", "config", "user.name", "Test"], cwd=path)
        (path / "README").write_text("x\n", encoding="utf-8")
        if day:
            archive = path / "docs" / "archive" / day / "index.html"
            archive.parent.mkdir(parents=True)
            archive.write_text("<html></html>\n", encoding="utf-8")
        subprocess.check_call(["git", "add", "."], cwd=path)
        subprocess.check_call(["git", "commit", "-m", "init"], cwd=path, stdout=subprocess.DEVNULL)
        subprocess.check_call(["git", "update-ref", f"refs/remotes/{ARCHIVE_REF}", "HEAD"], cwd=path)
        return path

    def test_sees_committed_archive_for_that_eastern_day_only(self):
        repo = self._repo("2026-11-15")
        self.assertTrue(archive_published(repo, datetime(2026, 11, 15).date()))
        self.assertFalse(archive_published(repo, datetime(2026, 11, 16).date()))

    def test_missing_archive(self):
        repo = self._repo(None)
        self.assertFalse(archive_published(repo, datetime(2026, 11, 15).date()))


class Cli(unittest.TestCase):
    def _run(self, iso: str, **env):
        full = os.environ.copy()
        full["TZ"] = "UTC"
        full["CC_SKIP_FETCH"] = "1"
        full.update(env)
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "morning_guard.py"), "--at", iso],
            cwd=ROOT,
            env=full,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_stdout_is_stable_under_utc_timezone(self):
        result = self._run(
            "2026-11-15T10:07:00Z",
            CC_EVENT_NAME="schedule",
            CC_ALREADY_PUBLISHED="false",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("decision=run\n", result.stdout)
        self.assertIn("reason=on_time\n", result.stdout)
        self.assertIn("eastern_date=2026-11-15\n", result.stdout)
        self.assertIn("pipeline_args=\n", result.stdout)

    def test_skip_is_exit_zero(self):
        result = self._run(
            "2026-10-31T14:35:00Z",
            CC_EVENT_NAME="schedule",
            CC_ALREADY_PUBLISHED="true",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("decision=skip\n", result.stdout)
        self.assertIn("reason=already_published\n", result.stdout)
        self.assertIn("already_published", result.stderr)

    def test_unknown_event_exits_nonzero(self):
        result = self._run("2026-11-15T10:07:00Z", CC_EVENT_NAME="push", CC_ALREADY_PUBLISHED="false")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unexpected event", result.stderr)


class WorkflowContract(unittest.TestCase):
    def test_schedule_is_5_07_am_eastern_not_the_old_utc_cron(self):
        self.assertIn('cron: "7 5 * * *"', WORKFLOW)
        self.assertIn('timezone: "America/New_York"', WORKFLOW)
        self.assertNotIn('cron: "0 10 * * *"', WORKFLOW)
        self.assertNotIn("6:00 AM", WORKFLOW)

    def test_catchup_slots_and_utc_fallback_exist(self):
        self.assertIn('cron: "17 6 * * *"', WORKFLOW)
        self.assertIn('cron: "37 8 * * *"', WORKFLOW)
        self.assertIn('cron: "7 10 * * *"', WORKFLOW)

    def test_second_arrival_cannot_cancel_an_in_flight_run(self):
        self.assertIn("cancel-in-progress: false", WORKFLOW)
        self.assertIn("daily-curator-morning", WORKFLOW)

    def test_pipeline_runs_only_after_the_guard_says_run(self):
        self.assertIn("needs: guard", WORKFLOW)
        self.assertIn("needs.guard.outputs.decision == 'run'", WORKFLOW)
        self.assertIn("needs.guard.outputs.pipeline_args", WORKFLOW)

    def test_morning_input_and_eastern_timezone(self):
        self.assertIn("morning:", WORKFLOW)
        self.assertIn("TZ: America/New_York", WORKFLOW)
        self.assertIn("scripts/morning_guard.py", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
