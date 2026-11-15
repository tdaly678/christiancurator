"""The daily email is sent at most once per Eastern day, and only after the
site is committed (Nov 15 2026: a failed voice gate after the send let the
6 AM slot email again).

Covers curator/email_sender.py (Brevo pre-send check, send_campaign,
pending email), scripts/send_daily_email.py and the workflow step order.

Run: python3 -m unittest tests.test_email_dedupe
"""
import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from curator import email_sender as es  # noqa: E402
from scripts import send_daily_email  # noqa: E402

NOV15 = date(2026, 11, 15)


def campaign(status="sent", sent="2026-11-15T10:07:41.000Z", lists=(2,), **kw):
    c = {"id": kw.pop("id", 101), "name": "Christian Curator — November 15, 2026",
         "status": status, "sentDate": sent, "recipients": {"lists": list(lists)}}
    c.update(kw)
    return c


def brevo_get(campaigns):
    resp = mock.Mock()
    resp.raise_for_status = mock.Mock()
    resp.json = lambda: {"campaigns": campaigns, "count": len(campaigns)}
    return mock.Mock(return_value=resp)


def brevo_post():
    return mock.Mock(return_value=mock.Mock(raise_for_status=mock.Mock(),
                                            json=lambda: {"id": 202}))


class Keys:
    """Patch the Brevo credentials and pin the edition date to Nov 15."""

    def __init__(self, day=NOV15):
        self.patches = [
            mock.patch.object(es, "BREVO_API_KEY", "k"),
            mock.patch.object(es, "BREVO_SENDER_EMAIL", "a@b.c"),
            mock.patch.object(es, "edition_date", return_value=day),
        ]

    def __enter__(self):
        for p in self.patches:
            p.start()

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()


class FindSentCampaignTests(unittest.TestCase):
    def test_sent_today_to_the_list_matches(self):
        self.assertEqual(es.find_sent_campaign([campaign()], NOV15)["id"], 101)

    def test_queued_and_in_process_count_as_sent(self):
        for status in ("queued", "in_process", "inProcess", "archive"):
            with self.subTest(status=status):
                c = campaign(status=status, sent=None, scheduledAt="2026-11-15T10:07:00Z")
                self.assertIsNotNone(es.find_sent_campaign([c], NOV15))

    def test_draft_and_suspended_do_not_count(self):
        # A draft is what's left when sendNow failed: nothing reached readers.
        for status in ("draft", "suspended"):
            with self.subTest(status=status):
                self.assertIsNone(es.find_sent_campaign([campaign(status=status)], NOV15))

    def test_uses_the_eastern_date(self):
        # 02:30 UTC Nov 15 is 9:30 PM Nov 14 in New York: yesterday's email.
        c = campaign(sent="2026-11-15T02:30:00Z")
        self.assertIsNone(es.find_sent_campaign([c], NOV15))
        self.assertIsNotNone(es.find_sent_campaign([c], date(2026, 11, 14)))

    def test_offset_timestamps(self):
        c = campaign(sent="2026-11-15T05:07:12.000-05:00")
        self.assertIsNotNone(es.find_sent_campaign([c], NOV15))

    def test_other_list_is_ignored(self):
        self.assertIsNone(es.find_sent_campaign([campaign(lists=(7,))], NOV15))

    def test_missing_recipients_falls_back_to_our_name(self):
        ours = campaign(recipients={})
        theirs = campaign(recipients={}, name="Some other newsletter")
        self.assertIsNotNone(es.find_sent_campaign([ours], NOV15))
        self.assertIsNone(es.find_sent_campaign([theirs], NOV15))


class BrevoCheckTests(unittest.TestCase):
    def test_lists_classic_campaigns_newest_first(self):
        get = brevo_get([campaign()])
        with Keys(), mock.patch.object(es.requests, "get", get):
            self.assertEqual(es.brevo_sent_campaign()["id"], 101)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["type"], "classic")
        self.assertEqual(params["sort"], "desc")

    def test_network_error_raises(self):
        get = mock.Mock(side_effect=requests.exceptions.ConnectionError("down"))
        with Keys(), mock.patch.object(es.requests, "get", get):
            with self.assertRaises(es.BrevoCheckError):
                es.brevo_sent_campaign()

    def test_http_error_raises(self):
        resp = mock.Mock()
        resp.raise_for_status = mock.Mock(side_effect=requests.exceptions.HTTPError("401"))
        with Keys(), mock.patch.object(es.requests, "get", mock.Mock(return_value=resp)):
            with self.assertRaises(es.BrevoCheckError):
                es.brevo_sent_campaign()


class SendCampaignTests(unittest.TestCase):
    def test_sends_when_nothing_sent_today(self):
        post = brevo_post()
        with Keys(), mock.patch.object(es.requests, "get", brevo_get([])), \
             mock.patch.object(es.requests, "post", post):
            self.assertTrue(es.send_campaign("Subject", "<html></html>"))
        self.assertEqual(post.call_count, 2)  # create, then sendNow
        self.assertTrue(post.call_args_list[1].args[0].endswith("/202/sendNow"))

    def test_refuses_when_brevo_shows_todays_send(self):
        post = brevo_post()
        with Keys(), mock.patch.object(es.requests, "get", brevo_get([campaign()])), \
             mock.patch.object(es.requests, "post", post):
            self.assertFalse(es.send_campaign("Subject", "<html></html>"))
        post.assert_not_called()

    def test_yesterdays_send_does_not_block_today(self):
        post = brevo_post()
        old = campaign(sent="2026-11-14T10:07:00Z")
        with Keys(), mock.patch.object(es.requests, "get", brevo_get([old])), \
             mock.patch.object(es.requests, "post", post):
            self.assertTrue(es.send_campaign("Subject", "<html></html>"))

    def test_fails_closed_when_brevo_cannot_answer(self):
        post = brevo_post()
        get = mock.Mock(side_effect=requests.exceptions.Timeout("slow"))
        with Keys(), mock.patch.object(es.requests, "get", get), \
             mock.patch.object(es.requests, "post", post):
            self.assertFalse(es.send_campaign("Subject", "<html></html>"))
        post.assert_not_called()

    def test_force_skips_the_check(self):
        post = brevo_post()
        get = brevo_get([campaign()])
        with Keys(), mock.patch.object(es.requests, "get", get), \
             mock.patch.object(es.requests, "post", post):
            self.assertTrue(es.send_campaign("Subject", "<html></html>", force=True))
        get.assert_not_called()
        self.assertEqual(post.call_count, 2)

    def test_send_email_passes_force_through(self):
        with mock.patch.object(es, "prepare_email", return_value=("S", "<h/>")), \
             mock.patch.object(es, "send_campaign", return_value=True) as send:
            es.send_email([], force=True)
        send.assert_called_once_with("S", "<h/>", force=True)

    def test_nov_15_replay_second_slot_does_not_resend(self):
        """5:07 AM run sends; 6:07 AM run sees it on Brevo and sends nothing."""
        sent = []

        def post(url, **kw):
            if url == es.BREVO_API_URL:
                sent.append(campaign(id=len(sent) + 1, status="draft", sent=None,
                                     createdAt="2026-11-15T10:07:30Z"))
                cid = sent[-1]["id"]
            else:
                cid = int(url.rstrip("/").split("/")[-2])
                c = next(c for c in sent if c["id"] == cid)
                c["status"], c["sentDate"] = "sent", "2026-11-15T10:07:41Z"
            return mock.Mock(raise_for_status=mock.Mock(), json=lambda: {"id": cid})

        def get(url, **kw):
            listed = list(reversed(sent))
            return mock.Mock(raise_for_status=mock.Mock(),
                             json=lambda: {"campaigns": listed})

        with Keys(), mock.patch.object(es.requests, "get", side_effect=get), \
             mock.patch.object(es.requests, "post", side_effect=post):
            self.assertTrue(es.send_campaign("First", "<html></html>"))
            self.assertFalse(es.send_campaign("Second", "<html></html>"))
        self.assertEqual([c["status"] for c in sent], ["sent"])


class SendDailyEmailScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "output" / "email_pending.json"

    def tearDown(self):
        self.tmp.cleanup()

    def hold(self, force=False, day=NOV15):
        with mock.patch.object(es, "edition_date", return_value=day):
            es.save_pending_email("Subject", "<html>x</html>", force=force, path=self.path)

    def test_no_pending_file_is_a_clean_no_op(self):
        post = brevo_post()
        with Keys(), mock.patch.object(es.requests, "post", post):
            self.assertEqual(send_daily_email.main(self.path), 0)
        post.assert_not_called()

    def test_sends_and_clears_the_pending_file(self):
        self.hold()
        post = brevo_post()
        with Keys(), mock.patch.object(es.requests, "get", brevo_get([])), \
             mock.patch.object(es.requests, "post", post):
            self.assertEqual(send_daily_email.main(self.path), 0)
        self.assertEqual(post.call_args_list[0].kwargs["json"]["subject"], "Subject")
        self.assertEqual(post.call_args_list[0].kwargs["json"]["htmlContent"],
                         "<html>x</html>")
        self.assertFalse(self.path.exists())

    def test_already_sent_today_is_refused_without_failing(self):
        self.hold()
        post = brevo_post()
        with Keys(), mock.patch.object(es.requests, "get", brevo_get([campaign()])), \
             mock.patch.object(es.requests, "post", post):
            self.assertEqual(send_daily_email.main(self.path), 0)
        post.assert_not_called()

    def test_brevo_check_failure_fails_the_step_and_sends_nothing(self):
        self.hold()
        post = brevo_post()
        get = mock.Mock(side_effect=requests.exceptions.ConnectionError("down"))
        with Keys(), mock.patch.object(es.requests, "get", get), \
             mock.patch.object(es.requests, "post", post):
            self.assertEqual(send_daily_email.main(self.path), 1)
        post.assert_not_called()

    def test_force_email_sends_even_when_already_sent(self):
        self.hold(force=True)
        post = brevo_post()
        get = brevo_get([campaign()])
        with Keys(), mock.patch.object(es.requests, "get", get), \
             mock.patch.object(es.requests, "post", post):
            self.assertEqual(send_daily_email.main(self.path), 0)
        get.assert_not_called()
        self.assertEqual(post.call_count, 2)

    def test_stale_edition_is_never_sent(self):
        self.hold(day=date(2026, 11, 14))
        post = brevo_post()
        with Keys(), mock.patch.object(es.requests, "get", brevo_get([])), \
             mock.patch.object(es.requests, "post", post):
            self.assertEqual(send_daily_email.main(self.path), 1)
        post.assert_not_called()

    def test_pending_file_records_force(self):
        self.hold(force=True)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["edition"], "2026-11-15")
        self.assertTrue(data["force"])


class WorkflowOrderTests(unittest.TestCase):
    """The email step must follow every publish-blocking gate and the commit."""

    @classmethod
    def setUpClass(cls):
        text = (ROOT / ".github/workflows/daily_run.yml").read_text(encoding="utf-8")
        cls.text = text
        cls.steps = re.findall(r"^      - name: (.+)$", text, flags=re.M)

    def index(self, prefix):
        return next(i for i, s in enumerate(self.steps) if s.startswith(prefix))

    def test_send_comes_after_gates_and_commit(self):
        send = self.index("Send daily email")
        for prefix in ("Run pipeline", "Gate topic curated lists", "Gate voice pages",
                       "Commit output files"):
            with self.subTest(step=prefix):
                self.assertLess(self.index(prefix), send)

    def test_pipeline_defers_the_email(self):
        self.assertIn("python3 main.py --defer-email ${{ needs.guard.outputs.pipeline_args }}",
                      self.text)

    def test_send_step_runs_only_on_success_with_brevo_secrets(self):
        block = self.text.split("- name: Send daily email", 1)[1].split("- name:", 1)[0]
        self.assertIn("if: success()", block)
        self.assertIn("secrets.BREVO_API_KEY", block)
        self.assertIn("python3 scripts/send_daily_email.py", block)


if __name__ == "__main__":
    unittest.main()
