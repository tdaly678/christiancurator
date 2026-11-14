"""Tests for scripts/build_topic_og.py: topic preview cards and head tags."""

import io
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))

import build_topic_og as og  # noqa: E402

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>On Baptism — Christian Curator</title>
<meta content="Evangelicals debate infant and believer's baptism." name="description"/>
<link href="https://www.christiancurator.com/topics/baptism/" rel="canonical"/>
<!-- CC-TOPIC-ASSETS:START -->
<link href="/assets/topic.css?v=abc" rel="stylesheet"/>
<!-- CC-TOPIC-ASSETS:END -->
<meta content="article" property="og:type"/><meta content="Christian Curator" property="og:site_name"/><meta content="On Baptism — Christian Curator" property="og:title"/>
<meta content="Old description" property="og:description"/>
<meta content="https://www.christiancurator.com/topics/baptism/" property="og:url"/>
<meta content="summary" name="twitter:card"/>
<meta content="On Baptism — Christian Curator" name="twitter:title"/>
</head>
<body>
<div class="cc-debate-side side-a" id="position-1"></div>
<div class="cc-debate-side side-b" id="position-2"></div>
<div class="cc-debate-side side-c" id="position-3"></div>
<meta content="body meta stays" property="og:title"/>
</body>
</html>
"""

CARD = {"question": "Should we baptize infants, or only those who profess faith?",
        "positions": ["Believer's Baptism", "Covenant Baptism", "The Irenic Middle"]}


def head(html: str) -> str:
    return html[:html.index("</head>")]


def test_page_title_drops_site_suffix():
    assert og.page_title(PAGE) == "On Baptism"
    assert og.page_title("<title>On Abortion &amp; Life | Christian Curator</title>") == "On Abortion & Life"


def test_valid_card_has_no_problems():
    assert og.validate("baptism", CARD, PAGE) == []


@pytest.mark.parametrize("card, needle", [
    (None, "no entry"),
    ({**CARD, "positions": CARD["positions"][:2]}, "3 debate positions"),
    ({**CARD, "question": "Infants or believers — which?"}, "dash"),
    ({**CARD, "question": "x" * 71}, "71 characters"),
    ({**CARD, "positions": ["A" * 49, "B", "C"]}, "over 48"),
    ({**CARD, "og_description": "x" * 201}, "201 characters"),
    ({**CARD, "og_description": "Read it https://x.org/?utm_source=a"}, "tracking"),
])
def test_validate_refuses(card, needle):
    errs = og.validate("baptism", card, PAGE)
    assert any(needle in e for e in errs), errs


def test_page_without_debate_needs_deck():
    page = re.sub(r'<div class="cc-debate-side[^>]*></div>\n', "", PAGE)
    assert any("needs a deck" in e for e in og.validate("baptism", {"question": "Q?"}, page))
    assert og.validate("baptism", {"question": "Q?", "deck": "A short deck."}, page) == []


def test_head_block_replaces_old_tags_once():
    new, name = og.build_page("baptism", PAGE, CARD, "Core Theology")
    h = head(new)
    for key in ["og:title", "og:description", "og:image", "og:image:alt", "twitter:card",
                "twitter:title", "twitter:image", "og:url", "og:site_name", "og:type"]:
        assert len(re.findall(rf'(?:property|name)="{key}"', h)) == 1, key
    assert og.meta_content(h, "property", "og:title") == "On Baptism"
    assert og.meta_content(h, "property", "og:description") == "Evangelicals debate infant and believer's baptism."
    assert og.meta_content(h, "name", "twitter:card") == "summary_large_image"
    assert og.meta_content(h, "property", "og:image") == f"{og.SITE}/og/topics/{name}"
    assert og.meta_content(h, "property", "og:image:width") == "1200"
    assert "Believer's Baptism; Covenant Baptism; The Irenic Middle" in og.meta_content(h, "property", "og:image:alt")
    # assets block and body untouched
    assert re.search(r"<!-- CC-TOPIC-ASSETS:START -->.*?END -->", PAGE, re.S).group(0) in new
    assert new[new.index("</head>"):] == PAGE[PAGE.index("</head>"):]


def test_build_is_idempotent_and_updates_in_place():
    once, _ = og.build_page("baptism", PAGE, CARD, "Core Theology")
    twice, _ = og.build_page("baptism", once, CARD, "Core Theology")
    assert once == twice
    changed, _ = og.build_page("baptism", once, {**CARD, "og_description": "New words."}, "Core Theology")
    assert changed.count(og.OG_START) == 1
    assert og.meta_content(head(changed), "property", "og:description") == "New words."


def test_missing_og_url_is_added_inside_block():
    page = PAGE.replace('<meta content="https://www.christiancurator.com/topics/baptism/" property="og:url"/>\n', "")
    new, _ = og.build_page("baptism", page, CARD, "")
    block = new[new.index(og.OG_START):new.index(og.OG_END)]
    assert 'content="https://www.christiancurator.com/topics/baptism/" property="og:url"' in block


def test_image_name_moves_with_text():
    a = og.image_name("baptism", CARD, "Core Theology")
    assert re.fullmatch(r"baptism-[0-9a-f]{10}\.png", a)
    assert og.image_name("baptism", CARD, "Core Theology") == a
    assert og.image_name("baptism", {**CARD, "question": "Other?"}, "Core Theology") != a
    # og_description is not drawn on the card, so it does not move the URL
    assert og.image_name("baptism", {**CARD, "og_description": "x"}, "Core Theology") == a


def test_every_card_is_dash_free():
    for slug, card in og.load_cards().items():
        for text in [card.get("question", ""), card.get("deck", ""), card.get("og_description", "")] \
                + list(card.get("positions") or []):
            assert not og.DASH_RE.search(text), (slug, text)


def test_committed_pages_and_images_are_current():
    assert og.main(["--check"]) == 0


def test_every_topic_page_has_a_card():
    assert set(og.topic_slugs()) <= set(og.load_cards())


@pytest.mark.parametrize("kwargs", [
    {"positions": ["Covenant Theology: One Covenant, Many Administrations",
                   "Historic Premillennialism and Postmillennialism", "Progressive Covenantalism"]},
    {"positions": ["Robust Church Authority", "Pastoral Discretion and Caution"]},
    {"deck": "Or must it require repentance from the offender?"},
])
def test_render_card_size_and_weight(kwargs):
    pytest.importorskip("PIL")
    img = og.render_card("How do Christians decide what the Bible does not directly address?",
                         category="Culture & Society", **kwargs)
    assert img.size == (1200, 630)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    assert buf.tell() < 600_000


def test_committed_images_are_1200x630():
    Image = pytest.importorskip("PIL.Image")
    files = list(og.OG_DIR.glob("*.png"))
    assert files
    for f in files:
        assert f.stat().st_size < 600_000, f
        with Image.open(f) as im:
            assert im.size == (1200, 630), f
