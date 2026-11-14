"""The faith-deconstruction page's real chart and top-block data stay valid and in sync.

Data: data/topic_charts/faith-deconstruction/ and data/topic_top/faith-deconstruction.json
(figures opened on their source pages 2026-11-14; see
.christian-orchestrator/team/B-deconstruction-report.md).
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_topic_charts as btc  # noqa: E402
import build_topic_top as btt  # noqa: E402

SLUG = "faith-deconstruction"
PAGE = REPO_ROOT / "docs" / "topics" / SLUG / "index.html"


def page_html() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_charts_validate():
    charts, section = btc.load_slug(SLUG)
    assert section and section["id"] == "by-the-numbers"
    assert len(charts) == len(section["charts"])
    assert btc.validate_slug(SLUG, charts, section, page_html()) == []


def test_committed_page_matches_chart_data():
    charts, section = btc.load_slug(SLUG)
    html = page_html()
    assert btc.build_page(html, charts, section) == html


def test_by_the_numbers_sits_before_the_debate():
    html = page_html()
    start, _ = btc.section_marker("by-the-numbers")
    assert html.index(start) < html.index('<div class="cc-debate" id="debate">')


def test_top_block_validates_and_keeps_flagged_names_out():
    data = json.loads((REPO_ROOT / "data" / "topic_top" / f"{SLUG}.json").read_text(encoding="utf-8"))
    assert btt.validate(data, SLUG, page_html()) == []
    flagged = json.loads(btt.FLAGGED.read_text(encoding="utf-8"))[SLUG]
    html = page_html()
    top = html[html.index(btt.TOP_START):html.index(btt.TOP_END)]
    for name in flagged:
        assert name not in top


def test_every_chart_source_was_opened_and_licensed():
    charts, _ = btc.load_slug(SLUG)
    for c in charts:
        for s in c["sources"]:
            assert s["fetched"] == "2026-11-14"
            assert s["license"] in {"reuse", "credit"}
            assert s["url"].startswith("https://")
