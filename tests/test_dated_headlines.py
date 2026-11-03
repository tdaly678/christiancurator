"""Dated column titles never appear as headlines (2026-11-03).

On Nov 3 2026 "The World and Everything in It: November 3, 2026" (World
Magazine) passed hard_reject() via the DATED_ALLOW allow-list and landed on the
News board and in the email's News section. The allow-list only keeps the item
from being dropped before scoring; a bare dated title is not a headline, so
build_homepage_layout() drops it from every article lane and email_eligible()
keeps it out of every email slot, unless rewritten_title states a real claim.
Watch and Listen (media items) may still carry it. The lead ban is unchanged.

Run: .venv/bin/python -m pytest tests/test_dated_headlines.py
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curator import email_sender as es  # noqa: E402
from curator.headline_voice import (  # noqa: E402
    hard_reject, headline_has_claim, is_dated_column_title,
)
from frontend.layout import (  # noqa: E402
    _pick_lead, build_homepage_layout, email_eligible, lead_block_eligible, outbound_urls,
)

WNG = "The World and Everything in It: November 3, 2026"
MOHLER = "Monday, November 3, 2026"
WNG_URL = "https://wng.org/podcasts/the-world-and-everything-in-it-november-3-2026"
MOHLER_URL = "https://albertmohler.com/2026/11/03/briefing"


def art(title, source, score, url=None, **kw):
    return {"title": title, "source_name": source, "final_score": score,
            "url": url or f"https://{source.lower().replace(' ', '')}.example/{abs(hash(title))}",
            "tags": ["news"], **kw}


def _articles(**wng_kw):
    return [
        art(WNG, "World Magazine", 9.9, url=WNG_URL, **wng_kw),
        art(MOHLER, "Albert Mohler", 9.8, url=MOHLER_URL),
        art("SBC Votes to Study Women Pastors Amendment", "Baptist Press", 9.0),
        art("Pastor Resigns After Investigation", "The Roys Report", 8.0),
        art("Church Leaders Urge Calm After Ruling", "Christianity Today", 7.0),
        art("Seminary Names New President", "Christian Post", 6.0),
        art("Court Upholds Church Zoning Win", "Religion News Service", 5.0),
    ]


def _board_titles(layout):
    return [a.get("rewritten_title") or a["title"]
            for col in layout["board"] for a in col["articles"]]


def _email_titles(email):
    items = ([email["lead"]] if email.get("lead") else []) + email["subleads"]
    items += [a for col in email["board"] for a in col["articles"]]
    items += email["worth_your_time"] + email["watch_listen"]
    items += [x for d in email["debate"] for x in (d["a"], d["b"])]
    return [a.get("rewritten_title") or a["title"] for a in items]


# ── headline_voice ───────────────────────────────────────────────────────────

def test_allow_list_unchanged():
    assert hard_reject(WNG, "World Magazine") is None
    assert hard_reject(MOHLER, "Albert Mohler") is None


@pytest.mark.parametrize("title", [WNG, MOHLER, "Works & Wonders (November 1)"])
def test_dated_titles_detected(title):
    assert is_dated_column_title(title)
    assert not headline_has_claim({"title": title})


@pytest.mark.parametrize("title", [
    "SBC Votes to Study Women Pastors Amendment",
    "Conference Talk: The History, Mystery and Myth of September 11",
])
def test_claim_titles_not_dated(title):
    assert not is_dated_column_title(title)
    assert headline_has_claim({"title": title})


def test_rewrite_with_claim_counts():
    assert headline_has_claim({"title": WNG, "rewritten_title": "Voters Head to Polls as Pastors Urge Prayer"})
    # The title rewriter echoes the original when it has nothing better.
    assert not headline_has_claim({"title": WNG, "rewritten_title": WNG})


# ── Layout ───────────────────────────────────────────────────────────────────

def test_dated_titles_not_on_board_or_lead_block():
    layout = build_homepage_layout(_articles())
    shown = _board_titles(layout) + [layout["lead"]["title"]] + [a["title"] for a in layout["subleads"]]
    assert WNG not in shown and MOHLER not in shown
    assert WNG_URL not in outbound_urls(layout)
    assert MOHLER_URL not in outbound_urls(layout)
    assert layout["lead"]["title"] == "SBC Votes to Study Women Pastors Amendment"


def test_dated_titles_out_of_worth_your_time():
    arts = _articles()
    for a in arts:
        a["depth"] = 9
    layout = build_homepage_layout(arts)
    wyt = [a["url"] for a in layout["worth_your_time"]]
    assert WNG_URL not in wyt and MOHLER_URL not in wyt


def test_rewritten_claim_may_sit_on_board_but_never_lead():
    claim = "Voters Head to Polls as Pastors Urge Prayer"
    layout = build_homepage_layout(_articles(rewritten_title=claim))
    assert layout["lead"]["url"] != WNG_URL
    placed = [layout["lead"], *layout["subleads"], *[a for c in layout["board"] for a in c["articles"]]]
    assert WNG_URL in [a["url"] for a in placed]


def test_lead_ban_intact_for_rewritten_briefing():
    a = art(WNG, "World Magazine", 9.9, rewritten_title="Voters Head to Polls as Pastors Urge Prayer")
    b = art("Pastor Resigns After Investigation", "The Roys Report", 8.0)
    assert _pick_lead([a, b], 2)[0] is b


def test_eligibility_helpers():
    assert not lead_block_eligible({"title": WNG})
    assert not email_eligible({"title": WNG})
    # Watch and Listen media items are the one place a dated show may appear.
    assert email_eligible({"title": WNG, "role": "media"})


# ── Email ────────────────────────────────────────────────────────────────────

def test_email_never_shows_dated_titles():
    email = es._email_layout([], layout=build_homepage_layout(_articles()))
    titles = _email_titles(email)
    assert WNG not in titles and MOHLER not in titles


def test_email_drops_dated_title_from_stale_layout():
    """A layout built before this fix (or cached) still gets filtered."""
    layout = build_homepage_layout(_articles()[2:])
    layout["board"][0]["articles"].insert(0, art(WNG, "World Magazine", 9.9, url=WNG_URL))
    titles = _email_titles(es._email_layout([], layout=layout))
    assert WNG not in titles
