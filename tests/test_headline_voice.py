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


# ── Slice 2: voice_score ─────────────────────────────────────────────────────

from curator.headline_voice import (  # noqa: E402
    BOOST_ISSUE_QUESTION,
    BOOST_NEWS_VERB,
    DEMOTE_ALL_CAPS,
    DEMOTE_EXCLAIM,
    DEMOTE_FIRST_PERSON_META,
    DEMOTE_LENGTH,
    apply_display_title,
    display_byline,
    display_title,
    strip_dashes,
    voice_adjustments,
    voice_score,
)


def test_neutral_title_scores_zero():
    assert voice_score("The Local Church and the Long Obedience of Ministry") == 0


def test_empty_title_scores_zero():
    assert voice_score("") == 0 and voice_score(None) == 0


@pytest.mark.parametrize("title", [
    "BREAKING: Church Splits Over Doctrine",
    "You MUST Read This Book About Prayer",
    "The Church Needs REVIVAL Right Now",
])
def test_all_caps_demoted(title):
    assert voice_adjustments(title).get("DEMOTE_ALL_CAPS") == DEMOTE_ALL_CAPS


@pytest.mark.parametrize("title", [
    "SBC Messengers Meet in Dallas Next June",
    "PCA General Assembly Debates Women Deacons",
    "ERLC and NAE Weigh In on AI Policy",
    "CBMW Releases New Statement on Manhood",
    "The ESV and NIV Compared for Families",
    "PC(USA) Assembly Elects New Leader",
    "COVID-19 and the Church's Long Recovery",
    '"STOP" Is the Wrong Word for Pastors',
])
def test_acronyms_and_quoted_caps_not_demoted(title):
    assert "DEMOTE_ALL_CAPS" not in voice_adjustments(title)


def test_exclaim_demoted():
    assert voice_adjustments("A Great Day for the Church!")["DEMOTE_EXCLAIM"] == DEMOTE_EXCLAIM


def test_exclaim_inside_quotes_not_demoted():
    assert "DEMOTE_EXCLAIM" not in voice_adjustments('Why "He Is Risen!" Still Matters Today')


@pytest.mark.parametrize("title", [
    "My Week in Books and Podcasts",
    "What I'm Reading This Fall Season",
    "This Week I Read Three Great Books",
    "Things I Loved in October This Year",
    "A Note to My Readers About Changes",
    "My Favorite Books of the Year So Far",
])
def test_first_person_meta_demoted(title):
    assert voice_adjustments(title)["DEMOTE_FIRST_PERSON_META"] == DEMOTE_FIRST_PERSON_META


@pytest.mark.parametrize("title", [
    "Why I Left the PCA",
    "I Was Wrong About Complementarianism",
    "How My Church Survived a Split",
])
def test_substantive_first_person_not_demoted(title):
    assert "DEMOTE_FIRST_PERSON_META" not in voice_adjustments(title)


@pytest.mark.parametrize("title", [
    "Grace",
    "On Hope",
    "A Very Long Headline That Keeps Going and Going Well Past the Point Where Anyone Reads",
])
def test_length_demoted(title):
    assert voice_adjustments(title)["DEMOTE_LENGTH"] == DEMOTE_LENGTH


@pytest.mark.parametrize("title", [
    "SBC Votes to Expel Saddleback Church",
    "Pastor Resigns After Abuse Report",
    "Supreme Court Rejects Appeal From Baker",
    "ERLC Urges Congress to Protect Conscience",
    "3 Churches Leave the Denomination",
])
def test_news_verb_boosted(title):
    assert voice_adjustments(title)["BOOST_NEWS_VERB"] == BOOST_NEWS_VERB


@pytest.mark.parametrize("title", [
    "The Ends of the Earth and the Great Commission",
    "Resigns Is a Word We Should Retire",
    "Notes on the Leave of Absence",
])
def test_news_verb_needs_a_subject(title):
    assert "BOOST_NEWS_VERB" not in voice_adjustments(title)


@pytest.mark.parametrize("title", [
    "Why the Church Needs Creeds",
    "Is Hell Eternal Torment or Annihilation?",
    "Should Christians Use AI to Write Sermons?",
    "Can Evangelicals Still Agree on Inerrancy?",
])
def test_issue_question_boosted(title):
    assert voice_adjustments(title)["BOOST_ISSUE_QUESTION"] == BOOST_ISSUE_QUESTION


def test_meta_question_not_boosted():
    assert "BOOST_ISSUE_QUESTION" not in voice_adjustments("What I'm Reading This Week")


def test_scores_stack():
    assert voice_score("AMAZING News!") == DEMOTE_ALL_CAPS + DEMOTE_EXCLAIM + DEMOTE_LENGTH


# ── Slice 2: display_title ───────────────────────────────────────────────────

@pytest.mark.parametrize("title,expected", [
    ("Pastor Resigns — and Why It Matters", "Pastor Resigns, and Why It Matters"),
    ("Pastor Resigns—and Why It Matters", "Pastor Resigns, and Why It Matters"),
    ("Romans 9–11 and the Hope of Israel", "Romans 9-11 and the Hope of Israel"),
    ("The 2025–2026 Ministry Year", "The 2025-2026 Ministry Year"),
    ("Grace Abounds – Even Here", "Grace Abounds, Even Here"),
    ("Grace Abounds \U0001F64F", "Grace Abounds"),
    ("SBC Votes to Expel Church | Baptist Press", "SBC Votes to Expel Church"),
    ("SBC Votes to Expel Church · Baptist Press", "SBC Votes to Expel Church"),
    ("The ERLC Urges Congress: Here's Why", "The ERLC Urges Congress"),
    ("The ERLC Urges Congress. Here’s How", "The ERLC Urges Congress"),
    ("New Abortion Law in Texas: What You Need to Know", "New Abortion Law in Texas"),
    ("A Study on Prayer and Fasting (Read More)", "A Study on Prayer and Fasting"),
    ("BREAKING: CHURCH SPLITS OVER DOCTRINE", "Breaking: Church Splits Over Doctrine"),
    ("SBC'S NEW PRESIDENT URGES UNITY IN THE CHURCH", "SBC's New President Urges Unity in the Church"),
])
def test_display_title_cleanup(title, expected):
    assert display_title(title) == expected


@pytest.mark.parametrize("title", [
    "Why I Left the PCA",
    "The iPhone and the Soul",
    "SBC and PCA Leaders Meet",
    "Romans 8 - A Study in Hope",
    "How to Read the Bible: Here's a Plan for 2027",
    "Here's Why",
])
def test_display_title_preserves_clean_titles(title):
    assert display_title(title) == title


def test_display_title_strips_source_tail_only_when_it_matches():
    t = "Ordinary Church Life Matters - Christianity Today"
    assert display_title(t, "Christianity Today") == "Ordinary Church Life Matters"
    assert display_title(t, "WORLD") == t


def test_service_tail_kept_when_too_little_would_remain():
    assert display_title("Pastor Resigns — Here's Why") == "Pastor Resigns, Here's Why"


def test_display_title_never_leaves_em_dash():
    for t in ["— Leading Dash Title Here", "Trailing Dash Title Here —", "A — B — C and D"]:
        assert "—" not in display_title(t) and "–" not in display_title(t)


def test_apply_display_title_sets_fields_only_when_changed():
    a = {"title": "Megachurch Pastor Resigns — Here's Why", "source_name": "WORLD"}
    assert apply_display_title(a) is True
    assert a["display_title"] == "Megachurch Pastor Resigns" == a["rewritten_title"]
    b = {"title": "Pastor Resigns After Report"}
    assert apply_display_title(b) is False
    assert "display_title" not in b and "rewritten_title" not in b


def test_apply_display_title_keeps_existing_rewrite():
    a = {"title": "Pastor Resigns — Here's Why", "rewritten_title": "Claude Rewrite"}
    apply_display_title(a)
    assert a["rewritten_title"] == "Claude Rewrite"


# ── Slice 2: display_byline ──────────────────────────────────────────────────

@pytest.mark.parametrize("author,source,expected", [
    ("Kevin DeYoung", "The Gospel Coalition", "Kevin DeYoung, The Gospel Coalition"),
    ("", "WORLD", "WORLD"),
    ("Russell Moore", None, "Russell Moore"),
    (None, None, ""),
    ("Desiring God", "Desiring God", "Desiring God"),
])
def test_display_byline(author, source, expected):
    assert display_byline(author, source) == expected


# ── strip_dashes (shared with the Pulse) ─────────────────────────────────────

def test_strip_dashes():
    out = strip_dashes("TGC says the threat is doctrinal — bad theology. Pages 3–5.")
    assert out == "TGC says the threat is doctrinal, bad theology. Pages 3-5."
