"""Tests for scripts/build_biblical_literacy_viz.py and data/biblical-literacy/surveys.json."""

import copy
import json
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_biblical_literacy_viz as viz  # noqa: E402

DATA = viz.load_data()
PAGE = viz.PAGE_PATH.read_text(encoding="utf-8")
EM_DASH = "\u2014"


def blank_page() -> str:
    """The real page with all three marker blocks emptied."""
    page = PAGE
    for name in viz.BLOCKS:
        page = viz.marker_re(name).sub(lambda m: m.group(1) + m.group(3), page)
    return page


def block(page: str, name: str) -> str:
    return viz.marker_re(name).search(page).group(2)


# ------------------------------------------------------------------ data file


def test_real_data_file_is_valid():
    assert viz.validate(DATA) == []


def test_every_row_has_url_and_license_status():
    for row in viz.merged_rows(DATA):
        assert row["url"].startswith("https://"), row["id"]
        assert row["license_status"] in viz.LICENSE_STATUSES, row["id"]


def test_validate_flags_missing_url():
    data = copy.deepcopy(DATA)
    data["studies"]["pew-rls-practices"]["url"] = ""
    errors = viz.validate(data)
    assert any("missing url" in e for e in errors)


def test_validate_flags_missing_license_status():
    data = copy.deepcopy(DATA)
    del data["studies"]["gallup-bible-views-2022"]["license_status"]
    errors = viz.validate(data)
    assert any("missing license_status" in e for e in errors)


def test_validate_flags_unknown_license_status():
    data = copy.deepcopy(DATA)
    data["rows"][0]["license_status"] = "probably-fine"
    assert any("license_status" in e for e in viz.validate(data))


def test_validate_flags_out_of_range_value_and_duplicate_id():
    data = copy.deepcopy(DATA)
    data["rows"][0]["value"] = 140
    data["rows"][1]["id"] = data["rows"][2]["id"]
    errors = viz.validate(data)
    assert any("value must be" in e for e in errors)
    assert any("duplicate id" in e for e in errors)


def test_build_fails_on_invalid_data():
    data = copy.deepcopy(DATA)
    data["studies"]["lifeway-quiz-2026"]["url"] = ""
    with pytest.raises(viz.BuildError, match="missing url"):
        viz.build_page(blank_page(), data, date(2026, 11, 9))


def test_main_exits_nonzero_on_invalid_data(tmp_path):
    data = copy.deepcopy(DATA)
    del data["studies"]["abs-sotb-2026"]["license_status"]
    data_path = tmp_path / "surveys.json"
    data_path.write_text(json.dumps(data), encoding="utf-8")
    page_path = tmp_path / "index.html"
    page_path.write_text(PAGE, encoding="utf-8")
    assert viz.main(["--data", str(data_path), "--page", str(page_path)]) == 2
    assert page_path.read_text(encoding="utf-8") == PAGE


def test_ask_first_rows_are_never_charted():
    data = copy.deepcopy(DATA)
    data["studies"]["pew-rls-practices"]["license_status"] = "ask-first"
    with pytest.raises(viz.BuildError, match="not cleared for charting"):
        viz.render_gap(data)


def test_barna_and_abs_are_cited_only():
    rows = [r for r in viz.merged_rows(DATA) if r["source"] in ("Barna Group", "American Bible Society")]
    assert rows
    assert {r["license_status"] for r in rows} == {"ask-first"}
    assert {r["figure"] for r in rows} == {"table-cited"}


def test_quiz_has_five_tap_questions_with_valid_answers():
    taps = [r for r in DATA["rows"] if r.get("tap")]
    assert len(taps) == 5
    for r in taps:
        assert r["tap"]["answer"] in r["tap"]["options"]


def test_grades_sum_to_100():
    grades = [r for r in DATA["rows"] if r["id"].startswith("lifeway-quiz-grade-")]
    assert sum(r["value"] for r in grades) == 100


# ------------------------------------------------------------------ rendering


def test_build_rewrites_only_marker_blocks():
    before = blank_page()
    after = viz.build_page(before, DATA, date(2026, 11, 9))
    assert after != before

    def outside(page: str) -> str:
        for name in viz.BLOCKS:
            page = viz.marker_re(name).sub(lambda m: m.group(1) + m.group(3), page)
        return viz.set_dates(page, date(2000, 1, 1))

    assert outside(after) == outside(before)


def test_build_is_idempotent_and_committed_page_is_current():
    once = viz.build_page(PAGE, DATA, date(2030, 1, 1))
    assert once == PAGE, "page is stale: run scripts/build_biblical_literacy_viz.py"
    assert viz.build_page(once, DATA, date(2030, 1, 1)) == once


def test_dates_bump_only_when_data_changes():
    # The data watch moves "Last updated" on real data changes, so compare with
    # whatever date the committed page carries rather than a fixed one.
    current = re.search(r"Last updated: ([A-Z][a-z]+ \d{1,2}, \d{4})", PAGE).group(1)
    unchanged = viz.build_page(PAGE, DATA, date(2030, 1, 1))
    assert f"Last updated: {current}" in unchanged
    assert "Last updated: January 1, 2030" not in unchanged

    data = copy.deepcopy(DATA)
    data["changelog"].append({"date": "2030-01-01", "note": "Test change."})
    changed = viz.build_page(PAGE, data, date(2030, 1, 1))
    assert "Last updated: January 1, 2030" in changed
    assert '"dateModified": "2030-01-01"' in changed
    assert "last updated January 1, 2030" in block(changed, "TRACKER")


def test_missing_marker_fails():
    page = PAGE.replace("<!-- CC-BL-VIZ-QUIZ:START -->", "")
    with pytest.raises(viz.BuildError, match="CC-BL-VIZ-QUIZ"):
        viz.build_page(page, DATA, date(2026, 11, 9))


def test_each_figure_has_svg_caption_table_and_source():
    for name in viz.BLOCKS:
        html = block(PAGE, name)
        for fig in re.findall(r"<figure.*?</figure>", html, re.S):
            assert "<svg" in fig and "</svg>" in fig
            assert "<figcaption>" in fig
            assert "<details" in fig and "<table>" in fig
            assert 'class="cc-viz-source"' in fig and "https://" in fig


def test_charts_need_no_javascript_and_quiz_js_is_small():
    gap, quiz, tracker = (block(PAGE, n) for n in viz.BLOCKS)
    assert "<script" not in gap
    assert "<script" not in tracker.replace('<script type="application/ld+json">', "")
    assert len(viz.QUIZ_JS.encode("utf-8")) < 5000
    # Without JS the answers are in the markup.
    for r in (r for r in DATA["rows"] if r.get("tap")):
        assert f"Answer: <strong>{r['tap']['answer']}</strong>" in quiz


def test_pew_charts_carry_disclaimer():
    assert viz.PEW_DISCLAIMER in block(PAGE, "GAP")
    assert viz.PEW_DISCLAIMER in block(PAGE, "TRACKER")


def test_no_em_dashes_in_generated_blocks_or_data():
    for name in viz.BLOCKS:
        assert EM_DASH not in block(PAGE, name)
    assert EM_DASH not in viz.DATA_PATH.read_text(encoding="utf-8")


def test_svgs_use_horizontal_bars_and_design_tokens():
    for name in viz.BLOCKS:
        for svg in re.findall(r"<svg.*?</svg>", block(PAGE, name), re.S):
            assert "viewBox" in svg and "<title" in svg
    assert viz.GREEN == "#2C4A2E" and viz.GAP_RED == "#8B1A1A"


def test_dataset_jsonld_is_based_on_every_source():
    m = re.search(r'<script type="application/ld\+json">\s*(\{.*?"@type": "Dataset".*?\})\s*</script>',
                  block(PAGE, "TRACKER"), re.S)
    doc = json.loads(m.group(1))
    assert doc["@type"] == "Dataset"
    urls = {w["url"] for w in doc["isBasedOn"]}
    assert urls == {s["url"] for s in DATA["studies"].values()}


# ------------------------------------------------------------------ page integrity


class _FAQ(HTMLParser):
    def __init__(self):
        super().__init__()
        self.qa, self._in, self._buf = [], None, []

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "")
        if cls in ("cc-faq-q", "cc-faq-a"):
            self._in, self._buf = cls, []

    def handle_endtag(self, tag):
        if self._in and tag in ("h3", "p"):
            self.qa.append((self._in, "".join(self._buf).strip()))
            self._in = None

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)


def test_faq_jsonld_matches_visible_text():
    m = re.search(r'<script type="application/ld\+json" data-cc-marker="AEO-FAQPAGE-SCHEMA">\s*(.*?)</script>', PAGE, re.S)
    schema = json.loads(m.group(1))
    p = _FAQ()
    p.feed(PAGE)
    qs = [t for k, t in p.qa if k == "cc-faq-q"]
    ans = [t for k, t in p.qa if k == "cc-faq-a"]
    assert [q["name"] for q in schema["mainEntity"]] == qs
    assert [q["acceptedAnswer"]["text"] for q in schema["mainEntity"]] == ans


def test_declining_faq_links_tracker():
    i = PAGE.index("Is biblical literacy declining?</h3>")
    answer = PAGE[i:PAGE.index("</p>", i)]
    assert 'href="#survey-tracker"' in answer
    assert "It depends on the survey and the measure." in answer


def test_blocks_in_reading_order_and_curated_list_untouched():
    order = [
        PAGE.index("has made it more acute.</p>"),
        PAGE.index("<!-- CC-BL-VIZ-GAP:START -->"),
        PAGE.index('<section class="cc-key-questions"'),
        PAGE.index("<!-- CC-BL-VIZ-QUIZ:START -->"),
        PAGE.index('<div class="cc-debate"'),
        PAGE.index("<!-- CC-FAQ:END -->"),
        PAGE.index("<!-- CC-BL-VIZ-TRACKER:START -->"),
        PAGE.index("<!-- CC-COMPANION-GUIDES:START -->"),
        PAGE.index("The Evangelical Conversation, Curated"),
    ]
    assert order == sorted(order)
    curated = PAGE[PAGE.index("The Evangelical Conversation, Curated"):PAGE.index("<!-- AEO-TOPIC-INDEX:START -->")]
    assert curated.count('<article class="cc-article-entry">') == 11
    assert "CC-BL-VIZ" not in curated and "cc-viz" not in curated
