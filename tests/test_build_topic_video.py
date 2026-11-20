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
