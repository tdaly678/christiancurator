"""Voices indexing rule and quality gate (voices cleanup step 5, Nov 12 2026).

Run: python3 -m pytest tests/test_check_voices.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import check_voices  # noqa: E402
from curator import voice_generator as vg  # noqa: E402


def test_repo_passes_voices_gate():
    results = check_voices.run_checks()
    for key in ("noindex", "dash", "posting-account", "title"):
        assert results[key] == [], (key, results[key][:5])
    baseline = set(json.loads((ROOT / "scripts" / "voices_check_baseline.json").read_text())["bar"])
    assert {s for s, _ in results["bar"]} <= baseline


def test_audit_noindex_pages_are_out_of_the_sitemap():
    slugs = (ROOT / "data" / "voices" / "noindex-2026-11-12.txt").read_text().split()
    listed = set(json.loads((ROOT / "frontend" / "voices_noindex.json").read_text()))
    sitemap = (ROOT / "docs" / "sitemap-voices.xml").read_text()
    assert len(slugs) == 994 and set(slugs) <= listed
    assert not [s for s in slugs if f"/voices/{s}/<" in sitemap]
    # Pages stay on disk; only the index status changes.
    assert all((ROOT / "docs" / "voices" / s / "index.html").exists() for s in slugs)


def test_new_voice_pages_are_generated_noindex(tmp_path):
    page = vg.noindex_page("<html><head><title>X</title></head></html>")
    assert '<meta name="robots" content="noindex, follow" />' in page
    path = tmp_path / "noindex.json"
    path.write_text("[]")
    vg.mark_noindex("new-writer", path)
    vg.mark_noindex("new-writer", path)
    assert json.loads(path.read_text()) == ["new-writer"]
