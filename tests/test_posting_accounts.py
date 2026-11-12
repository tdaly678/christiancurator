"""Posting accounts and editors are never credited (voices cleanup step 2).

Christianity Today bylines come from the visible byline, not Yoast's JSON-LD
author (the editing account). 9Marks, WORLD and Pew read bylines from the
page; WORLD podcast episodes are media; Pew newsletters are dropped at ingest.

Run: python3 -m pytest tests/test_posting_accounts.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fetcher import rss_fetcher  # noqa: E402
from fetcher.sources import SOURCES  # noqa: E402
import reattribute_bylines as ra  # noqa: E402
import retire_posting_accounts as rpa  # noqa: E402

BY_NAME = {s["name"]: s for s in SOURCES}

CT_PAGE = (
    '<script>var ga4ArticleContext = {"event":"ct_article_view","point_editor":"Kara Bettis Carvalho",'
    '"byline":"Andrew Wilson","post_id":397096};</script>'
    '<script type="application/ld+json">{"@type":"Article","author":{"@type":"Person",'
    '"name":"Kara Bettis Carvalho"}}</script>'
)


def test_ct_byline_is_visible_byline_not_editor():
    assert rss_fetcher.page_byline(CT_PAGE) == "Andrew Wilson"


def test_sources_read_bylines_from_page():
    for name in ("Christianity Today", "9Marks", "World Magazine", "Pew Research", "First Things"):
        assert BY_NAME[name].get("byline_from_page") is True, name


def _feed(entries):
    return SimpleNamespace(entries=entries, bozo=False, feed={}, get=lambda k, d=None: d)


def _entry(link, title="A Title", author="Posting Account"):
    return {"link": link, "title": title, "author": author, "summary": "", "content": []}


def _fetch(monkeypatch, source, entries, bylines=None):
    resp = SimpleNamespace(status_code=200, content=b"", headers={})
    monkeypatch.setattr(rss_fetcher, "_get_feed", lambda *a, **k: resp)
    monkeypatch.setattr(rss_fetcher.feedparser, "parse", lambda _c: _feed(entries))
    monkeypatch.setattr(rss_fetcher, "fetch_page_byline", lambda url: (bylines or {}).get(url, ""))
    monkeypatch.setattr(rss_fetcher, "apply_page_bylines",
                        lambda arts, health, fetch=None: [a.update(author=(bylines or {}).get(a["url"], ""))
                                                          for a in arts])
    items, health = rss_fetcher.fetch_feed(source)
    return items, health


def test_world_podcast_is_media_without_byline(monkeypatch):
    items, _ = _fetch(monkeypatch, BY_NAME["World Magazine"], [
        _entry("https://wng.org/podcasts/the-world-and-everything-in-it-november-12-2026-1"),
        _entry("https://wng.org/sift/some-news-story-1", title="Some News"),
    ], bylines={"https://wng.org/sift/some-news-story-1": "Lauren Canterberry"})
    pod, sift = items
    assert pod["role"] == "media" and pod["author"] == "" and pod["media_format"] == "podcast"
    assert sift["role"] == "primary" and sift["author"] == "Lauren Canterberry"


def test_pew_newsletters_dropped_at_ingest(monkeypatch):
    items, health = _fetch(monkeypatch, BY_NAME["Pew Research"], [
        _entry("https://www.pewresearch.org/newsletter/weekly-roundup/weekly-10-31-26/"),
        _entry("https://www.pewresearch.org/?prc_newsletter=update-x"),
        _entry("https://www.pewresearch.org/religion/2026/11/01/a-report/", title="A Report"),
    ])
    assert [a["url"] for a in items] == ["https://www.pewresearch.org/religion/2026/11/01/a-report/"]
    assert len(health["url_dropped"]) == 2


def test_accounts_queued_for_retirement():
    for slug in ("jeri-choi", "keegan-martin", "arla-eicher", "anna-jackson",
                 "beshay-sakla", "reem-nadeem", "sara-atske"):
        assert slug in rpa.ACCOUNTS


def test_reattribution_rebuilds_byline_and_keeps_source():
    inner = ('\n            <a href="/voices/kate-lucky/" class="cc-author-link cc-article-author">'
             '<strong>Kate Lucky</strong></a>\n            <span class="cc-meta-dot">·</span>\n'
             '            <span>Christianity Today</span>\n          ')
    out = ra.rewrite_meta_div(inner, "Andrew Wilson", "Christianity Today",
                              {"andrew wilson": "andrew-wilson"}, "article")
    assert "kate-lucky" not in out and "/voices/andrew-wilson/" in out
    assert out.count("<span>Christianity Today</span>") == 1
    gone = ra.rewrite_meta_div(inner, "", "Christianity Today", {}, "article")
    assert "Kate Lucky" not in gone and "cc-meta-dot" not in gone and "Christianity Today" in gone


def test_unreadable_page_never_keeps_posting_account(tmp_path):
    url = "https://www.9marks.org/article/x/"
    assert ra.real_byline(url, "Jeri Choi", tmp_path, fetch=False)[0] == ""
    assert ra.real_byline(url, "Real Writer", tmp_path, fetch=False)[0] is None
    assert ra.real_byline("https://wng.org/podcasts/x", "Keegan Martin", tmp_path, False)[0] == ""


def test_visible_byline_decorations_are_stripped():
    clean = rss_fetcher.clean_visible_byline
    assert clean("Interview by Cody Benjamin") == "Cody Benjamin"
    assert clean("Cody Benjamin in Falcon Heights, Minnesota") == "Cody Benjamin"
    assert clean("Compiled By Haleluya Hadero") == "Haleluya Hadero"
    assert clean("Kathryn Post - Religion News Service") == "Kathryn Post"
    assert clean("Kathryn Post—Religion New Service") == "Kathryn Post"
    assert clean("Jean-Luc Marion") == "Jean-Luc Marion"
