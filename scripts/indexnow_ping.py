#!/usr/bin/env python3
"""Ping IndexNow (Bing / Yandex / Seznam / DuckDuckGo, etc.) with changed URLs.

Usage:
    python3 scripts/indexnow_ping.py            # diff vs HEAD~1, submit changed URLs only
    python3 scripts/indexnow_ping.py --all      # submit every URL in the sitemaps (use sparingly)

IndexNow accepts up to 10,000 URLs per request. Google does NOT use IndexNow,
so this is mainly a Bing / Yandex / Seznam booster — but it's free and instant.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
HOST = "www.christiancurator.com"
BASE = f"https://{HOST}"
KEY = "7dc7799e4f9634a7d6540b3cb92c30e7"
KEY_LOCATION = f"{BASE}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/IndexNow"
MAX_PER_BATCH = 10000


def all_sitemap_urls() -> list[str]:
    """Extract every <loc> from every per-section sitemap-*.xml."""
    urls: list[str] = []
    for sm in sorted(DOCS_DIR.glob("sitemap-*.xml")):
        text = sm.read_text(encoding="utf-8")
        urls.extend(re.findall(r"<loc>([^<]+)</loc>", text))
    # dedupe, preserve order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def changed_urls_since(ref: str = "HEAD~1") -> list[str]:
    """Map files changed since `ref` to public URLs.

    Maps:
      docs/index.html               -> /
      docs/<dir>/index.html         -> /<dir>/
      docs/<a>/<b>/index.html       -> /<a>/<b>/
    Skips non-html and infra files (sitemap*.xml, _pagefind, json data).
    """
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", ref, "HEAD", "--", "docs/"],
            cwd=REPO_ROOT,
            text=True,
        )
    except subprocess.CalledProcessError:
        return []

    urls: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or not line.endswith("index.html"):
            continue
        # strip "docs/" prefix and "/index.html" suffix
        rel = line[len("docs/") :] if line.startswith("docs/") else line
        rel = rel[: -len("index.html")]
        # rel is now "" (root) or "topics/abortion/" etc.
        urls.append(f"{BASE}/{rel}")
    # dedupe
    return sorted(set(urls))


def submit(urls: list[str]) -> None:
    if not urls:
        print("indexnow: no URLs to submit")
        return
    for i in range(0, len(urls), MAX_PER_BATCH):
        batch = urls[i : i + MAX_PER_BATCH]
        body = json.dumps(
            {
                "host": HOST,
                "key": KEY,
                "keyLocation": KEY_LOCATION,
                "urlList": batch,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            ENDPOINT,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
                print(f"indexnow: submitted batch of {len(batch)} URLs -> HTTP {status}")
        except Exception as e:
            print(f"indexnow: submission failed: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="submit every URL from sitemaps")
    ap.add_argument("--ref", default="HEAD~1", help="git ref to diff against (default HEAD~1)")
    ap.add_argument("--dry-run", action="store_true", help="print URLs but don't POST")
    args = ap.parse_args()

    if args.all:
        urls = all_sitemap_urls()
        print(f"indexnow: --all mode, {len(urls)} URLs from sitemaps")
    else:
        urls = changed_urls_since(args.ref)
        print(f"indexnow: {len(urls)} URLs changed since {args.ref}")

    if args.dry_run:
        for u in urls[:25]:
            print(f"  {u}")
        if len(urls) > 25:
            print(f"  ... and {len(urls) - 25} more")
        return 0

    submit(urls)
    return 0


if __name__ == "__main__":
    sys.exit(main())
