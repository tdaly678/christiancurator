from curator.clusters import build_story_clusters
from curator.dedup import dedupe_articles
from frontend.layout import build_homepage_layout, outbound_urls


def _a(url, src, cluster="", score=5.0, **kw):
    return {"url": url, "source_name": src, "title": f"Title {url}", "topic_cluster": cluster,
            "final_score": score, **kw}


def test_three_outlets_collapse_to_one_story():
    ranked = [_a("u1", "CT", "sbc_vote"), _a("u2", "World", "sbc_vote"),
              _a("u3", "RNS", "sbc_vote"), _a("u4", "TGC", "other_story")]
    sibs, gone = build_story_clusters(ranked)
    assert [s["source_name"] for s in sibs["u1"]] == ["World", "RNS"]
    assert gone == {"u2", "u3"}


def test_two_outlets_stay_separate():
    ranked = [_a("u1", "CT", "sbc_vote"), _a("u2", "World", "sbc_vote")]
    assert build_story_clusters(ranked) == ({}, set())


def test_unique_cluster_never_groups():
    ranked = [_a(f"u{i}", f"S{i}", "unique") for i in range(4)]
    assert build_story_clusters(ranked) == ({}, set())


def test_same_source_counts_once_and_is_suppressed():
    ranked = [_a("u1", "CT", "x"), _a("u2", "CT", "x"), _a("u3", "World", "x"), _a("u4", "RNS", "x")]
    sibs, gone = build_story_clusters(ranked)
    assert [s["source_name"] for s in sibs["u1"]] == ["World", "RNS"]
    assert gone == {"u2", "u3", "u4"}


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
    ranked = [_a(f"u{i}", f"S{i}", "big") for i in range(8)]
    sibs, gone = build_story_clusters(ranked, max_siblings=4)
    assert len(sibs["u0"]) == 4
    assert len(gone) == 7


def test_layout_shows_story_once_with_siblings():
    arts = [_a("https://a.com/1", "CT", "sbc_vote", 9, tags=["news"]),
            _a("https://b.com/1", "World", "sbc_vote", 8, tags=["news"]),
            _a("https://c.com/1", "RNS", "sbc_vote", 7, tags=["news"])]
    arts += [_a(f"https://z.com/{i}", f"Src{i}", "", 5 - i * 0.1) for i in range(10)]
    layout = build_homepage_layout(arts)
    urls = outbound_urls(layout)
    assert layout["lead"]["url"] == "https://a.com/1"
    assert "https://b.com/1" not in urls and "https://c.com/1" not in urls
    assert [s["source_name"] for s in layout["siblings"]["https://a.com/1"]] == ["World", "RNS"]
