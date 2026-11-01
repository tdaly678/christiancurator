"""
backfill_history.py: record every article a past edition actually linked to.

Until 2026-11-01 main.py logged only the top 20 by score plus the lane picks to
docs/article_history.json, so board items (and anything placed outside the top
20) were never marked as shown and could repeat the next day. This script reads
the published pages from git and appends the missing rows:

  - docs/index.html: every external <a> carrying data-pos (lead, sublead,
    board_*, debate, worth_your_time, watch_listen, research), except the
    "also" sibling links
  - docs/email_draft.html: every external article href (the email has no
    data-pos, so masthead, social and unsubscribe links are filtered out)

Rows get date_shown = the edition date and scored_by = "backfill". A row is
"already" present when history has the url or canonical_url on that date.

Usage:
    python scripts/backfill_history.py            # dry run, prints counts
    python scripts/backfill_history.py --write    # append rows

Edit EDITIONS to backfill other days; a day may list several publish commits
(the union of their links is recorded).
"""

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from curator.dedup import canonical_url  # noqa: E402

HISTORY_PATH = ROOT / "docs" / "article_history.json"
PAGES = ("docs/index.html", "docs/email_draft.html")

# date_shown -> publish commits for that day
EDITIONS = {
    "2026-10-31": ["6e514fd7f", "c2aa05b6e", "ec0f15983"],
    "2026-11-01": ["2b1c294f8"],
}

SKIP_HOSTS = (
    "christiancurator.com", "brevo.com", "sendibt", "sendinblue", "facebook.com",
    "twitter.com", "x.com", "linkedin.com", "instagram.com", "google.com",
    "googletagmanager.com", "fonts.googleapis.com", "fonts.gstatic.com",
)

_A_RE = re.compile(r"<a\s([^>]*)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
_TAG_RE = re.compile(r"<[^>]+>")


def git_show(commit: str, path: str) -> str:
    try:
        return subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout
    except subprocess.CalledProcessError:
        return ""


def _external(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        return False
    return not any(host == h or host.endswith("." + h) or h in host for h in SKIP_HOSTS)


def extract_links(page: str, need_data_pos: bool) -> list[dict]:
    """[{url, title, source_name, pos}] for article links on a rendered page."""
    out = []
    for m in _A_RE.finditer(page):
        attrs = dict(_ATTR_RE.findall(m.group(1)))
        url = html.unescape(attrs.get("href", ""))
        pos = attrs.get("data-pos", "")
        if not _external(url) or pos == "also":
            continue
        if need_data_pos and not pos:
            continue
        title = " ".join(html.unescape(_TAG_RE.sub("", m.group(2))).split())
        if not title:
            continue
        out.append({"url": url, "title": title,
                    "source_name": html.unescape(attrs.get("data-src", "")), "pos": pos})
    return out


def edition_links(commits: list[str]) -> list[dict]:
    """Union of index.html data-pos links and email article links, by canonical URL."""
    seen, links = set(), []
    for commit in commits:
        for path in PAGES:
            page = git_show(commit, path)
            if not page:
                print(f"  warning: {commit}:{path} not found")
                continue
            for link in extract_links(page, need_data_pos=path.endswith("index.html")):
                canon = canonical_url(link["url"])
                if canon in seen:
                    continue
                seen.add(canon)
                links.append({**link, "canonical_url": canon})
    return links


def backfill(history: list[dict], editions: dict) -> tuple[list[dict], dict]:
    """Return (rows to append, {date: (found, already, new)})."""
    shown = {(u, e.get("date_shown")) for e in history
             for u in (e.get("url"), e.get("canonical_url")) if u}
    by_url = {}
    for e in history:
        by_url.setdefault(e.get("url"), e)
    new_rows, counts = [], {}
    for day, commits in editions.items():
        links = edition_links(commits)
        already = 0
        for link in links:
            if (link["url"], day) in shown or (link["canonical_url"], day) in shown:
                already += 1
                continue
            prior = by_url.get(link["url"], {})
            new_rows.append({
                "url": link["url"],
                "title": link["title"],
                "source_name": link["source_name"] or prior.get("source_name", ""),
                "date_shown": day,
                "final_score": prior.get("final_score", 0),
                "tags": prior.get("tags", []),
                "topic_cluster": prior.get("topic_cluster", ""),
                "canonical_url": link["canonical_url"],
                "boosts": {},
                "scored_by": "backfill",
                "backfill_pos": link["pos"] or "email",
                "clicks": 0,
            })
            shown |= {(link["url"], day), (link["canonical_url"], day)}
        counts[day] = (len(links), already, len(links) - already)
    return new_rows, counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="append rows (default: dry run)")
    args = ap.parse_args()

    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    rows, counts = backfill(history, EDITIONS)
    for day, (found, already, new) in counts.items():
        print(f"  {day}: found {found}, already {already}, new {new}")
    if not args.write:
        print(f"Dry run: {len(rows)} rows would be appended. Re-run with --write.")
        return 0
    history.extend(rows)
    HISTORY_PATH.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows)} rows; {len(history)} total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
