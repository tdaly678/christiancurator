"""The /topics/ hub page and its click tracking, the plain Topics nav link and
topic page breadcrumbs (S9, S9b)."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import add_breadcrumbs  # noqa: E402
import add_topics_nav  # noqa: E402
import build_topics_index  # noqa: E402
from frontend.topics_hub import (  # noqa: E402
    HUB_CATEGORIES,
    HUB_TOPICS,
    has_four_views,
    hub_category,
    hub_sections,
    live_slugs,
    search_terms,
    topic_count,
)

FORBIDDEN_BUCKETS = re.compile(r"\b(debates?|controvers\w*|other|misc\w*)\b", re.I)


def filter_matches(query: str, terms: str) -> bool:
    """Python twin of the hub page's JS filter: every query word must be the
    start of some term word."""
    words = terms.split()
    q = re.findall(r"[a-z0-9]+", query.lower().replace("'", ""))
    return all(any(w.startswith(t) for w in words) for t in q)


def matching_slugs(query: str) -> set[str]:
    return {s for s in live_slugs() if filter_matches(query, search_terms(s))}


# ── Category assignment ─────────────────────────────────────────────────────

def test_every_live_topic_in_exactly_one_category():
    live = set(live_slugs())
    assert live, "no live topic pages found"
    assert live == set(HUB_TOPICS), (
        f"missing: {sorted(live - set(HUB_TOPICS))}, extra: {sorted(set(HUB_TOPICS) - live)}")
    sections = hub_sections()
    placed = [t["slug"] for s in sections for t in s["topics"]]
    assert sorted(placed) == sorted(live)
    assert len(placed) == len(set(placed))


def test_six_named_categories_no_catch_all_bucket():
    assert [c for c, _ in HUB_CATEGORIES] == [
        "scripture-and-interpretation", "doctrine", "church-and-practice",
        "christian-living", "culture-and-ethics", "faith-and-doubt"]
    for cat_id, name in HUB_CATEGORIES:
        assert not FORBIDDEN_BUCKETS.search(name)
    for s in hub_sections():
        assert s["topics"], f"empty category {s['id']}"


def test_contested_topics_sit_under_their_subject():
    assert hub_category("baptism")[0] == "doctrine"
    assert hub_category("eschatology")[0] == "doctrine"
    assert hub_category("complementarianism-egalitarianism")[0] == "church-and-practice"
    for slug in ("apologetics", "faith-deconstruction", "progressive-christianity"):
        assert hub_category(slug)[0] == "faith-and-doubt"


def test_lines_are_6_to_10_words_without_dashes():
    for slug, (_cat, line) in HUB_TOPICS.items():
        n = len(line.split())
        assert 6 <= n <= 10, f"{slug}: {n} words"
        assert "—" not in line and "–" not in line and " - " not in line, slug
        assert "#" not in line


# ── Filter synonyms ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("query,slug", [
    ("rapture", "eschatology"),
    ("millennium", "eschatology"),
    ("deconversion", "faith-deconstruction"),
    ("deconstruct", "faith-deconstruction"),
    ("communion", "lords-supper"),
    ("tongues", "holy-spirit-spiritual-gifts"),
    ("calvinism", "predestination-free-will"),
    ("women pastors", "complementarianism-egalitarianism"),
    ("chatgpt", "artificial-intelligence"),
    ("lord's supper", "lords-supper"),
    ("rapt", "eschatology"),
])
def test_synonyms_find_the_topic(query, slug):
    assert slug in matching_slugs(query)


def test_filter_narrows():
    assert len(matching_slugs("rapture")) < 5
    assert matching_slugs("zzzz") == set()
    assert len(matching_slugs("")) == topic_count()


# ── Four views ──────────────────────────────────────────────────────────────

def test_four_views_tag_follows_the_page():
    assert has_four_views("eschatology")
    assert not has_four_views("baptism")
    tagged = {t["slug"] for s in hub_sections() for t in s["topics"] if t["four_views"]}
    assert "eschatology" in tagged


# ── Hub page ────────────────────────────────────────────────────────────────

def _page() -> str:
    return build_topics_index.render_page(hub_sections())


def test_hub_page_head_and_schema():
    page = _page()
    assert "<title>Topics | Christian Curator</title>" in page
    desc = re.search(r'<meta name="description" content="([^"]+)"', page).group(1)
    assert 50 <= len(desc) <= 160
    assert '<link rel="canonical" href="https://www.christiancurator.com/topics/" />' in page
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    data = json.loads(blocks[0])
    graph = {g["@type"]: g for g in data["@graph"]}
    lst = graph["CollectionPage"]["mainEntity"]
    assert lst["@type"] == "ItemList"
    assert lst["numberOfItems"] == topic_count() == len(lst["itemListElement"])
    urls = {i["url"] for i in lst["itemListElement"]}
    assert urls == {f"https://www.christiancurator.com/topics/{s}/" for s in live_slugs()}
    assert [i["name"] for i in graph["BreadcrumbList"]["itemListElement"]] == ["Home", "Topics"]


def test_hub_page_plain_links_jump_row_and_no_js_fallback():
    page = _page()
    main = page.split("<main", 1)[1].split("</main>", 1)[0]
    for slug in live_slugs():
        cat_id, _ = hub_category(slug)
        # A plain, crawlable href: no redirect wrapper, no query string.
        assert (f'<a href="/topics/{slug}/" data-pos="topics-hub" data-topic="{slug}" '
                f'data-category="{cat_id}">') in main, slug
    for cat_id, _name in HUB_CATEGORIES:
        assert f'<a href="#{cat_id}">' in main
        assert f'id="{cat_id}"' in main
    # The filter box only appears when the script un-hides it.
    assert re.search(r'<div class="cc-hub-filter" id="cc-hub-filter" hidden>', page)
    # No image cards.
    assert "<img" not in main
    assert "four views" in main.lower()


def test_hub_page_copy_rules():
    page = _page()
    intro = re.search(r'<p class="cc-hub-intro">(.*?)</p>', page).group(1)
    assert "—" not in page and "–" not in page
    assert "#" not in intro
    assert not re.search(r"\d", intro), "intro must not give counts"
    assert not re.search(r"\bfeeds?\b|\bsources\b", intro, re.I)


def test_committed_hub_page_is_current():
    committed = (REPO / "docs" / "topics" / "index.html").read_text(encoding="utf-8")
    year = re.compile(r"&copy; \d{4}")
    assert year.sub("", committed) == year.sub("", _page()), (
        "docs/topics/index.html is stale: run python scripts/build_topics_index.py")


def test_hub_click_tracking():
    page = _page()
    main = page.split("<main", 1)[1].split("</main>", 1)[0]
    assert main.count('data-pos="topics-hub"') == topic_count()
    # Every tracked link goes straight to its topic page.
    for href in re.findall(r'<a href="([^"]*)" data-pos="topics-hub"', main):
        assert re.fullmatch(r"/topics/[a-z0-9-]+/", href), href
    script = page.rsplit("<script>", 1)[1]
    assert 'gtag("event", "article_click"' in script
    for param in ("position:", "topic:", "topic_category:", "hub_filter:", "link_url: a.href",
                  'transport_type: "beacon"'):
        assert param in script, param
    assert "preventDefault" not in script and "location.href" not in script
    # Tracking does not depend on the filter box.
    assert script.count("(function ()") == 2


# ── Nav: plain Topics link ──────────────────────────────────────────────────

def test_nav_block_is_a_plain_topics_link():
    block = add_topics_nav.build_topics_html()
    inner = [ln.strip() for ln in block.strip().splitlines()[1:-1]]
    assert inner == ['<a class="cc-nav-topics" href="/topics/">Topics</a>']
    assert "<button" not in block and "dropdown-menu" not in block and "hidden" not in block
    assert "@media" not in add_topics_nav.TOPICS_CSS


def test_no_page_keeps_the_topics_dropdown():
    stale = []
    for path in sorted((REPO / "docs").rglob("*.html")):
        html = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"<button[^>]*>\s*Topics\s*</button>", html) or "cc-nav-dropdown-topics" in html:
            stale.append(str(path.relative_to(REPO)))
    assert not stale, f"run python scripts/add_topics_nav.py: {stale[:5]}"


def test_hub_marks_topics_current():
    nav = re.search(r'<nav class="cc-nav">.*?</nav>', _page(), re.S).group(0)
    assert '<a class="cc-nav-topics" href="/topics/" aria-current="page">Topics</a>' in nav
    assert 'class="active"' not in nav


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


@pytest.mark.parametrize("name", [
    "template.html", "digest_template.html", "archive_template.html", "daily_template.html"])
def test_templates_carry_the_current_nav(name):
    src = (REPO / "frontend" / name).read_text(encoding="utf-8")
    m = add_topics_nav.HTML_BLOCK_RE.search(src)
    assert m, f"{name} has no Topics nav markers"
    assert _norm(m.group(0)) == _norm(add_topics_nav.build_topics_html()), (
        f"{name} nav is stale: run python scripts/add_topics_nav.py")
    assert _norm(add_topics_nav.TOPICS_CSS) in _norm(src)


def test_archive_index_python_nav_is_current():
    src = (REPO / "frontend" / "__init__.py").read_text(encoding="utf-8")
    assert '<a class="cc-nav-topics" href="/topics/">Topics</a>' in src
    assert "cc-nav-dropdown-topics" not in src and "cc-nav-submenu" not in src


def test_nav_rewrite_is_idempotent(tmp_path):
    src = (REPO / "frontend" / "archive_template.html").read_text(encoding="utf-8")
    once, _, _ = add_topics_nav._patch_html(src)
    twice, h, c = add_topics_nav._patch_html(once)
    assert once == twice and not h and not c


# ── Breadcrumbs ─────────────────────────────────────────────────────────────

def test_breadcrumb_rewrite_on_a_copy(tmp_path):
    src = REPO / "docs" / "topics" / "baptism" / "index.html"
    page = tmp_path / "baptism" / "index.html"
    page.parent.mkdir()
    shutil.copy(src, page)
    html = page.read_text(encoding="utf-8")
    # Rewind to the old two-level trail.
    old = add_breadcrumbs.BREADCRUMB_NAV_RE.sub(
        '<nav aria-label="Breadcrumb" class="cc-breadcrumb"><a href="/">Home</a>'
        '<span class="cc-breadcrumb-sep">›</span><a href="/#topics">Topics</a>'
        '<span class="cc-breadcrumb-sep">›</span><span aria-current="page">Baptism</span></nav>',
        html)
    page.write_text(old, encoding="utf-8")
    assert "updated" in add_breadcrumbs.process_topic_page(page)
    new = page.read_text(encoding="utf-8")
    assert '<a href="/topics/">Topics</a>' in new
    assert '<a href="/topics/#doctrine">Doctrine</a>' in new
    assert new.count('class="cc-breadcrumb"') == 1
    assert "no change" in add_breadcrumbs.process_topic_page(page)


def test_every_topic_page_has_category_breadcrumb():
    for slug in live_slugs():
        html = (REPO / "docs" / "topics" / slug / "index.html").read_text(encoding="utf-8")
        cat_id, cat_name = hub_category(slug)
        navs = add_breadcrumbs.BREADCRUMB_NAV_RE.findall(html)
        assert len(navs) == 1, slug
        assert '<a href="/topics/">Topics</a>' in navs[0], slug
        assert f'<a href="/topics/#{cat_id}">' in navs[0], slug
        ld = add_breadcrumbs.BREADCRUMB_JSONLD_RE.findall(html)
        assert len(ld) == 1, slug
        data = json.loads(re.sub(r"^<script[^>]*>|</script>$", "", ld[0]))
        names = [i["name"] for i in data["itemListElement"]]
        assert names[:3] == ["Home", "Topics", cat_name], slug
        assert data["itemListElement"][2]["item"].endswith(f"/topics/#{cat_id}")
