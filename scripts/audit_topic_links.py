#!/usr/bin/env python3
"""Audit every external link on docs/topics/*/index.html and write a report.

Why this exists
---------------
Topic pages are hand-curated and many of their external article links have
turned out to be fabricated or stale (see /topics/preaching/ April 2026).
This script HTTP-checks every link, classifies it as live / redirect /
broken / unreachable, and writes two artifacts:

  output/link_audit/report.json   — structured data, one row per occurrence
  output/link_audit/report.csv    — same data, spreadsheet-friendly

Runs locally OR in GitHub Actions. In the sandboxed Cowork environment
outbound HTTP is blocked; run this on your laptop or via the
link_audit.yml workflow instead.

Usage
-----
    python scripts/audit_topic_links.py
    python scripts/audit_topic_links.py --only preaching apologetics   # filter by slug
    python scripts/audit_topic_links.py --concurrency 8                # slow down
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:  # pragma: no cover
    print("This script requires `requests`. Install it: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
TOPICS_DIR = REPO_ROOT / "docs" / "topics"
OUT_DIR = REPO_ROOT / "output" / "link_audit"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
TIMEOUT = 25
MIN_GAP_SECONDS = 0.6  # per-domain politeness gap
SKIP_SUBSTRINGS = (
    "fonts.googleapis.com",
    "schema.org",
    "christiancurator.com",
)

ANCHOR_RE = re.compile(
    r'<a\s+[^>]*href=["\'](https?://[^"\'#]+)["\'][^>]*>([^<]*)</a>',
    re.IGNORECASE,
)


@dataclass
class LinkOccurrence:
    slug: str
    line: int
    url: str
    anchor: str


@dataclass
class CheckResult:
    url: str
    status: int | None
    final_url: str | None
    method: str | None
    error: str | None
    classification: str  # live | redirect | broken | unreachable

    @classmethod
    def from_raw(cls, url: str, status, final_url, method, error) -> "CheckResult":
        if error:
            cls_ = "unreachable"
        elif status and status < 300:
            cls_ = "live"
        elif status and status < 400:
            cls_ = "redirect"  # rare — we allow_redirects=True so most land as 2xx
        elif status == 403:
            # Persistent 403 after HEAD+GET fallback is almost always Cloudflare /
            # WAF bot-blocking, not a real broken page. Treat as 'blocked' so
            # human reviewers don't waste cycles re-curating live URLs.
            cls_ = "blocked"
        elif status == 429:
            cls_ = "rate_limited"
        else:
            cls_ = "broken"
        return cls(url=url, status=status, final_url=final_url, method=method, error=error, classification=cls_)


def extract_links(slug_filter: set[str] | None) -> list[LinkOccurrence]:
    out: list[LinkOccurrence] = []
    for page in sorted(TOPICS_DIR.glob("*/index.html")):
        slug = page.parent.name
        if slug_filter and slug not in slug_filter:
            continue
        with page.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                for m in ANCHOR_RE.finditer(line):
                    url = m.group(1).strip()
                    if any(s in url for s in SKIP_SUBSTRINGS):
                        continue
                    if url.lower().endswith((".jpg", ".png", ".svg", ".gif", ".webp")):
                        continue
                    anchor = m.group(2).strip()
                    out.append(LinkOccurrence(slug=slug, line=i, url=url, anchor=anchor))
    return out


_domain_locks: dict[str, threading.Lock] = {}
_domain_last: dict[str, float] = {}


def _throttle(url: str) -> None:
    domain = urlparse(url).netloc
    lock = _domain_locks.setdefault(domain, threading.Lock())
    with lock:
        last = _domain_last.get(domain, 0.0)
        wait = MIN_GAP_SECONDS - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        _domain_last[domain] = time.time()


def check_url(url: str) -> CheckResult:
    _throttle(url)
    session = requests.Session()
    session.headers.update(HEADERS)
    status = final_url = method = error = None
    try:
        resp = session.head(url, allow_redirects=True, timeout=TIMEOUT)
        method, status, final_url = "HEAD", resp.status_code, resp.url
        # Many CDNs reject HEAD; fall back to GET on suspicious status.
        if status in (400, 403, 405) or (status and status >= 500):
            resp = session.get(url, allow_redirects=True, timeout=TIMEOUT, stream=True)
            method, status, final_url = "GET", resp.status_code, resp.url
            resp.close()
    except requests.exceptions.Timeout:
        error = "timeout"
    except requests.exceptions.SSLError as e:
        error = f"ssl:{type(e).__name__}"
    except requests.exceptions.ConnectionError as e:
        error = f"conn:{type(e).__name__}"
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}:{str(e)[:120]}"
    return CheckResult.from_raw(url, status, final_url, method, error)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="Restrict to specific topic slugs")
    parser.add_argument("--concurrency", type=int, default=16, help="Max parallel requests")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug_filter = set(args.only) if args.only else None

    occurrences = extract_links(slug_filter)
    unique_urls = sorted({o.url for o in occurrences})
    print(
        f"Found {len(occurrences)} link occurrences across "
        f"{len({o.slug for o in occurrences})} topic pages "
        f"({len(unique_urls)} unique URLs)."
    )

    results: dict[str, CheckResult] = {}
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(check_url, u): u for u in unique_urls}
        for done_n, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            results[r.url] = r
            if done_n % 25 == 0 or done_n == len(unique_urls):
                elapsed = time.time() - start
                print(f"  checked {done_n}/{len(unique_urls)} ({elapsed:.0f}s)")

    # Report
    rows = []
    for o in occurrences:
        r = results[o.url]
        rows.append(
            {
                "slug": o.slug,
                "line": o.line,
                "anchor": o.anchor,
                "url": o.url,
                "classification": r.classification,
                "status": r.status,
                "final_url": r.final_url,
                "method": r.method,
                "error": r.error,
            }
        )

    json_path = OUT_DIR / "report.json"
    csv_path = OUT_DIR / "report.csv"
    json_path.write_text(json.dumps(rows, indent=2))
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    from collections import Counter
    summary = Counter(r["classification"] for r in rows)
    unique_summary = Counter(r.classification for r in results.values())
    cats = ("live", "redirect", "broken", "blocked", "rate_limited", "unreachable")
    print("\nResult summary (link occurrences):")
    for k in cats:
        print(f"  {k:12s} {summary.get(k, 0)}")
    print("\nResult summary (unique URLs):")
    for k in cats:
        print(f"  {k:12s} {unique_summary.get(k, 0)}")
    print(f"\nWrote: {json_path.relative_to(REPO_ROOT)}")
    print(f"Wrote: {csv_path.relative_to(REPO_ROOT)}")

    # Exit non-zero if ANY broken/unreachable — useful as a CI gate
    # Fail the run only on REAL broken pages (not bot-blocked or rate-limited,
    # which usually indicate the auditor is being filtered, not the URL).
    broken_count = summary.get("broken", 0) + summary.get("unreachable", 0)
    return 1 if broken_count else 0


if __name__ == "__main__":
    sys.exit(main())
