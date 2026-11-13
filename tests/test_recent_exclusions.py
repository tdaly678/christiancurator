"""Per-writer Recent Articles exclusions (Nov 13 2026,
data/voices/recent_exclusions.json, scripts/build_recent_articles.is_excluded)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_recent_articles as recent  # noqa: E402

THESES_URL = "https://feeds.ligonier.org/~/926268260/0/ligonierministriesblog"


def test_rule_matches_by_url_or_headline():
    rules = [{"url": "https://a.example/x", "title": "What Were the Ninety-Five Theses?"}]
    assert recent.is_excluded({"url": "https://a.example/x", "title": "Other"}, rules)
    assert recent.is_excluded({"url": "https://b.example/y", "title": "What Were the  ninety-five Theses?"}, rules)
    assert not recent.is_excluded({"url": "https://b.example/y", "title": "Who Was John Knox?"}, rules)
    assert not recent.is_excluded({"url": "https://a.example/x", "title": "x"}, [])


def test_rules_load_and_skip_the_about_note(tmp_path):
    f = tmp_path / "x.json"
    f.write_text('{"_about": "note", "a-writer": [{"url": "u"}]}')
    assert recent.load_exclusions(f) == {"a-writer": [{"url": "u"}]}
    assert recent.load_exclusions(tmp_path / "missing.json") == {}


def test_ferguson_ninety_five_theses_item_stays_off_his_block():
    rules = recent.load_exclusions()["sinclair-ferguson"]
    assert [r["url"] for r in rules] == [THESES_URL]
    items = recent.collect_by_voice().get("sinclair-ferguson", [])
    assert THESES_URL not in [i["url"] for i in items]
    assert "What Were the Ninety-Five Theses?" not in [i["title"] for i in items]

