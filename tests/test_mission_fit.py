"""Mission fit and board routing (S1 2.2, 2.3, 3.6; Nov 22 2026).

- off_mission_kind(): lifestyle posts, horse-race politics and entertainment
  with no faith hook are capped at 3 (scorer backstop to the prompt rule).
- WORLD Sift and Christian Post news briefs face the faith-hook gate.
- Catholic-internal and off-mission items never lead and sit at the bottom of
  their board column.
- is_audio_video() catches /erlc-podcast/, /episode-844, /p/ep205 and
  "Ep." / "Join me as I talk with" openers.
- board_column() sends only news reports to News, not politics/data essays.

Run: .venv/bin/python -m pytest tests/test_mission_fit.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from curator import scorer  # noqa: E402
from curator.editorial import TIER_EXCLUDED, board_sort_key, lead_tier  # noqa: E402
from curator.mission import is_news_brief, is_off_mission  # noqa: E402
from frontend.layout import board_column, is_audio_video  # noqa: E402


# ── Off-mission backstop ────────────────────────────────────────────────────

@pytest.mark.parametrize("title,summary,kind", [
    ("Favorite Perfumes, Aritzia Dupes", "A few things I loved this month.", "lifestyle"),
    ("When Democrats Show Up for Men", "Party strategists court young male voters.", "horse_race"),
    ("After the Republican Rout", "What the GOP must learn from Tuesday.", "horse_race"),
    ("GTA 6 is pornographic and gory", "Christians should not buy this game.", "entertainment"),
])
def test_off_mission_kinds(title, summary, kind):
    assert scorer.off_mission_kind({"title": title, "summary": summary}) == kind


@pytest.mark.parametrize("title,summary", [
    ("Evangelical Voters Shift in the Midterms", "A look at white evangelical turnout."),
    ("Republicans Push Religious Liberty Bill", ""),
    ("When Democrats Show Up for Men", "Churches have been doing this for years."),
    ("Druski's Megachurch Comedy Has a Trailer", "A Netflix special mocks pastors."),
    ("C.J. Stroud: We're doing it for an audience of one, that's God", "The quarterback spoke."),
    ("Why Paper Books Endure", "Digital reading has not displaced print."),
])
def test_faith_angle_keeps_items_uncapped(title, summary):
    assert scorer.off_mission_kind({"title": title, "summary": summary}) is None


def test_prompt_caps_off_mission_items():
    prompt = " ".join(scorer.SCORING_PROMPT.split()) if hasattr(scorer, "SCORING_PROMPT") else ""
    text = prompt or " ".join(Path(scorer.__file__).read_text().split())
    for phrase in ("partisan horse-race politics", "celebrity, sports and entertainment",
                   "lifestyle newsletters", "Catholic-internal items"):
        assert phrase in text


def test_trads_counts_as_catholic():
    assert any(kw in "tk: trads" for kw in scorer.CATHOLIC_CLUSTER_KEYWORDS)


# ── News briefs ──────────────────────────────────────────────────────────────

SIFT = "https://wng.org/sift/iranian-agent-gets-over-27-year-sentence-for-trump-murder-plot-1795038850"


def test_world_sift_brief_without_hook_is_off_mission():
    a = {"url": SIFT, "source_name": "World Magazine", "source_type": "christian",
         "title": "Iranian agent gets more than 27-year sentence for Trump murder plot",
         "summary": "A federal judge sentenced the man on Thursday."}
    assert is_news_brief(a) and is_off_mission(a)


@pytest.mark.parametrize("title,summary", [
    ("Judge rules Iowa officials must allow satanic event in state Capitol", ""),
    ("OneHope founder Bob Hoskins, who championed child evangelism worldwide, dies at 90", ""),
    ("Parent stopped shooter at Oregon class, police say", "The church community gathered to pray."),
])
def test_briefs_with_a_hook_stay(title, summary):
    a = {"url": "https://www.christianpost.com/news/x.html", "source_type": "christian",
         "title": title, "summary": summary}
    assert is_news_brief(a) and not is_off_mission(a)


def test_essays_from_the_same_outlets_are_not_gated():
    for url in ("https://wng.org/articles/some-essay-1", "https://www.christianpost.com/voices/x.html",
                "https://wng.org/opinions/after-the-rout-2"):
        a = {"url": url, "source_type": "christian", "title": "After the Republican Rout"}
        assert not is_news_brief(a) and not is_off_mission(a)


# ── Lead and board placement ────────────────────────────────────────────────

def _a(title, score, **kw):
    return {"title": title, "url": f"https://x.example/{abs(hash(title))}", "final_score": score,
            "tags": ["theology"], **kw}


def test_catholic_and_off_mission_never_lead():
    for flag in ({"catholic_internal": True}, {"off_mission_capped": "lifestyle"}):
        assert lead_tier(_a("TK: Trads", 9, **flag), {}, set()) == TIER_EXCLUDED


def test_catholic_and_off_mission_sink_in_board():
    pool = [_a("A Strong Essay", 5), _a("TK: Trads", 9, catholic_internal=True),
            _a("Another Essay", 4), _a("Favorite Perfumes", 8, off_mission_capped="lifestyle")]
    order = [a["title"] for a in sorted(pool, key=lambda a: board_sort_key(a, pool))]
    assert order[:2] == ["A Strong Essay", "Another Essay"]


# ── Audio and video ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("article", [
    {"url": "https://erlc.com/erlc-podcast/a-biblical-response-to-physician-assisted-suicide/"},
    {"url": "https://careynieuwhof.com/episode-844/"},
    {"url": "https://theartofsimple.substack.com/p/ep205"},
    {"url": "https://example.org/shows/great-talk-episode-12"},
    {"url": "https://example.org/post", "summary": "Ep. 205: rest, rhythm and a slower Advent."},
    {"url": "https://example.org/post", "summary": "<p>Join me as I talk with Karen Swallow Prior.</p>"},
    {"url": "https://example.org/post", "summary": "In this episode, we discuss grief."},
    {"url": "https://example.org/post", "title": "Episode 12: Grief"},
    {"url": "https://www.youtube.com/watch?v=x"},
    {"url": "https://example.org/podcast/x"},
])
def test_audio_video_detected(article):
    assert is_audio_video(article)


@pytest.mark.parametrize("article", [
    {"url": "https://example.org/why-podcasts-matter-for-churches"},
    {"url": "https://example.org/2026/11/episodes-of-grace", "title": "Episodes of Grace"},
    {"url": "https://example.org/p/epiphany-reflections"},
    {"url": "https://example.org/post", "summary": "Join me in praying for Burundi this week."},
    {"url": "https://example.org/post", "summary": "Episcopal leaders met on Tuesday."},
])
def test_articles_not_mistaken_for_audio(article):
    assert not is_audio_video(article)


# ── Board columns ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("article,column", [
    # News reports.
    ({"perspective": "news", "tags": ["politics"]}, "news"),
    ({"source_type": "world_news", "tags": []}, "news"),
    ({"tags": ["news", "church life"]}, "news"),
    ({"source_category": "news", "perspective": "neutral", "url": "https://wng.org/sift/x-1"}, "news"),
    # Essays tagged politics or data are commentary, not news.
    ({"perspective": "supportive", "tags": ["politics"]}, "commentary"),
    ({"perspective": "neutral", "tags": ["data", "culture"]}, "commentary"),
    ({"source_category": "news", "perspective": "critical", "tags": ["politics"]}, "commentary"),
    ({"source_category": "news", "perspective": "neutral", "tags": [],
      "url": "https://www.christianpost.com/voices/x.html"}, "commentary"),
    # Podcasts never go to News.
    ({"perspective": "news", "tags": ["news", "theology"],
      "url": "https://erlc.com/erlc-podcast/x/"}, "church"),
    ({"perspective": "news", "tags": ["politics"], "url": "https://careynieuwhof.com/episode-844/"},
     "commentary"),
    ({"tags": ["theology", "politics"], "perspective": "neutral"}, "church"),
])
def test_board_column_routing(article, column):
    assert board_column(article) == column
