"""Tests for scripts/build_topic_video.py (compact expandable topic video strip)."""
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_topic_video as btv  # noqa: E402

DATA = btv.load("eschatology")
PAGE = '<main><section class="cc-tldr" id="tldr"><p>x</p></section>\n<section class="cc-editorial"><p>y</p></section></main>'


def test_data_file_validates():
    assert btv.validate(DATA) == []


def test_first_insert_goes_before_editorial_and_rerun_is_idempotent():
    block = btv.render_block(DATA)
    once = btv.apply(PAGE, block)
    assert once.index(btv.START) > once.index("cc-tldr")
    assert once.index(btv.END) < once.index('<section class="cc-editorial"')
    assert btv.apply(once, block) == once
    assert once.count(btv.START) == 1


def test_no_iframe_or_youtube_request_before_click():
    block = btv.render_block(DATA)
    assert "<iframe" not in block
    # The only YouTube URLs are data attributes, a plain link, and schema text: nothing the browser loads.
    assert not re.search(r'src="[^"]*youtube', block)
    assert 'aria-expanded="false"' in block
    assert "Narrated by Tom Daly, editor of Christian Curator" in block
    assert 'data-embed="https://www.youtube-nocookie.com/embed/L3IzTHCC_mo?autoplay=1&amp;rel=0&amp;cc_load_policy=0"' in block


def test_schema_fields():
    block = btv.render_block(DATA)
    raw = block.split('data-cc-marker="CC-VIDEO-SCHEMA">', 1)[1].split("</script>", 1)[0]
    obj = json.loads(raw)
    assert obj["@type"] == "VideoObject"
    assert "contentUrl" not in obj
    assert obj["embedUrl"] == "https://www.youtube-nocookie.com/embed/L3IzTHCC_mo"
    assert obj["thumbnailUrl"].startswith("https://www.christiancurator.com/")
    assert obj["duration"] == "PT3M22S"
    assert obj["uploadDate"] == "2026-11-19"


def test_copy_rules():
    block = btv.render_block(DATA)
    assert "—" not in block and "–" not in block
    assert not re.search(r"\bpastor\b", block, re.IGNORECASE)
    bad = copy.deepcopy(DATA)
    bad["video"]["headline"] = "Four Views — Explained #endtimes"
    bad["video"]["narrator"] = "Narrated by Pastor Tom"
    errs = " ".join(btv.validate(bad))
    assert "dash" in errs and "hashtag" in errs and "Pastor" in errs


def test_duration_must_match():
    bad = copy.deepcopy(DATA)
    bad["video"]["duration_iso"] = "PT3M10S"
    assert any("does not match" in e for e in btv.validate(bad))


# Shorts per view (S6)

def _cards(n=4):
    return "".join(
        f'<div class="cc-debate-side side-x" id="position-{i}">\n<div class="cc-debate-name">View {i}</div>\n'
        f'<div class="cc-debate-reads">\n<a href="https://example.com/{i}">Read {i}</a>\n</div>\n</div>\n'
        for i in range(1, n + 1)
    )


CARD_PAGE = f'<div class="cc-debate-grid four-way">\n{_cards()}</div>'


def _card(page, key):
    start = page.index(f'id="{key}"')
    nxt = page.find('<div class="cc-debate-side', start)
    return page[start:nxt if nxt >= 0 else len(page)]


def test_current_shorts_land_in_their_cards_only():
    out = btv.apply_shorts(CARD_PAGE, DATA["shorts"])
    assert DATA["shorts"]["position-1"]["youtube_id"] == "0-sH-7oJMSU"
    assert DATA["shorts"]["position-2"]["youtube_id"] == "jrkytvZbMYY"
    assert DATA["shorts"]["position-3"]["youtube_id"] == "BGnBWK-58ik"
    assert 'data-video="0-sH-7oJMSU"' in _card(out, "position-1")
    assert 'data-video="jrkytvZbMYY"' in _card(out, "position-2")
    assert 'data-video="BGnBWK-58ik"' in _card(out, "position-3")
    assert "Watch the 28-second version" in _card(out, "position-3")
    for key in ("position-1", "position-2"):
        assert "BGnBWK-58ik" not in _card(out, key)
    # Short 4 (postmillennialism) is not live yet: its card stays empty.
    assert "position-4" not in DATA["shorts"]
    assert "cc-short" not in _card(out, "position-4")
    # Placed after Key Reads, not inside it.
    c1 = _card(out, "position-1")
    assert c1.index("</a>\n</div>") < c1.index("CC-TOPIC-SHORT:position-1:START")
    assert btv.apply_shorts(out, DATA["shorts"]) == out


def test_missing_short_renders_nothing_and_removed_short_is_dropped():
    only_one = {"position-2": DATA["shorts"]["position-2"]}
    out = btv.apply_shorts(CARD_PAGE, only_one)
    assert "cc-short" not in _card(out, "position-1")
    both = btv.apply_shorts(CARD_PAGE, DATA["shorts"])
    assert btv.apply_shorts(both, only_one) == out
    assert btv.apply_shorts(both, {}) == CARD_PAGE


def test_short_has_no_iframe_until_click():
    block = btv.render_short("position-1", DATA["shorts"]["position-1"])
    assert "<iframe" not in block
    assert not re.search(r'src="[^"]*(youtube|ytimg)', block)
    assert 'aria-expanded="false"' in block and " hidden>" in block
    assert "Watch the 37-second version" in block
    assert 'href="https://www.youtube.com/shorts/0-sH-7oJMSU" target="_blank" rel="noopener"' in block
    assert "Hide video" in block
    raw = block.split('data-cc-marker="CC-SHORT-SCHEMA">', 1)[1].split("</script>", 1)[0]
    obj = json.loads(raw)
    assert obj["duration"] == "PT37S" and "contentUrl" not in obj
    assert obj["thumbnailUrl"].startswith("https://www.christiancurator.com/assets/")


def test_shorts_copy_rules():
    main_block = btv.render_block(DATA)
    blocks = [btv.render_short(k, v) for k, v in DATA["shorts"].items()]
    for b in [main_block, *blocks]:
        assert "—" not in b and "–" not in b
        assert not re.search(r"(^|\s)#[A-Za-z]", re.sub(r"<style>.*?</style>", "", b, flags=re.S))
        assert not re.search(r"\bpastor\b", b, re.IGNORECASE)
    bad = copy.deepcopy(DATA)
    bad["shorts"]["position-3"] = dict(bad["shorts"]["position-1"], description="Amill — explained #endtimes")
    bad["shorts"]["position-9x"] = dict(bad["shorts"]["position-2"], youtube_id="short")
    errs = " ".join(btv.validate(bad))
    assert "dash" in errs and "hashtag" in errs and "used twice" in errs
    assert "debate card id" in errs and "11 character" in errs


def test_check_catches_stale_page(tmp_path, monkeypatch, capsys):
    page_dir = tmp_path / "eschatology"
    page_dir.mkdir()
    page = page_dir / "index.html"
    live = (btv.TOPICS_DIR / "eschatology" / "index.html").read_text(encoding="utf-8")
    page.write_text(live, encoding="utf-8")
    monkeypatch.setattr(btv, "TOPICS_DIR", tmp_path)
    assert btv.main(["--slug", "eschatology", "--check"]) == 0
    page.write_text(btv.apply_shorts(live, {}), encoding="utf-8")
    assert btv.main(["--slug", "eschatology", "--check"]) == 1
    assert "stale" in capsys.readouterr().out
    assert btv.main(["--slug", "eschatology"]) == 0
    assert page.read_text(encoding="utf-8") == live
