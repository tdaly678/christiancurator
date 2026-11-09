"""Tests for the topic data watch (curator/data_watch.py, scripts/run_data_watch.py)."""

import copy
import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_biblical_literacy_viz as viz  # noqa: E402
import build_recent_articles as recent  # noqa: E402
import run_data_watch  # noqa: E402
from curator import data_watch as dw  # noqa: E402
from frontend.topic_matcher import TOPICS as CURATED  # noqa: E402

TODAY = date(2026, 11, 10)
EM_DASH = "\u2014"
ALL_SLUGS = dw.existing_topic_slugs()


def page_html(body: str) -> str:
    """A fetched source page: chrome around an article body."""
    return (
        "<html><head><title>2 in 3 Churchgoers Fail Bible Quiz - Lifeway Research</title></head><body>"
        "<nav><p>Save 50% on Bibles today.</p></nav>"
        f"<article>{body}</article>"
        "<footer><p>Subscribe for 20% off your first order.</p></footer></body></html>"
    )


TOPIC_PAGE = """<html><head><script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Article", "headline": "On Abortion",
 "datePublished": "2026-04-17", "dateModified": "2026-04-17"}
</script></head><body><main class="cc-prose">
<p class="cc-last-updated">Last updated: April 17, 2026</p>
<section class="cc-synthesis"><p>Synthesis.</p></section>
<!-- AEO-RELATED-TOPICS:START --><nav>related</nav><!-- AEO-RELATED-TOPICS:END -->
<section class="cc-article-list"><h2 class="cc-article-list-label">The Evangelical Conversation, Curated</h2>
<article class="cc-article-entry"><a href="https://example.org/a">Curated piece</a><p>Annotation.</p></article>
</section>
</main></body></html>
"""


def verified(**over) -> dict:
    f = {
        "quote": "Barna found 42% of U.S. adults read the Bible weekly in 2025.",
        "figure": "42%",
        "publisher": "Barna Group",
        "license_status": "ask-first",
        "url": "https://example.org/story",
        "title": "Bible Reading Rises",
        "reported_by": "Example News",
        "found_on": "2026-11-10",
    }
    f.update(over)
    f["id"] = dw.figure_id(f["url"], f["quote"])
    return f


# ------------------------------------------------------------------ detection


@pytest.mark.parametrize("title,summary,tags", [
    ("Lifeway Research Finds Pastors Are Tired", "", []),
    ("2 in 3 Churchgoers Fail Bible Literacy Quiz", "", []),
    ("Most Americans Pray, New Survey Shows", "", []),
    ("Why Pastors Quit", "Barna's latest numbers say 38% have considered it.", []),
    ("The State of the Bible 2026", "", []),
    ("What the Data Says About Gen Z", "", ["data"]),
])
def test_detects_data_stories(title, summary, tags):
    assert dw.detect_signals({"title": title, "summary": summary, "tags": tags})


@pytest.mark.parametrize("title,summary,tags", [
    ("A Bible Study on Ruth for Small Groups", "Join our Bible study this fall.", []),
    ("Why I Love the Psalms", "A meditation on lament.", []),
    ("A New Report on Preaching", "Thoughts from a pastor.", []),  # weak word, no data tag
])
def test_ignores_non_data_stories(title, summary, tags):
    assert dw.detect_signals({"title": title, "summary": summary, "tags": tags}) is None


def test_signals_name_publishers_figures_and_source_host():
    sig = dw.detect_signals({"title": "Gen Z Reads More", "summary": "Barna says 49% read weekly.",
                             "url": "https://research.lifeway.com/2026/x/"})
    assert sig["publishers"][:2] == ["Barna Group", "Lifeway Research"]
    assert "49%" in sig["figures"]


def test_trend_uses_score_outlets_and_digest():
    pool = [
        {"source_name": "Lifeway Research", "topic_cluster": "bible_quiz", "final_score": 7},
        {"source_name": "TGC", "topic_cluster": "bible_quiz"},
        {"source_name": "Christian Post", "topic_cluster": "bible_quiz"},
        {"source_name": "WORLD", "topic_cluster": "unique"},
    ]
    assert dw.outlet_count(pool[0], pool) == 3
    assert dw.outlet_count(pool[3], pool) == 1
    assert dw.trend_score(pool[0], 3, on_digest=True) == 7 + 3.0 + 1.0
    assert dw.outlet_count({"source_name": "A", "also_from": ["B", "C"]}, []) == 3


# ------------------------------------------------------------------ topic matching


def test_biblical_literacy_is_in_the_matcher_and_has_a_page():
    assert "biblical-literacy" in {t["slug"] for t in CURATED}
    assert "biblical-literacy" in ALL_SLUGS


def test_matches_bible_literacy_story():
    a = {"title": "Most Churchgoers Fail Bible Literacy Quiz, Lifeway Research Finds"}
    assert dw.match_topic_slugs(a, ALL_SLUGS)[0] == "biblical-literacy"


def test_matches_other_real_topic_pages():
    assert "abortion" in dw.match_topic_slugs({"title": "Abortion Survey: Pro-Life Views Hold Steady"}, ALL_SLUGS)
    assert "pastoral-ministry" in dw.match_topic_slugs({"title": "Survey of Pastors Finds Burnout Easing"}, ALL_SLUGS)


def test_only_existing_pages_and_narrow_catch_all():
    a = {"title": "Most Churchgoers Fail Bible Literacy Quiz"}
    assert dw.match_topic_slugs(a, {"evangelicalism"}) == []
    assert dw.match_topic_slugs({"title": "Evangelicals Split on Tariffs, Poll Finds"}, ALL_SLUGS)[:1] == ["evangelicalism"]
    assert "evangelicalism" not in dw.match_topic_slugs({"title": "Church Attendance Rises in a Survey of Christians"}, ALL_SLUGS)


# ------------------------------------------------------------------ figure extraction and verification

BIBLE_KW = dw.topic_keywords("biblical-literacy")


def test_extracts_only_sentences_on_the_page_with_a_known_publisher():
    page = page_html(
        "<p>Lifeway Research surveyed 2,012 churchgoers. Three in 4 churchgoers (74%) know the verse is in the Bible.</p>"
        "<p>About 30% of churchgoers said they read the Bible daily, according to an unnamed poll.</p>"
    )
    figs = dw.find_figures(page, BIBLE_KW)
    assert [f["figure"] for f in figs] == ["Three in 4"]
    assert figs[0]["publisher"] == "Lifeway Research" and figs[0]["license_status"] == "reuse"


def test_unknown_publisher_is_never_a_figure():
    page = "<html><body><p>About 30% of Christians read the Bible daily, a new survey found.</p></body></html>"
    assert dw.find_figures(page, BIBLE_KW) == []


def test_ask_first_publishers_are_tagged():
    page = page_html("<p>Barna found 42% of U.S. adults read the Bible weekly in 2025.</p>"
                     "<p>The American Bible Society says 17% of adults are Scripture Engaged.</p>")
    figs = dw.find_figures(page, BIBLE_KW, limit=5)
    assert {(f["publisher"], f["license_status"]) for f in figs} == {
        ("Barna Group", "ask-first"), ("American Bible Society", "ask-first")}


def test_skips_head_nav_footer_promo_dashes_and_fragments():
    page = page_html(
        "<p>Pew Research found 44% of adults say the Bible is very important " + EM_DASH + " a big number.</p>"
        "<p>Respondents knew Moses received the commandments (94% correct v. 6% wrong).</p>"
        "<p>Bible sale: Pew readers get 30% off a study Bible.</p>"
    )
    assert dw.find_figures(page, BIBLE_KW) == []


def test_sentence_split_keeps_abbreviations():
    s = dw.sentences(["Pew says 22% of U.S. adults read scripture weekly. Next sentence here."])
    assert s[0] == "Pew says 22% of U.S. adults read scripture weekly."


def test_verify_figure_fails_closed():
    page = page_html("<p>Barna found 42% of U.S. adults read the Bible weekly in 2025.</p>")
    assert dw.verify_figure(verified(), page)
    assert not dw.verify_figure(verified(), page_html("<p>Barna found 41% of adults read.</p>"))  # not on page
    assert not dw.verify_figure(verified(figure="43%"))           # figure not in quote
    assert not dw.verify_figure(verified(url="http://example.org/story"))
    assert not dw.verify_figure(verified(url=""))
    assert not dw.verify_figure(verified(license_status="maybe"))
    assert not dw.verify_figure(verified(publisher=""))
    assert not dw.verify_figure(verified(quote="Barna found many adults read the Bible.", figure="many"))


# ------------------------------------------------------------------ Latest Figures block


def test_block_drops_unverified_figures_and_never_charts():
    block = dw.render_latest_figures("Abortion", [verified(), verified(quote="No number here at all.", figure="")])
    assert block.count('class="cc-lf-item"') == 1
    assert "<svg" not in block and "<canvas" not in block
    assert block.startswith(dw.LF_START) and block.endswith(dw.LF_END)
    assert EM_DASH not in block
    assert dw.render_latest_figures("Abortion", [verified(url="")]) == ""


def test_pew_figures_carry_disclaimer():
    block = dw.render_latest_figures("X", [verified(publisher="Pew Research Center", license_status="reuse",
                                                    quote="Pew found 42% of adults pray daily.")])
    assert "bears no responsibility" in block


def test_insert_once_refresh_in_place_and_bump_dates_only_on_change():
    page, changed = dw.apply_latest_figures(TOPIC_PAGE, "Abortion", [verified()], TODAY)
    assert changed
    assert page.count(dw.LF_START) == 1
    assert page.index(dw.LF_END) < page.index("<!-- AEO-RELATED-TOPICS:START -->")
    assert "Last updated: November 10, 2026" in page and '"dateModified": "2026-11-10"' in page
    # curated list and everything outside the block untouched
    assert dw.LF_BLOCK_RE.sub("", page).replace("\n", "") == TOPIC_PAGE.replace(
        "April 17, 2026", "November 10, 2026").replace('"dateModified": "2026-04-17"', '"dateModified": "2026-11-10"').replace("\n", "")
    # same content next day: no change, no date bump
    again, changed2 = dw.apply_latest_figures(page, "Abortion", [verified()], date(2026, 11, 11))
    assert not changed2 and again == page
    # no verified figures and no markers: page untouched
    same, changed3 = dw.apply_latest_figures(TOPIC_PAGE, "Abortion", [verified(url="")], TODAY)
    assert not changed3 and same == TOPIC_PAGE


# ------------------------------------------------------------------ structured data file (biblical literacy)


def test_watch_rows_are_added_once_with_changelog_and_unverified_rejected():
    data = copy.deepcopy(viz.load_data())
    new, added = dw.add_watch_rows(data, [verified(), verified(), verified(url="")], TODAY)
    assert len(added) == 1 and len(new["watch"]) == 1
    assert new["changelog"][-1]["date"] == "2026-11-10"
    assert "not charted" in new["changelog"][-1]["note"]
    again, added2 = dw.add_watch_rows(new, [verified()], TODAY)
    assert added2 == [] and again["changelog"] == new["changelog"]
    assert "watch" not in data  # pure


def test_builder_validates_and_renders_watch_rows_as_text_only():
    data, _ = dw.add_watch_rows(copy.deepcopy(viz.load_data()), [verified()], TODAY)
    assert viz.validate(data) == []
    page = viz.build_page(viz.PAGE_PATH.read_text(encoding="utf-8"), data, TODAY)
    tracker = viz.marker_re("TRACKER").search(page).group(2)
    assert 'id="data-watch"' in tracker and "42% of U.S. adults" in tracker
    for svg in re.findall(r"<svg.*?</svg>", page, re.S):
        assert "42% of U.S. adults" not in svg
    assert "Last updated: November 10, 2026" in page  # data changed, so the date moved
    bad = copy.deepcopy(data)
    bad["watch"][0]["figure"] = "43%"
    assert any("not in its quote" in e for e in viz.validate(bad))
    bad["watch"][0]["url"] = ""
    assert any("missing url" in e for e in viz.validate(bad))


def test_committed_data_file_and_page_unchanged_without_watch_rows():
    assert "watch" not in viz.load_data()
    assert viz.main(["--check"]) == 0


# ------------------------------------------------------------------ end to end


@pytest.fixture
def site(tmp_path):
    topics = tmp_path / "topics"
    for slug in ("abortion", "biblical-literacy", "prayer", "technology"):
        (topics / slug).mkdir(parents=True)
        (topics / slug / "index.html").write_text(TOPIC_PAGE, encoding="utf-8")
    return topics


def story(title, url, **over):
    a = {"title": title, "url": url, "source_name": "Example News", "final_score": 7.0,
         "summary": "", "tags": ["data"], "role": "primary"}
    a.update(over)
    return a


def test_run_writes_only_verified_figures_and_alerts_on_403(site):
    pool = [
        story("Abortion Survey: Lifeway Finds Pro-Life Views Hold", "https://example.org/abortion"),
        story("Pew: Americans Pray Less, Survey Finds", "https://example.org/prayer"),
        story("Abortion Poll Shows Shift", "https://example.org/unverified"),
    ]
    pages = {
        "https://example.org/abortion": page_html(
            "<p>Lifeway Research found 61% of churchgoers say abortion is morally wrong.</p>"),
        "https://example.org/unverified": page_html("<p>Most people changed their views on abortion this year.</p>"),
    }
    fetch = lambda u: (pages[u], "") if u in pages else (None, "HTTP 403")  # noqa: E731
    state = dw.run_watch(pool, [], {}, TODAY, fetch=fetch, topics_dir=site, repo_root=REPO_ROOT)

    abortion = (site / "abortion" / "index.html").read_text(encoding="utf-8")
    assert "61% of churchgoers say abortion is morally wrong" in abortion
    assert "Last updated: November 10, 2026" in abortion
    prayer = (site / "prayer" / "index.html").read_text(encoding="utf-8")
    assert prayer == TOPIC_PAGE  # 403: nothing written
    stories = {s["url"]: s for s in state["last_run"]["stories"]}
    assert "fetch failed (HTTP 403)" in " ".join(stories["https://example.org/prayer"]["actions"])
    assert stories["https://example.org/prayer"]["warning"]
    assert "link only" in " ".join(stories["https://example.org/unverified"]["actions"])
    assert [f["figure"] for f in state["figures"]["abortion"]] == ["61%"]

    summary = dw.summary_markdown(state)
    assert summary.startswith("## Topic data to review")
    assert "abortion" in summary and EM_DASH not in summary

    # second run: pages already checked, no refetch, no page change
    calls = []
    state2 = dw.run_watch(pool, [], copy.deepcopy(state), date(2026, 11, 11),
                          fetch=lambda u: calls.append(u) or (None, "x"), topics_dir=site, repo_root=REPO_ROOT)
    assert "https://example.org/abortion" not in calls
    assert (site / "abortion" / "index.html").read_text(encoding="utf-8") == abortion
    assert state2["figures"]["abortion"]


def test_figures_need_a_faith_angle(site):
    pool = [story("Smartphone Survey: Teens Online Constantly", "https://example.org/a")]
    page = page_html("<p>Pew Research found 46% of teens say they use a smartphone almost constantly.</p>")
    state = dw.run_watch(pool, [], {}, TODAY, fetch=lambda u: (page, ""), topics_dir=site, repo_root=REPO_ROOT)
    story_row = state["last_run"]["stories"][0]
    assert "technology" in story_row["topics"]
    assert state["figures"] == {}
    assert (site / "technology" / "index.html").read_text(encoding="utf-8") == TOPIC_PAGE


def test_digest_stories_feed_fresh_and_low_scores_are_not_fetched(site):
    history = [{"url": "https://example.org/quiz", "title": "Most Churchgoers Fail Bible Literacy Quiz",
                "source_name": "Lifeway Research", "date_shown": "2026-11-09", "final_score": 1.0}]
    pool = [story("Prayer Survey Finds Little Change", "https://example.org/low", final_score=2.0)]
    calls = []
    state = dw.run_watch(pool, history, {}, TODAY, fetch=lambda u: calls.append(u) or (None, "x"),
                         topics_dir=site, repo_root=REPO_ROOT, write=False)
    assert state["fresh"]["biblical-literacy"][0]["url"] == "https://example.org/quiz"
    assert calls == ["https://example.org/quiz"]  # on the digest, so fetched; the low scorer was not
    low = next(s for s in state["last_run"]["stories"] if s["url"] == "https://example.org/low")
    assert "watching only" in " ".join(low["actions"])


def test_structured_topic_goes_to_data_file_not_latest_figures(site):
    pool = [story("Bible Reading Survey: Barna Finds Rise", "https://example.org/bible")]
    page = page_html("<p>Barna found 42% of U.S. adults read the Bible weekly in 2025.</p>")
    state = dw.run_watch(pool, [], {}, TODAY, fetch=lambda u: (page, ""), topics_dir=site,
                         repo_root=REPO_ROOT, write=False)
    assert "biblical-literacy" not in state["figures"]
    assert state["last_run"]["pages"] == [
        {"slug": "biblical-literacy", "kind": "data-file", "note": "dry run: would add 1 watch row(s)"}]
    assert (site / "biblical-literacy" / "index.html").read_text(encoding="utf-8") == TOPIC_PAGE


def test_cli_never_fails_the_run(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("source exploded")
    monkeypatch.setattr(dw, "run_watch", boom)
    out = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out))
    assert run_data_watch.main(["--dry-run"]) == 0
    assert "Topic data to review" in out.read_text()
    assert run_data_watch.main(["--dry-run", "--strict"]) == 1


# ------------------------------------------------------------------ Fresh From the Digest


def test_recent_articles_merges_data_watch_stories(tmp_path):
    kw = [{"date": "2026-11-01", "title": "Old", "url": "https://a/1", "source": "A"}]
    watch = [{"date": "2026-11-09", "title": "Quiz", "url": "https://a/2", "source": "B"},
             {"date": "2026-11-01", "title": "Old", "url": "https://a/1", "source": "A"}]
    assert [i["url"] for i in recent.merge_items(kw, watch)] == ["https://a/2", "https://a/1"]
    p = tmp_path / "dw.json"
    p.write_text(json.dumps({"fresh": {"abortion": watch}}))
    assert recent.load_data_watch_fresh(p)["abortion"] == watch
    assert recent.load_data_watch_fresh(tmp_path / "missing.json") == {}


def test_initial_state_file_is_committed():
    state = json.loads((REPO_ROOT / "docs" / "data_watch.json").read_text())
    assert {"seen", "fresh", "figures"} <= set(state)


def test_rejects_methodology_first_person_and_context_dependent_sentences():
    page = page_html(
        "<p>When a county is split, I allocated 30% of its evangelicals to each district.</p>"
        "<p>So the evangelicals who show up in that 42% are likely mostly white.</p>"
        "<p>We found 55% of evangelicals read the Bible weekly, Barna said.</p>"
        "<p>Barna found 42% of evangelicals read the Bible weekly in 2025.</p>"
    )
    figs = dw.find_figures(page, dw.topic_keywords("biblical-literacy"), limit=5)
    assert [f["quote"] for f in figs] == ["Barna found 42% of evangelicals read the Bible weekly in 2025."]
