"""Sitemap lastmod comes from dateModified or the last content change, not today (S1 report, section 6)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import frontend
from frontend.sitemap_lastmod import LastmodState, content_fingerprint, date_modified

PAGE = ('<html><head><style>.a{color:#888}</style></head><body><nav><a href="/">Home</a></nav>'
        '<main><h1>Writer</h1><p>Bio text.</p></main><footer>Footer</footer></body></html>')


def test_fingerprint_ignores_head_nav_footer_and_markup():
    swept = (PAGE.replace("#888", "#6b6b6b").replace("<nav>", "<nav class='x'>")
             .replace("Footer", "New tagline").replace("<p>", '<p class="lead">'))
    assert content_fingerprint(swept) == content_fingerprint(PAGE)
    assert content_fingerprint(PAGE.replace("Bio text.", "New bio.")) != content_fingerprint(PAGE)


def test_date_modified_from_json_ld_or_meta():
    assert date_modified('{"dateModified": "2026-11-12T08:00:00"}') == "2026-11-12"
    assert date_modified('<meta property="article:modified_time" content="2026-10-01" />') == "2026-10-01"
    assert date_modified(PAGE) is None


def test_state_keeps_date_until_content_changes(tmp_path):
    path = tmp_path / "state.json"
    st = LastmodState(path)
    assert st.lastmod("u", PAGE, "2026-11-01") == "2026-11-01"
    st.save()
    st = LastmodState(path)
    assert st.lastmod("u", PAGE.replace("#888", "#6b6b6b"), "2026-11-22") == "2026-11-01"
    assert st.lastmod("u", PAGE.replace("Bio text.", "New bio."), "2026-11-22") == "2026-11-22"
    dm = PAGE.replace("</head>", '<script>{"dateModified": "2026-09-09"}</script></head>')
    assert st.lastmod("v", dm, "2026-11-22") == "2026-09-09"


def test_regenerate_sitemap_uses_state(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    (docs / "voices" / "writer").mkdir(parents=True)
    (docs / "voices" / "writer" / "index.html").write_text(PAGE, encoding="utf-8")
    state = tmp_path / "sitemap_lastmod.json"
    url = "https://www.christiancurator.com/voices/writer/"
    state.write_text(json.dumps({url: [content_fingerprint(PAGE), "2026-07-18"]}), encoding="utf-8")
    monkeypatch.setattr(frontend, "VOICES_DIR", docs / "voices")
    monkeypatch.setattr(frontend, "VOICES_NOINDEX_PATH", tmp_path / "none.json")
    for name in ("TOPICS_DIR", "DAILY_DIR", "ARCHIVE_DIR"):
        monkeypatch.setattr(frontend, name, docs / name.lower())
    monkeypatch.setattr(frontend, "DOCS_DIR", docs)
    monkeypatch.setattr(frontend, "SITEMAP_DIR", docs)
    monkeypatch.setattr(frontend, "SITEMAP_PATH", docs / "sitemap.xml")
    monkeypatch.setattr(frontend, "SITEMAP_LASTMOD_PATH", state)
    frontend.regenerate_sitemap()
    voices = (docs / "sitemap-voices.xml").read_text(encoding="utf-8")
    assert "<lastmod>2026-07-18</lastmod>" in voices
    index = (docs / "sitemap.xml").read_text(encoding="utf-8")
    assert "<lastmod>2026-07-18</lastmod>" in index.split("sitemap-voices.xml")[1]
