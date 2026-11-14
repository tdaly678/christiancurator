#!/usr/bin/env python3
"""Voices quality gate (voices cleanup, Nov 12 2026).

Checks every page under docs/voices/ and docs/voices_data.json:

  bar              an indexable voice page must meet curator.voice_pilot.needs_noindex():
                   "reviewed": true, or 2+ of the writer's own verified pieces plus a
                   sourced bio (bio_sources). Ratcheted: pages listed in
                   scripts/voices_check_baseline.json may still fail (they await a
                   sourced bio or a noindex decision); any other page may not.
  noindex          a slug in frontend/voices_noindex.json must carry a robots noindex
                   tag and be absent from sitemap-voices.xml.
  dash             no em or en dash in a voice page's visible text or in voices_data.json.
  posting-account  a retired slug (voices_redirects.json "to": "") is a stub, has no
                   voices_data.json record, and is linked from no page under docs/.
  title            every Recent Articles headline on a voice page equals the publisher's
                   headline (archive meta.json original_title or data/original_titles.json).
  deceased         a deceased writer's Recent Articles list nothing curated after the death
                   (build_recent_articles.before_death).

Exit 1 on any violation outside the baseline.

    python scripts/check_voices.py                    # gate
    python scripts/check_voices.py --report           # list every violation
    python scripts/check_voices.py --update-baseline  # lock in the current bar failures
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_recent_articles as recent  # noqa: E402
from curator import voice_pilot as vp  # noqa: E402
from curator.voice_filters import HUB_SLUGS  # noqa: E402

DOCS = REPO_ROOT / "docs"
VOICES = DOCS / "voices"
DATA = DOCS / "voices_data.json"
NOINDEX = REPO_ROOT / "frontend" / "voices_noindex.json"
REDIRECTS = REPO_ROOT / "frontend" / "voices_redirects.json"
SITEMAP = DOCS / "sitemap-voices.xml"
BASELINE = Path(__file__).resolve().parent / "voices_check_baseline.json"

DASH_RE = re.compile("[–—]")
ROBOTS_NOINDEX_RE = re.compile(r'<meta\b[^>]*name="robots"[^>]*content="[^"]*noindex|'
                               r'<meta\b[^>]*content="[^"]*noindex[^"]*"[^>]*name="robots"', re.I)
RECENT_LINK_RE = re.compile(r'<a class="cc-recent-link" href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def visible_text(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    return html_mod.unescape(re.sub(r"<[^>]+>", " ", page))


def is_stub(page: str) -> bool:
    return 'http-equiv="refresh"' in page and "cc-voice-name" not in page


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def run_checks() -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {k: [] for k in
                                              ("bar", "noindex", "dash", "posting-account", "title",
                                               "deceased")}
    data = load_json(DATA, [])
    by_slug = {v["slug"]: v for v in data}
    pilot = {w["slug"]: w for w in vp.load_pilot()["writers"]}
    noindex = set(load_json(NOINDEX, []))
    redirects = load_json(REDIRECTS, {})
    retired = {s for s, r in redirects.items() if not r.get("to")}
    sitemap = SITEMAP.read_text(encoding="utf-8") if SITEMAP.exists() else ""
    in_sitemap = set(re.findall(r"/voices/([a-z0-9-]+)/</loc>", sitemap))

    # Expected Recent Articles headlines, keyed (slug, url). Pages link the URL
    # with utm_* parameters stripped (build_recent_articles.strip_tracking).
    by_voice = recent.collect_by_voice()
    clean = recent.strip_tracking
    expected = {(s, clean(i["url"])): recent.strip_dashes(i["title"]) for s, items in by_voice.items() for i in items}
    deaths = recent.death_dates()
    allowed = {(s, clean(i["url"])) for s, items in by_voice.items()
               for i in recent.before_death(items, deaths.get(s))}

    for d in sorted(p for p in VOICES.iterdir() if p.is_dir()):
        slug = d.name
        path = d / "index.html"
        if slug in HUB_SLUGS or not path.exists():
            continue
        page = path.read_text(encoding="utf-8", errors="replace")
        if DASH_RE.search(visible_text(page)):
            hit = DASH_RE.search(visible_text(page))
            text = visible_text(page)
            out["dash"].append((slug, " ".join(text[max(0, hit.start() - 40):hit.end() + 40].split())))
        if is_stub(page):
            continue
        if slug in retired:
            out["posting-account"].append((slug, "retired slug is a full page, not a stub"))
        has_robots_noindex = bool(ROBOTS_NOINDEX_RE.search(page))
        if slug in noindex and not has_robots_noindex:
            out["noindex"].append((slug, "listed in voices_noindex.json but the page has no robots noindex"))
        if (slug in noindex or has_robots_noindex) and slug in in_sitemap:
            out["noindex"].append((slug, "noindexed page is in sitemap-voices.xml"))
        indexable = slug not in noindex and not has_robots_noindex
        entry = pilot.get(slug) or by_slug.get(slug) or {"slug": slug}
        credited = {i["url"] for i in by_voice.get(slug, [])}
        if indexable and vp.needs_noindex(entry, credited):
            out["bar"].append((slug, f"{vp.own_piece_count(entry, credited)} piece(s), "
                                     f"sourced bio: {vp.has_sourced_bio(entry)}"))
        for url, raw in RECENT_LINK_RE.findall(page):
            shown = " ".join(html_mod.unescape(re.sub(r"<[^>]+>", "", raw)).split())
            url = clean(html_mod.unescape(url))
            want = expected.get((slug, url))
            if slug in deaths and (slug, url) not in allowed:
                out["deceased"].append((slug, f"{url} was curated after the writer's death"))
            if want is None:
                out["title"].append((slug, f"no publisher headline known for {url}"))
            elif shown != " ".join(want.split()):
                out["title"].append((slug, f"{shown!r} is not the publisher headline {want!r}"))

    for v in data:
        if DASH_RE.search(json.dumps(v, ensure_ascii=False)):
            out["dash"].append((v["slug"], "voices_data.json record"))
        if v["slug"] in retired:
            out["posting-account"].append((v["slug"], "retired slug has a voices_data.json record"))

    if retired:
        link_re = re.compile(r'href="(?:https://www\.christiancurator\.com)?/voices/('
                             + "|".join(map(re.escape, sorted(retired))) + r')/"')
        for path in DOCS.rglob("*.html"):
            if path.parent.name in retired and path.parent.parent == VOICES:
                continue
            for slug in set(link_re.findall(path.read_text(encoding="utf-8", errors="replace"))):
                out["posting-account"].append((slug, f"linked from {path.relative_to(DOCS)}"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args(argv)
    results = run_checks()
    bar_slugs = sorted({s for s, _ in results["bar"]})
    if args.update_baseline:
        BASELINE.write_text(json.dumps({"bar": bar_slugs}, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline written: {len(bar_slugs)} page(s) below the indexing bar.")
        return 0
    baseline = set(load_json(BASELINE, {}).get("bar", []))
    failures = [(k, s, why) for k, rows in results.items() for s, why in rows
                if not (k == "bar" and s in baseline)]
    for k, rows in results.items():
        if args.report:
            for s, why in rows:
                print(f"{k}: {s}: {why}")
    for k, s, why in failures:
        print(f"::error title=Voices check::{k}: {s}: {why}")
    fixed = sorted(baseline - set(bar_slugs))
    if fixed:
        print(f"{len(fixed)} baselined page(s) now pass or are noindexed; run --update-baseline to lock it in.")
    counts = ", ".join(f"{k} {len(v)}" for k, v in results.items())
    print(f"Voices check: {counts}; {len(baseline & set(bar_slugs))} baselined; {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
