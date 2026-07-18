#!/usr/bin/env python3
"""build_recent_articles.py — Add "Recent articles" sections to voice and topic pages.

Voice pages get "Recent articles by <name>" built from archive-page bylines
(every curated article whose byline links to that voice). Topic pages get
"Recent articles on this topic" built from article_history.json matched via
frontend.topic_matcher keyword lists.

Both sections are wrapped in marker comments and rewritten in place on each
run, so the daily pipeline keeps them fresh — a recurring freshness signal on
otherwise-static evergreen pages, plus genuinely useful recent reading for
visitors.

Idempotent; safe to re-run anytime.
"""
from __future__ import annotations

import html as html_mod
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from frontend.topic_matcher import TOPICS, _normalise  # noqa: E402

DOCS_DIR = REPO_ROOT / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"
VOICES_DIR = DOCS_DIR / "voices"
TOPICS_DIR = DOCS_DIR / "topics"
HISTORY = DOCS_DIR / "article_history.json"

V_START = "<!-- CC-RECENT-ARTICLES:START -->"
V_END = "<!-- CC-RECENT-ARTICLES:END -->"

MAX_ITEMS = 5

STYLE = (
    "<style>"
    ".cc-recent{margin-top:2.5rem;padding-top:1.75rem;border-top:2px solid #e0ddd8;}"
    ".cc-recent-label{font-size:10px;font-weight:700;letter-spacing:0.16em;"
    "text-transform:uppercase;color:#2C4A2E;margin-bottom:0.5rem;}"
    ".cc-recent-title{font-family:'Lora',Georgia,serif;font-size:22px;font-weight:600;"
    "margin-bottom:1.25rem;color:#1a1a1a;}"
    ".cc-recent-item{margin-bottom:1.1rem;}"
    ".cc-recent-item:last-child{margin-bottom:0;}"
    ".cc-recent-link{font-family:'Lora',Georgia,serif;font-size:16px;font-weight:600;"
    "line-height:1.35;color:#1a1a1a;text-decoration:none;}"
    ".cc-recent-link:hover{color:#2C4A2E;text-decoration:underline;}"
    ".cc-recent-meta{font-size:12px;color:#888;margin-top:2px;}"
    "</style>"
)


def _esc(t: str) -> str:
    return html_mod.escape(t or "", quote=True)


def _fmt_date(iso: str) -> str:
    from datetime import date
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return date(y, m, d).strftime("%B %-d, %Y")
    except Exception:
        return iso


ARTICLE_RE = re.compile(r"<article\b.*?</article>", re.DOTALL)
TITLE_RE = re.compile(
    r'<a href="(https?://[^"]+)" class="cc-(?:lead-title|article-title)"[^>]*>\s*(.*?)\s*</a>',
    re.DOTALL,
)
VOICE_RE = re.compile(r'href="/voices/([a-z0-9-]+)/"')
SOURCE_RE = re.compile(r"'article_source':'([^']*)'")


def collect_by_voice() -> dict[str, list[dict]]:
    by_voice: dict[str, dict[str, dict]] = {}
    if not ARCHIVE_DIR.exists():
        return {}
    for day_dir in sorted(ARCHIVE_DIR.iterdir()):
        idx = day_dir / "index.html"
        if not day_dir.is_dir() or not idx.exists():
            continue
        date_iso = day_dir.name
        h = idx.read_text(encoding="utf-8", errors="replace")
        for block in ARTICLE_RE.finditer(h):
            b = block.group(0)
            t = TITLE_RE.search(b)
            if not t:
                continue
            url = t.group(1)
            title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t.group(2))).strip()
            src = SOURCE_RE.search(b)
            source = src.group(1) if src else ""
            for slug in set(VOICE_RE.findall(b)):
                entry = {"date": date_iso, "title": title, "url": url, "source": source}
                cur = by_voice.setdefault(slug, {})
                prev = cur.get(url)
                if not prev or date_iso > prev["date"]:
                    cur[url] = entry
    return {
        slug: sorted(items.values(), key=lambda a: a["date"], reverse=True)
        for slug, items in by_voice.items()
    }


def render_section(heading_label: str, heading: str, items: list[dict]) -> str:
    rows = []
    for a in items[:MAX_ITEMS]:
        meta_bits = [b for b in (a["source"], _fmt_date(a["date"])) if b]
        rows.append(
            f'\n  <div class="cc-recent-item">'
            f'\n    <a class="cc-recent-link" href="{_esc(a["url"])}" target="_blank" rel="noopener">{_esc(a["title"])}</a>'
            f'\n    <div class="cc-recent-meta">{_esc(" · ".join(meta_bits))}</div>'
            f'\n  </div>'
        )
    return (
        f"\n{V_START}\n"
        f'<section class="cc-recent">{STYLE}'
        f'\n  <div class="cc-recent-label">{_esc(heading_label)}</div>'
        f'\n  <h2 class="cc-recent-title">{_esc(heading)}</h2>'
        + "".join(rows)
        + f"\n</section>\n{V_END}\n"
    )


def inject(html: str, section: str) -> str | None:
    html = re.sub(
        re.escape(V_START) + r".*?" + re.escape(V_END) + r"\s*",
        "",
        html,
        flags=re.DOTALL,
    )
    for anchor in (
        "<!-- AEO-TOPIC-BACKLINKS:START -->",
        '<section class="cc-faq"',
        '<a class="cc-back-link"',
        "</main>",
    ):
        pos = html.find(anchor)
        if pos != -1:
            return html[:pos] + section + html[pos:]
    return None


def update_voices() -> int:
    by_voice = collect_by_voice()
    voices_data = json.loads((DOCS_DIR / "voices_data.json").read_text(encoding="utf-8"))
    names = {v["slug"]: v["name"] for v in voices_data}
    n = 0
    for slug, items in by_voice.items():
        page = VOICES_DIR / slug / "index.html"
        if not page.exists() or slug not in names:
            continue
        section = render_section(
            "From Our Daily Digest", f"Recent Articles by {names[slug]}", items
        )
        html = page.read_text(encoding="utf-8")
        out = inject(html, section)
        if out and out != html:
            page.write_text(out, encoding="utf-8")
            n += 1
    return n


def match_articles_to_topic(topic: dict, history: list[dict]) -> list[dict]:
    kws = [k.lower() for k in topic["keywords"]]
    out = []
    for a in reversed(history):  # newest last in file -> iterate newest first
        text = _normalise(a.get("title", "") + " " + " ".join(a.get("tags", [])))
        if any(k in text for k in kws):
            out.append(
                {
                    "date": a.get("date_shown", ""),
                    "title": a.get("title", ""),
                    "url": a.get("url", ""),
                    "source": a.get("source_name", ""),
                }
            )
        if len(out) >= MAX_ITEMS:
            break
    # dedupe by url, keep order
    seen, deduped = set(), []
    for a in out:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        deduped.append(a)
    return deduped


def update_topics() -> int:
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    n = 0
    for topic in TOPICS:
        page = TOPICS_DIR / topic["slug"] / "index.html"
        if not page.exists():
            continue
        items = match_articles_to_topic(topic, history)
        if len(items) < 2:  # don't render a thin section
            continue
        section = render_section(
            "Fresh From the Digest", f"Recent Articles on {topic['label']}", items
        )
        html = page.read_text(encoding="utf-8")
        out = inject(html, section)
        if out and out != html:
            page.write_text(out, encoding="utf-8")
            n += 1
    return n


def main() -> int:
    nv = update_voices()
    nt = update_topics()
    print(f"recent-articles sections: {nv} voice pages, {nt} topic pages updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
