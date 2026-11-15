import importlib.util
import json
import os

_spec = importlib.util.spec_from_file_location(
    "check_feed_health", os.path.join(os.path.dirname(__file__), "..", "scripts", "check_feed_health.py"))
cfh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cfh)

REPORT = {
    "run_at": "2026-11-09T09:30:00",
    "sources": [
        {"source": "TGC", "url": "https://tgc/feed", "http_status": 200, "n_entries": 60},
        {"source": "Scot McKnight", "url": "https://scotmcknight.substack.com/feed",
         "http_status": 403, "n_entries": 0, "error": "HTTP 403"},
        {"source": "Gone", "url": "https://gone/feed", "http_status": 200, "n_entries": 0},
        {"source": "Pew Research", "url": "https://pew/feed", "http_status": 403,
         "n_entries": 0, "error": "HTTP 403"},
    ],
    "zero_streaks": {
        "Scot McKnight": {"days": 10},
        "Gone": {"days": 8},
        "Pew Research": {"days": 1},
        "Removed Source": {"days": 30},
    },
}


def _run(tmp_path, monkeypatch, report, argv=()):
    path = tmp_path / "feed_health.json"
    if report is not None:
        path.write_text(json.dumps(report))
    summary = tmp_path / "summary.md"
    monkeypatch.setattr(cfh, "FEED_HEALTH_PATH", path)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    return cfh.main(list(argv)), summary


def test_long_streaks_warn_without_failing(tmp_path, monkeypatch, capsys):
    code, summary = _run(tmp_path, monkeypatch, REPORT)
    out = capsys.readouterr().out
    assert code == 0
    assert "::warning title=Feed health::2 feeds" in out
    assert "::error" not in out
    text = summary.read_text()
    assert "## Feed health" in text and "Scot McKnight" in text and "Gone" in text


def test_strict_restores_failure(tmp_path, monkeypatch, capsys):
    code, _ = _run(tmp_path, monkeypatch, REPORT, ["--strict"])
    assert code == 1
    assert "::error title=Feed health::" in capsys.readouterr().out


def test_missing_file_still_errors(tmp_path, monkeypatch):
    code, _ = _run(tmp_path, monkeypatch, None)
    assert code == 1


def test_report_separates_blocked_from_empty():
    lines, long_streaks = cfh.build_report(REPORT)
    text = "\n".join(lines)
    # Removed sources and short streaks are not long streaks.
    assert set(long_streaks) == {"Scot McKnight", "Gone"}
    blocked = text.index("Blocked on runner")
    empty = text.index("Empty 7+ days")
    recent = text.index("Empty today, under 7 days")
    assert blocked < text.index("Scot McKnight") < empty < text.index("- Gone") < recent
    assert text.index("Pew Research") > recent


def test_healthy_report_is_ok(tmp_path, monkeypatch, capsys):
    report = {"run_at": "x", "sources": REPORT["sources"][:1], "zero_streaks": {}}
    code, _ = _run(tmp_path, monkeypatch, report)
    assert code == 0
    assert "Feed health OK." in capsys.readouterr().out


def _feeds(n_ok, n_empty, substack_ok=0, substack_empty=0):
    rows = [{"source": f"ok{i}", "url": f"https://ok{i}/feed", "http_status": 200, "n_entries": 5}
            for i in range(n_ok)]
    rows += [{"source": f"e{i}", "url": f"https://e{i}/feed", "http_status": 200, "n_entries": 0}
             for i in range(n_empty)]
    rows += [{"source": f"s{i}", "url": f"https://s{i}.substack.com/feed", "http_status": 200,
              "n_entries": 3, "via": "proxy"} for i in range(substack_ok)]
    rows += [{"source": f"z{i}", "url": f"https://z{i}.substack.com/feed", "http_status": 403,
              "n_entries": 0, "error": "HTTP 403", "proxy_error": "HTTP 401"}
             for i in range(substack_empty)]
    return {"run_at": "2026-11-15T10:00:00", "sources": rows, "zero_streaks": {}}


def test_a_few_429s_through_the_proxy_are_not_an_outage(tmp_path, monkeypatch, capsys):
    code, _ = _run(tmp_path, monkeypatch, _feeds(43, 4, substack_ok=26, substack_empty=4))
    assert code == 0
    assert "::error" not in capsys.readouterr().out


def test_most_feeds_empty_is_an_outage(tmp_path, monkeypatch, capsys):
    code, summary = _run(tmp_path, monkeypatch, _feeds(10, 30))
    out = capsys.readouterr().out
    assert code == 1
    assert "::error title=Feed outage::30 of 40 feeds" in out
    assert "**Outage:**" in summary.read_text()


def test_every_substack_feed_empty_is_a_proxy_outage(tmp_path, monkeypatch, capsys):
    # Oct 31 to Nov 9 2026: 30 Substack feeds 403 on the runner, a third of all feeds.
    code, _ = _run(tmp_path, monkeypatch, _feeds(47, 0, substack_empty=30))
    out = capsys.readouterr().out
    assert code == 1
    assert "all 30 Substack feeds returned nothing" in out and "HTTP 401" in out
