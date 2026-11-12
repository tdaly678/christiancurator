"""Ideas over scandal in the lead block (Tom, 2026-11-12).

Tom: thinking, philosophy, theology and praxis first; news second; scandal
last unless it is truly the dominant story. The Pulse "looks pretty good", so
the Lead and subleads follow the stories it draws on. These tests lock the
content kinds, the dominant-story bar, the Pulse anchoring and the slot rules
in curator/editorial.py and frontend/layout.py.

Run: .venv/bin/python -m pytest tests/test_ideas_over_scandal.py
"""
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from curator import editorial as ed  # noqa: E402
from curator.dedup import canonical_url  # noqa: E402
from curator.headline_voice import SCANDAL_RE  # noqa: E402
from frontend.layout import BOARD_COLUMNS, build_homepage_layout  # noqa: E402


def _a(title, source, score=7.0, tags=("theology",), depth=None, cluster="unique", **kw):
    slug = "".join(c for c in title.lower() if c.isalnum())[:40]
    return {"title": title, "source_name": source, "url": f"https://{source.lower().replace(' ', '')}.example/{slug}",
            "final_score": score, "depth": score if depth is None else depth,
            "tags": list(tags), "topic_cluster": cluster, **kw}


ESSAYS = [
    _a("Pastors Must Put Christ Before Party", "ERLC", 7.5, ("politics", "church life")),
    _a("Discipleship Aims at Christ, Not the Tribe", "Desiring God", 5.75, ("theology", "church life")),
    _a("Faith Does Not Erase Trauma, Moore Writes", "Christianity Today", 8.0, ("theology", "devotional"),
       author="Russell Moore"),
    _a("Scholars Debate Who Wrote 2 Peter", "Michael Bird", 8.0),
    _a("Why Families Should Sit Together in Worship", "Stephen McAlpine", 7.0, ("church life",)),
]
NEWS = [
    _a("Pastor Arrested in Beijing on Fraud Charges", "Religion News Service", 9.5, ("news",)),
    _a("Religious Right Fractures After Midterm Losses", "World Magazine", 7.75, ("news", "politics")),
    _a("Apologist Admits to Plagiarism in Seminary Paper", "The Roys Report", 7.5, ("news", "apologetics")),
]


def _lead_block(layout):
    return [layout["lead"], *layout["subleads"]]


# ── Content kinds ────────────────────────────────────────────────────────────

def test_content_kinds():
    assert ed.content_kind(ESSAYS[0]) == "ideas"
    assert ed.content_kind(NEWS[1]) == "news"
    assert ed.content_kind(NEWS[0]) == "scandal"
    assert ed.content_kind(NEWS[2]) == "scandal"
    assert ed.content_kind(_a("Texas Shifts Democratic", "CT", 5, ("politics", "culture"))) == "commentary"
    assert ed.content_kind(_a("Untagged Discovery Item", "Blog", 5, ())) == "commentary"


def test_plagiarism_is_a_scandal_word():
    assert SCANDAL_RE.search("Wesley Huff Admits to Plagiarism")
    assert SCANDAL_RE.search("Seminary paper was plagiarized, critic says")


def test_crisis_alone_marks_scandal_only_on_news():
    essay = _a("Contemporary Culture Faces a Crisis of Meaning", "Crossway", 6.5, ("theology", "culture"))
    report = _a("Denomination Faces Budget Crisis", "Baptist Press", 6.5, ("news",))
    assert ed.content_kind(essay) == "ideas"
    assert ed.content_kind(report) == "scandal"
    assert ed.content_kind(_a("Ministry Leader Faces Abuse Allegations", "Blog", 6, ("church life",))) == "scandal"


# ── Dominant story bar ───────────────────────────────────────────────────────

def _story(n_outlets, score=9.0, title="Southern Baptists Vote to Expel Churches", tags=("news",)):
    srcs = ["Baptist Press", "World Magazine", "Religion News Service", "Christianity Today", "The Christian Post"]
    return [_a(title + f" ({i})", srcs[i], score - i * 0.1, tags, cluster="sbc_vote") for i in range(n_outlets)]


def test_dominant_needs_four_outlets_and_high_score():
    four = _story(4)
    assert ed.is_dominant_story(four[0], four)
    three = _story(3)
    assert not ed.is_dominant_story(three[0], three)
    low = _story(4, score=8.0)
    assert not ed.is_dominant_story(low[0], low)


def test_dedup_copies_count_as_outlets():
    a = _a("SBC Messengers Vote on Women Pastors", "Baptist Press", 9.0, ("news",),
           also_from=["World Magazine", "Religion News Service", "Christianity Today"])
    assert ed.is_dominant_story(a, [a])


# ── Lead block ───────────────────────────────────────────────────────────────

def test_ideas_outrank_higher_scored_news_in_lead_block():
    block = _lead_block(build_homepage_layout(ESSAYS + NEWS))
    assert all(ed.content_kind(a) == "ideas" for a in block)
    assert block[0]["source_name"] in ("Christianity Today", "Michael Bird")


def test_scandal_never_in_lead_block_even_as_filler():
    pool = [ESSAYS[0], NEWS[0], NEWS[2]]
    block = [a for a in _lead_block(build_homepage_layout(pool)) if a]
    assert [a["title"] for a in block] == [ESSAYS[0]["title"]]


def test_news_fills_only_when_ideas_run_out():
    block = _lead_block(build_homepage_layout(ESSAYS[:2] + NEWS))
    kinds = [ed.content_kind(a) for a in block if a]
    assert kinds[:2] == ["ideas", "ideas"]
    assert "news" in kinds and "scandal" not in kinds


def test_ideas_below_floor_do_not_lead():
    weak = _a("A Short Note on Psalm 23", "Blog", ed.LEAD_MIN_SCORE - 1)
    layout = build_homepage_layout([weak, NEWS[1]])
    assert layout["lead"]["title"] == NEWS[1]["title"]


def test_dominant_scandal_takes_first_sublead_not_lead():
    story = _story(4, title="Megachurch Founder Indicted for Fraud")
    layout = build_homepage_layout(ESSAYS + story)
    assert ed.content_kind(layout["lead"]) == "ideas"
    assert layout["subleads"][0]["title"] == story[0]["title"]
    assert sum(ed.content_kind(a) == "scandal" for a in _lead_block(layout)) == 1


def test_dominant_story_leads_when_nothing_else_qualifies():
    story = _story(4)
    layout = build_homepage_layout(story + [_a("Thin Note", "Blog", 2.0)])
    assert layout["lead"]["title"] == story[0]["title"]


# ── Pulse anchoring ──────────────────────────────────────────────────────────

PULSE = {
    "paragraphs_html": [
        "Evangelical writers are asking what holds Christian identity together. "
        "The ERLC tells pastors that loyalty to Christ comes before party. "
        "Desiring God frames the same pressure as discipleship.",
        "Russell Moore at Christianity Today pulls it somewhere personal. "
        '<a href="https://stephenmcalpine.example/whyfamiliesshouldsittogetherinworship">'
        "Stephen McAlpine</a> brings it to the pew.",
    ],
    "themes": ["christian identity", "discipleship and formation"],
}


def test_pulse_cited_articles_lead_in_mention_order():
    block = _lead_block(build_homepage_layout(ESSAYS + NEWS, daily_summary=PULSE))
    assert [a["source_name"] for a in block] == [
        "ERLC", "Desiring God", "Christianity Today", "Stephen McAlpine"]


def test_named_author_beats_same_named_outlet():
    moore_site = _a("Fukuyama on Bored Citizens", "Russell Moore", 7.0, ("culture", "politics"))
    cited = ed.pulse_cited_urls(PULSE, ESSAYS + [moore_site])
    assert canonical_url(ESSAYS[2]["url"]) in cited
    assert canonical_url(moore_site["url"]) not in cited


def test_outlet_named_inside_link_text_is_not_a_second_citation():
    other = _a("Another McAlpine Essay on Liturgy", "Stephen McAlpine", 9.0, ("church life",))
    cited = ed.pulse_cited_urls(PULSE, ESSAYS + [other])
    assert not any("anothermcalpine" in c for c in cited)
    assert any("whyfamilies" in c for c in cited)


def test_reported_source_urls_come_first_and_candidates_limit_names():
    summary = {**PULSE, "source_urls": [ESSAYS[3]["url"]],
               "candidate_urls": [ESSAYS[3]["url"], ESSAYS[0]["url"]]}
    cited = ed.pulse_cited_urls(summary, ESSAYS)
    assert "michaelbird" in cited[0]
    assert any("erlc" in c for c in cited)
    assert not any("desiringgod" in c for c in cited)


def test_scandal_is_not_promoted_by_a_pulse_mention():
    pulse = {"paragraphs_html": ["The Roys Report and the ERLC both wrote today."]}
    block = [a for a in _lead_block(build_homepage_layout([ESSAYS[0], NEWS[2]], daily_summary=pulse)) if a]
    assert [a["source_name"] for a in block] == ["ERLC"]


def test_fallback_pulse_anchors_nothing():
    assert ed.pulse_cited_urls({**PULSE, "fallback": True}, ESSAYS) == []
    assert ed.pulse_cited_urls(None, ESSAYS) == []


def test_pulse_theme_ideas_outrank_off_theme_ideas():
    on_theme = _a("Formation Happens in Ordinary Weeks", "Ligonier", 6.0)
    off_theme = _a("A New Reading of Leviticus", "Crossway", 8.0)
    layout = build_homepage_layout([off_theme, on_theme],
                                   daily_summary={"paragraphs_html": ["No outlets named."],
                                                  "themes": ["spiritual formation"]})
    assert layout["lead"]["title"] == on_theme["title"]


# ── Board order ──────────────────────────────────────────────────────────────

def test_board_puts_ideas_columns_before_news():
    assert [k for k, _ in BOARD_COLUMNS] == ["church", "commentary", "news"]


def test_non_dominant_scandal_sinks_to_bottom_of_news_column():
    news = [_a(f"Routine Report {i}", f"Wire{i}", 6.0 - i * 0.1, ("news",)) for i in range(3)]
    pool = ESSAYS + [NEWS[0]] + news
    col = next(c for c in build_homepage_layout(pool)["board"] if c["key"] == "news")
    assert col["articles"][-1]["title"] == NEWS[0]["title"]


def test_email_board_follows_page_order():
    from curator import email_sender as es
    layout = es._email_layout([], layout=build_homepage_layout(ESSAYS * 1 + NEWS + [
        _a(f"Essay {i}", f"Writer{i}", 6.0, ("church life",)) for i in range(4)]))
    keys = [c["key"] for c in layout["board"]]
    assert keys == ["church", "commentary", "news"]
    html = es._render_board(layout)
    assert html.index("Church &amp; Theology") < html.index(">News<")


def test_pulse_prompt_asks_for_its_sources():
    from curator import daily_summary as ds
    flat = " ".join(ds.SUMMARY_PROMPT.split())
    assert '"sources": [' in flat
    assert "in the order the paragraphs first mention it" in flat
