"""Publisher headlines under bylines (voices cleanup step 1, Nov 12 2026).

The RealClear rewrite stays on the front page and in the email. Voice pages,
Recent Articles blocks, archive and digest pages show the publisher's own
headline, and saved rows store it as `original_title`.

Run: python3 -m pytest tests/test_original_titles.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_recent_articles as recent  # noqa: E402
from curator import original_titles as ot  # noqa: E402
from output import history_row  # noqa: E402

TRUEMAN_URL = "https://firstthings.com/the-cult-of-pastoral-vulnerability/"
REWRITE = "Pastor's 'Vulnerable' Image Crumbles as Hidden Affair Emerges"


def test_extract_headline_prefers_json_ld_and_strips_site_tail():
    page = ('<html><head><title>The Cult of Pastoral Vulnerability | First Things</title>'
            '<meta property="og:title" content="The Cult of Pastoral Vulnerability - First Things">'
            '<script type="application/ld+json">{"@type":"Article",'
            '"headline":"The Cult of Pastoral Vulnerability"}</script></head></html>')
    assert ot.extract_headline(page, TRUEMAN_URL, "First Things") == "The Cult of Pastoral Vulnerability"


def test_extract_headline_falls_back_to_title_tag_without_tail():
    page = "<title>What Is the Gospel? - 9Marks</title>"
    assert ot.extract_headline(page, "https://www.9marks.org/article/x/") == "What Is the Gospel?"


def test_site_tail_kept_when_not_a_site_name():
    assert ot.strip_site_tail("Faith and Work: A Primer", {"9marks"}) == "Faith and Work: A Primer"


def test_publisher_title_only_cleans_never_rewords():
    assert ot.publisher_title("  Grace &amp; Truth — Again  ") == "Grace & Truth, Again"
    assert ot.publisher_title("Revival in 1970–1972") == "Revival in 1970-1972"


def test_history_and_yesterday_rows_store_publisher_headline():
    a = {"url": TRUEMAN_URL, "title": "The Cult of Pastoral Vulnerability",
         "original_title": "The Cult of Pastoral Vulnerability", "rewritten_title": REWRITE}
    row = history_row(a, "2026-11-12")
    assert row["title"] == REWRITE
    assert row["original_title"] == "The Cult of Pastoral Vulnerability"


def test_byline_title_ignores_rewrite():
    a = {"url": "https://example.com/a", "title": "Original Headline Here",
         "rewritten_title": REWRITE, "source_name": "Example"}
    assert ot.byline_title(a) == "Original Headline Here"


def test_archive_and_digest_templates_never_print_the_rewrite():
    for name in ("archive_template.html", "digest_template.html"):
        text = (ROOT / "frontend" / name).read_text(encoding="utf-8")
        assert "rewritten_title" not in text, name
        assert "|pub_title" in text, name


def _archive_day(tmp_path, meta_titles, title_text):
    day = tmp_path / "2026-11-12"
    day.mkdir(parents=True)
    day.joinpath("index.html").write_text(
        f'<article class="cc-article"><a href="{TRUEMAN_URL}" class="cc-article-title" '
        f"onclick=\"gtag('event','article_click',{{'article_source':'First Things'}});\">"
        f'{title_text}</a><a href="/voices/carl-r-trueman/">Carl R. Trueman</a></article>',
        encoding="utf-8")
    day.joinpath("meta.json").write_text(json.dumps({"articles": [
        {"url": TRUEMAN_URL, **({"original_title": meta_titles} if meta_titles else {})}]}),
        encoding="utf-8")


def test_voice_recent_uses_publisher_headline(tmp_path, monkeypatch):
    _archive_day(tmp_path, "The Cult of Pastoral Vulnerability", REWRITE)
    monkeypatch.setattr(recent, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(recent, "lookup", lambda url: None)
    items = recent.collect_by_voice()["carl-r-trueman"]
    assert [i["title"] for i in items] == ["The Cult of Pastoral Vulnerability"]


def test_voice_recent_drops_piece_with_unknown_headline(tmp_path, monkeypatch):
    _archive_day(tmp_path, None, REWRITE)
    monkeypatch.setattr(recent, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(recent, "lookup", lambda url: None)
    dropped = []
    assert "carl-r-trueman" not in recent.collect_by_voice(dropped=dropped)
    assert dropped and dropped[0]["slugs"] == ["carl-r-trueman"]


def test_topic_recent_uses_publisher_headline(monkeypatch):
    monkeypatch.setattr(recent, "lookup", lambda url: None)
    history = [
        {"url": "https://example.com/a", "title": "Prayer Rewrite", "original_title": "On Prayer",
         "source_name": "Example", "date_shown": "2026-11-12", "tags": []},
        {"url": "https://example.com/b", "title": "Prayer Rewrite Two", "source_name": "Example",
         "date_shown": "2026-11-11", "tags": []},
    ]
    items = recent.match_articles_to_topic({"keywords": ["prayer"]}, history)
    assert [i["title"] for i in items] == ["On Prayer"]


def test_fetcher_sets_original_title_at_ingest():
    text = (ROOT / "fetcher" / "rss_fetcher.py").read_text(encoding="utf-8")
    assert '"original_title": title' in text


def test_remove_block_drops_stale_recent_articles():
    page = f"<main>\n<p>Bio</p>\n{recent.V_START}\n<section>old</section>\n{recent.V_END}\n</main>"
    out = recent.remove_block(page)
    assert recent.V_START not in out and "old" not in out and "<p>Bio</p>" in out


def test_homepage_title_is_not_a_headline():
    page = "<title>Pew Research Center | Nonpartisan, nonadvocacy, public opinion polling</title>"
    assert ot.extract_headline(page, "https://www.pewresearch.org/?prc_newsletter=x") == ""
