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
        "https://example.org/essays/gods-left-hand",  # utm_* stripped
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


# ---------------------------------------------------------- non-articles (S1 2.4)

def test_blocked_reason_refuses_stores_apps_affiliates_and_hubs():
    for url in [
        "https://apps.apple.com/us/app/daily-spurgeon-devotionals/id1476230796",
        "https://play.google.com/store/apps/details?id=x",
        "https://link.amazon/B0jkiV4jE",
        "https://www.amazon.com/dp/1496433416?tag=x",
        "https://www.amazon.co.uk/dp/1496433416",
        "https://amzn.to/3abc",
        "https://logos.sjv.io/PzEPWz",
        "https://en.wikipedia.org/wiki/The_Andy_Griffith_Show_season_3",
        "https://truth78.org/collections/fighter-verses-songs",
        "https://www.crossway.org/books/esv-study-bible/",
        "https://www.monergism.com/christs-incarnation-foundation-christianity-ebook",
        "https://www.theguardian.com/education/office-for-students",
        "https://example.org/tag/prayer/",
    ]:
        assert d.blocked_reason(url), url


def test_blocked_reason_keeps_real_articles():
    for url in [
        "https://www.theguardian.com/education/2026/nov/11/ai-close-to-impossible-assess",
        "https://relevantmagazine.com/culture/books/8-devotionals-for-anyone",
        "https://www.thegospelcoalition.org/reviews/editors-pick-middle-grade-books/",
        "https://zakmellgren.substack.com/p/theres-no-such-thing-as-your-weekend",
        "https://www.desiringgod.org/interviews/are-my-prayers-selfish",
        "https://www.facebook-free-blog.org/notebook-thoughts",
    ]:
        assert d.blocked_reason(url) == "", url


def test_anchor_quality():
    assert d.anchor_ok("Can You Keep Falling into the Same Sin")
    for weak in ["see here for images", "season 3, episode 16", "Bible Study Week deals",
                 "Download the app", "Read more here", "a of it", "https://x.org/a/b c"]:
        assert not d.anchor_ok(weak), weak


def test_clean_url_strips_gift_and_utm_params():
    url = ("https://thedispatch.com/article/trauma-mental-health-therapy/?gift_key=d7f3"
           "&gift_ref=d277&gift_t=17951&utm_source=x&id=7")
    assert d.clean_url(url) == "https://thedispatch.com/article/trauma-mental-health-therapy/?id=7"
    assert d.clean_url("https://x.org/a") == "https://x.org/a"


def test_article_from_page_refuses_blocked_final_url_and_hub_pages():
    entry = {"anchor": "All God's Creatures: What the Bible Says"}
    assert d.article_from_page(entry, PAGE, "https://www.amazon.com/dp/B0jk") is None
    hub = ('<meta property="og:type" content="website">'
           '<meta property="og:title" content="Office for Students">')
    assert d.article_from_page(entry, hub, "https://example.org/office-for-students") is None


def test_article_from_page_strips_gift_params_and_credits_platform_writer():
    page = ('<meta property="og:title" content="There is No Such Thing as Your Weekend">'
            '<meta name="author" content="Zak Mellgren">'
            '<meta property="og:site_name" content="Substack">')
    a = d.article_from_page({"anchor": "x y z"}, page,
                            "https://zakmellgren.substack.com/p/weekend?utm_source=x&gift_key=1")
    assert a["url"] == "https://zakmellgren.substack.com/p/weekend"
    assert a["source_name"] == "Zak Mellgren"
    bare = d.article_from_page({"anchor": "x y z"}, '<meta property="og:title" content="Essay">',
                               "https://someone.substack.com/p/essay")
    assert bare["source_name"] == "someone.substack.com"


def test_article_from_page_uses_anchor_when_title_is_site_name():
    page = ('<meta property="og:title" content="Biblical Counseling Coalition">'
            '<meta property="og:site_name" content="Biblical Counseling Coalition">')
    a = d.article_from_page({"anchor": "Getting a Handle on Our Emotions"}, page,
                            "https://www.biblicalcounselingcoalition.org/2026/11/16/emotions/")
    assert a["title"] == "Getting a Handle on Our Emotions"


def test_graduate_blocks_queued_non_articles_without_fetching():
    q = {"entries": {
        "app": {"url": "https://apps.apple.com/us/app/x/id1", "anchor": "Daily Spurgeon Devotionals",
                "found_on": "2026-11-21", "status": "pending"},
        "weak": {"url": "https://example.org/news/sky", "anchor": "see here for images",
                 "found_on": "2026-11-21", "status": "pending"},
    }}
    fetched = []
    assert d.graduate(q, fetch=lambda e: fetched.append(e) or (e, None, "x")) == []
    assert fetched == []
    assert q["entries"]["app"]["status"] == "blocked"
    assert q["entries"]["weak"]["status"] == "blocked"
