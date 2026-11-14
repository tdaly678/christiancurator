"""Tests for scripts/build_topic_timeline.py (parallel-timeline explainer visuals)."""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_topic_timeline as btl  # noqa: E402

DATA = REPO / "data" / "topic_timelines" / "eschatology.json"
PAGE = REPO / "docs" / "topics" / "eschatology" / "index.html"


class NoVoices:
    def linkable(self, slug):
        return slug == "john-piper"


def mini():
    return {
        "id": "timelines", "slug": "demo", "label": "Timelines", "title": "Two views",
        "image_title": "Two views side by side", "caption": "What it shows.",
        "stations": [{"id": "a", "label": "Start"}, {"id": "b", "label": "Middle"},
                     {"id": "c", "label": "End"}],
        "common": ["a", "c"],
        "lanes": [
            {"id": "one", "name": "View one", "color": "green",
             "segments": [{"span": ["a"], "kind": "shared"}, {"span": ["b"], "kind": "period", "text": "Wait"},
                          {"span": ["c"], "kind": "shared"}],
             "proponent": {"name": "Writer One", "work": "Essay", "source": "s1"}},
            {"id": "two", "name": "View two", "color": "blue",
             "segments": [{"span": ["a"], "kind": "shared"},
                          {"span": ["b", "c"], "kind": "event", "text": "All at once"}],
             "proponent": {"name": "John Piper", "slug": "john-piper", "work": "Talk", "source": "s1"}},
        ],
        "differ": ["One", "Two", "Three"],
        "sources": [{"id": "s1", "publisher": "Pub", "title": "Essay", "year": 2020,
                     "url": "https://example.org/essay", "fetched": "2026-11-14", "quote": "words"}],
        "place": {"before": "<!-- ANCHOR -->"},
    }


def test_mini_is_valid():
    assert btl.validate(mini(), "<p><!-- ANCHOR --></p>") == []


@pytest.mark.parametrize("mutate, expect", [
    (lambda d: d["lanes"][0]["segments"].pop(1), "gap"),
    (lambda d: d["lanes"][0]["segments"].pop(), "cover every station"),
    (lambda d: d["lanes"][0]["segments"][1].update(kind="shared"), "shared mark"),
    (lambda d: d["lanes"][0]["proponent"].update(source="nope"), "not in sources"),
    (lambda d: d["sources"][0].pop("quote"), "missing quote"),
    (lambda d: d["sources"][0].pop("fetched"), "missing fetched"),
    (lambda d: d.update(caption="A view — another"), "dash"),
    (lambda d: d["sources"][0].update(url="https://example.org/?utm_source=x"), "tracking"),
    (lambda d: d.update(differ=["only one"]), "3 to 5"),
    (lambda d: d["lanes"].pop(), "2 to 5 lanes"),
])
def test_validator_refuses(mutate, expect):
    d = mini()
    mutate(d)
    errs = btl.validate(d, "<!-- ANCHOR -->")
    assert any(expect in e for e in errs), errs


def test_missing_place_anchor():
    assert any("place anchor" in e for e in btl.validate(mini(), "<p>no anchor</p>"))


def test_build_is_idempotent_and_in_place():
    page = "<html><head></head><body><!-- ANCHOR --></body></html>"
    once = btl.build_page(page, mini(), NoVoices())
    twice = btl.build_page(once, mini(), NoVoices())
    assert once == twice
    assert once.count("<!-- CC-TIMELINE:timelines:START -->") == 1
    assert once.index("CC-TIMELINE:timelines:START") < once.index("<!-- ANCHOR -->")


def test_block_contents():
    block = btl.render_block(mini(), NoVoices())
    assert block.count("<svg") == 2
    assert "cc-chart-wide" in block and "cc-chart-narrow" in block
    assert 'role="img"' in block and "<desc" in block
    assert "Table version" in block and 'colspan="2"' in block
    assert '<a href="/voices/john-piper/"' in block
    assert "/voices/writer-one/" not in block
    assert "Chart by Christian Curator" in block
    assert btl.BRAND in block
    assert not re.search("[–—]", block)


def test_desc_spells_out_every_lane():
    desc = btl.lane_desc(mini())
    assert "View one" in desc and "View two" in desc and "All at once" in desc
    assert "All views affirm: Start, End." in desc


def test_fit_shrinks_long_words():
    lines, size = btl.fit("Postmillennialism", 40, 12, True)
    assert size < 12 and lines == ["Postmillennialism"]


def test_optional_year():
    d = mini()
    d["sources"][0].pop("year")
    assert btl.validate(d, "<!-- ANCHOR -->") == []
    assert "(None)" not in btl.render_block(d, NoVoices())


def test_eschatology_data_is_valid_and_page_current():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    html = PAGE.read_text(encoding="utf-8")
    assert btl.validate(d, html) == []
    assert btl.build_page(html, d) == html, "run scripts/build_topic_timeline.py --slug eschatology"
    names = [lane["name"] for lane in d["lanes"]]
    assert names == ["Dispensational premillennialism", "Historic premillennialism",
                     "Amillennialism", "Postmillennialism"]
    assert set(d["common"]) == {"cross", "return", "judgment", "newcreation"}
    assert 'href="#timelines" data-pos="topic-jump"' in html


# ---------------------------------------------------------------- spectrum and matrix types

def _src():
    return [{"id": "s1", "publisher": "Pub", "title": "Essay", "year": 2020,
             "url": "https://example.org/essay", "fetched": "2026-11-14", "quote": "words"}]


def _prop(name, slug=None):
    p = {"name": name, "work": "Essay", "source": "s1"}
    if slug:
        p["slug"] = slug
    return p


def spectrum():
    return {
        "id": "spectrum", "slug": "demo", "type": "spectrum", "label": "Spectrum", "title": "Where views sit",
        "image_title": "Three views on one line", "caption": "What it shows.",
        "axis": {"left": "Word for word", "right": "Thought for thought", "label": "Translation approach"},
        "bands": [{"from": 0, "to": 40, "label": "Formal"}],
        "positions": [
            {"id": "c", "name": "View C", "color": "blue", "at": 90, "text": "Far right.", "proponent": _prop("C")},
            {"id": "a", "name": "View A", "color": "green", "at": 5, "text": "Far left.",
             "proponent": _prop("John Piper", "john-piper")},
            {"id": "x", "name": "View X", "color": "grey", "at": 99, "text": "Beyond.", "outside": True,
             "outside_label": "A paraphrase", "proponent": _prop("X")},
        ],
        "differ": ["One", "Two", "Three"], "sources": _src(), "place": {"before": "<!-- ANCHOR -->"},
    }


def spectrum_2d():
    d = spectrum()
    d.pop("bands")
    d["axis_y"] = {"label": "Common descent", "bottom": "No", "top": "Yes"}
    for p, y in zip(d["positions"], (10, 90, 50)):
        p["y"] = y
    return d


def matrix():
    return {
        "id": "matrix", "slug": "demo", "type": "matrix", "label": "Compared", "title": "Views compared",
        "image_title": "Three views by question", "caption": "What it shows.",
        "columns": [
            {"id": "a", "name": "View A", "color": "green", "proponent": _prop("A")},
            {"id": "b", "name": "View B", "color": "blue", "proponent": _prop("B")},
            {"id": "x", "name": "View X", "color": "grey", "outside": True, "proponent": _prop("X")},
        ],
        "rows": [
            {"id": "q1", "label": "Question one?", "cells": [
                {"text": "Yes, plainly", "mark": "yes"}, {"text": "In part", "mark": "partly"},
                {"text": "No", "mark": "no"}]},
            {"id": "q2", "label": "Question two?", "cells": [
                {"text": "Alpha"}, {"text": "Beta"}, {"text": "Gamma"}]},
        ],
        "differ": ["One", "Two", "Three"], "sources": _src(), "place": {"before": "<!-- ANCHOR -->"},
    }


@pytest.mark.parametrize("make", [spectrum, spectrum_2d, matrix])
def test_new_types_valid_and_render(make):
    d = make()
    assert btl.validate(d, "<!-- ANCHOR -->") == []
    block = btl.render_block(d, NoVoices())
    assert block.count("<svg") == 2
    assert 'role="img"' in block and "<desc" in block and "Table version" in block
    assert "Shown for contrast" in block or "A paraphrase" in block
    assert btl.BRAND in block
    assert not re.search("[–—]", block)
    page = "<html><head></head><body><!-- ANCHOR --></body></html>"
    once = btl.build_page(page, d, NoVoices())
    assert btl.build_page(once, d, NoVoices()) == once
    assert once.count(f"<!-- CC-TIMELINE:{d['id']}:START -->") == 1


def test_spectrum_numbers_left_to_right_and_places():
    d = spectrum()
    assert [p["id"] for p in btl.ordered(d)] == ["a", "c", "x"]
    desc = btl.describe(d)
    assert "1. View A: At the word for word end." in desc
    assert "View X (A paraphrase)" in desc
    table = btl.table_html(d)
    assert "Translation approach" in table and "Toward" not in table.split("View C")[0]
    assert '<a href="/voices/john-piper/"' in btl.render_block(d, NoVoices())


def test_spectrum_2d_placement_names_both_axes():
    d = spectrum_2d()
    assert "common descent" in btl.placement(d, d["positions"][1]).lower()
    assert "Common descent: from No to Yes." in btl.describe(d)


def test_matrix_desc_and_table():
    d = matrix()
    desc = btl.describe(d)
    assert "View A. Question one?: Yes, plainly; Question two?: Alpha." in desc
    assert "View X (Shown for contrast)" in desc
    table = btl.table_html(d)
    assert table.count("<tr>") == 3 and 'data-label="View B"' in table
    wide = btl.render_wide(d)
    assert "In part" in wide and 'stroke-dasharray="4 3"' in wide


@pytest.mark.parametrize("make, mutate, expect", [
    (spectrum, lambda d: d["positions"][0].update(at=120), "0 to 100"),
    (spectrum, lambda d: d["positions"][0].pop("text"), "missing text"),
    (spectrum, lambda d: d["positions"][0].update(y=3), "y needs axis_y"),
    (spectrum, lambda d: d["axis"].pop("right"), "axis needs left and right"),
    (spectrum, lambda d: d["bands"][0].update(to=-1), "band"),
    (spectrum, lambda d: d["positions"].__setitem__(slice(1, None), []), "2 to 7 positions"),
    (spectrum_2d, lambda d: d["positions"][0].pop("y"), "two-axis"),
    (matrix, lambda d: d["rows"][0]["cells"].pop(), "one cell per column"),
    (matrix, lambda d: d["rows"][0]["cells"][0].update(mark="maybe"), "mark must be"),
    (matrix, lambda d: d["rows"][1]["cells"][2].pop("text"), "needs text"),
    (matrix, lambda d: d["columns"][0]["proponent"].update(source="nope"), "not in sources"),
    (matrix, lambda d: d.update(type="pie"), "type must be"),
    (matrix, lambda d: d["columns"][1].update(id="a"), "unique"),
])
def test_new_types_refuse(make, mutate, expect):
    d = make()
    mutate(d)
    errs = btl.validate(d, "<!-- ANCHOR -->")
    assert any(expect in e for e in errs), errs


# ---------------------------------------------------------------- orgchart and chronology types

def orgchart():
    tiers = [{"id": "top", "label": "Whole church"}, {"id": "mid", "label": "Region"},
             {"id": "low", "label": "Congregation"}]

    def chart(cid, color, loose=False):
        return {"id": cid, "name": f"Chart {cid}", "color": color, "tag": "For example, a body",
                "boxes": [{"tier": "top", "text": "Assembly", "sub": "Elders", "loose": loose},
                          {"tier": "mid", "text": "Presbytery"}, {"tier": "low", "text": "Members"}],
                "links": ([{"between": ["top", "mid"], "loose": "No authority"}] if loose else
                          [{"between": ["top", "mid"], "down": "Reviews"}])
                         + [{"between": ["mid", "low"], "down": "Governs", "up": "Elects elders"}],
                "proponent": _prop(cid)}
    return {
        "id": "polity", "slug": "demo", "type": "orgchart", "label": "Polity", "title": "Who decides",
        "image_title": "Two shapes of church government", "caption": "What it shows.",
        "tiers": tiers, "charts": [chart("a", "green"), chart("b", "brown", loose=True)],
        "differ": ["One", "Two", "Three"], "sources": _src(), "place": {"before": "<!-- ANCHOR -->"},
    }


def chronology():
    def ev(i, year, outside=False):
        return {"id": f"e{i}", "date": f"c. {year}", "year": year, "name": f"Model {i}", "who": "A writer",
                "text": "What it says.", "color": "blue", "outside": outside, "proponent": _prop(f"W{i}")}
    return {
        "id": "models", "slug": "demo", "type": "chronology", "label": "History", "title": "Models in order",
        "image_title": "Five models and when they took shape", "caption": "What it shows.",
        "events": [ev(1, 180), ev(2, 1098), ev(3, 1134), ev(4, 1617), ev(5, 1931, outside=True)],
        "differ": ["One", "Two", "Three"], "sources": _src(), "place": {"before": "<!-- ANCHOR -->"},
    }


@pytest.mark.parametrize("make", [orgchart, chronology])
def test_orgchart_and_chronology_render(make):
    d = make()
    assert btl.validate(d, "<!-- ANCHOR -->") == []
    block = btl.render_block(d, NoVoices())
    assert block.count("<svg") == 2 and "<desc" in block and "Table version" in block
    assert btl.BRAND in block and not re.search("[–—]", block)
    page = "<html><head></head><body><!-- ANCHOR --></body></html>"
    once = btl.build_page(page, d, NoVoices())
    assert btl.build_page(once, d, NoVoices()) == once


def test_orgchart_desc_and_table():
    d = orgchart()
    desc = btl.describe(d)
    assert "Chart a. Whole church: Assembly (Elders)" in desc
    assert "upward, elects or consents: Elects elders" in desc and "cooperation only: No authority" in desc
    table = btl.table_html(d)
    assert "Lines of authority" in table and "(cooperation, no authority)" in table
    assert "Cooperation, no authority" in btl.render_wide(d)


def test_chronology_cards_do_not_overlap():
    for n in (4, 5, 6):
        d = chronology()
        d["events"] = d["events"][:n] if n <= 5 else d["events"] + [dict(d["events"][0], id="e6", year=2000)]
        svg = btl.render_wide(d)
        cards = [(float(x), float(w)) for x, w in
                 re.findall(r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)" height="[\d.]+" rx="6"', svg)]
        assert len(cards) == n
        for row in (cards[0::2], cards[1::2]):
            for (x1, w1), (x2, _) in zip(row, row[1:]):
                assert x1 + w1 <= x2
    assert "In date order. 1. c. 180: Model 1" in btl.describe(chronology())


@pytest.mark.parametrize("make, mutate, expect", [
    (orgchart, lambda d: d["charts"][0]["boxes"].pop(), "one box per tier"),
    (orgchart, lambda d: d["charts"][0]["links"][0].update(between=["top", "low"]), "neighbouring tiers"),
    (orgchart, lambda d: d["charts"][1]["links"][0].update(down="x"), "loose link stands alone"),
    (orgchart, lambda d: d["charts"][0]["links"][1].pop("down") and d["charts"][0]["links"][1].pop("up"),
     "needs down, up or loose"),
    (chronology, lambda d: d["events"].reverse(), "date order"),
    (chronology, lambda d: d["events"][0].update(year="180"), "whole number"),
    (chronology, lambda d: d["events"][0].pop("date"), "missing date"),
])
def test_orgchart_and_chronology_refuse(make, mutate, expect):
    d = make()
    mutate(d)
    errs = btl.validate(d, "<!-- ANCHOR -->")
    assert any(expect in e for e in errs), errs
# ---------------------------------------------------------------- tree type, shared visuals, team4 V3 pages

def _tree():
    return {
        "id": "family-tree", "slug": "demo", "type": "tree", "label": "Tree", "title": "Families",
        "image_title": "A family tree", "caption": "What it shows.", "span": [1500, 2000],
        "differ": ["First difference.", "Second difference.", "Third difference."],
        "families": [
            {"id": "a", "name": "Family A", "color": "green",
             "nodes": [{"year": 1517, "label": "Start A", "source": "s1"},
                       {"year": 1900, "label": "Later A", "source": "s1"}],
             "proponent": _prop("Writer A")},
            {"id": "b", "name": "Family B", "color": "blue", "parent": "a", "parent_text": "Grew out of A",
             "nodes": [{"year": 1600, "label": "Start B", "source": "s1"}],
             "proponent": _prop("Writer B")},
        ],
        "sources": _src(), "place": {"before": "<section class=\"cc-synthesis\""},
    }


def test_tree_valid_renders_wide_phone_and_table():
    d = _tree()
    assert btl.validate(d) == []
    wide, narrow = btl.render_wide(d), btl.render_narrow(d)
    assert "1517 Start A" in wide and "Later A" in wide
    assert "Grew out of A" in narrow
    block = btl.render_block(d, NoVoices())
    assert "Grew out of A" in block and "1600 Start B" in block


@pytest.mark.parametrize("mutate, expect", [
    (lambda d: d["families"][1].update(parent="zzz"), "is not another family"),
    (lambda d: d["families"][1].pop("parent_text"), "parent_text"),
    (lambda d: d["families"][0]["nodes"].reverse(), "year order"),
    (lambda d: d["families"][0]["nodes"][0].update(source="nope"), "unknown source"),
    (lambda d: d.update(span=[2000, 1500]), "span"),
])
def test_tree_refuses(mutate, expect):
    d = _tree()
    mutate(d)
    assert any(expect in e for e in btl.validate(d))


def test_also_repeats_a_visual_on_another_page():
    path = REPO / "data" / "topic_timelines" / "covenant-theology-continuity.json"
    got = [(slug, primary) for _, slug, _, primary in btl.targets([path])]
    assert got == [("covenant-theology", True), ("israel-and-prophecy", False)]


@pytest.mark.parametrize("name, slug, anchor", [
    ("church-history", "church-history", "family-tree"),
    ("covenant-theology-continuity", "covenant-theology", "continuity"),
    ("covenant-theology-continuity", "israel-and-prophecy", "continuity"),
    ("heaven-hell-eternity", "heaven-hell-eternity", "views-of-hell"),
    ("worship-and-liturgy", "worship-and-liturgy", "worship-spectrum"),
])
def test_v3_pages_current_and_in_jump_nav(name, slug, anchor):
    path = REPO / "data" / "topic_timelines" / f"{name}.json"
    d = next(d for _, s, d, _ in btl.targets([path]) if s == slug)
    html = (REPO / "docs" / "topics" / slug / "index.html").read_text(encoding="utf-8")
    assert btl.validate(d, html) == []
    assert btl.build_page(html, d) == html, f"run scripts/build_topic_timeline.py --slug {slug}"
    assert f'href="#{anchor}" data-pos="topic-jump"' in html
    assert "—" not in json.dumps(d, ensure_ascii=False) and "–" not in json.dumps(d, ensure_ascii=False)


def test_universalism_is_marked_outside_bounds():
    d = json.loads((REPO / "data" / "topic_timelines" / "heaven-hell-eternity.json").read_text(encoding="utf-8"))
    outside = [c["id"] for c in d["columns"] if c.get("outside")]
    assert outside == ["universalism"]
