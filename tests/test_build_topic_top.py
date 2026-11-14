"""Tests for scripts/build_topic_top.py, the topic-page top block, and the
CC-TOPIC-LATEST line refreshed by scripts/build_recent_articles.py."""

import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))

import build_recent_articles as bra  # noqa: E402
import build_topic_top as btt  # noqa: E402

DECON = (btt.TOPICS_DIR / "faith-deconstruction" / "index.html").read_text(encoding="utf-8")
MENWOMEN = (btt.TOPICS_DIR / "complementarianism-egalitarianism" / "index.html").read_text(encoding="utf-8")
TOP_RE = re.compile(re.escape(btt.TOP_START) + r".*?" + re.escape(btt.TOP_END), re.DOTALL)


def strip_top(html: str) -> str:
    return TOP_RE.sub("", html)


def first_curated(html: str) -> list[str]:
    urls = []
    for block in btt.CURATED_RE.findall(html):
        m = btt.HREF_RE.search(block)
        if m and m.group(1) not in urls:
            urls.append(m.group(1))
    return urls


class FakeVoices(btt.VoiceIndex):
    def __init__(self, linkable=(), existing=()):
        self._link = set(linkable)
        self._exist = set(existing) | self._link
        self.redirects = {}
        self.noindex = set()

    def exists(self, slug):
        return slug in self._exist

    def retired(self, slug):
        return False

    def linkable(self, slug):
        return slug in self._link


def sample_data(html: str = DECON) -> dict:
    urls = first_curated(html)
    return {
        "slug": "faith-deconstruction",
        "glance": {
            "question": "What is deconstruction, and how should churches respond?",
            "positions": [
                {"name": "Position one", "claim": "A short claim for the first position.",
                 "voices": [{"name": "Indexed Writer", "slug": "indexed-writer"},
                            {"name": "Hidden Writer", "slug": "hidden-writer"}]},
                {"name": "Position two", "claim": "A short claim for the second position."},
                {"name": "Position three", "claim": "A short claim for the third position."},
            ],
        },
        "start_here": [
            {"kind": "Primer", "url": urls[0], "title": "First pick", "author": "A. Writer",
             "outlet": "Outlet", "why": "Why it is first."},
            {"url": urls[1], "title": "Second pick", "author": "B. Writer", "outlet": "Outlet",
             "why": "Why it is second."},
        ],
        "key_number": {
            "figure": "12%", "text": "An example sentence with 12% in it.",
            "publisher": "Example Research", "study": "Example Study", "year": 2025,
            "source_url": "https://example.org/study", "fetched": "2026-11-14",
            "license": "reuse", "link": "#debate",
        },
        "related": [{"slug": "biblical-inerrancy", "question": "Is the Bible without error?"}],
        "changes": [{"date": "2026-10-01", "text": "older change"},
                    {"date": "2026-11-14", "text": "added the top block"}],
    }


VOICES = FakeVoices(linkable={"indexed-writer"}, existing={"hidden-writer"})
ITEMS = [{"date": "2026-11-12", "title": "A fresh piece", "url": "https://example.org/a", "source": "Outlet"},
         {"date": "2026-11-10", "title": "Another piece", "url": "https://example.org/b", "source": "Other"}]


# ---------------------------------------------------------------- ids and assets

def test_ensure_ids_both_debate_variants_and_idempotent():
    for html in (DECON, MENWOMEN):
        once = btt.ensure_ids(strip_top(html))
        assert btt.ensure_ids(once) == once
        ids = btt.page_ids(once)
        for ident in ("tldr", "key-questions", "debate", "position-1", "position-2", "position-3",
                      "synthesis", "reading"):
            assert ident in ids, ident
        assert len(re.findall(r'id="debate"', once)) == 1


def test_ensure_ids_keeps_existing_id():
    html = '<section class="cc-tldr" id="custom"><p>x</p></section>'
    assert btt.ensure_ids(html) == html


def test_ensure_ids_changes_no_text():
    html = btt.ensure_ids(strip_top(DECON))
    assert re.sub(r' id="[^"]+"', "", html) == re.sub(r' id="[^"]+"', "", strip_top(DECON))


def test_assets_block_once_with_hash():
    out = btt.ensure_assets(btt.ensure_assets(DECON))
    assert out.count(btt.ASSET_START) == 1
    assert re.search(r'/assets/topic\.css\?v=[0-9a-f]{10}"', out)
    assert re.search(r'<script defer src="/assets/topic\.js\?v=[0-9a-f]{10}"', out)
    assert out.index(btt.ASSET_END) < out.index("</head>")


# ---------------------------------------------------------------- the block

def test_no_data_gives_only_jump_nav():
    out = btt.build_page("faith-deconstruction", strip_top(DECON), None, voices=VOICES)
    block = TOP_RE.search(out).group(0)
    assert 'class="cc-tt-jump"' in block
    for cls in ("cc-tt-glance", "cc-tt-start", "cc-tt-num", "cc-tt-signup", btt.LATEST_START):
        assert cls not in block
    assert 'href="#debate" data-pos="topic-jump"' in block
    # placed right after the TL;DR
    assert out.index(btt.TOP_START) > out.index('class="cc-tldr"')
    assert out.index(btt.TOP_START) < out.index('class="cc-editorial"')


def test_jump_links_only_to_existing_sections():
    out = btt.build_page("x", strip_top(MENWOMEN), None, voices=VOICES)
    block = TOP_RE.search(out).group(0)
    ids = btt.page_ids(out)
    for target in re.findall(r'href="#([^"]+)"', block):
        assert target in ids


def test_build_is_idempotent():
    data = sample_data()
    once = btt.build_page("faith-deconstruction", DECON, data, voices=VOICES, latest_items=ITEMS)
    twice = btt.build_page("faith-deconstruction", once, data, voices=VOICES, latest_items=ITEMS)
    assert once == twice
    assert once.count(btt.TOP_START) == 1


def test_full_block_renders_every_part():
    out = btt.build_page("faith-deconstruction", DECON, sample_data(), voices=VOICES, latest_items=ITEMS)
    block = TOP_RE.search(out).group(0)
    assert 'id="at-a-glance"' in block and 'id="start-here"' in block and 'id="key-number"' in block
    assert 'data-pos="topic-glance"' in block and 'data-pos="topic-start"' in block
    assert '<a href="/voices/indexed-writer/" data-pos="topic-voices">Indexed Writer</a>' in block
    assert "/voices/hidden-writer/" not in block and "Hidden Writer" in block
    assert 'name="source" value="topic:faith-deconstruction"' in block
    assert "What changed:</strong> Nov 2026, added the top block" in block
    assert btt.LATEST_START in block and "A fresh piece" in block and "Nov 12" in block
    assert "Print for a group" in block
    assert 'href="/topics/biblical-inerrancy/"' in block
    assert "&#10;" in block  # share summaries keep their line breaks
    assert "Example Research, Example Study, 2025" in block
    assert "utm_" not in block


def test_block_has_no_dashes():
    out = btt.build_page("faith-deconstruction", DECON, sample_data(), voices=VOICES, latest_items=ITEMS)
    assert not btt.DASH_RE.search(TOP_RE.search(out).group(0))


def test_page_summary_strips_dashes():
    html = '<h1>Title</h1><section class="cc-tldr"><div class="cc-tldr-label">TL;DR</div><p>One — two. Three.</p></section>'
    assert btt.page_summary(html) == "Title\nOne, two."


def test_missing_tldr_raises():
    with pytest.raises(ValueError):
        btt.insert_top("<main></main>", "<!-- block -->")


# ---------------------------------------------------------------- validation

def errs(data, html=DECON):
    return btt.validate(data, "faith-deconstruction", html, voices=VOICES,
                        flagged={"faith-deconstruction": ["Chrissy Stroop"]})


def test_sample_validates():
    assert errs(sample_data()) == []


@pytest.mark.parametrize("mutate, needle", [
    (lambda d: d["glance"]["positions"][0].update(claim="A claim — with a dash."), "dash"),
    (lambda d: d["glance"]["positions"][1].update(voices=[{"name": "Chrissy Stroop"}]),
     "flagged name"),
    (lambda d: d["start_here"][0].update(url="https://example.org/not-curated"), "not in the page's curated list"),
    (lambda d: d["key_number"].update(figure="13%"), "verbatim"),
    (lambda d: d["key_number"].pop("fetched"), "fetched is required"),
    (lambda d: d["key_number"].update(license="ask-first"), "license"),
    (lambda d: d["key_number"].update(source_url="https://example.org/s?utm_source=x"), "tracking"),
    (lambda d: d["glance"].update(question="What the Quiet Revival shows"), "Quiet Revival"),
    (lambda d: d["glance"]["positions"][0].update(claim=" ".join(["word"] * 19)), "over 18 words"),
    (lambda d: d["glance"]["positions"][0].update(anchor="nowhere"), "not on the page"),
    (lambda d: d["glance"]["positions"][0]["voices"].append({"name": "X", "slug": "no-such-voice"}), "does not exist"),
    (lambda d: d["related"].append({"slug": "no-such-topic", "question": "?"}), "does not exist"),
    (lambda d: d.update(extra=1), "unknown key"),
    (lambda d: d.update(slug="other"), '"slug"'),
    (lambda d: d["glance"].update(positions=d["glance"]["positions"][:1]), "2 to 4"),
    (lambda d: d["glance"].update(question="Drawn from 450 feeds"), "feed count"),
])
def test_validation_catches(mutate, needle):
    data = copy.deepcopy(sample_data())
    mutate(data)
    assert any(needle in e for e in errs(data)), errs(data)


def test_notes_are_not_checked_for_names():
    data = sample_data()
    data["notes"] = "Chrissy Stroop is flagged; see the report."
    assert errs(data) == []


def test_real_data_files_validate():
    voices = btt.VoiceIndex()
    for path in btt.DATA_DIR.glob("*.json"):
        if path.name == btt.FLAGGED.name:
            continue
        page = btt.TOPICS_DIR / path.stem / "index.html"
        assert page.exists(), path
        assert btt.validate(btt.load_data(path.stem), path.stem, page.read_text(encoding="utf-8"),
                            voices=voices) == [], path


def test_flagged_names_file_covers_report_names():
    flagged = json.loads(btt.FLAGGED.read_text(encoding="utf-8"))
    assert "Chrissy Stroop" in flagged["faith-deconstruction"]
    assert "Tim Keller" in flagged["complementarianism-egalitarianism"]


def test_voice_index_respects_noindex_and_retired(tmp_path):
    vdir = tmp_path / "voices"
    for slug, head in (("good", "<head></head>"), ("meta", '<head><meta name="robots" content="noindex"/></head>'),
                       ("listed", "<head></head>"), ("gone", "<head></head>")):
        (vdir / slug).mkdir(parents=True)
        (vdir / slug / "index.html").write_text(head, encoding="utf-8")
    (tmp_path / "noindex.json").write_text('["listed"]')
    (tmp_path / "redirects.json").write_text('{"gone": {"to": ""}}')
    vi = btt.VoiceIndex(vdir, tmp_path / "noindex.json", tmp_path / "redirects.json")
    assert vi.linkable("good")
    assert not vi.linkable("meta") and not vi.linkable("listed") and not vi.linkable("gone")
    assert not vi.linkable("missing")


# ---------------------------------------------------------------- site state

def test_every_topic_page_has_one_block_and_assets():
    for page in btt.TOPICS_DIR.glob("*/index.html"):
        html = page.read_text(encoding="utf-8")
        assert html.count(btt.TOP_START) == 1, page
        assert html.count(btt.ASSET_START) == 1, page
        assert 'class="cc-tt-jump"' in html, page
        assert 'id="debate"' in html, page


def test_committed_pages_are_up_to_date():
    """Rebuilding with no changes must be a no-op (the builder was run)."""
    voices = btt.VoiceIndex()
    for page in sorted(btt.TOPICS_DIR.glob("*/index.html"))[:12]:
        slug = page.parent.name
        if btt.load_data(slug):
            continue
        html = page.read_text(encoding="utf-8")
        assert btt.build_page(slug, html, None, voices=voices) == html, slug


# ---------------------------------------------------------------- latest line

def test_render_latest_line():
    line = bra.render_latest_line(ITEMS + ITEMS + ITEMS)
    assert line.startswith(bra.L_START) and line.endswith(bra.L_END)
    assert line.count('data-pos="topic-latest"') == 3
    assert bra.render_latest_line([]) == bra.L_START + bra.L_END


def test_refresh_latest_line_only_touches_marked_pages():
    page = f"<p>x</p>{bra.L_START}old{bra.L_END}<p>y</p>"
    out = bra.refresh_latest_line(page, ITEMS)
    assert "old" not in out and "A fresh piece" in out and out.endswith("<p>y</p>")
    assert bra.refresh_latest_line("<p>none</p>", ITEMS) == "<p>none</p>"


def test_recent_section_id_only_when_asked():
    assert 'id="recent"' in bra.render_section("L", "H", ITEMS, section_id="recent")
    assert "id=" not in bra.render_section("L", "H", ITEMS).split("<style>")[0]


def test_recent_block_inserts_before_faq_markers():
    page = "<main><!-- CC-FAQ:START -->\n<section class=\"cc-faq\" id=\"faq\"></section>\n<!-- CC-FAQ:END --></main>"
    out = bra.inject(page, bra.render_section("L", "H", ITEMS))
    assert out.index(bra.V_START) < out.index("<!-- CC-FAQ:START -->")


def test_topic_matcher_feeds_deconstruction_and_literacy():
    from frontend.topic_matcher import TOPICS
    slugs = {t["slug"] for t in TOPICS}
    assert {"faith-deconstruction", "biblical-literacy"} <= slugs
    hist = [{"date_shown": "2026-11-01", "url": "https://e.org/x", "source_name": "E",
             "original_title": "Why Young Adults Deconstruct Their Faith"}]
    assert bra.topic_items("faith-deconstruction", hist, {})[0]["url"] == "https://e.org/x"


# ---------------------------------------------------------------- assets

def test_topic_js_parses():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    subprocess.run([node, "--check", str(btt.ASSETS / "topic.js")], check=True)


def test_topic_js_tracks_all_positions():
    js = (btt.ASSETS / "topic.js").read_text(encoding="utf-8")
    for pos in ("topic-curated", "topic-voices", "topic-latest"):
        assert pos in js
    assert "'article_click'" in js and "link_url: a.href" in js and "position:" in js
    assert "utm_" not in js


def test_assets_have_no_dashes():
    for name in ("topic.css", "topic.js"):
        assert not btt.DASH_RE.search((btt.ASSETS / name).read_text(encoding="utf-8")), name
