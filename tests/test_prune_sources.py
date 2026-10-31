import ast
import importlib.util
import os
from datetime import date

_spec = importlib.util.spec_from_file_location(
    "prune_sources", os.path.join(os.path.dirname(__file__), "..", "scripts", "prune_sources.py"))
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

TODAY = date(2026, 10, 30)


def test_decide_requires_both_conditions_and_respects_grace():
    sources = [
        {"name": "Quiet", "url": "q", "independent": True},
        {"name": "Busy", "url": "b", "independent": True},
        {"name": "Placed", "url": "p", "independent": True},
        {"name": "New", "url": "n", "independent": True},
        {"name": "Outlet", "url": "o"},
        {"name": "Roundup", "url": "r", "independent": True, "role": "discovery"},
    ]
    rows = ps.decide(sources, placements={"Placed": 2}, rates={"Busy": 6, "Placed": 0.3},
                     added_on={"New": "2026-10-01", "Quiet": "2026-01-01"}, today=TODAY)
    by = {r["name"]: r for r in rows}
    assert set(by) == {"Quiet", "Busy", "Placed", "New"}
    assert [r["name"] for r in rows if r["prune"]] == ["Quiet"]
    assert "grace" in by["New"]["reason"]


def test_counts_and_rate():
    history = [{"source_name": "A", "date_shown": "2026-10-01"},
               {"source_name": "A", "date_shown": "2026-06-01"},
               {"source_name": "M", "date_shown": "2026-10-01", "scored_by": "media"}]
    assert ps.count_history_placements(history, "2026-08-01") == {"A": 1}
    pages = {"2026-10-01": "x 'article_source':'B' 'article_source':'B' data-src=\"C\"",
             "2026-01-01": "'article_source':'D'"}
    assert ps.count_archive_placements(pages, "2026-08-01") == {"B": 1, "C": 1}
    pubs = ["Mon, 26 Oct 2026 10:00:00 +0000", "Thu, 01 Oct 2026 10:00:00 +0000",
            "Wed, 01 Jan 2025 10:00:00 +0000", ""]
    assert ps.posts_per_month(pubs, TODAY) == round(2 / 3, 2)


def test_remove_and_watchlist_on_real_sources_file_stays_valid():
    text = open(ps.SOURCES_PATH, encoding="utf-8").read()
    from fetcher.sources import SOURCES
    for s in ps.independents(SOURCES):
        new, ok = ps.remove_source_block(text, s["name"])
        assert ok, s["name"]
        new = ps.add_to_watchlist(new, s["name"], s["url"], "test")
        tree = ast.parse(new)
        ns = {}
        exec(compile(tree, "sources.py", "exec"), ns)
        names = [x["name"] for x in ns["SOURCES"]]
        assert s["name"] not in names and len(names) == len(SOURCES) - 1
        assert new.index(f"#   {s['name']}") < new.index(ps.WATCHLIST_ANCHOR)
