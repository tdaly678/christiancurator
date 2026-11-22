"""Story clustering (curator/clusters.py): one story, one slot.

Since Nov 22 2026 clusters follow story identity (shared distinctive names and
numbers), not the scorer's theme-level topic_cluster.
"""
from curator.clusters import build_story_clusters, same_story, story_groups
from curator.dedup import dedupe_articles
from frontend.layout import build_homepage_layout, outbound_urls

# Lower-case vocabulary a real pool carries in its snippets; tests that build
# tiny pools add it so Title Case headline words are not taken for names.
FILLER = ("the writer argues that parents should teach children about faith and fear "
          "in the church today, with projections and research from scholars and leaders "
          "on the right and the left, and what pastors say about silence and wisdom")


def _a(url, src, cluster="", score=5.0, title=None, summary="", **kw):
    return {"url": url, "source_name": src, "title": title or f"Title {url}",
            "topic_cluster": cluster, "final_score": score, "summary": summary, **kw}


def _filler(n=1):
    return [_a(f"https://filler.example/{i}", f"Filler{i}", title="A quiet note", score=0.1,
               summary=FILLER) for i in range(n)]


SBC = "Southern Baptists Vote on Law Amendment in Dallas"


def test_three_outlets_collapse_to_one_story():
    ranked = [_a("u1", "CT", "sbc_vote", title=SBC),
              _a("u2", "World", "sbc_vote", title="SBC Messengers Weigh Law Amendment in Dallas"),
              _a("u3", "RNS", "sbc_vote", title="Law Amendment Fails Again at Dallas Meeting"),
              _a("u4", "TGC", "other_story", title="Why Advent Waiting Matters")]
    sibs, gone = build_story_clusters(ranked)
    assert [s["source_name"] for s in sibs["u1"]] == ["World", "RNS"]
    assert gone == {"u2", "u3"}


def test_two_outlets_stay_separate():
    ranked = [_a("u1", "CT", "sbc_vote", title=SBC),
              _a("u2", "World", "sbc_vote", title="SBC Messengers Weigh Law Amendment in Dallas")]
    assert build_story_clusters(ranked) == ({}, set())


def test_shared_topic_cluster_alone_never_groups():
    # Theme, not story: the scorer gave all three the same cluster string.
    ranked = [_a(f"u{i}", f"S{i}", "christian_nationalism_debate", title=t)
              for i, t in enumerate(["Why Advent Waiting Matters", "Lessons From Exile",
                                     "Hope in a Hard Season", "Saints and Sinners Alike"])]
    assert build_story_clusters(ranked) == ({}, set())


def test_same_source_counts_once_and_is_suppressed():
    ranked = [_a("u1", "CT", title=SBC), _a("u2", "CT", title="Law Amendment Returns in Dallas"),
              _a("u3", "World", title="Dallas Messengers Debate the Law Amendment"),
              _a("u4", "RNS", title="Law Amendment Vote Splits Dallas Messengers")]
    sibs, gone = build_story_clusters(ranked)
    assert [s["source_name"] for s in sibs["u1"]] == ["World", "RNS"]
    assert gone == {"u2", "u3", "u4"}


def test_three_copies_from_two_outlets_collapse():
    # Nov 21 2026: Pew's own two releases plus CT's write-up of the 2070 projection.
    ranked = [
        _a("https://pew.org/a", "Pew Research", title="Muslims Projected to Become World's Largest Religious Group by 2070",
           original_title="The Future of World Religions: Population Growth Projections, 2020-2070"),
        _a("https://pew.org/b", "Pew Research", title="Muslim Population Growth Outpaces Religious Switching",
           summary="Muslims will grow fastest through 2070, the projections show."),
        _a("https://ct.com/pew", "Christianity Today", title="Pew Projects Christians as North American Minority by 2070"),
    ] + _filler()
    sibs, gone = build_story_clusters(ranked)
    assert [s["source_name"] for s in sibs["https://pew.org/a"]] == ["Christianity Today"]
    assert gone == {"https://pew.org/b", "https://ct.com/pew"}


def test_dedup_also_links_count_as_outlets():
    arts = dedupe_articles([
        _a("https://ct.com/a", "Christianity Today"),
        {**_a("https://ct.com/a?utm_source=x", "World"), "title": "Other"},
        {**_a("https://ct.com/a/", "Religion News Service"), "title": "Third"},
    ])
    assert len(arts) == 1
    sibs, gone = build_story_clusters(arts)
    assert {s["source_name"] for s in sibs[arts[0]["url"]]} == {"World", "Religion News Service"}
    assert gone == set()


def test_max_siblings_cap():
    ranked = [_a(f"u{i}", f"S{i}", title=f"Dannenfelser Rejects Ballot Measure Results, Part {i}")
              for i in range(8)]
    sibs, gone = build_story_clusters(ranked, max_siblings=4)
    assert len(sibs["u0"]) == 4
    assert len(gone) == 7


def test_layout_shows_story_once_with_siblings():
    arts = [_a("https://a.com/1", "CT", "sbc_vote", 9, title=SBC, tags=["church life"]),
            _a("https://b.com/1", "World", "sbc_vote", 8, tags=["church life"],
               title="SBC Messengers Weigh Law Amendment in Dallas"),
            _a("https://c.com/1", "RNS", "sbc_vote", 7, tags=["church life"],
               title="Law Amendment Fails Again at Dallas Meeting")]
    arts += [_a(f"https://z.com/{i}", f"Src{i}", "", 5 - i * 0.1) for i in range(10)]
    layout = build_homepage_layout(arts)
    urls = outbound_urls(layout)
    assert layout["lead"]["url"] == "https://a.com/1"
    assert "https://b.com/1" not in urls and "https://c.com/1" not in urls
    assert [s["source_name"] for s in layout["siblings"]["https://a.com/1"]] == ["World", "RNS"]


# ── S1 review cases (Nov 20 2026 homepage) ──────────────────────────────────

PEW_NOV20 = [
    _a("https://religionnews.com/pew-islam", "Religion News Service", "christian_decline_global_projections", 8,
       title="Pew Research Moves Up Timeline for Islam Surpassing Christianity",
       original_title="How Pew's projections for Christianity and Islam worldwide changed, and why"),
    _a("https://christianpost.com/muslims-2035", "The Christian Post", "global_christian_demographics", 7.5,
       title="Muslims Projected to Outnumber Christians Globally by 2035",
       original_title="Muslims to outnumber Christians globally by 2035 amid demographic shifts: Pew"),
    _a("https://pewresearch.org/explorer", "Pew Research", "pew_religious_projections", 7,
       title="Religious Groups Will Shift Significantly in Size by 2070",
       original_title="Data Explorer: The Future of World Religions"),
    _a("https://pewresearch.org/islam-largest", "Pew Research", "global_religion_demographics", 7,
       title="Muslims Will Outnumber Christians by 2035, Projections Show",
       original_title="Islam Will Soon Be the World's Largest Religion, but Christianity Will Keep Growing Too"),
    _a("https://christianitytoday.com/pew-2070", "Christianity Today", "christianity_decline_global_shift", 6.5,
       title="Pew Projects Christians Will Become North American Minority by 2070",
       original_title="Pew: Christians Will Be Minority in North America by 2070, Will Double in Africa"),
]

THEME_NOV20 = [
    _a("https://firstthings.com/the-godless-new-christian-right/", "First Things", "christian_nationalism_debate", 6.5,
       title="Christian Right's Secular Wing Gains Influence After Election Losses",
       original_title="The Godless New Christian Right",
       summary="A new right is forming that wants the culture of Christianity without the faith."),
    _a("https://careynieuwhof.com/episode-843/", "Carey Nieuwhof", "christian_nationalism_debate", 5,
       title="Mark Batterson: Pastors Silence Themselves Out of Fear, Not Wisdom",
       summary="Mark Batterson talks about fear, courage and why leaders go quiet on hard topics."),
    _a("https://stephenmcalpine.substack.com/p/progressive-christian-nationalism", "Stephen McAlpine",
       "christian_nationalism_debate", 5, title="Progressive Christian Nationalism.",
       summary="The left has its own version of the thing it fears most in the right."),
]


def test_pew_projection_copies_collapse_to_one_slot():
    sibs, gone = build_story_clusters(PEW_NOV20 + _filler())
    rep = "https://religionnews.com/pew-islam"
    assert rep in sibs
    assert {s["source_name"] for s in sibs[rep]} == {"The Christian Post", "Pew Research", "Christianity Today"}
    assert gone == {a["url"] for a in PEW_NOV20[1:]}


def test_theme_cluster_does_not_collapse():
    # First Things / Nieuwhof / McAlpine shared "christian_nationalism_debate"
    # and wrongly carried "also:" links on Nov 20.
    sibs, gone = build_story_clusters(THEME_NOV20 + _filler())
    assert sibs == {} and gone == set()
    assert all(len(g) == 1 for g in story_groups(THEME_NOV20 + _filler()))


def test_both_cases_in_one_pool():
    pool = sorted(PEW_NOV20 + THEME_NOV20 + _filler(), key=lambda a: -a["final_score"])
    sibs, gone = build_story_clusters(pool)
    assert list(sibs) == ["https://religionnews.com/pew-islam"]
    assert not gone & {a["url"] for a in THEME_NOV20}


def test_same_story_needs_more_than_one_shared_name():
    a = _a("u1", "First Things", title="Trump Says He Cannot Forgive His Enemies")
    b = _a("u2", "World", title="Supreme Court Takes Case on Trump Refugee Policy")
    assert not same_story(a, b)


def test_story_id_decides_when_both_have_one():
    a = _a("u1", "CT", title="One", story_id="pew-2070")
    b = _a("u2", "RNS", title="Two", story_id="pew-2070")
    c = _a("u3", "WORLD", title=SBC, story_id="other")
    assert same_story(a, b)
    assert not same_story(_a("u4", "X", title=SBC, story_id="x"), c)
