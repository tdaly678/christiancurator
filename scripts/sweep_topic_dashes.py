#!/usr/bin/env python3
"""Punctuation-only sweep of em and en dashes in hand-written topic page copy (S2 item 10).

Writing rule: no em dashes. This replaces them with commas (a paired aside "A, aside, B"), and en
dashes in number ranges with a hyphen. It never changes a word.

What it touches, on each live `docs/topics/<slug>/index.html`:
- visible text outside the marker blocks that builders own (any `<!-- X:START --> ... X:END -->` block is
  skipped; those blocks are written from data files and rebuilt by their builder)
- the `<meta name="description">` content and string values in JSON-LD outside the builder blocks (not a
  FAQPage schema on a page whose FAQ is builder-owned, `CC-FAQ`)

What it never touches:
- text inside quotation marks (curly or straight) or inside `<blockquote>`, `<q>`, `<cite>`
- the text of links to other sites (publisher headlines) and `<title>`
- `<style>` and non JSON-LD `<script>`

Dry run by default (prints counts per page); `--check` exits 1 when a page still needs the sweep; `--apply` writes. Idempotent: a second run finds nothing.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TOPICS = ROOT / "docs" / "topics"

DASH = "—–"
ENTITY_RE = re.compile(r"&(mdash|ndash|#8212|#8211|#x2014|#x2013);")
BLOCK_RE = re.compile(r"<!--\s*([A-Z0-9-]+(?::[A-Za-z0-9_-]+)?):START\s*-->.*?<!--\s*\1:END\s*-->", re.S)
TAG_RE = re.compile(r"<(/?)([a-zA-Z0-9]+)([^>]*)>|<!--.*?-->", re.S)
OUTLET_SUFFIX_RE = re.compile(
    r"\s+[—–]\s+(TGC(?: Essay)?|The Gospel Coalition|Crossway|Desiring God|Christianity Today|Ligonier|"
    r"Mere Orthodoxy|9Marks|Sam Storms|First Things|ERLC|BioLogos|CCEF|Acts 29)\s*$")
SKIP_TAGS ={"style", "blockquote", "q", "cite", "title", "textarea"}
QUOTE_RE = re.compile(r"(“[^”]*”|\"[^\"<>]*\"|‘[^’]{0,200}’(?![a-z]))")


COMMA_NEXT = {
    "and", "but", "or", "nor", "yet", "so", "not", "which", "who", "whom", "whose", "where", "when", "while",
    "even", "though", "although", "because", "since", "as", "if", "unless", "until", "a", "an", "rather",
    "including", "especially", "often", "sometimes", "usually", "just", "only", "too", "also", "then",
}


def _single(m: re.Match) -> str:
    nxt = re.sub(r"[^A-Za-z']", "", m.group(1)).lower()
    sentence = re.split(r"[.!?]\s", m.string[:m.start()])[-1]
    if not nxt or nxt in COMMA_NEXT or nxt.endswith("ing") or ":" in sentence:
        return ", "
    return ": "


def _fix_plain(text: str) -> str:
    """Replace dashes in text that has no quotation in it."""
    if not any(d in text for d in DASH):
        return text
    # number ranges: 1–3, 2010—2020
    text = re.sub(r"(\d)\s?[–—]\s?(\d)", r"\1-\2", text)
    # unspaced en dash joining two words (Luther–Owen, pre–Reformation) is a hyphen
    text = re.sub(r"(?<=[A-Za-z])–(?=[A-Za-z])", "-", text)
    # paired aside inside one sentence: "A — aside — B" -> "A, aside, B"
    text = re.sub(r"\s*[—–]\s*([^—–.!?;:]{1,160}?)\s*[—–]\s*", r", \1, ", text)
    # a leading dash right after a tag (attribution style) is dropped
    text = re.sub(r"^(\s*)[—–]\s*", r"\1", text)
    # a dash right before the end of the segment: keep a separator
    text = re.sub(r"\s*[—–]\s*$", ", ", text)
    # every other dash: a comma before a conjunction, relative word, participle or article ("A, and B",
    # "A, which B", "A, arguing B", "A, a note"); otherwise a colon, unless the sentence already has one
    text = re.sub(r"\s*[—–]\s*(?=(\S*))", _single, text)
    # tidy
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r",\s*([.;:!?)])", r"\1", text)
    text = re.sub(r"\(\s*,\s*", "(", text)
    return text


def fix_text(text: str) -> str:
    """Replace dashes outside quotations."""
    if not any(d in text for d in DASH):
        return text
    out, pos = [], 0
    for m in QUOTE_RE.finditer(text):
        out.append(_fix_plain(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_fix_plain(text[pos:]))
    return "".join(out)


def _fix_jsonld(js: str) -> str:
    def repl(m):
        inner = m.group(1)
        return '"' + fix_text(inner.replace('\\"', "\x00")).replace("\x00", '\\"') + '"'
    return re.sub(r'"((?:[^"\\]|\\.)*)"', repl, js)


def _fix_segment(html: str, builder_faq: bool = False) -> str:
    """Walk one region with no builder blocks in it."""
    out, pos = [], 0
    skip_stack: list[str] = []      # tags whose text we leave alone
    ext_link = 0                    # depth of external <a>
    script_kind = None
    for m in TAG_RE.finditer(html):
        text = html[pos:m.start()]
        if ext_link and not skip_stack:
            # our own " — Outlet" label after a publisher headline becomes " (Outlet)"
            text = OUTLET_SUFFIX_RE.sub(r" (\1)", text)
        if script_kind == "ld":
            # a FAQPage schema written by build_topic_reference.py must keep matching its builder-owned FAQ
            if not (builder_faq and "FAQPage" in text):
                text = _fix_jsonld(text)
        elif script_kind is None and not skip_stack and not ext_link:
            text = fix_text(text)
        out.append(text)
        tag = m.group(0)
        if m.group(2):
            closing, name, attrs = m.group(1) == "/", m.group(2).lower(), m.group(3)
            if name == "script":
                script_kind = None if closing else ("ld" if "ld+json" in attrs else "other")
            elif name in SKIP_TAGS and not attrs.rstrip().endswith("/"):
                if closing:
                    if name in skip_stack:
                        skip_stack.remove(name)
                else:
                    skip_stack.append(name)
            elif name == "a":
                if closing:
                    ext_link = max(0, ext_link - 1) if ext_link else 0
                elif re.search(r'href="https?://(?!www\.christiancurator\.com)', attrs):
                    ext_link += 1
            elif name == "meta" and re.search(r'name="description"', attrs):
                tag = re.sub(r'content="([^"]*)"', lambda c: 'content="' + fix_text(c.group(1)) + '"', tag)
        out.append(tag)
        pos = m.end()
    out.append(html[pos:])
    return "".join(out)


def sweep(html: str) -> str:
    html = ENTITY_RE.sub(lambda m: "—" if m.group(1) in ("mdash", "#8212", "#x2014") else "–", html) \
        if ENTITY_RE.search(html) else html
    builder_faq = "<!-- CC-FAQ:START" in html
    out, pos = [], 0
    for m in BLOCK_RE.finditer(html):
        out.append(_fix_segment(html[pos:m.start()], builder_faq))
        out.append(m.group(0))
        pos = m.end()
    out.append(_fix_segment(html[pos:], builder_faq))
    return "".join(out)


def live_pages() -> list[Path]:
    try:
        from frontend.topic_redirects import retired_topic_slugs
        retired = set(retired_topic_slugs())
    except Exception:
        retired = set()
    return sorted(p / "index.html" for p in TOPICS.iterdir()
                  if p.is_dir() and p.name not in retired and (p / "index.html").exists())


def count_dashes(html: str) -> int:
    return sum(html.count(d) for d in DASH)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true", help="exit 1 if any page still has a dash to sweep")
    ap.add_argument("--slug", action="append")
    args = ap.parse_args(argv)
    total_before = total_after = changed = 0
    for page in live_pages():
        if args.slug and page.parent.name not in args.slug:
            continue
        html = page.read_text(encoding="utf-8")
        new = sweep(html)
        b, a = count_dashes(html), count_dashes(new)
        total_before += b
        total_after += a
        if new != html:
            changed += 1
            print(f"{page.parent.name}: {b} -> {a}")
            if args.apply:
                page.write_text(new, encoding="utf-8")
    print(f"{'Rewrote' if args.apply else 'Would rewrite'} {changed} page(s); dashes {total_before} -> {total_after} "
          f"(the rest are in quotes, publisher link text or builder blocks)")
    return 1 if (args.check and changed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
