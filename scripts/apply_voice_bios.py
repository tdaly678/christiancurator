#!/usr/bin/env python3
"""Apply researched, sourced bios to legacy voice pages (overnight Nov 12 2026).

Input: one or more JSON files, each a list of research rows:

    {"slug", "decision": "bio" | "journalist" | "noindex", "name", "bio", "role",
     "affiliation", "website", "books": [title, ...], "deceased", "died": "YYYY-MM-DD",
     "bio_sources": [url, ...]}

For "bio" and "journalist" rows the docs/voices_data.json record is rewritten:
bio, role, affiliation, website, deceased and bio_sources come from the row;
books become the row's verified titles (none when the row lists none). Fields
that were generated without sources (education, faqs, denomination, tradition,
known_for, current_role) are removed, so every fact on the page is sourced.
The page is then refreshed in place (scripts/apply_voice_enrichment.process plus
the meta box, book list and meta descriptions) and its /voices/ card updated.

For "noindex" rows the page gets the robots noindex tag, is listed in
frontend/voices_noindex.json and leaves sitemap-voices.xml (same helpers as
scripts/apply_voice_noindex.py).

A row whose bio or role contains an em or en dash, or a bio row with no
bio_sources, is refused. Display names are never changed here.

DRY RUN BY DEFAULT. --apply writes.

    python scripts/apply_voice_bios.py /tmp/vr/out-1.json --apply
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from bs4 import BeautifulSoup  # noqa: E402

import apply_voice_enrichment as enrich  # noqa: E402
from junk_review_list import remove_from_sitemap  # noqa: E402
from curator.voice_generator import NOINDEX_LIST_PATH, noindex_page  # noqa: E402

DOCS = REPO_ROOT / "docs"
VOICES = DOCS / "voices"
DATA = DOCS / "voices_data.json"
INDEX = VOICES / "index.html"

DASH_RE = re.compile("[–—]")
UNSOURCED_FIELDS = ("education", "faqs", "denomination", "tradition", "known_for", "current_role")


def _esc(text) -> str:
    return html_mod.escape(str(text or ""), quote=True)


def clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    return text[: n - 3].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def check_row(row: dict) -> str | None:
    if row.get("decision") not in ("bio", "journalist", "noindex"):
        return f"unknown decision {row.get('decision')!r}"
    if row["decision"] == "noindex":
        return None
    if not (row.get("bio") or "").strip():
        return "empty bio"
    if not row.get("bio_sources"):
        return "no bio_sources"
    for key in ("bio", "role", "affiliation"):
        if DASH_RE.search(row.get(key) or ""):
            return f"dash in {key}"
    if any(DASH_RE.search(b) for b in row.get("books") or []):
        return "dash in books"
    return None


def update_record(entry: dict, row: dict) -> dict:
    name = entry["name"]
    entry["bio"] = " ".join(row["bio"].split())
    entry["role"] = (row.get("role") or "").strip() or entry.get("role", "")
    entry["affiliation"] = (row.get("affiliation") or "").strip()
    if row.get("website"):
        entry["website"] = row["website"].strip()
    entry["books"] = [{"title": t, "amazon_url": "https://www.amazon.com/s?k=" + quote_plus(f"{t} {name}")}
                      for t in row.get("books") or []]
    entry["deceased"] = bool(row.get("deceased"))
    if row.get("died"):
        entry["died"] = row["died"]
    entry["bio_sources"] = list(dict.fromkeys(row["bio_sources"]))
    for key in UNSOURCED_FIELDS:
        entry.pop(key, None)
    entry["education"] = ""
    return entry


def refresh_meta_box(soup: BeautifulSoup, entry: dict) -> None:
    box = soup.select_one(".cc-voice-meta")
    if box is None:
        return
    items = []
    if entry.get("affiliation"):
        label = "Writes for" if box.find(string=re.compile(r"^\s*Writes for\s*$")) else "Affiliation"
        items.append(f'<div class="cc-meta-item"><span class="cc-meta-label">{label}</span>'
                     f'<span class="cc-meta-value">{_esc(entry["affiliation"])}</span></div>')
    if entry.get("website"):
        w = entry["website"]
        display = w.replace("https://", "").replace("http://", "").rstrip("/")
        items.append(f'<div class="cc-meta-item"><span class="cc-meta-label">Website</span>'
                     f'<a class="cc-meta-link" href="{_esc(w)}" rel="noopener noreferrer" target="_blank">'
                     f'{_esc(display)}</a></div>')
    if not items:
        box.decompose()
        return
    new = BeautifulSoup('<div class="cc-voice-meta">\n' + "\n".join(items) + "\n</div>", "html.parser")
    box.replace_with(new)


def refresh_books(soup: BeautifulSoup, entry: dict) -> None:
    section = None
    for label in soup.select(".cc-section-label"):
        if label.get_text(strip=True) == "Notable Books":
            section = label.find_parent(class_="cc-voice-section")
            break
    books = entry.get("books") or []
    if not books:
        if section is not None:
            section.decompose()
        return
    rows = "".join(
        f'\n<a class="cc-book-item" href="{_esc(b["amazon_url"])}" rel="noopener noreferrer" target="_blank">'
        f'<span class="cc-book-title">{_esc(b["title"])}</span><span class="cc-book-link">Amazon &rarr;</span></a>'
        for b in books)
    new = BeautifulSoup('<div class="cc-voice-section">\n<div class="cc-section-label">Notable Books</div>\n'
                        f'<div class="cc-books-list">{rows}\n</div>\n</div>', "html.parser")
    if section is not None:
        section.replace_with(new)
    else:
        anchor = soup.select_one(".cc-voice-meta") or soup.select("p.cc-voice-bio")[-1]
        anchor.insert_after(new)


def refresh_descriptions(soup: BeautifulSoup, bio: str) -> None:
    for attrs, n in (({"name": "description"}, 158), ({"property": "og:description"}, 200),
                     ({"name": "twitter:description"}, 200)):
        tag = soup.find("meta", attrs=attrs)
        if tag is not None:
            tag["content"] = clip(bio, n)


def refresh_page(slug: str, entry: dict) -> bool:
    path = VOICES / slug / "index.html"
    if not path.exists():
        return False
    enrich.process(slug, entry)
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    refresh_meta_box(soup, entry)
    refresh_books(soup, entry)
    refresh_descriptions(soup, entry["bio"])
    new = str(soup)
    if new != html:
        path.write_text(new, encoding="utf-8")
    return True


def refresh_card(index_html: str, entry: dict) -> str:
    bio = entry["bio"]
    teaser = bio[:120].rsplit(" ", 1)[0] + "…" if len(bio) > 120 else bio
    pat = re.compile(r'(<a href="/voices/' + re.escape(entry["slug"]) + r'/" class="cc-voice-card">.*?'
                     r'<div class="cc-voice-card-role">)(.*?)(</div>\s*<div class="cc-voice-card-teaser">)'
                     r'(.*?)(</div>)', re.S)
    return pat.sub(lambda m: m.group(1) + _esc(entry["role"]) + m.group(3) + _esc(teaser) + m.group(5),
                   index_html, count=1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("rows", type=Path, nargs="+")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated slugs to apply (default: all rows)")
    args = ap.parse_args(argv)
    only = {s for s in args.only.split(",") if s}

    rows = [r for f in args.rows for r in json.loads(f.read_text(encoding="utf-8"))]
    if only:
        rows = [r for r in rows if r["slug"] in only]
    data = json.loads(DATA.read_text(encoding="utf-8"))
    by_slug = {v["slug"]: v for v in data}
    index_html = INDEX.read_text(encoding="utf-8")

    bios, noindexed, refused = [], [], []
    for row in rows:
        why = check_row(row)
        if why or row["slug"] not in by_slug:
            refused.append((row["slug"], why or "no voices_data record"))
            continue
        if row["decision"] == "noindex":
            noindexed.append(row["slug"])
            continue
        bios.append(row["slug"])
        if args.apply:
            entry = update_record(by_slug[row["slug"]], row)
            refresh_page(row["slug"], entry)
            index_html = refresh_card(index_html, entry)

    if args.apply:
        DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        INDEX.write_text(index_html, encoding="utf-8")
        for slug in noindexed:
            page = VOICES / slug / "index.html"
            if page.exists():
                page.write_text(noindex_page(page.read_text(encoding="utf-8")), encoding="utf-8")
        listed = set(json.loads(NOINDEX_LIST_PATH.read_text())) if NOINDEX_LIST_PATH.exists() else set()
        NOINDEX_LIST_PATH.write_text(json.dumps(sorted(listed | set(noindexed)), indent=2) + "\n",
                                     encoding="utf-8")
    removed = remove_from_sitemap(set(noindexed), args.apply)
    verb = "" if args.apply else "would be "
    print(f"{len(bios)} bios {verb}written; {len(noindexed)} pages {verb}noindexed "
          f"({removed} sitemap URLs); {len(refused)} refused.")
    for slug, why in refused:
        print(f"  refused {slug}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
