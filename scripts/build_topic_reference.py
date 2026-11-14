#!/usr/bin/env python3
"""build_topic_reference.py: definition box and FAQ (with FAQPage schema) on a topic page.

For a topic page that has data/topic_reference/<slug>.json, writes, idempotently:

1. <!-- CC-REFERENCE-CSS:START/END --> in <head>: the definition and FAQ styles
   (the same rules the hand-built definition pages carry inline). The shared
   docs/assets/topic.css is left alone so branches do not conflict on its hash.
2. <!-- CC-DEFINITION:START/END -->: <section class="cc-definition" id="definition">
   with the question, a short sourced answer and an "Also known as" line. First
   insert goes right before the TL;DR.
3. <!-- CC-FAQ:START/END -->: <section class="cc-faq" id="faq"> with every
   question and answer visible on the page. First insert goes at "faq.place".
4. The FAQPage JSON-LD (<script ... data-cc-marker="AEO-FAQPAGE-SCHEMA">) is
   rewritten from the same items, so the markup always matches the visible
   text (Google's rule for FAQ markup). Answers are stored as HTML; the schema
   gets the plain text.
5. "dateModified" in the Article JSON-LD and the visible "Last updated" line are
   set to "date_modified".

Schema of data/topic_reference/<slug>.json:

{
  "slug": "complementarianism-egalitarianism",
  "date_modified": "2026-11-14",
  "definition": {
    "question": "What are complementarianism and egalitarianism?",
    "html": "<p>Answer paragraph(s); links allowed.</p>",
    "also_known_as": ["biblical manhood and womanhood", "biblical equality"]
  },
  "faq": {
    "label": "Frequently Asked Questions",
    "title": "Men, Women and the Church, Briefly Answered",
    "place": {"before": "<!-- CC-TOPIC-VOICES:START -->"},   # first insert only
    "items": [{"q": "Question?", "a": "Answer HTML (inline tags and links only)."}]
  },
  "sources": [{"id": "danvers", "publisher": "CBMW", "title": "The Danvers Statement",
               "url": "https://...", "fetched": "2026-11-14"}],   # what the copy rests on
  "notes": "editor notes; never rendered"
}

Rules (validate()): no em or en dashes; no tracking parameters; no Quiet
Revival; no feed counts; no name flagged for the slug in
data/topic_top/flagged_names.json; at least 3 FAQ items, each with a question
ending in "?" and an answer; every link is https:// or an in-page #anchor that
exists on the page (or is written by this builder); every source has a URL and
the ISO date it was opened; a first insert needs its anchor on the page.

Usage:
  python scripts/build_topic_reference.py                     # every slug with a data file
  python scripts/build_topic_reference.py --slug complementarianism-egalitarianism
  python scripts/build_topic_reference.py --check             # validate only
  python scripts/build_topic_reference.py --dry-run           # report, write nothing
Run it before scripts/build_topic_top.py, so the jump nav sees #faq.
Tests: tests/test_build_topic_reference.py
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "topic_reference"
FLAGGED_PATH = REPO_ROOT / "data" / "topic_top" / "flagged_names.json"
TOPICS_DIR = REPO_ROOT / "docs" / "topics"

CSS_START, CSS_END = "<!-- CC-REFERENCE-CSS:START -->", "<!-- CC-REFERENCE-CSS:END -->"
DEF_START, DEF_END = "<!-- CC-DEFINITION:START -->", "<!-- CC-DEFINITION:END -->"
FAQ_START, FAQ_END = "<!-- CC-FAQ:START -->", "<!-- CC-FAQ:END -->"
ASSETS_START = "<!-- CC-TOPIC-ASSETS:START -->"
TLDR_TAG = '<section class="cc-tldr"'

DASH_RE = re.compile("[–—]")
BANNED_RE = re.compile(r"quiet revival", re.I)
FEED_COUNT_RE = re.compile(r"\b\d[\d,]*\s+(?:feeds|sources|outlets)\b", re.I)
TRACKING_RE = re.compile(r"[?&](?:utm_[a-z]+|fbclid|gclid|mc_eid|ref)=", re.I)
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HREF_RE = re.compile(r'href="([^"]*)"')
ID_RE = re.compile(r'\bid="([^"]+)"')
TAG_RE = re.compile(r"<[^>]+>")
FAQ_SCHEMA_RE = re.compile(
    r'<script(?=[^>]*type="application/ld\+json")(?=[^>]*data-cc-marker="AEO-FAQPAGE-SCHEMA")[^>]*>.*?</script>',
    re.DOTALL,
)
DATE_MODIFIED_RE = re.compile(r'("dateModified"\s*:\s*")\d{4}-\d{2}-\d{2}(")')
LAST_UPDATED_RE = re.compile(r'(<p class="cc-last-updated">Last updated: )[^<]*(</p>)')

CSS = """<style>
.cc-definition { margin-bottom: 2rem; padding: 1.1rem 1.25rem; background: #f0f4f0; border-left: 3px solid #2C4A2E; border-radius: 0 4px 4px 0; }
.cc-definition-q { font-family: 'Lora', Georgia, serif; font-size: 19px; font-weight: 600; color: #1a1a1a; margin-bottom: 0.45rem; }
.cc-definition p { font-size: 15px; line-height: 1.7; color: #2a2a2a; margin: 0 0 0.6rem; }
.cc-definition p:last-child { margin-bottom: 0; }
.cc-definition .cc-definition-aka { font-size: 13px; color: #555; }
.cc-definition a, .cc-faq-a a { color: #2C4A2E; }
.cc-faq { margin-top: 2.5rem; padding-top: 1.75rem; border-top: 2px solid #e0ddd8; }
.cc-faq-label { font-size: 10px; font-weight: 600; letter-spacing: 0.16em; text-transform: uppercase; color: #2C4A2E; margin-bottom: 0.5rem; }
.cc-faq-title { font-family: 'Lora', Georgia, serif; font-size: 24px; font-weight: 600; margin-bottom: 1.25rem; color: #1a1a1a; }
.cc-faq-item { margin-bottom: 1.5rem; }
.cc-faq-item:last-child { margin-bottom: 0; }
.cc-faq-q { font-family: 'Lora', Georgia, serif; font-size: 17px; font-weight: 600; line-height: 1.35; margin-bottom: 0.35rem; color: #1a1a1a; }
.cc-faq-a { font-size: 15px; color: #333; line-height: 1.7; }
</style>"""


def esc(s) -> str:
    return html_mod.escape(str(s if s is not None else ""), quote=True)


def plain(fragment: str) -> str:
    return " ".join(html_mod.unescape(TAG_RE.sub("", fragment)).split())


def load_flagged(slug: str, path: Path = FLAGGED_PATH) -> list[str]:
    if not path.exists():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get(slug) or [])


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in ("place", "notes"):
                yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


# ---------------------------------------------------------------- validation

def validate(data: dict, slug: str, page_html: str, flagged: list[str] | None = None) -> list[str]:
    errs: list[str] = []
    if data.get("slug") != slug:
        errs.append(f"slug must be {slug!r}")
    if not ISO_RE.match(str(data.get("date_modified", ""))):
        errs.append("date_modified must be YYYY-MM-DD")
    for s in _strings(data):
        if DASH_RE.search(s):
            errs.append(f"em or en dash in {s[:70]!r}")
        if BANNED_RE.search(s):
            errs.append("Quiet Revival is withdrawn and may not be cited")
        if FEED_COUNT_RE.search(s):
            errs.append(f"feed count in {s[:70]!r}")
        if TRACKING_RE.search(s):
            errs.append(f"tracking parameter in {s[:70]!r}")
        for name in flagged or []:
            if name.lower() in s.lower():
                errs.append(f"{name!r} is flagged for this page until Tom reviews it")

    d = data.get("definition")
    if d is not None:
        if not str(d.get("question", "")).strip().endswith("?"):
            errs.append("definition.question must be a question")
        if not str(d.get("html", "")).strip():
            errs.append("definition.html is required")

    faq = data.get("faq")
    items = (faq or {}).get("items") or []
    if faq is not None:
        if len(items) < 3:
            errs.append("faq needs at least 3 items")
        for n, it in enumerate(items, 1):
            if not str(it.get("q", "")).strip().endswith("?"):
                errs.append(f"faq item {n}: q must be a question ending in '?'")
            if not plain(str(it.get("a", ""))):
                errs.append(f"faq item {n}: answer is empty")
        qs = [it.get("q") for it in items]
        if len(qs) != len(set(qs)):
            errs.append("faq has duplicate questions")
        if FAQ_START not in page_html:
            errs += _place_errors("faq", faq.get("place"), page_html)
    if d is not None and DEF_START not in page_html and TLDR_TAG not in page_html:
        errs.append("definition: no TL;DR on the page to insert before")

    # Ids this builder writes count as present.
    ids = set(ID_RE.findall(page_html))
    if d is not None:
        ids.add("definition")
    if faq is not None:
        ids.add("faq")
    fragments = [str((d or {}).get("html", ""))] + [str(it.get("a", "")) for it in items]
    for frag in fragments:
        for href in HREF_RE.findall(frag):
            if href.startswith("#"):
                if href[1:] not in ids:
                    errs.append(f"link {href} has no target on the page")
            elif href.startswith("/"):
                target = REPO_ROOT / "docs" / href.lstrip("/").split("#")[0]
                if not (target.exists() or (target / "index.html").exists()):
                    errs.append(f"internal link {href} does not exist")
            elif not href.startswith("https://"):
                errs.append(f"link {href!r} must be https:// or an in-page anchor")

    for s in data.get("sources") or []:
        for f in ("id", "publisher", "title", "url", "fetched"):
            if not str(s.get(f, "")).strip():
                errs.append(f"source {s.get('id', '?')}: {f} is required")
        if s.get("fetched") and not ISO_RE.match(str(s["fetched"])):
            errs.append(f"source {s.get('id', '?')}: fetched must be YYYY-MM-DD")
    return errs


def _place_errors(who: str, place, page_html: str) -> list[str]:
    if not isinstance(place, dict) or not (place.get("before") or place.get("after")):
        return [f"{who}: place {{'before': ...}} or {{'after': ...}} is required for the first build"]
    anchor = place.get("before") or place.get("after")
    if anchor not in page_html:
        return [f"{who}: place anchor {anchor[:60]!r} is not on the page"]
    return []


# ---------------------------------------------------------------- rendering

def render_definition(d: dict) -> str:
    aka = d.get("also_known_as") or []
    aka_html = (f'<p class="cc-definition-aka"><strong>Also known as:</strong> {esc(", ".join(aka))}.</p>'
                if aka else "")
    return (f'{DEF_START}\n<section class="cc-definition" id="definition">\n'
            f'<h2 class="cc-definition-q">{esc(d["question"])}</h2>\n{d["html"].strip()}\n{aka_html}\n'
            f"</section>\n{DEF_END}")


def render_faq(faq: dict) -> str:
    items = "\n".join(
        f'<div class="cc-faq-item">\n<h3 class="cc-faq-q">{esc(it["q"])}</h3>\n'
        f'<p class="cc-faq-a">{it["a"].strip()}</p>\n</div>'
        for it in faq["items"]
    )
    return (f'{FAQ_START}\n<section class="cc-faq" id="faq">\n'
            f'<h2 class="cc-faq-label">{esc(faq.get("label") or "Frequently Asked Questions")}</h2>\n'
            f'<div class="cc-faq-title">{esc(faq.get("title") or "Briefly Answered")}</div>\n'
            f"{items}\n</section>\n{FAQ_END}")


def render_schema(faq: dict) -> str:
    doc = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": it["q"],
             "acceptedAnswer": {"@type": "Answer", "text": plain(it["a"])}}
            for it in faq["items"]
        ],
    }
    body = json.dumps(doc, indent=2, ensure_ascii=False)
    return f'<script type="application/ld+json" data-cc-marker="AEO-FAQPAGE-SCHEMA">\n{body}\n</script>'


def put(page_html: str, start: str, end: str, block: str, place: dict | None) -> str:
    block_re = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if block_re.search(page_html):
        return block_re.sub(lambda _: block, page_html, count=1)
    place = place or {}
    if place.get("before"):
        i = page_html.index(place["before"])
        return page_html[:i] + block + "\n" + page_html[i:]
    anchor = place["after"]
    i = page_html.index(anchor) + len(anchor)
    return page_html[:i] + "\n" + block + page_html[i:]


def long_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def build_page(page_html: str, data: dict) -> str:
    out = page_html
    head_anchor = ASSETS_START if ASSETS_START in out else "</head>"
    out = put(out, CSS_START, CSS_END, f"{CSS_START}\n{CSS}\n{CSS_END}", {"before": head_anchor})
    if data.get("definition"):
        out = put(out, DEF_START, DEF_END, render_definition(data["definition"]), {"before": TLDR_TAG})
    faq = data.get("faq")
    if faq:
        out = put(out, FAQ_START, FAQ_END, render_faq(faq), faq.get("place"))
        schema = render_schema(faq)
        if FAQ_SCHEMA_RE.search(out):
            out = FAQ_SCHEMA_RE.sub(lambda _: schema, out, count=1)
        else:
            i = out.index(CSS_START)
            out = out[:i] + schema + "\n" + out[i:]
    iso = data["date_modified"]
    out = DATE_MODIFIED_RE.sub(lambda m: m.group(1) + iso + m.group(2), out, count=1)
    out = LAST_UPDATED_RE.sub(lambda m: m.group(1) + long_date(iso) + m.group(2), out, count=1)
    return out


def slugs_with_data(data_dir: Path = DATA_DIR) -> list[str]:
    return sorted(p.stem for p in data_dir.glob("*.json"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug", action="append")
    ap.add_argument("--check", action="store_true", help="validate only")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    errors = 0
    for slug in args.slug or slugs_with_data():
        path = DATA_DIR / f"{slug}.json"
        page = TOPICS_DIR / slug / "index.html"
        if not path.exists() or not page.exists():
            print(f"::error::{slug}: needs data/topic_reference/{slug}.json and a topic page")
            errors += 1
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        html = page.read_text(encoding="utf-8")
        problems = validate(data, slug, html, load_flagged(slug))
        for p in problems:
            print(f"::error::data/topic_reference/{slug}.json: {p}")
        if problems:
            errors += len(problems)
            continue
        if args.check:
            continue
        out = build_page(html, data)
        if out != html and not args.dry_run:
            page.write_text(out, encoding="utf-8")
        print(f"{slug}: {'changed' if out != html else 'unchanged'}")
    if errors:
        print(f"{errors} problem(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
