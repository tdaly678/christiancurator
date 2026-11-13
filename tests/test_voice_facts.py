"""Factual fixes on voice pages (voices cleanup step 3, Nov 12 2026).

Run: python3 -m pytest tests/test_voice_facts.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = {v["slug"]: v for v in json.loads((ROOT / "docs" / "voices_data.json").read_text(encoding="utf-8"))}


def page(slug):
    return (ROOT / "docs" / "voices" / slug / "index.html").read_text(encoding="utf-8")


def test_macarthur_is_past_tense_and_sourced():
    v = DATA["john-macarthur"]
    assert v["deceased"] is True and "July 14, 2025" in v["bio"]
    assert any("gty.org" in s for s in v["bio_sources"])
    assert "is the longtime pastor" not in page("john-macarthur")


def test_identity_mixes_fixed():
    assert DATA["william-barcley"]["name"] == "William Barcley"
    assert "Barclay" not in page("william-barcley")
    assert "AskDrBrown" not in json.dumps(DATA["michael-g-brown"])
    # christy-smith was retired overnight Nov 12 2026: no record, a stub page.
    assert "christy-smith" not in DATA
    assert "Nockels" not in page("christy-smith")
    assert "CBS Sports" in DATA["cody-benjamin"]["bio"]


def test_secular_reporters_carry_no_invented_faith_focus():
    for slug in ("margaret-sullivan", "kejal-vyas", "alaina-demopoulos"):
        bio = DATA[slug]["bio"]
        assert not re.search(r"christian|faith|church|religio", bio, re.I), slug


def test_no_dashes_in_voices_data():
    assert not re.search("[–—]", json.dumps(DATA, ensure_ascii=False))
