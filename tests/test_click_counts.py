import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "fetch_click_counts",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "fetch_click_counts.py"),
)
fcc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fcc)


def _row(day, event, url, n):
    return {"dimensionValues": [{"value": day}, {"value": event}, {"value": url}],
            "metricValues": [{"value": str(n)}]}


def test_parse_takes_max_of_events_not_sum():
    rows = [
        _row("20261030", "article_click", "https://www.example.com/a?utm_source=x", 4),
        _row("20261030", "click", "https://example.com/a/", 5),
        _row("20261029", "article_click", "https://example.com/a", 2),
    ]
    out = fcc.parse_report_rows(rows)
    assert list(out) == ["https://example.com/a"]
    assert out["https://example.com/a"]["by_day"] == {"2026-10-30": 5, "2026-10-29": 2}


def test_parse_skips_internal_and_unknown_events():
    rows = [
        _row("20261030", "click", "https://www.christiancurator.com/topics/prayer/", 9),
        _row("20261030", "page_view", "https://example.com/b", 9),
        _row("20261030", "click", "", 9),
    ]
    assert fcc.parse_report_rows(rows) == {}


def test_merge_replaces_window_and_keeps_older_days():
    existing = {"urls": {
        "https://example.com/a": {"url": "https://example.com/a",
                                  "by_day": {"2026-10-01": 3, "2026-10-30": 1}},
        "https://example.com/gone": {"url": "https://example.com/gone",
                                     "by_day": {"2026-10-30": 2}},
    }}
    fetched = {"https://example.com/a": {"url": "https://example.com/a", "by_day": {"2026-10-30": 6}},
               "https://example.com/new": {"url": "https://example.com/new", "by_day": {"2026-10-29": 1}}}
    merged = fcc.merge_counts(existing, fetched, ["2026-10-29", "2026-10-30"])["urls"]
    assert merged["https://example.com/a"]["by_day"] == {"2026-10-01": 3, "2026-10-30": 6}
    assert merged["https://example.com/a"]["total"] == 9
    assert "https://example.com/gone" not in merged
    assert list(merged)[0] == "https://example.com/a"  # sorted by total


def test_apply_clicks_matches_canonical_url():
    history = [
        {"url": "https://www.example.com/a/", "clicks": 0},
        {"url": "https://example.com/x", "canonical_url": "https://example.com/x", "clicks": 3},
    ]
    urls = {"https://example.com/a": {"total": 7}}
    assert fcc.apply_clicks_to_history(history, urls) == 2
    assert history[0]["clicks"] == 7 and history[1]["clicks"] == 0
