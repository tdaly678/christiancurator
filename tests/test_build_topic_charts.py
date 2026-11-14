"""Tests for scripts/build_topic_charts.py (the topic chart convention).

The figures below are made-up fixtures for the renderer ("Example Research");
they never reach a page. Real chart data lives in data/topic_charts/<slug>/.
"""

import copy
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_topic_charts as btc  # noqa: E402

SRC = [{"id": "ex", "publisher": "Example Research", "study": "Example Study", "year": 2025,
        "url": "https://example.org/study", "fetched": "2026-11-14", "license": "reuse",
        "field_dates": "May 1 to 9, 2025", "sample": "1,000 adults"}]
PAGE = ("<html><head></head><body><main class=\"cc-prose\"><p>intro</p>"
        "<!-- AEO-RELATED-TOPICS:START --><nav></nav><!-- AEO-RELATED-TOPICS:END --></main></body></html>")


def hbar():
    return {
        "id": "why-left", "type": "hbar", "kicker": "Example", "title": "Why people say they left",
        "subtitle": "Example adults", "caption": "An example caption.", "unit": "%",
        "categories": [{"id": "a", "label": "Belief", "color": "green"},
                       {"id": "b", "label": "Conduct", "color": "brown"}],
        "rows": [{"label": "Reason one", "value": 42, "as_published": "42%", "source": "ex", "category": "a"},
                 {"label": "Reason two", "value": 17.5, "as_published": "17.5%", "source": "ex", "category": "b"}],
        "sources": copy.deepcopy(SRC), "place": {"before": "<!-- AEO-RELATED-TOPICS:START -->"},
    }


def column():
    return {
        "id": "vote-tracker", "type": "column", "title": "Example vote", "subtitle": "Example delegates",
        "caption": "Votes against the line.", "unit": "%",
        "series": [{"id": "yes", "label": "Yes", "color": "green"}],
        "reference": {"value": 66.67, "label": "Two-thirds"},
        "rows": [{"label": "2024", "values": {"yes": 60.74}, "as_published": {"yes": "60.74%"}, "source": "ex"},
                 {"label": "2025", "values": {"yes": 61.08}, "as_published": {"yes": "61.08 percent"}, "source": "ex"}],
        "sources": copy.deepcopy(SRC), "place": {"after": "<p>intro</p>"},
    }


def line():
    return {
        "id": "doubt-trend", "type": "line", "title": "Example trend", "subtitle": "Example churchgoers",
        "caption": "A trend.", "unit": "%",
        "series": [{"id": "s1", "label": "Series one", "color": "blue"},
                   {"id": "s2", "label": "Series two", "color": "red"}],
        "rows": [{"label": "2012", "values": {"s1": 10, "s2": 20}, "as_published": {"s1": "10%", "s2": "20%"}, "source": "ex"},
                 {"label": "2019", "values": {"s1": 15, "s2": 25}, "as_published": {"s1": "15%", "s2": "25%"}, "source": "ex"},
                 {"label": "2025", "values": {"s1": 30}, "as_published": {"s1": "30%"}, "source": "ex"}],
        "sources": copy.deepcopy(SRC), "place": {"before": "<!-- AEO-RELATED-TOPICS:START -->"},
    }


def table():
    return {
        "id": "where-churches-stand", "type": "table", "title": "Where churches stand",
        "subtitle": "Example bodies", "caption": "A table.", "columns": ["Body", "Position"],
        "rows": [{"cells": ["Example Church", "Example position"], "source": "ex"}],
        "sources": copy.deepcopy(SRC), "place": {"before": "<!-- AEO-RELATED-TOPICS:START -->"},
    }


ALL = [hbar, column, line, table]


@pytest.mark.parametrize("make", ALL)
def test_fixture_charts_validate(make):
    assert btc.validate_chart(make()) == []


@pytest.mark.parametrize("make", [hbar, column, line])
def test_svg_is_wellformed_and_self_explaining(make):
    c = make()
    html = btc.render_chart(c)
    svg = re.search(r"<svg.*?</svg>", html, re.DOTALL).group(0)
    root = ET.fromstring(svg)
    assert root.get("role") == "img"
    assert root.get("aria-labelledby") == f"{c['id']}-t {c['id']}-d"
    text = " ".join(t.text or "" for t in root.iter("{http://www.w3.org/2000/svg}text")) or \
        " ".join(t.text or "" for t in root.iter("text"))
    assert c["title"].split()[0] in text
    assert "Example Research, 2025" in text  # source drawn on the image
    assert btc.BRAND in text                 # brand mark on the image
    desc = root.find("desc").text
    assert desc and any(ch.isdigit() for ch in desc)


def test_chart_block_has_markers_caption_table_and_source():
    html = btc.render_chart(hbar())
    s, e = btc.chart_marker("why-left")
    assert html.startswith(s) and html.endswith(e)
    assert '<figure class="cc-chart cc-chart-hbar" id="why-left">' in html
    assert "<figcaption>An example caption.</figcaption>" in html
    assert 'class="cc-chart-data"' in html
    assert "Example Research, <a href=\"https://example.org/study\"" in html
    assert "May 1 to 9, 2025; 1,000 adults" in html
    assert "Chart by Christian Curator." in html


def test_reference_line_drawn_for_column():
    html = btc.render_chart(column())
    assert "stroke-dasharray" in html and "Two-thirds (66.67%)" in html


@pytest.mark.parametrize("make", [hbar, column, line])
def test_wide_and_narrow_images_with_unique_ids(make):
    c = make()
    svgs = [ET.fromstring(s) for s in re.findall(r"<svg.*?</svg>", btc.render_chart(c), re.DOTALL)]
    assert [s.get("class") for s in svgs] == ["cc-chart-svg cc-chart-wide", "cc-chart-svg cc-chart-narrow"]
    assert svgs[1].get("viewBox").split()[2] == str(btc.W_NARROW)
    assert svgs[1].get("aria-labelledby") == f"{c['id']}-n-t {c['id']}-n-d"
    # Phone image: no text below 12px (drawn at 360 units, about 0.9x on a 390px screen).
    sizes = [float(t.get("font-size")) for t in svgs[1].iter("text")]
    assert min(sizes) >= 12


def test_narrow_column_is_horizontal_bars_and_text_fits():
    svg = re.findall(r"<svg.*?</svg>", btc.render_chart(column()), re.DOTALL)[1]
    root = ET.fromstring(svg)
    bars = [r for r in root.iter("rect") if r.get("height") == "15"]
    assert bars and all(float(r.get("x")) == btc.PAD for r in bars)
    for t in root.iter("text"):
        if t.get("text-anchor") != "end":
            assert float(t.get("x")) + 7.4 * len(t.text) <= btc.W_NARROW


def test_reference_label_sits_in_legend_above_the_bars():
    svg = re.search(r"<svg.*?</svg>", btc.render_chart(column()), re.DOTALL).group(0)
    root = ET.fromstring(svg)
    label = [t for t in root.iter("text") if t.text == "Two-thirds (66.67%)"]
    assert len(label) == 1
    bar_tops = [float(r.get("y")) for r in root.iter("rect") if r.get("width") != str(btc.W) and r.get("rx") is None]
    assert float(label[0].get("y")) < min(bar_tops)


def test_table_type_renders_html_table_with_sources():
    html = btc.render_chart(table())
    assert "<svg" not in html and "<table class=\"cc-chart-table cc-chart-stack\">" in html
    assert "Example Research, 2025</a>" in html


def test_table_cells_carry_column_labels_and_a_visible_title():
    html = btc.render_chart(table())
    assert '<td data-label="Body">Example Church</td>' in html
    assert '<td data-label="Position">Example position</td>' in html
    assert '<td data-label="Source"><a href="https://example.org/study"' in html
    assert '<span class="cc-chart-table-title">Where churches stand</span>' in html
    assert '<span class="cc-chart-table-sub">Example bodies</span>' in html
    css = (REPO_ROOT / "docs" / "assets" / "topic.css").read_text()
    assert "content: attr(data-label)" in css and ".cc-chart-table-title" in css


def test_build_page_places_and_is_idempotent():
    charts = [f() for f in ALL]
    for c in charts:
        c["_file"] = c["id"]
    assert btc.validate_slug("x", charts, None, PAGE) == []
    once = btc.build_page(PAGE, charts, None)
    assert btc.build_page(once, charts, None) == once
    assert once.index('id="vote-tracker"') < once.index('id="why-left"')  # "after intro" comes first
    assert once.index('id="why-left"') < once.index("<!-- AEO-RELATED-TOPICS:START -->")
    assert "/assets/topic.css" in once


def test_section_groups_charts_and_absorbs_standalone_blocks():
    charts = [hbar(), column()]
    once = btc.build_page(PAGE, charts, None)
    section = {"id": "by-the-numbers", "label": "By the Numbers", "title": "What the surveys show",
               "intro": "Two example charts.", "charts": ["why-left", "vote-tracker"],
               "place": {"before": "<!-- AEO-RELATED-TOPICS:START -->"}}
    assert btc.validate_slug("x", charts, section, once) == []
    out = btc.build_page(once, charts, section)
    assert out.count(btc.chart_marker("why-left")[0]) == 1
    assert out.count(btc.chart_marker("vote-tracker")[0]) == 1
    s, e = btc.section_marker("by-the-numbers")
    inner = out[out.index(s):out.index(e)]
    assert 'id="why-left"' in inner and 'id="vote-tracker"' in inner
    assert inner.index("why-left") < inner.index("vote-tracker")
    assert btc.build_page(out, charts, section) == out


@pytest.mark.parametrize("mutate, needle", [
    (lambda c: c["sources"][0].update(license="ask-first"), "may not be charted"),
    (lambda c: c["sources"][0].update(license="cite-only"), "may not be charted"),
    (lambda c: c["sources"][0].pop("fetched"), "fetched is required"),
    (lambda c: c["sources"][0].update(fetched="Nov 14"), "YYYY-MM-DD"),
    (lambda c: c["sources"][0].update(url="example.org"), "full URL"),
    (lambda c: c["rows"][0].update(as_published="43%"), "does not match"),
    (lambda c: c["rows"][0].update(source="nope"), "not in sources"),
    (lambda c: c["rows"][0].update(category="zzz"), "not in categories"),
    (lambda c: c.update(caption="A caption – dashed."), "dash"),
    (lambda c: c.update(note="From the Quiet Revival report."), "Quiet Revival"),
    (lambda c: c["sources"][0].update(url="https://example.org/?utm_source=cc"), "tracking"),
    (lambda c: c.update(type="pie"), "type must be"),
    (lambda c: c.pop("subtitle"), "subtitle is required"),
    (lambda c: c.update(id="Bad Id"), "kebab"),
])
def test_validation_catches(mutate, needle):
    c = hbar()
    mutate(c)
    assert any(needle in e for e in btc.validate_chart(c)), btc.validate_chart(c)


def test_column_value_mismatch_caught():
    c = column()
    c["rows"][0]["as_published"]["yes"] = "70%"
    assert any("does not match" in e for e in btc.validate_chart(c))


def test_missing_place_anchor_caught():
    c = hbar()
    c["place"] = {"before": "<!-- NOT-THERE -->"}
    assert any("not on the page" in e for e in btc.validate_slug("x", [c], None, PAGE))


def test_real_chart_data_validates():
    for slug in btc.chart_slugs():
        page = btc.TOPICS_DIR / slug / "index.html"
        assert page.exists(), slug
        charts, section = btc.load_slug(slug)
        html = page.read_text(encoding="utf-8")
        assert btc.validate_slug(slug, charts, section, html) == [], slug
        # Built pages are current.
        assert btc.build_page(html, charts, section) == html, slug


def test_wrap_and_fmt():
    assert btc.wrap("one two three four", 9) == ["one two", "three", "four"]
    assert btc.fmt(66.670, "%") == "66.67%" and btc.fmt(42.0, "%") == "42%"
