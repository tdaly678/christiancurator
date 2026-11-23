"""Title rewrites may not say more than the piece (S1 3.4, Nov 22 2026).

Cases from the Nov 21 2026 site review: rewrites that invented a white paper,
turned one editorial into "Christian groups", made a question a statement,
stated an opinion as fact, or rewrote a podcast or newsletter title.

Run: .venv/bin/python -m pytest tests/test_title_rewriter_facts.py
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from curator import title_rewriter as tr  # noqa: E402


def _art(title, summary, url="https://example.org/2026/11/piece", source="Example"):
    return {"title": title, "original_title": title, "summary": summary, "url": url,
            "source_name": source}


# ── Keep the publisher's title ──────────────────────────────────────────────

@pytest.mark.parametrize("article,reason", [
    (_art("A Biblical Response to Physician-Assisted Suicide",
          "Brent Leatherwood and guests discuss assisted suicide.",
          url="https://erlc.com/erlc-podcast/a-biblical-response-to-physician-assisted-suicide/"),
     "KEEP_PODCAST"),
    (_art("Leadership in a Season of Change", "Ep. 844 with a guest.",
          url="https://careynieuwhof.com/episode-844/"), "KEEP_PODCAST"),
    (_art("Making Home", "Join me as I talk with Sally Clarkson about rest.",
          url="https://example.substack.com/p/making-home"), "KEEP_PODCAST"),
    (_art("notes for the weekend: mere Christianity revisited",
          "Some notes on Lewis and other things."), "KEEP_ROUNDUP"),
    (_art("Favorite Perfumes and Other Things",
          "Welcome to the monthly(ish) newsletter, friends."), "KEEP_ROUNDUP"),
    (_art("November Newsletter From the Farm", "Updates from our family."), "KEEP_NEWSLETTER"),
])
def test_roundups_podcasts_and_newsletters_keep_publisher_title(article, reason):
    assert tr.keep_publisher_title(article) == reason


def test_kept_title_never_calls_claude(monkeypatch):
    def boom(**kw):
        raise AssertionError("Claude should not be called")
    monkeypatch.setattr(tr, "client", SimpleNamespace(messages=SimpleNamespace(create=boom)))
    a = tr.rewrite_title(_art("A Biblical Response to Physician-Assisted Suicide",
                              "A conversation on assisted suicide.",
                              url="https://erlc.com/erlc-podcast/a-biblical-response/"))
    assert a["rewritten_title"] == "A Biblical Response to Physician-Assisted Suicide"
    assert a["rewrite_skipped"] == "KEEP_PODCAST"


def test_ordinary_article_is_not_kept():
    assert tr.keep_publisher_title(_art("Why Paper Books Endure",
                                        "Digital reading has not displaced the printed page.")) is None


# ── Fact rejections ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("candidate,article,reason", [
    ("ERLC Argues Against Physician-Assisted Suicide in New White Paper",
     _art("A Biblical Response to Physician-Assisted Suicide",
          "The ERLC responds to physician-assisted suicide."),
     "REWRITE_INVENTED_NOUN"),
    ("Christian Groups Denounce Grand Theft Auto 6",
     _art("GTA 6 is pornographic and gory",
          "Grand Theft Auto 6 glorifies violence and lust, and Christians should not buy it."),
     "REWRITE_INVENTED_NOUN"),
    ("Readers Choose Paper Books Over Digital Alternatives",
     _art("Why paper books endure", "Digital reading has not displaced the printed page."),
     "REWRITE_CHANGES_MODALITY"),
    ("Christians Will Retain Memories in the Afterlife, Theologian Argues",
     _art("What will we remember in the afterlife?",
          "A theologian answers a question about memory in heaven."),
     "REWRITE_CHANGES_MODALITY"),
    ("Church Should Listen to Women on Speaking Truth to Power",
     _art("Speaking Truth to Power in the Church",
          "Women who spoke up describe what it cost them to speak truth to power."),
     "REWRITE_UNCREDITED_OPINION"),
    ("Pew Finds Muslim Growth Outpaces Switching to Unbelief",
     _art("The Future of World Religions",
          "Projections of religious populations through 2070, including Muslims."),
     "REWRITE_UNKNOWN_ENTITY"),
    ("Tim Keller Says Churches Must Rethink Membership",
     _art("Rethinking Church Membership", "Membership matters more than many churches think."),
     "REWRITE_UNKNOWN_ENTITY"),
])
def test_fact_rejections(candidate, article, reason):
    assert tr.fact_rejection(candidate, article) == reason


@pytest.mark.parametrize("candidate,article", [
    ("Why Paper Books Still Outlast Digital Reading",
     _art("Why paper books endure", "Digital reading has not displaced the printed page.")),
    ("What Will Believers Remember in the Afterlife?",
     _art("What will we remember in the afterlife?",
          "A theologian answers a question about memory in heaven.")),
    ("Pastors Should Guard Their Sabbath Rest, Writer Argues",
     _art("Pastor, Take Your Day Off", "Pastors who skip their sabbath burn out.")),
    ("Kevin Flatt Challenges the Secularization Thesis",
     _art("Kevin Flatt", "Albert Mohler talks with historian Kevin Flatt about secularization.")),
    ("SBC Messengers Vote to Expel Church Over Women Pastors",
     _art("Messengers vote on church with women pastors",
          "SBC messengers voted to expel a church that has women pastors.")),
    ("Lifeway Survey Finds Pastors Feel Lonely",
     _art("Pastors and loneliness", "A new Lifeway Research survey of pastors found many feel lonely.")),
])
def test_faithful_rewrites_pass(candidate, article):
    # In the daily run the vocabulary comes from every summary and feed text of
    # the day (rewrite_titles -> build_vocab); a small stand-in here.
    day = tr.build_vocab([{"summary": "these books outlast fads; guard your rest; "
                                      "a thesis that challenges the sabbath"}])
    assert tr.fact_rejection(candidate, article, day) is None


def test_common_vocabulary_from_todays_summaries_is_not_a_name():
    art = _art("Teach your children well", "Parents shape what children love.")
    # "Habits" is not in the article but is everyday vocabulary on the day.
    assert tr.fact_rejection("Parents Shape Children's Habits of Love", art) == "REWRITE_UNKNOWN_ENTITY"
    vocab = tr.build_vocab([{"summary": "small habits form us"}])
    assert tr.fact_rejection("Parents Shape Children's Habits of Love", art, vocab) is None


def test_rejected_rewrite_falls_back_to_publisher_title(monkeypatch):
    msg = SimpleNamespace(content=[SimpleNamespace(
        text="ERLC Argues Against Physician-Assisted Suicide in New White Paper")])
    monkeypatch.setattr(tr, "client", SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: msg)))
    a = tr.rewrite_title(_art("A Biblical Response to Physician-Assisted Suicide",
                              "The ERLC responds to physician-assisted suicide."))
    assert a["rewritten_title"] == "A Biblical Response to Physician-Assisted Suicide"
    assert a["rewrite_rejected"] == "REWRITE_INVENTED_NOUN"


def test_prompt_states_the_fact_rules():
    prompt = " ".join(tr.REWRITE_PROMPT.split())
    assert "stays a question" in prompt
    assert "credit it to the writer" in prompt
    assert '"white paper"' in prompt
    assert "Never add a person, church, outlet or organization" in prompt
    for dash in ("—", "–"):
        assert dash not in tr.REWRITE_PROMPT


# ── Quote handling (S8, Nov 23 2026) ────────────────────────────────────────
# Shown on Nov 17 and Nov 18 2026: 'The Elect Lady" in 2 John ...' and
# 'The Chosen" Season 6 Depicts ...'. str.strip('"') cut the opening quote of
# a headline that starts with a quoted phrase and left the closing one.

@pytest.mark.parametrize("reply,expected", [
    ('"The Chosen" Season 6 Depicts the Trial of Jesus',
     '"The Chosen" Season 6 Depicts the Trial of Jesus'),
    ('Critics Answer "Born This Way"', 'Critics Answer "Born This Way"'),
    ('"Pastors Weigh AI Sermon Tools"', 'Pastors Weigh AI Sermon Tools'),
    ('“Pastors Weigh AI Sermon Tools”', 'Pastors Weigh AI Sermon Tools'),
    ('  Pastors Weigh AI Sermon Tools  ', 'Pastors Weigh AI Sermon Tools'),
    ('"The Chosen" and "The Office" Share a Writer',
     '"The Chosen" and "The Office" Share a Writer'),
])
def test_unwrap_quotes_removes_only_a_wrapping_pair(reply, expected):
    assert tr._unwrap_quotes(reply) == expected


def test_accepted_rewrite_keeps_a_leading_quoted_phrase():
    article = _art("Tangled Up In Blue",
                   "The editors of First Things discuss the Erasmus Lecture.",
                   source="First Things")
    shown = tr.accept_rewrite(article, '"First Things" Editors Discuss the Erasmus Lecture')
    assert shown == '"First Things" Editors Discuss the Erasmus Lecture'
    assert "rewrite_rejected" not in article
