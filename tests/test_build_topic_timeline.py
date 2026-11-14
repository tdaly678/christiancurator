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
