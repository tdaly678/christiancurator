from datetime import date

from fetcher import discovery as d

ROUNDUP = (
    '<p><a href="https://www.challies.com/kindle-deals-for-christians/">Kindle deals</a> '
    '<a href="https://churchsource.com/products/visual-theology">Visual Theology</a></p>'
    '<p><a href="https://www.desiringgod.org/interviews/was-piper-unprepared">Was Piper Unprepared?</a>. '
    '<a href="https://grow.ligonier.org/?utm_source=challies&amp;utm_medium=web">Take Your Faith Deeper Today.</a> '
    '<a href="https://thefunnies.substack.com/">The Funnies Every Week</a> '
    '<a href="https://www.challies.com/media/2026/10/5-2.jpg">Download</a> '
    '<a href="https://example.org/essays/gods-left-hand?utm_medium=x">God&#8217;s Left Hand.</a> '
    '<a href="https://example.org/essays/gods-left-hand">God&#8217;s Left Hand again</a></p>'
)


def _item(title="A La Carte (October 30)", published="Fri, 30 Oct 2026 10:00:00 +0000"):
    return {"source_name": "Tim Challies", "role": "discovery", "title": title,
            "url": "https://www.challies.com/a-la-carte/a-la-carte-october-30-2026/",
            "full_content": ROUNDUP, "published": published}


def test_extract_links_filters_stores_sponsors_and_homepages():
    links = d.extract_links(_item())
    assert [l["url"] for l in links] == [
        "https://www.desiringgod.org/interviews/was-piper-unprepared",
        "https://example.org/essays/gods-left-hand?utm_medium=x",
    ]
    assert links[1]["anchor"] == "God’s Left Hand"


def test_harvest_respects_title_pattern_and_age():
    today = date(2026, 10, 30)
    assert len(d.harvest_links([_item()], today)) == 2
    assert d.harvest_links([_item(title="Free Stuff Fridays (Ligonier)")], today) == []
    old = _item(published="Mon, 19 Oct 2026 10:00:00 +0000")
    assert d.harvest_links([old], today) == []
    assert d.harvest_links([{**_item(), "role": "primary"}], today) == []


def test_merge_skips_shown_and_prunes_old():
    q = {"entries": {"https://old.com/x": {"found_on": "2026-10-01", "status": "pending"}}}
    entries = d.harvest_links([_item()], date(2026, 10, 30))
    added = d.merge_into_queue(q, entries, {"https://desiringgod.org/interviews/was-piper-unprepared/"},
                               today=date(2026, 10, 30))
    assert added == 1
    assert list(q["entries"]) == ["https://example.org/essays/gods-left-hand"]
    assert d.merge_into_queue(q, entries, set(), today=date(2026, 10, 30)) == 1  # DG now new, GLH known


PAGE = """<html><head><title>ignored</title>
<meta property="og:title" content="God&#39;s Left Hand | Modern Reformation">
<meta content="An essay on God's vocation." property="og:description">
<meta property="og:site_name" content="Modern Reformation">
<meta name="author" content="https://facebook.com/someone">
<meta property="article:published_time" content="2026-10-28T13:00:06Z">
</head></html>"""


def test_article_from_page_builds_scorer_ready_dict():
    a = d.article_from_page({"found_via": "Tim Challies", "anchor": "x"}, PAGE,
                            "https://modernreformation.org/essays/glh")
    assert a["title"] == "God's Left Hand"
    assert a["source_name"] == "Modern Reformation"
    assert a["author"] == ""
    assert a["summary"] == "An essay on God's vocation."
    assert a["role"] == "primary" and a["creates_voices"] is False
    assert a["published"].startswith("Wed, 28 Oct 2026 13:00:06")
    assert a["discovered_via"] == "Tim Challies"


def test_graduate_marks_status_and_retries():
    q = {"entries": {
        "ok": {"url": "ok", "found_on": "2026-10-30", "status": "pending"},
        "bad": {"url": "bad", "found_on": "2026-10-30", "status": "pending", "attempts": 1},
    }}

    def fake(e):
        return (e, {"title": "T", "source_name": "S"}, "") if e["url"] == "ok" else (e, None, "HTTP 403")

    out = d.graduate(q, fetch=fake)
    assert len(out) == 1
    assert q["entries"]["ok"]["status"] == "graduated"
    assert q["entries"]["bad"]["status"] == "failed"


def test_strip_site_suffix():
    assert d._strip_site_suffix("Hello, Stained Glass. - Christianity Today", {"Christianity Today"}) == \
        "Hello, Stained Glass."
    assert d._strip_site_suffix("Faith - and Doubt", {"Christianity Today"}) == "Faith - and Doubt"
    assert d._strip_site_suffix("Essay | Some Site", set()) == "Essay"
