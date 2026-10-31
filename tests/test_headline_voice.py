"""Tests for curator/headline_voice.py hard rejects."""

import pytest

from curator.headline_voice import (
    HARD_REJECT_EMOJI,
    HARD_REJECT_ISSUE_NUMBER,
    HARD_REJECT_PROMO,
    HARD_REJECT_ROUNDUP,
    hard_reject,
)


# Tom's rejects from the 2026-10-31 homepage.
def test_tom_fixture_promo_curly_quotes():
    assert hard_reject("“Scroll Less, Live More” is HERE") == HARD_REJECT_PROMO


def test_tom_fixture_promo_straight_quotes():
    assert hard_reject('"Scroll Less, Live More" is HERE') == HARD_REJECT_PROMO


def test_tom_fixture_newsletter_issue():
    assert hard_reject("5 Quick Things #432 \U0001F47B") is not None


@pytest.mark.parametrize("title,reason", [
    ("Happy Fall \U0001F342", HARD_REJECT_EMOJI),
    ("Big News ❤️", HARD_REJECT_EMOJI),
    ("5 Quick Things #432", HARD_REJECT_ISSUE_NUMBER),
    ("The Weekly Letter, Issue 57", HARD_REJECT_ISSUE_NUMBER),
    ("Field Notes Vol. 3", HARD_REJECT_ISSUE_NUMBER),
    ("Ep. 112: On Calvin", HARD_REJECT_ISSUE_NUMBER),
    ("Episode 9 with Russell Moore", HARD_REJECT_ISSUE_NUMBER),
    ("Dispatch No. 45", HARD_REJECT_ISSUE_NUMBER),
    ("My New Book Is Out Now", HARD_REJECT_PROMO),
    ("Now Available: A Study of Romans", HARD_REJECT_PROMO),
    ("Pre-order My New Book", HARD_REJECT_PROMO),
    ("Book Giveaway This Week", HARD_REJECT_PROMO),
    ("The Course Launch Starts Monday", HARD_REJECT_PROMO),
    ("The Book Is Here!", HARD_REJECT_PROMO),
    ("Register Now for the Fall Conference", HARD_REJECT_PROMO),
    ("Five Quick Things", HARD_REJECT_ROUNDUP),
    ("Weekly Roundup: October", HARD_REJECT_ROUNDUP),
    ("Things I’m Reading", HARD_REJECT_ROUNDUP),
    ("Friday Five", HARD_REJECT_ROUNDUP),
    ("Open Thread", HARD_REJECT_ROUNDUP),
    ("Links", HARD_REJECT_ROUNDUP),
    ("Weekend Links: Halloween Edition", HARD_REJECT_ROUNDUP),
])
def test_rejects(title, reason):
    assert hard_reject(title) == reason


@pytest.mark.parametrize("title", [
    "Pope Urges Europe To Draw From Christian Roots",
    "Why Is the SBC Membership Declining?",
    "Trump: Media Conspiring to Throw Election",
    "Missing Links in Theology",
    "SpaceX Launch Delayed by Weather",
    "Southern Baptists Launch New Church Planting Initiative",
    "Historic Church Building Put Up for Sale",
    "Abortion Is the No. 1 Issue for These Voters",
    "The Age of AI Is Here. Is the Church Ready?",
    "Register of Deeds Refuses Marriage Licenses",
    "Why Subscribers Leave Christian Magazines",
    "Psalm 23 and the Shepherd's Care",
    "Romans 8:28 Does Not Mean What You Think",
    "",
])
def test_keeps_real_headlines(title):
    assert hard_reject(title) is None
