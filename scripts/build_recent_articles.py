#!/usr/bin/env python3
"""build_recent_articles.py — Add "Recent articles" sections to voice and topic pages.

Voice pages get "Recent articles by <name>" built from archive-page bylines
(every curated article whose byline links to that voice). Topic pages get
"Recent articles on this topic" built from article_history.json matched via
frontend.topic_matcher keyword lists.

Topic pages also get the stories the daily data watch matched to them
(`fresh` in docs/data_watch.json, written by scripts/run_data_watch.py), so a
page outside the keyword list still shows a survey story placed on the digest.

Headlines are the publisher's own (Nov 12 2026): a writer is never credited
with a front-page rewrite. Archive pages from Nov 12 on store `original_title`
in meta.json; older rows use the headline recovered by
scripts/backfill_original_titles.py (data/original_titles.json). An item whose
publisher headline is unknown is left off the page.

Topic pages with a top-of-page block (scripts/build_topic_top.py) also carry a
one-line "Latest" list between <!-- CC-TOPIC-LATEST:START/END --> markers. It
reads the same items (topic_items()) and is refreshed here on every run, so the
line near the top and the block near the bottom never disagree.

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

from curator.headline_voice import strip_dashes  # noqa: E402
from curator.original_titles import lookup, publisher_title  # noqa: E402
from frontend.topic_matcher import TOPICS, _normalise  # noqa: E402

DOCS_DIR = REPO_ROOT / "docs"
ARCHIVE_DIR = DOCS_DIR / "archive"
VOICES_DIR = DOCS_DIR / "voices"
TOPICS_DIR = DOCS_DIR / "topics"
HISTORY = DOCS_DIR / "article_history.json"
PILOT = REPO_ROOT / "data" / "voices" / "pilot.json"
DATA_WATCH = DOCS_DIR / "data_watch.json"
EXCLUSIONS = REPO_ROOT / "data" / "voices" / "recent_exclusions.json"

V_START = "<!-- CC-RECENT-ARTICLES:START -->"
V_END = "<!-- CC-RECENT-ARTICLES:END -->"
L_START = "<!-- CC-TOPIC-LATEST:START -->"
L_END = "<!-- CC-TOPIC-LATEST:END -->"
LATEST_MAX_ITEMS = 3

MAX_ITEMS = 5
# Voice pages list up to 10 recent pieces (Voices pilot, Nov 2026).
VOICE_MAX_ITEMS = 10

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


def _meta_original_titles(day_dir: Path) -> dict[str, str]:
    try:
        meta = json.loads((day_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {a["url"]: a["original_title"] for a in meta.get("articles", [])
            if a.get("url") and a.get("original_title")}


def original_title_for(url: str, meta_titles: dict[str, str]) -> str | None:
    """Publisher headline for a saved article, or None when unknown."""
    return meta_titles.get(url) or lookup(url)


def collect_by_voice(*, dropped: list | None = None) -> dict[str, list[dict]]:
    """Archive pieces per voice slug, newest first, with publisher headlines.

    Pieces whose publisher headline is unknown are skipped (and appended to
    `dropped` when given)."""
    by_voice: dict[str, dict[str, dict]] = {}
    if not ARCHIVE_DIR.exists():
        return {}
    for day_dir in sorted(ARCHIVE_DIR.iterdir()):
        idx = day_dir / "index.html"
        if not day_dir.is_dir() or not idx.exists():
            continue
        date_iso = day_dir.name
        meta_titles = _meta_original_titles(day_dir)
        h = idx.read_text(encoding="utf-8", errors="replace")
        for block in ARTICLE_RE.finditer(h):
            b = block.group(0)
            t = TITLE_RE.search(b)
            if not t:
                continue
            url = t.group(1)
            src = SOURCE_RE.search(b)
            source = src.group(1) if src else ""
            original = original_title_for(url, meta_titles)
            if not original:
                if dropped is not None and VOICE_RE.search(b):
                    dropped.append({"date": date_iso, "url": url,
                                    "slugs": sorted(set(VOICE_RE.findall(b)))})
                continue
            title = publisher_title(original, source, url)
            for slug in set(VOICE_RE.findall(b)):
                entry = {"date": date_iso, "title": title, "url": url, "source": source}
                cur = by_voice.setdefault(slug, {})
                prev = cur.get(url)
                if not prev or date_iso > prev["date"]:
                    cur[url] = entry
    rules = load_exclusions()
    out = {
        slug: [a for a in sorted(items.values(), key=lambda a: a["date"], reverse=True)
               if not is_excluded(a, rules.get(slug, []))]
        for slug, items in by_voice.items()
    }
    return {slug: items for slug, items in out.items() if items}


def load_exclusions(path: Path | None = None) -> dict[str, list[dict]]:
    """Slug -> rules from data/voices/recent_exclusions.json ("_about" skipped)."""
    try:
        data = json.loads((path or EXCLUSIONS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, list)}


def is_excluded(item: dict, rules: list[dict]) -> bool:
    """True when a rule names this piece by url or by publisher headline (Nov 13
    2026: a single bad item comes off one writer's block, not the whole block)."""
    title = " ".join((item.get("title") or "").split()).lower()
    for r in rules:
        if r.get("url") and r["url"] == item.get("url"):
            return True
        if r.get("title") and " ".join(r["title"].split()).lower() == title:
            return True
    return False


def death_dates() -> dict[str, str]:
    """Slug -> death date for every writer marked deceased, from voices_data.json
    and data/voices/pilot.json (pilot wins). The date is ISO ("2017-12-14") or a
    year ("1683"); "" when the writer is deceased but no date is recorded."""
    out: dict[str, str] = {}
    for path, key in ((DOCS_DIR / "voices_data.json", None), (PILOT, "writers")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for v in (rows.get(key, []) if key else rows):
            if v.get("deceased") or v.get("died"):
                out[v["slug"]] = str(v.get("died") or out.get(v["slug"], ""))
    return out


def before_death(items: list[dict], died: str | None) -> list[dict]:
    """Recent Articles for a deceased writer (overnight Nov 12 2026): a piece we
    curated after the writer's death is a republication, so only pieces dated on
    or before the death are listed. With no recorded date, none are (our archive
    starts in 2026). Living writers (died None) keep every piece."""
    if died is None:
        return items
    if not died:
        return []
    return [i for i in items if i["date"][:len(died)] <= died]


def render_section(heading_label: str, heading: str, items: list[dict],
                   limit: int = MAX_ITEMS, section_id: str = "") -> str:
    id_attr = f' id="{section_id}"' if section_id else ""
    rows = []
    for a in items[:limit]:
        meta_bits = [b for b in (a["source"], _fmt_date(a["date"])) if b]
        rows.append(
            f'\n  <div class="cc-recent-item">'
            f'\n    <a class="cc-recent-link" href="{_esc(a["url"])}" target="_blank" rel="noopener">{_esc(strip_dashes(a["title"]))}</a>'
            f'\n    <div class="cc-recent-meta">{_esc(" · ".join(meta_bits))}</div>'
            f'\n  </div>'
        )
    return (
        f"\n{V_START}\n"
        f'<section class="cc-recent"{id_attr}>{STYLE}'
        f'\n  <div class="cc-recent-label">{_esc(heading_label)}</div>'
        f'\n  <h2 class="cc-recent-title">{_esc(heading)}</h2>'
        + "".join(rows)
        + f"\n</section>\n{V_END}\n"
    )


def inject(html: str, section: str) -> str | None:
    # Replace an existing block where it sits. Removing it and re-inserting at
    # an anchor left one extra blank line on the page every daily run.
    block_re = re.compile(re.escape(V_START) + r".*?" + re.escape(V_END), re.DOTALL)
    if block_re.search(html):
        return block_re.sub(lambda _: section.strip("\n"), html, count=1)
    for anchor in (
        "<!-- AEO-TOPIC-BACKLINKS:START -->",
        "<!-- CC-FAQ:START -->",
        '<section class="cc-faq"',
        '<a class="cc-back-link"',
        "</main>",
    ):
        pos = html.find(anchor)
        if pos != -1:
            return html[:pos] + section + html[pos:]
    return None


def remove_block(html: str) -> str:
    """Drop the Recent Articles block (and the newline before it)."""
    return re.sub(r"\n?" + re.escape(V_START) + r".*?" + re.escape(V_END) + r"\n?", "\n",
                  html, count=1, flags=re.DOTALL)


def update_voices() -> int:
    deaths = death_dates()
    by_voice = {slug: before_death(items, deaths.get(slug))
                for slug, items in collect_by_voice().items()}
    by_voice = {slug: items for slug, items in by_voice.items() if items}
    voices_data = json.loads((DOCS_DIR / "voices_data.json").read_text(encoding="utf-8"))
    names = {v["slug"]: v["name"] for v in voices_data}
    n = 0
    # A voice left with no credited piece (reattributed byline, unknown
    # publisher headline) loses its stale block rather than keep old credits.
    for slug in names:
        if slug in by_voice:
            continue
        page = VOICES_DIR / slug / "index.html"
        if page.exists():
            html = page.read_text(encoding="utf-8")
            if V_START in html:
                page.write_text(remove_block(html), encoding="utf-8")
                n += 1
    for slug, items in by_voice.items():
        page = VOICES_DIR / slug / "index.html"
        if not page.exists() or slug not in names:
            continue
        section = render_section(
            "From Our Daily Digest", f"Recent Articles by {names[slug]}", items,
            limit=VOICE_MAX_ITEMS,
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
        original = a.get("original_title") or lookup(a.get("url", ""))
        if not original:
            continue
        text = _normalise(original + " " + " ".join(a.get("tags", [])))
        if any(k in text for k in kws):
            out.append(
                {
                    "date": a.get("date_shown", ""),
                    "title": publisher_title(original, a.get("source_name", ""), a.get("url", "")),
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


def load_data_watch_fresh(path: Path = DATA_WATCH) -> dict[str, list[dict]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("fresh") or {}
    except (OSError, ValueError):
        return {}


def merge_items(keyword_items: list[dict], watch_items: list[dict]) -> list[dict]:
    """Keyword matches plus data-watch stories, newest first, one per URL."""
    seen, out = set(), []
    for a in sorted(keyword_items + watch_items, key=lambda a: a.get("date", ""), reverse=True):
        if not a.get("url") or a["url"] in seen:
            continue
        seen.add(a["url"])
        out.append(a)
    return out[:MAX_ITEMS]


def _short_date(iso: str) -> str:
    from datetime import date
    try:
        y, m, d = (int(x) for x in iso[:10].split("-"))
        return date(y, m, d).strftime("%b %-d")
    except Exception:
        return ""


def render_latest_line(items: list[dict], limit: int = LATEST_MAX_ITEMS) -> str:
    """The top-of-page "Latest" line: Title, Outlet, Nov 9 (one to three items).

    Returns the marker pair with nothing between when there are no items, so the
    line disappears instead of going stale.
    """
    if not items:
        return f"{L_START}{L_END}"
    parts = []
    for a in items[:limit]:
        meta = ", ".join(b for b in (a.get("source", ""), _short_date(a.get("date", ""))) if b)
        parts.append(
            f'<a href="{_esc(a["url"])}" target="_blank" rel="noopener" data-pos="topic-latest"'
            f' data-src="{_esc(a.get("source", ""))}">{_esc(strip_dashes(a["title"]))}</a>'
            + (f' <span class="cc-tt-latest-meta">{_esc(meta)}</span>' if meta else "")
        )
    return (
        f'{L_START}<p class="cc-tt-latest" id="latest"><span class="cc-tt-label">Latest</span>'
        + '<span class="cc-tt-latest-sep">·</span>'.join(parts)
        + f"</p>{L_END}"
    )


def refresh_latest_line(html: str, items: list[dict]) -> str:
    """Replace an existing CC-TOPIC-LATEST block; pages without one are untouched."""
    block_re = re.compile(re.escape(L_START) + r".*?" + re.escape(L_END), re.DOTALL)
    if not block_re.search(html):
        return html
    return block_re.sub(lambda _: render_latest_line(items), html, count=1)


def topic_list() -> list[dict]:
    """Keyword topics from frontend.topic_matcher plus every slug the data watch fed."""
    from frontend.topics_data import TOPICS as ALL_TOPICS

    fresh = load_data_watch_fresh()
    names = {t["slug"]: t["name"] for t in ALL_TOPICS}
    return list(TOPICS) + [
        {"slug": slug, "label": names.get(slug, slug), "keywords": []}
        for slug in sorted(fresh) if slug not in {t["slug"] for t in TOPICS}
    ]


def topic_items(slug: str, history: list[dict] | None = None,
                fresh: dict[str, list[dict]] | None = None) -> list[dict]:
    """The items a topic page lists: keyword matches plus data-watch stories."""
    if history is None:
        history = json.loads(HISTORY.read_text(encoding="utf-8"))
    if fresh is None:
        fresh = load_data_watch_fresh()
    topic = next((t for t in TOPICS if t["slug"] == slug), None)
    keyword_items = match_articles_to_topic(topic, history) if topic and topic["keywords"] else []
    return merge_items(keyword_items, fresh.get(slug, []))


def update_topics() -> int:
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    fresh = load_data_watch_fresh()
    n = 0
    for topic in topic_list():
        page = TOPICS_DIR / topic["slug"] / "index.html"
        if not page.exists():
            continue
        watch_items = fresh.get(topic["slug"], [])
        items = topic_items(topic["slug"], history, fresh)
        html = page.read_text(encoding="utf-8")
        out = refresh_latest_line(html, items)
        # don't render a thin section, unless a data-watch story is in it
        if len(items) >= 2 or watch_items:
            section = render_section(
                "Fresh From the Digest", f"Recent Articles on {topic['label']}", items,
                section_id="recent",
            )
            out = inject(out, section) or out
        if out != html:
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
