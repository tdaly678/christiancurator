"""scripts/verify_live.py: the daily run confirms the edition reached the live site."""
import sys
from datetime import date
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import verify_live as vl  # noqa: E402

DAY = date(2026, 11, 15)


def resp(status=200, text=""):
    return mock.Mock(status_code=status, text=text)


def site(archive=200, home_text="Sunday, November 15, 2026"):
    def get(url):
        return resp(archive) if "/archive/" in url else resp(200, home_text)
    return get


def test_live_when_archive_and_homepage_date_are_up():
    assert vl.live_problem(DAY, get=site()) is None


def test_missing_archive_is_reported():
    assert "HTTP 404" in vl.live_problem(DAY, get=site(archive=404))


def test_homepage_still_on_yesterday_is_reported():
    assert "November 15, 2026" in vl.live_problem(DAY, get=site(home_text="November 14, 2026"))


def test_network_error_is_a_problem_not_a_crash():
    def get(url):
        raise requests.ConnectionError("dns")
    assert "fetch failed" in vl.live_problem(DAY, get=get)


class Clock:
    def __init__(self):
        self.t = 0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_stalled_deploy_gets_one_rebuild_then_goes_live(capsys):
    clock = Clock()
    rebuilds = []
    check = lambda day: None if clock.t >= 900 else "homepage does not show it yet"  # noqa: E731
    code = vl.main(["--date", "2026-11-15"], check=check,
                   rebuild=lambda: rebuilds.append(1) or "rebuild requested: HTTP 201",
                   sleep=clock.sleep, clock=clock)
    assert code == 0
    assert rebuilds == [1]
    assert "::warning title=Pages deploy::" in capsys.readouterr().out


def test_never_live_fails_loudly(capsys):
    clock = Clock()
    code = vl.main(["--date", "2026-11-15", "--no-rebuild"], check=lambda d: "HTTP 404",
                   rebuild=lambda: 1 / 0, sleep=clock.sleep, clock=clock)
    assert code == 1
    assert clock.t >= vl.TIMEOUT
    assert "::error title=Site not live::" in capsys.readouterr().out


def test_rebuild_request_needs_a_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert "not requested" in vl.request_rebuild(post=lambda *a, **k: 1 / 0)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "tdaly678/christiancurator")
    post = mock.Mock(return_value=resp(201))
    assert vl.request_rebuild(post=post) == "rebuild requested: HTTP 201"
    assert post.call_args.args[0].endswith("/repos/tdaly678/christiancurator/pages/builds")


def test_workflow_verifies_after_the_email_and_before_indexnow():
    text = (Path(vl.__file__).parent.parent / ".github/workflows/daily_run.yml").read_text()
    send = text.index("scripts/send_daily_email.py")
    verify = text.index("scripts/verify_live.py")
    indexnow = text.index("scripts/indexnow_ping.py")
    assert send < verify < indexnow
    assert "pages: write" in text
