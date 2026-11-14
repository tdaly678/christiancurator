"""The flagship AI topic page (Nov 14 2026): matcher, retired slug, glossary, page shape."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_recent_articles as bra  # noqa: E402
import build_topic_reference as btr  # noqa: E402
import retire_topic_slug as rts  # noqa: E402
from frontend import topic_matcher as tm  # noqa: E402
from frontend import topic_redirects as tr  # noqa: E402

SLUG = "artificial-intelligence"
OLD = "ai-and-the-church"
PAGE = ROOT / "docs" / "topics" / SLUG / "index.html"
STUB = ROOT / "docs" / "topics" / OLD / "index.html"


# ---------------------------------------------------------------- matcher

def test_short_keywords_match_whole_words_only():
    assert tm.keyword_in("ai", "is ai the anti-christ?")
    assert tm.keyword_in("ai", "ai-generated sermons")
    assert tm.keyword_in("ai", "the church and ai's promise")
    assert not tm.keyword_in("ai", "pastor said faith matters")
    assert not tm.keyword_in("ai", "maintain the main thing")
    # longer keywords keep the substring match
    assert tm.keyword_in("deconstruct", "the deconstruction story")


def _topic(slug):
    return next(t for t in tm.TOPICS if t["slug"] == slug)


def test_ai_headlines_go_to_the_ai_page_not_technology():
    ai, tech = _topic(SLUG), _topic("technology")
    for title in ("Is AI the Anti-Christ?", "Does Artificial Intelligence Need to be Saved?",
                  "Pastors Turn to ChatGPT for Sermons", "The Chatbot Will See You Now"):
        text = tm._normalise(title)
        assert any(tm.keyword_in(k, text) for k in ai["keywords"]), title
        assert not any(tm.keyword_in(k, text) for k in tech["keywords"]), title
    faith = tm._normalise("Faith, Grace and the Daily Walk")
    assert not any(tm.keyword_in(k, faith) for k in ai["keywords"])


def test_match_topics_scores_ai():
    got = tm.match_topics([{"title": "Is AI the Anti-Christ?"}, {"title": "ChatGPT and the pulpit"}], None)
    assert got and got[0]["slug"] == SLUG


def test_recent_articles_match_uses_whole_words():
    history = [
        {"date_shown": "2026-11-13", "url": "https://x.example/a", "original_title": "Is AI the Anti-Christ?",
         "source_name": "X", "tags": []},
        {"date_shown": "2026-11-13", "url": "https://x.example/b", "original_title": "A Faith That Said Yes",
         "source_name": "X", "tags": []},
    ]
    items = bra.match_articles_to_topic(_topic(SLUG), history)
    assert [i["url"] for i in items] == ["https://x.example/a"]


# ---------------------------------------------------------------- retired slug

def test_redirect_record_and_helpers(tmp_path):
    rec = tr.load_topic_redirects()
    assert rec[OLD]["to"] == SLUG
    assert tr.redirect_target(OLD) == SLUG and tr.redirect_target(SLUG) == SLUG
    topics = tmp_path / "topics"
    for slug in (OLD, SLUG, "technology"):
        (topics / slug).mkdir(parents=True)
        (topics / slug / "index.html").write_text("x")
    (topics / "empty").mkdir()
    assert [p.name for p in tr.live_topic_dirs(topics)] == [SLUG, "technology"]


def test_stub_is_a_redirect():
    html = STUB.read_text(encoding="utf-8")
    assert 'http-equiv="refresh" content="0; url=/topics/artificial-intelligence/"' in html
    assert '<link rel="canonical" href="https://www.christiancurator.com/topics/artificial-intelligence/"' in html
    assert 'name="robots" content="noindex, follow"' in html
    assert html == tr.render_stub(OLD, SLUG, tr.load_topic_redirects()[OLD]["name"], "Artificial Intelligence")


def test_rewrite_links():
    src = ('<a href="/topics/ai-and-the-church/">Artificial Intelligence & the Church</a>\n'
           '<a class="x" href="/topics/ai-and-the-church/">Artificial Intelligence &amp; the Church</a>\n'
           '<a href="https://www.christiancurator.com/topics/ai-and-the-church/" class="cc-topic-index-link"\n'
           "   onclick=\"gtag('event','topic_click',{'topic':'ai-and-the-church','position':'index'});\">\n"
           "  Artificial Intelligence & the Church\n</a>\n"
           '<a href="/topics/ai-and-the-church/" class="cc-topic-card"><div>On AI</div></a>\n'
           '<p>Artificial Intelligence & the Church is mentioned in prose.</p>\n'
           '<a href="/topics/ai-and-the-church-two/">Other</a>')
    out = rts.rewrite_links(src, OLD, SLUG, "Artificial Intelligence & the Church", "Artificial Intelligence")
    assert "/topics/ai-and-the-church/" not in out
    assert "'topic':'artificial-intelligence'" in out
    assert out.count(">Artificial Intelligence</a>") == 2
    assert "\n  Artificial Intelligence\n</a>" in out
    assert "<p>Artificial Intelligence & the Church is mentioned in prose.</p>" in out
    assert 'href="/topics/ai-and-the-church-two/"' in out
    assert rts.rewrite_links(out, OLD, SLUG, "Artificial Intelligence & the Church", "Artificial Intelligence") == out


def test_no_live_page_links_the_old_slug():
    hits = []
    for path in (ROOT / "docs").rglob("*.html"):
        if path == STUB:
            continue
        if f"/topics/{OLD}/" in path.read_text(encoding="utf-8", errors="replace"):
            hits.append(str(path.relative_to(ROOT)))
    for name in ("template.html", "digest_template.html", "archive_template.html", "daily_template.html", "__init__.py"):
        if f"/topics/{OLD}/" in (ROOT / "frontend" / name).read_text(encoding="utf-8"):
            hits.append(name)
    assert hits == []


def test_sitemap_and_taxonomy():
    sm = (ROOT / "docs" / "sitemap-topics.xml").read_text(encoding="utf-8")
    assert f"/topics/{SLUG}/</loc>" in sm and f"/topics/{OLD}/" not in sm
    assert sm.count("<loc>") == 70
    from frontend.topics_data import TOPICS
    slugs = [t["slug"] for t in TOPICS]
    assert SLUG in slugs and OLD not in slugs and len(slugs) == 70


def test_data_watch_fresh_moves_to_new_slug(tmp_path):
    f = tmp_path / "dw.json"
    f.write_text(json.dumps({"fresh": {OLD: [{"url": "a"}], SLUG: [{"url": "b"}], "x": [{"url": "c"}]}}))
    fresh = bra.load_data_watch_fresh(f)
    assert OLD not in fresh
    assert sorted(i["url"] for i in fresh[SLUG]) == ["a", "b"]
    assert fresh["x"] == [{"url": "c"}]


# ---------------------------------------------------------------- glossary builder

GLOSS_DATA = {
    "slug": "t", "date_modified": "2026-11-14",
    "glossary": {"label": "Glossary", "title": "Terms", "place": {"before": "<!-- END -->"},
                 "items": [{"term": "Imago Dei", "def": "The image of God."},
                           {"term": "Deepfake", "def": "A fake video."},
                           {"term": "LLM", "def": "A model that predicts text."}]},
}
SKELETON = ('<html><head><!-- CC-TOPIC-ASSETS:START --></head><body>'
            '<p class="cc-last-updated">Last updated: May 1, 2026</p><!-- END --></body></html>')


def test_glossary_validates():
    assert btr.validate(GLOSS_DATA, "t", SKELETON) == []
    bad = json.loads(json.dumps(GLOSS_DATA))
    bad["glossary"]["items"] = bad["glossary"]["items"][:2]
    assert any("at least 3" in e for e in btr.validate(bad, "t", SKELETON))
    dup = json.loads(json.dumps(GLOSS_DATA))
    dup["glossary"]["items"][1]["term"] = "imago dei"
    assert any("duplicate" in e for e in btr.validate(dup, "t", SKELETON))
    dash = json.loads(json.dumps(GLOSS_DATA))
    dash["glossary"]["items"][0]["def"] = "The image — of God."
    assert any("dash" in e for e in btr.validate(dash, "t", SKELETON))


def test_glossary_renders_idempotently_with_schema():
    out = btr.build_page(SKELETON, GLOSS_DATA)
    assert out.count(btr.GLOSS_START) == 1 and 'id="glossary"' in out
    assert '<dt id="term-imago-dei">Imago Dei</dt>' in out
    m = btr.GLOSS_SCHEMA_RE.search(out)
    doc = json.loads(m.group(0).split(">", 1)[1].rsplit("<", 1)[0])
    assert doc["@type"] == "DefinedTermSet" and len(doc["hasDefinedTerm"]) == 3
    assert btr.build_page(out, GLOSS_DATA) == out


# ---------------------------------------------------------------- the page

def _html():
    return PAGE.read_text(encoding="utf-8")


def _schemas(html):
    return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)]


def test_page_shape():
    html = _html()
    for i in range(1, 5):
        assert f'id="position-{i}"' in html
    assert 'class="cc-debate-grid four-way"' in html
    for sid in ("definition", "tldr", "debate", "synthesis", "by-the-numbers", "key-documents", "faq",
                "glossary", "reading", "recent", "at-a-glance", "start-here", "key-number"):
        assert f'id="{sid}"' in html, sid
    assert '<link href="https://www.christiancurator.com/topics/artificial-intelligence/" rel="canonical"/>' in html
    assert html.count("<h1") == 1


def test_schema_matches_visible_faq_and_glossary():
    html = _html()
    docs = {d["@type"]: d for d in _schemas(html)}
    assert {"Article", "BreadcrumbList", "FAQPage", "DefinedTermSet"} <= set(docs)
    visible_q = re.findall(r'<h3 class="cc-faq-q">(.*?)</h3>', html)
    assert len(visible_q) == len(docs["FAQPage"]["mainEntity"]) >= 6
    assert len(re.findall(r"<dt id=", html)) == len(docs["DefinedTermSet"]["hasDefinedTerm"])
    assert docs["BreadcrumbList"]["itemListElement"][-1]["item"].endswith(f"/topics/{SLUG}/")


def test_curated_list_and_start_here():
    html = _html()
    urls = re.findall(r'<article class="cc-article-entry">.*?<a href="([^"]+)"', html, re.S)
    assert len(urls) == 40 and len(set(urls)) == 40
    assert all(u.startswith("https://") for u in urls)
    top = json.loads((ROOT / "data" / "topic_top" / f"{SLUG}.json").read_text(encoding="utf-8"))
    assert all(p["url"] in urls for p in top["start_here"])


def test_no_dashes_or_tracking_in_page_copy():
    html = _html()
    body = html[html.index('<main class="cc-prose">'):html.index("<!-- AEO-TOPIC-INDEX:START -->")]
    assert not re.search("[–—]|&#821[12];|&[mn]dash;", body)
    assert "utm_" not in body
    assert "quiet revival" not in body.lower()
