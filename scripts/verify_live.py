#!/usr/bin/env python3
"""Confirm today's edition is live on christiancurator.com after the daily push.

The daily workflow pushes to main and GitHub Pages deploys it on its own
(pages-build-deployment). That deploy can be cancelled by a later push (12
times Nov 12 to 14 2026, benign: the later build deploys) or stall in
`syncing_files` until it times out (Nov 10 2026), which leaves the site on the
previous commit with nothing to retry it. This step watches for today's
archive page and homepage date. If they are not live after REBUILD_AFTER
seconds it asks GitHub for one Pages rebuild of main (needs `pages: write` and
GITHUB_TOKEN), then keeps watching until TIMEOUT.

Exit 0 when live. Exit 1 when still not live at the end (::error, so GitHub's
failure email goes out). Read-only apart from the one rebuild request.

  python3 scripts/verify_live.py [--date YYYY-MM-DD] [--timeout S] [--no-rebuild]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

SITE = "https://www.christiancurator.com"
TIMEOUT = 20 * 60
REBUILD_AFTER = 10 * 60
INTERVAL = 30
UA = "ChristianCurator/1.0 verify_live (+https://www.christiancurator.com/)"


def eastern_today() -> date:
    return datetime.now(ZoneInfo("America/New_York")).date()


def date_label(day: date) -> str:
    return f"{day.strftime('%B')} {day.day}, {day.year}"


def _get(url: str) -> requests.Response:
    # The query string sidesteps the Pages CDN cache (max-age 600).
    return requests.get(url, params={"cc_verify": int(time.time())}, timeout=20,
                        headers={"User-Agent": UA, "Cache-Control": "no-cache"})


def live_problem(day: date, get=_get) -> str | None:
    """None when today's edition is live, else what is missing."""
    try:
        archive = get(f"{SITE}/archive/{day.isoformat()}/")
        if archive.status_code != 200:
            return f"/archive/{day.isoformat()}/ returned HTTP {archive.status_code}"
        home = get(f"{SITE}/")
        if home.status_code != 200:
            return f"homepage returned HTTP {home.status_code}"
        if date_label(day) not in home.text:
            return f"homepage does not show {date_label(day)} yet"
    except requests.RequestException as e:
        return f"fetch failed: {type(e).__name__}: {e}"[:300]
    return None


def request_rebuild(post=requests.post) -> str:
    """Ask GitHub Pages to rebuild the published branch. Returns a log line."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        return "no GITHUB_REPOSITORY / GITHUB_TOKEN; rebuild not requested"
    try:
        resp = post(f"https://api.github.com/repos/{repo}/pages/builds", timeout=30,
                    headers={"Authorization": f"Bearer {token}",
                             "Accept": "application/vnd.github+json",
                             "X-GitHub-Api-Version": "2022-11-28"})
    except requests.RequestException as e:
        return f"rebuild request failed: {e}"[:300]
    return f"rebuild requested: HTTP {resp.status_code}"


def main(argv: list[str] | None = None, *, check=live_problem, rebuild=request_rebuild,
         sleep=time.sleep, clock=time.monotonic) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--timeout", type=int, default=TIMEOUT)
    parser.add_argument("--rebuild-after", type=int, default=REBUILD_AFTER)
    parser.add_argument("--interval", type=int, default=INTERVAL)
    parser.add_argument("--no-rebuild", action="store_true")
    args = parser.parse_args(argv)
    day = args.date or eastern_today()

    start = clock()
    rebuilt = args.no_rebuild
    while True:
        problem = check(day)
        waited = int(clock() - start)
        if problem is None:
            print(f"Live: {SITE}/archive/{day.isoformat()}/ and the homepage show "
                  f"{date_label(day)} ({waited}s after the push).")
            return 0
        print(f"Not live yet after {waited}s: {problem}")
        if not rebuilt and waited >= args.rebuild_after:
            print(f"::warning title=Pages deploy::{problem} after {waited}s; "
                  f"{rebuild()}")
            rebuilt = True
        if waited >= args.timeout:
            print(f"::error title=Site not live::{problem} {waited}s after the push. "
                  "Check Settings > Pages and the pages-build-deployment runs; "
                  "an empty commit to main also redeploys.")
            return 1
        sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
