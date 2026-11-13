"""Deceased writers: Recent Articles list nothing curated after the death
(overnight Nov 12 2026, scripts/build_recent_articles.before_death)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_recent_articles as recent  # noqa: E402

ITEMS = [{"date": "2026-10-27", "url": "a"}, {"date": "2017-12-01", "url": "b"},
         {"date": "2017-12-20", "url": "c"}, {"date": "1683-01-01", "url": "d"}]


def test_living_writer_keeps_every_piece():
    assert recent.before_death(ITEMS, None) == ITEMS


def test_pieces_after_an_exact_death_date_are_dropped():
    assert [i["url"] for i in recent.before_death(ITEMS, "2017-12-14")] == ["b", "d"]


def test_year_only_death_date_keeps_that_year():
    assert [i["url"] for i in recent.before_death(ITEMS, "2017")] == ["b", "c", "d"]


def test_deceased_with_no_date_shows_nothing():
    assert recent.before_death(ITEMS, "") == []


def test_death_dates_cover_sproul_and_every_deceased_record():
    deaths = recent.death_dates()
    assert deaths["rc-sproul"] == "2017-12-14"
    assert deaths["tim-keller"] == "2023-05-19"
    data = json.loads((ROOT / "docs" / "voices_data.json").read_text(encoding="utf-8"))
    for v in data:
        if v.get("deceased"):
            assert v["slug"] in deaths


def test_live_pages_of_deceased_writers_show_no_republications():
    by_voice = recent.collect_by_voice()
    for slug, died in recent.death_dates().items():
        page = ROOT / "docs" / "voices" / slug / "index.html"
        if not page.exists():
            continue
        html = page.read_text(encoding="utf-8")
        for item in by_voice.get(slug, []):
            if item not in recent.before_death([item], died):
                assert f'href="{item["url"]}"' not in html.split(recent.V_START)[-1].split(recent.V_END)[0] \
                    or recent.V_START not in html, (slug, item["url"])
