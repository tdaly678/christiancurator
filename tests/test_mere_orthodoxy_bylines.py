"""Mere Orthodoxy bylines come from the visible byline, not the page metadata.

Mere Orthodoxy runs on Ghost. Its feed creator is "Mere Orthodoxy" and the
page's JSON-LD author and data-post-author name a posting account ("Mere
Orthodoxy", or Jake Meador, the editor, on essays by other writers). The
visible byline is the post's author-* tags in the data-byline block.

Fixtures in tests/fixtures/mere_orthodoxy/ are trimmed copies of live pages
(Nov 13 2026): the head metadata and the article header.

Run: python3 -m pytest tests/test_mere_orthodoxy_bylines.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fetcher import rss_fetcher  # noqa: E402
from fetcher.sources import SOURCES  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "mere_orthodoxy"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_visible_byline_beats_editor_in_metadata():
    # that-hideous-narcissism: data-post-author and JSON-LD say Jake Meador.
    p = page("meta-jake-meador.html")
    assert 'data-post-author="Jake Meador"' in p
    assert rss_fetcher.page_byline(p) == "Eddie LaRow"


def test_visible_byline_beats_outlet_in_metadata():
    p = page("jody-benson.html")
    assert '"name": "Mere Orthodoxy"' in p or '"name":"Mere Orthodoxy"' in p
    assert rss_fetcher.page_byline(p) == "Jody Benson"


def test_two_authors_in_byline_order():
    assert rss_fetcher.page_byline(page("two-authors.html")) == "Edward Song and Don Patterson"


def test_suffix_comma_does_not_split_a_writer():
    assert rss_fetcher.page_byline(page("suffix-comma.html")) == "E. Wesley Reynolds III"


def test_editor_credited_on_his_own_piece():
    assert rss_fetcher.page_byline(page("jake-meador-own.html")) == "Jake Meador"


def test_topic_tags_in_byline_block_are_not_writers():
    # The block lists Books, Culture and Fusionism Forum as candidates too.
    p = page("jake-meador-own.html")
    assert 'data-tag-slug="book-reviews"' in p
    assert "Books" not in rss_fetcher.page_byline(p)


def test_byline_block_without_author_tag_names_nobody():
    block = ('<span class="meta-authors" data-byline>\n'
             '<a href="/tag/culture/" class="meta-author meta-author--candidate" data-tag-slug="culture">'
             '<div class="meta-author-name"><em>Culture</em></div></a>\n</span>\n'
             '<span class="meta-authors-fallback"><a href="/author/jake-meador/" class="meta-author">'
             '<div class="meta-author-name"><em>Jake Meador</em></div></a></span>'
             '<script type="application/ld+json">{"author": {"@type": "Person", "name": "Jake Meador"}}</script>')
    assert rss_fetcher.page_byline(block) == ""


def test_other_pages_unchanged():
    assert rss_fetcher.page_byline('<meta name="author" content="Jane Writer">') == "Jane Writer"
    ct = ('<script>var ga4ArticleContext = {"point_editor":"Ed Itor","byline":"Andrew Wilson"};</script>'
          '<script type="application/ld+json">{"author":{"@type":"Person","name":"Ed Itor"}}</script>')
    assert rss_fetcher.page_byline(ct) == "Andrew Wilson"


def test_mere_orthodoxy_reads_bylines_from_page():
    src = next(s for s in SOURCES if s["name"] == "Mere Orthodoxy")
    assert src.get("byline_from_page") is True


def test_essay_credited_to_editor_goes_to_its_writer():
    # The one wrong credit the Nov 13 sweep found: Jake Meador in our archive.
    assert rss_fetcher.page_byline(page("miscredited-to-editor.html")) == "Sarah Ashbach"


def test_couple_tag_is_two_writers():
    assert rss_fetcher.page_byline(page("couple-tag.html")) == "John Starke and Jena Starke"
