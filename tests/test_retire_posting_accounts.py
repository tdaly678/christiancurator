"""retire_posting_accounts.py reruns change nothing and keep KEEP_BYLINE bylines.

Rerunning it used to strip the plain-text "FM AI" bylines kept in voices
cleanup step 4 (the page reread now yields no byline for a machine credit).
These tests run the script twice against a temporary site.

Run: python3 -m pytest tests/test_retire_posting_accounts.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import retire_posting_accounts as rpa  # noqa: E402

FM_URL = "https://faithfullymagazine.com/some-ai-piece/"
NM_URL = "https://www.9marks.org/article/a-real-article/"


def _article(url, slug, name):
    return (f'<article class="cc-article">\n  <a href="{url}" class="cc-article-title">T</a>\n'
            f'  <div class="cc-article-meta">\n'
            f'    <a href="/voices/{slug}/" class="cc-author-link cc-article-author"><strong>{name}</strong></a>\n'
            f'    <span class="cc-meta-dot">·</span>\n    <span>Outlet</span>\n  </div>\n</article>\n')


def _site(tmp_path, monkeypatch, bylines):
    docs = tmp_path / "docs"
    day = docs / "archive" / "2026-05-10"
    day.mkdir(parents=True)
    (day / "index.html").write_text(_article(FM_URL, "fm-ai", "FM AI") + _article(NM_URL, "jeri-choi", "Jeri Choi"))
    (day / "meta.json").write_text(json.dumps({"authors": ["FM AI", "Jeri Choi"], "articles": [
        {"url": FM_URL, "author": "FM AI", "authors": ["FM AI"]},
        {"url": NM_URL, "author": "Jeri Choi", "authors": ["Jeri Choi"]},
    ]}))
    voices = docs / "voices"
    voices.mkdir()
    (voices / "index.html").write_text("<p>: 3 voices worth following.</p>\n")
    data = voices.parent / "voices_data.json"
    data.write_text(json.dumps([{"slug": s, "name": n} for s, n in
                                (("fm-ai", "FM AI"), ("jeri-choi", "Jeri Choi"), ("real-writer", "Real Writer"))]))
    for attr, val in {
        "DOCS_DIR": docs, "ARCHIVE_DIR": docs / "archive", "VOICES_DIR": voices,
        "VOICES_DATA_PATH": data, "INDEX_PATH": voices / "index.html",
        "NOINDEX_LIST_PATH": tmp_path / "voices_noindex.json",
        "REDIRECTS_PATH": tmp_path / "voices_redirects.json",
        "ACCOUNTS": {"fm-ai": ("FM AI", "faithfullymagazine.com", "a machine byline, not a person"),
                     "jeri-choi": ("Jeri Choi", "9marks.org")},
    }.items():
        monkeypatch.setattr(rpa, attr, val)
    monkeypatch.setattr(rpa, "remove_from_sitemap", lambda slugs, apply: 0)
    monkeypatch.setattr(rpa, "rerender_archive_index", lambda: None)
    monkeypatch.setattr(rpa, "fetch_page_byline", lambda url: bylines.get(url, ""))
    return tmp_path


def _snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


def test_first_run_keeps_fm_ai_and_reattributes_posting_account(tmp_path, monkeypatch):
    # The FM AI page reread names nobody (clean_author drops machine credits).
    root = _site(tmp_path, monkeypatch, {FM_URL: "", NM_URL: "Real Writer"})
    rpa.main(["--apply"])
    page = (root / "docs/archive/2026-05-10/index.html").read_text()
    meta = json.loads((root / "docs/archive/2026-05-10/meta.json").read_text())
    assert '<span class="cc-author-link cc-article-author"><strong>FM AI</strong></span>' in page
    assert "/voices/fm-ai/" not in page and "/voices/jeri-choi/" not in page
    assert '<a href="/voices/real-writer/"' in page
    by_url = {a["url"]: a for a in meta["articles"]}
    assert by_url[FM_URL]["author"] == "FM AI" and by_url[FM_URL]["authors"] == ["FM AI"]
    assert by_url[NM_URL]["author"] == "Real Writer"


def test_second_run_changes_nothing(tmp_path, monkeypatch):
    bylines = {FM_URL: "", NM_URL: "Real Writer"}
    root = _site(tmp_path, monkeypatch, bylines)
    rpa.main(["--apply"])
    first = _snapshot(root)
    # Pages read differently on the second run; retired accounts are not reread.
    bylines.update({FM_URL: "", NM_URL: "Somebody Else"})
    rpa.main(["--apply"])
    assert _snapshot(root) == first


def test_rerun_on_live_state_keeps_plain_text_fm_ai(tmp_path, monkeypatch):
    # The archive as voices cleanup step 4 left it: both accounts retired, the
    # FM AI byline kept as plain text on the page and in meta.json.
    root = _site(tmp_path, monkeypatch, {FM_URL: "", NM_URL: "Real Writer"})
    day = root / "docs/archive/2026-05-10"
    page = day / "index.html"
    page.write_text(page.read_text()
                    .replace('<a href="/voices/fm-ai/" class="cc-author-link cc-article-author"><strong>FM AI</strong></a>',
                             '<span class="cc-author-link cc-article-author"><strong>FM AI</strong></span>')
                    .replace('<a href="/voices/jeri-choi/" class="cc-author-link cc-article-author">'
                             '<strong>Jeri Choi</strong></a>',
                             '<a href="/voices/real-writer/" class="cc-author-link cc-article-author">'
                             '<strong>Real Writer</strong></a>'))
    meta = json.loads((day / "meta.json").read_text())
    meta["articles"][1].update(author="Real Writer", authors=["Real Writer"])
    (day / "meta.json").write_text(json.dumps(meta))
    (root / "voices_redirects.json").write_text(json.dumps({
        s: {"to": "", "name": n, "retired": "x"} for s, n in (("fm-ai", "FM AI"), ("jeri-choi", "Jeri Choi"))}))
    rpa.main(["--apply"])
    first = _snapshot(root)
    assert '"author": "FM AI"' in first["docs/archive/2026-05-10/meta.json"]
    assert "<strong>FM AI</strong></span>" in first["docs/archive/2026-05-10/index.html"]
    rpa.main(["--apply"])
    assert _snapshot(root) == first


def test_recheck_still_keeps_fm_ai(tmp_path, monkeypatch):
    root = _site(tmp_path, monkeypatch, {FM_URL: "", NM_URL: "Real Writer"})
    rpa.main(["--apply"])
    rpa.main(["--apply", "--recheck"])
    meta = json.loads((root / "docs/archive/2026-05-10/meta.json").read_text())
    assert {a["url"]: a["author"] for a in meta["articles"]}[FM_URL] == "FM AI"
