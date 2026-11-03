"""Nov 1 fixes: dated-column / review-meta hard rejects, REVIEW_SOFT and
DEMOTE_CLAIMLESS_SHORT voice rules, and the cross-day split (yesterday's picks
barred from lead, subleads and email; older repeats only penalised).

Run: .venv/bin/python -m pytest tests/test_cross_day_and_voice.py
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import output  # noqa: E402
from curator import email_sender as es  # noqa: E402
from curator.headline_voice import (  # noqa: E402
    DEMOTE_CLAIMLESS_SHORT, HARD_REJECT_DATED_COLUMN, HARD_REJECT_REVIEW_META, REVIEW_SOFT,
    hard_reject, is_claimless_short, is_dated_briefing, voice_adjustments,
)
from curator.dedup import canonical_url  # noqa: E402
from curator.scorer import matches_history  # noqa: E402
from frontend.layout import build_homepage_layout, outbound_urls  # noqa: E402

FRANNI = ("https://relevantmagazine.com/faith/franni-cash-on-leaving-the-family-band-"
          "her-solo-debut-and-growing-up-in-a-cult/")
MOHLER_FRIDAY = "Friday, October 30, 2026"
WNG_TITLE = "The World and Everything in It: October 30, 2026"


# ── Hard rejects ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "Works & Wonders (November 1)",
    "Works & Wonders: October 25",
    "Weekend A La Carte (October 24)",
])
def test_dated_column_rejected(title):
    assert hard_reject(title, "Tim Challies") == HARD_REJECT_DATED_COLUMN


def test_review_meta_rejected():
    assert hard_reject("Church History Lives Up to Its Title") == HARD_REJECT_REVIEW_META
    assert hard_reject("‘Church History for Everyone’ Lives Up to Its Title",
                       "Christianity Today") == HARD_REJECT_REVIEW_META


def test_mohler_and_wng_briefings_allow_listed():
    assert hard_reject(MOHLER_FRIDAY, "Albert Mohler") is None
    assert hard_reject(WNG_TITLE, "World Magazine") is None
    assert is_dated_briefing(MOHLER_FRIDAY, "Albert Mohler")
    assert is_dated_briefing(WNG_TITLE, "World Magazine")


def test_same_mohler_title_from_other_source_rejected():
    assert hard_reject(MOHLER_FRIDAY, "Random Blog") == HARD_REJECT_DATED_COLUMN
    assert hard_reject(MOHLER_FRIDAY) == HARD_REJECT_DATED_COLUMN
    assert hard_reject(WNG_TITLE, "Random Blog") == HARD_REJECT_DATED_COLUMN


@pytest.mark.parametrize("title", [
    "Conference Talk: The History, Mystery and Myth of September 11",
    "SBC Votes on Women Pastors Amendment",
    "Tyranny of Preferences",
])
def test_not_dated_or_review_meta(title):
    assert hard_reject(title) is None


# ── Voice rules ───────────────────────────────────────────────────────────────

def test_tyranny_of_preferences_is_claimless():
    assert hard_reject("Tyranny of Preferences") is None
    assert voice_adjustments("Tyranny of Preferences")["DEMOTE_CLAIMLESS_SHORT"] == DEMOTE_CLAIMLESS_SHORT
    assert DEMOTE_CLAIMLESS_SHORT == -15


@pytest.mark.parametrize("title", [
    "Myth of St. Francis",
    "Dangers of Christian Nationalism",
    "The Myth of St. Francis",
    "The Pastor Resigns",
    "The Church: A Field Guide",
    "Is the Church Dying?",
    "Pastors Who Burn Out Quietly in Small Towns",  # over 5 words
])
def test_claim_titles_not_claimless(title):
    assert not is_claimless_short(title)
    assert "DEMOTE_CLAIMLESS_SHORT" not in voice_adjustments(title)


@pytest.mark.parametrize("title", [
    "Review: Rethinking the Reformation",
    "A Review of Carl Trueman's New Book",
    "New and Notable Books for Pastors",
])
def test_review_soft(title):
    assert voice_adjustments(title)["REVIEW_SOFT"] == REVIEW_SOFT == -20


# ── Cross-day split ───────────────────────────────────────────────────────────

def art(title, source, score, url=None, **kw):
    return {"title": title, "source_name": source, "final_score": score,
            "url": url or f"https://{source.lower().replace(' ', '')}.example/{abs(hash(title))}",
            "tags": ["news"], **kw}


def _articles():
    return [
        art("Franni Cash on Leaving the Family Band, Her Solo Debut and Growing Up in a Cult",
            "Relevant Magazine", 9.9, url=FRANNI, shown_yesterday=True, previously_shown=True),
        art("Tyranny of Preferences", "Some Substack", 9.8),
        art(MOHLER_FRIDAY, "Albert Mohler", 9.7),
        art("An Older Repeat Still Worth the Board", "Older Outlet", 9.6, previously_shown=True),
        art("SBC Votes to Study Women Pastors Amendment", "Baptist Press", 9.0),
        art("Pastor Resigns After Investigation", "The Roys Report", 8.0),
        art("Church Leaders Urge Calm After Ruling", "Christianity Today", 7.0),
        art("Seminary Names New President", "World Magazine", 6.0),
    ]


def test_yesterday_url_barred_from_lead_block_but_on_board():
    layout = build_homepage_layout(_articles())
    lead_block = [layout["lead"]["url"]] + [a["url"] for a in layout["subleads"]]
    assert FRANNI not in lead_block
    board = [a["url"] for col in layout["board"] for a in col["articles"]]
    assert FRANNI in board


def test_claimless_and_briefing_kept_out_of_lead():
    layout = build_homepage_layout(_articles())
    # Older repeats are only penalised (their final_score already carries it),
    # so the top eligible item leads; Tyranny and the briefing never do.
    assert layout["lead"]["title"] == "An Older Repeat Still Worth the Board"
    sub_titles = [a["title"] for a in layout["subleads"]]
    assert "Tyranny of Preferences" not in sub_titles
    # The allow-listed briefing never leads, and since 2026-11-03 a bare dated
    # title is not a sublead either (subleads are email headline slots).
    assert MOHLER_FRIDAY not in sub_titles
    board = [a["title"] for col in layout["board"] for a in col["articles"]]
    assert "Tyranny of Preferences" in board


def test_older_repeat_stays_in_pool():
    layout = build_homepage_layout(_articles())
    assert any(a["title"] == "An Older Repeat Still Worth the Board"
               for a in [layout["lead"], *layout["subleads"]]
               + [a for col in layout["board"] for a in col["articles"]])


def test_email_skips_yesterday_and_claimless():
    email = es._email_layout([], layout=build_homepage_layout(_articles()))
    urls = ([email["lead"]["url"]] + [a["url"] for a in email["subleads"]]
            + [a["url"] for col in email["board"] for a in col["articles"]]
            + [a["url"] for a in email["worth_your_time"]])
    titles = {a["title"] for col in email["board"] for a in col["articles"]}
    assert FRANNI not in urls
    assert "Tyranny of Preferences" not in titles
    assert email["lead"]["title"] != MOHLER_FRIDAY


def test_canonical_match_flags_yesterday():
    tracked = {"url": "http://www." + FRANNI.split("://", 1)[1] + "?utm_source=rss"}
    assert matches_history(tracked, {FRANNI}, {canonical_url(FRANNI)})
    assert not matches_history({"url": "https://other.example/x"}, {FRANNI}, {canonical_url(FRANNI)})


def test_history_split_and_full_layout_logging(tmp_path, monkeypatch):
    hist = tmp_path / "article_history.json"
    hist.write_text(json.dumps([
        {"url": "https://a.example/old", "date_shown": "2026-10-29"},
        {"url": FRANNI, "canonical_url": "relevantmagazine.com/x", "date_shown": "2026-10-31"},
        {"url": "https://a.example/today", "date_shown": "2026-11-01"},
    ]))
    monkeypatch.setattr(output, "HISTORY_JSON_PATH", hist)
    day, urls = output.load_yesterday_shown(today="2026-11-01")
    assert day == "2026-10-31"
    assert FRANNI in urls and "https://a.example/old" not in urls

    # Every rendered URL is logged, and a repeat gets a new row for the new day.
    layout = build_homepage_layout(_articles())
    output.save_article_history([a for a in [layout["lead"], *layout["subleads"]]
                                 + [a for c in layout["board"] for a in c["articles"]]],
                                day="2026-11-02")
    rows = json.loads(hist.read_text())
    logged = {r["url"] for r in rows if r["date_shown"] == "2026-11-02"}
    assert logged == set(outbound_urls(layout))
    assert all(r.get("canonical_url") for r in rows if r["date_shown"] == "2026-11-02")
    assert FRANNI in logged
