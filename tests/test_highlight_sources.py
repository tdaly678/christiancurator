"""Highlighted sources: Ryan Burge on the front page (S5, Nov 23 2026).

Tom: "I love this stuff from Burge, we should be highlighting him on curator
feed." These tests lock curator/highlight.py and its three uses: the reserved
sublead in frontend/layout.py, the cap exemptions in curator/scorer.py and the
kept publisher headline in curator/title_rewriter.py.

Run: .venv/bin/python -m pytest tests/test_highlight_sources.py
"""
import os
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from curator import scorer  # noqa: E402
from curator import title_rewriter  # noqa: E402
from curator.highlight import (  # noqa: E402
    HIGHLIGHT_FRESH_DAYS, HIGHLIGHT_SOURCES, is_highlighted, needs_featured_slot,
)
from fetcher.sources import SOURCES  # noqa: E402
from frontend.layout import SUBLEAD_COUNT, build_homepage_layout, reserve_highlight  # noqa: E402

NOW = datetime.now(timezone.utc)
TODAY_TITLE = "Catholics Are Going to Church Less\u2014and Voting Republican More"


def _published(days_ago: float) -> str:
    return format_datetime(NOW - timedelta(days=days_ago))


def _a(title, source, score=7.0, tags=("theology",), days_ago=0.5, **kw):
    slug = "".join(c for c in title.lower() if c.isalnum())[:40]
    return {"title": title, "original_title": title, "source_name": source,
            "url": f"https://{source.lower().replace(' ', '')}.example/{slug}",
            "final_score": score, "depth": score, "tags": list(tags),
            "topic_cluster": "unique", "published": _published(days_ago), **kw}


def _burge(title="Who Do Teenagers Turn To When They Doubt Their Religion?", score=4.5,
           tags=("data",), perspective="news", **kw):
    return _a(title, "Ryan Burge", score, tags, perspective=perspective, **kw)


ESSAYS = [
    _a("Pastors Must Put Christ Before Party", "ERLC", 8.5, ("church life",)),
    _a("Discipleship Aims at Christ, Not the Tribe", "Desiring God", 8.0),
    _a("Why Families Should Sit Together in Worship", "Stephen McAlpine", 7.5, ("church life",)),
    _a("Scholars Debate Who Wrote 2 Peter", "Michael Bird", 7.0),
    _a("How to Preach to Workers", "The Gospel Coalition", 6.5),
]


def _block(layout):
    return [layout["lead"], *layout["subleads"]]


# ── Configuration ────────────────────────────────────────────────────────────

def test_only_burge_is_highlighted():
    assert HIGHLIGHT_SOURCES == {"Ryan Burge": "research"}
    burge = next(s for s in SOURCES if s["name"] == "Ryan Burge")
    assert burge["highlight"] == "research" and burge["independent"] is True


def test_highlight_by_source_name_or_item_field():
    assert is_highlighted({"source_name": "Ryan Burge"})
    assert is_highlighted({"source_name": "Someone", "highlight": "research"})
    assert not is_highlighted({"source_name": "Pew Research"})


def test_featured_slot_only_on_first_showing_while_fresh():
    assert needs_featured_slot(_burge(days_ago=0.9))
    assert needs_featured_slot(_burge(days_ago=HIGHLIGHT_FRESH_DAYS - 0.1))
    assert not needs_featured_slot(_burge(days_ago=HIGHLIGHT_FRESH_DAYS + 0.5))
    assert not needs_featured_slot(_burge(previously_shown=True))
    assert not needs_featured_slot(_burge(shown_yesterday=True))
    assert not needs_featured_slot(_burge(published=""))
    assert not needs_featured_slot(_a("Fresh Essay on Grace", "Desiring God"))


# ── Layout: the reserved sublead ─────────────────────────────────────────────

def test_new_burge_post_takes_first_sublead_over_stronger_essays():
    post = _burge()
    block = _block(build_homepage_layout(ESSAYS + [post]))
    assert len(block) == 1 + SUBLEAD_COUNT
    assert block[0]["source_name"] == "ERLC"          # the Lead is untouched
    assert block[1]["url"] == post["url"]
    assert "The Gospel Coalition" not in {a["source_name"] for a in block}


def test_shown_burge_post_gets_no_reserved_slot():
    post = _burge(previously_shown=True)
    layout = build_homepage_layout(ESSAYS + [post])
    assert post["url"] not in {a["url"] for a in _block(layout)}


def test_old_burge_post_gets_no_reserved_slot():
    post = _burge(days_ago=HIGHLIGHT_FRESH_DAYS + 1)
    layout = build_homepage_layout(ESSAYS + [post])
    assert post["url"] not in {a["url"] for a in _block(layout)}


def test_newest_unshown_post_wins_and_one_per_source():
    older = _burge("The Religious Gender Gap Is Really a Political Gap", days_ago=3.5)
    newer = _burge("How Much Less Religious Is Australia Than the U.S.?", days_ago=0.8)
    block = _block(build_homepage_layout(ESSAYS + [older, newer]))
    burge = [a for a in block if a["source_name"] == "Ryan Burge"]
    assert [a["url"] for a in burge] == [newer["url"]]


def test_burge_already_in_block_is_not_duplicated():
    post = _burge(score=9.5, tags=("theology",), perspective="neutral")
    block = _block(build_homepage_layout(ESSAYS + [post]))
    assert [a["url"] for a in block].count(post["url"]) == 1
    assert len(block) == 1 + SUBLEAD_COUNT


def test_reserved_slot_sits_after_the_dominant_story():
    lead, dom, s2, s3 = (_a(t, src) for t, src in
                         (("A", "ERLC"), ("B", "RNS"), ("C", "TGC"), ("D", "WORLD")))
    post = _burge()
    top = reserve_highlight([lead, dom, s2, s3], post, dom)
    assert [a["url"] for a in top] == [lead["url"], dom["url"], post["url"], s2["url"]]


def test_reserved_slot_takes_the_lead_only_when_block_is_empty():
    post = _burge()
    assert reserve_highlight([], post, None) == [post]


def test_scandal_never_takes_the_reserved_slot():
    post = _burge("Pastor Abuse Scandal Hits Church Attendance Data")
    layout = build_homepage_layout(ESSAYS + [post])
    assert post["url"] not in {a["url"] for a in _block(layout)}


# ── Scorer: data about any religious group is on mission ─────────────────────

def _score(monkeypatch, articles):
    monkeypatch.setenv("TRENDING_BOOST_DISABLED", "1")

    def fake_batch(batch):
        for a in batch:
            a.update(importance=8, depth=4, tags=["data"], perspective="news",
                     topic_cluster=a.get("cluster", "unique"))
        return batch

    monkeypatch.setattr(scorer, "score_batch", fake_batch)
    monkeypatch.setattr(scorer, "load_source_last_shown", lambda: {})
    return {a["source_name"]: a for a in scorer.score_articles(articles)}


def _raw(title, source, cluster="unique"):
    return {"title": title, "original_title": title, "source_name": source, "summary": "",
            "url": f"https://{source.lower().replace(' ', '')}.example/x",
            "published": _published(0.8), "source_type": "christian", "role": "primary",
            "cluster": cluster}


def test_burge_catholic_post_escapes_catholic_cap(monkeypatch):
    out = _score(monkeypatch, [
        _raw(TODAY_TITLE, "Ryan Burge", cluster="catholic_voting"),
        _raw("Catholics Flock to Latin Mass Parishes", "Some Outlet", cluster="catholic_trads"),
    ])
    burge, other = out["Ryan Burge"], out["Some Outlet"]
    assert burge["final_score"] > scorer.CATHOLIC_SCORE_CAP
    assert not burge.get("catholic_capped") and not burge.get("catholic_internal")
    assert not burge.get("off_mission_capped")
    # Later boosts (stale source) can lift a capped item a little; the flag
    # is what keeps it out of the lead block and the board's top.
    assert other["catholic_capped"] and other["catholic_internal"]


def test_burge_mainline_and_horse_race_titles_not_capped(monkeypatch):
    out = _score(monkeypatch, [
        _raw("Methodist Bishops and the Clergy Shortage, in Five Graphs", "Ryan Burge"),
        _raw("Democrats Gain Ground With Swing Voters", "Other Blog"),
    ])
    assert not out["Ryan Burge"].get("mainline_capped")
    assert out["Ryan Burge"]["final_score"] > scorer.MAINLINE_SCORE_CAP
    assert out["Other Blog"]["off_mission_capped"] == "horse_race"


def test_todays_post_reaches_a_sublead_end_to_end(monkeypatch):
    scored = list(_score(monkeypatch, [_raw(TODAY_TITLE, "Ryan Burge")]).values())
    block = _block(build_homepage_layout(ESSAYS + scored))
    hit = next(a for a in block if a["source_name"] == "Ryan Burge")
    assert block.index(hit) == 1
    assert hit["display_title"] == "Catholics Are Going to Church Less, and Voting Republican More"


# ── Headlines: the publisher's own title ─────────────────────────────────────

def test_burge_keeps_publisher_title(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Claude must not be called for a highlighted source")

    monkeypatch.setattr(title_rewriter.client.messages, "create", boom)
    art = {"title": TODAY_TITLE, "original_title": TODAY_TITLE, "source_name": "Ryan Burge",
           "summary": "Mass attendance is falling among Catholics while their vote shifts right.",
           "url": "https://www.graphsaboutreligion.com/p/catholics-are-going-to-church-lessand"}
    out = title_rewriter.rewrite_title(art)
    assert out["rewrite_skipped"] == "KEEP_HIGHLIGHT"
    assert out["rewritten_title"] == "Catholics Are Going to Church Less, and Voting Republican More"
    assert "\u2014" not in out["rewritten_title"]


def test_other_sources_still_eligible_for_rewrite():
    art = {"title": "A Long Essay on Grace", "source_name": "Desiring God", "summary": "x",
           "url": "https://www.desiringgod.org/articles/grace"}
    assert title_rewriter.keep_publisher_title(art) is None
