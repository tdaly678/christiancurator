"""sitemap-voices.xml never lists a voice page whose HTML carries robots noindex.

Nov 15 2026: the Nov 14 run wrote 10 new voice pages noindex and recorded them in
frontend/voices_noindex.json on the runner, but the commit step did not add that
file. The next run's sitemap read the stale list, listed the pages, and the
check_voices gate failed. The page's own robots tag now decides.
"""
import json
from pathlib import Path

import pytest

import frontend
from frontend.robots import html_has_noindex

REPO_ROOT = Path(__file__).resolve().parent.parent

NOINDEX_PAGE = ('<html><head><title>X</title>\n'
                '  <meta name="robots" content="noindex, follow" />\n</head><body></body></html>')
INDEX_PAGE = '<html><head><title>Y</title></head><body></body></html>'


def test_html_has_noindex_both_attribute_orders():
    assert html_has_noindex(NOINDEX_PAGE)
    assert html_has_noindex('<meta content="noindex,follow" name="robots">')
    assert not html_has_noindex(INDEX_PAGE)
    assert not html_has_noindex('<meta name="robots" content="index, follow" />')


@pytest.fixture
def site(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    voices = docs / "voices"
    for slug, page in {"listed-writer": INDEX_PAGE,
                       "noindex-not-in-list": NOINDEX_PAGE,
                       "noindex-in-list": NOINDEX_PAGE}.items():
        (voices / slug).mkdir(parents=True)
        (voices / slug / "index.html").write_text(page, encoding="utf-8")
    noindex_list = tmp_path / "voices_noindex.json"
    noindex_list.write_text(json.dumps(["noindex-in-list"]), encoding="utf-8")
    monkeypatch.setattr(frontend, "VOICES_DIR", voices)
    monkeypatch.setattr(frontend, "VOICES_NOINDEX_PATH", noindex_list)
    for name in ("TOPICS_DIR", "DAILY_DIR", "ARCHIVE_DIR"):
        monkeypatch.setattr(frontend, name, docs / name.lower())
    monkeypatch.setattr(frontend, "SITEMAP_DIR", docs)
    monkeypatch.setattr(frontend, "SITEMAP_PATH", docs / "sitemap.xml")
    monkeypatch.setattr(frontend, "SITEMAP_LASTMOD_PATH", tmp_path / "sitemap_lastmod.json")
    return docs


def test_sitemap_skips_page_with_noindex_even_when_list_is_stale(site):
    frontend.regenerate_sitemap()
    xml = (site / "sitemap-voices.xml").read_text(encoding="utf-8")
    assert "/voices/listed-writer/" in xml
    assert "/voices/noindex-not-in-list/" not in xml
    assert "/voices/noindex-in-list/" not in xml


def test_daily_workflow_commits_the_noindex_list():
    workflow = (REPO_ROOT / ".github" / "workflows" / "daily_run.yml").read_text(encoding="utf-8")
    commit_step = workflow.split("bash scripts/commit_daily_run.sh", 1)[1].split("\n\n", 1)[0]
    assert "frontend/voices_noindex.json" in commit_step


def test_committed_sitemap_has_no_noindexed_voice_page():
    xml = (REPO_ROOT / "docs" / "sitemap-voices.xml").read_text(encoding="utf-8")
    voices = REPO_ROOT / "docs" / "voices"
    bad = [d.name for d in voices.iterdir()
           if f"/voices/{d.name}/" in xml and (d / "index.html").exists()
           and html_has_noindex((d / "index.html").read_text(encoding="utf-8", errors="replace"))]
    assert bad == []
