"""
fetch_click_counts.py: pull outbound headline clicks from GA4 and store them.

How clicks are recorded (P2.1, 2026-10-30):
  * Homepage headlines carry data-pos / data-src. One delegated listener in
    frontend/template.html sends a GA4 `article_click` event with `link_url`
    set to the publisher URL. Digest and archive pages send the same event
    from inline onclick handlers.
  * GA4 enhanced measurement also logs every outbound link as a `click` event
    with the same built-in Link URL dimension. That covers history from before
    `link_url` was added to article_click.
  * This script asks the GA4 Data API for eventCount by (date, linkUrl) for
    both events, keeps the larger of the two per day and URL (they describe
    the same physical click, so summing would double count), keys each URL by
    curator.dedup.canonical_url, and writes:
      - docs/click_counts.json: {"updated", "property", "urls": {canonical:
        {"url", "total", "by_day": {YYYY-MM-DD: n}}}}. Covers every outbound
        link that got a click, including board items not logged to history.
      - the `clicks` field of matching rows in docs/article_history.json
        (matched on canonical_url, falling back to canonical_url(url)).

Credentials (both optional; without them the script prints a notice and
exits 0 so the daily run never fails on analytics):
  GA4_PROPERTY_ID            numeric GA4 property id (Admin > Property details)
  GA4_SERVICE_ACCOUNT_JSON   the full service-account key JSON. The service
                             account needs Viewer on the GA4 property.

Usage:
  python scripts/fetch_click_counts.py               # last 7 days (default)
  python scripts/fetch_click_counts.py --days 90     # backfill
  python scripts/fetch_click_counts.py --top 20      # print the top URLs only
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from curator.dedup import canonical_url  # noqa: E402

CLICKS_PATH = os.path.join(ROOT, "docs", "click_counts.json")
HISTORY_PATH = os.path.join(ROOT, "docs", "article_history.json")
EVENTS = ("article_click", "click")
SITE_HOSTS = ("christiancurator.com",)
API = "https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"
SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


# ---------------------------------------------------------------- pure helpers

def parse_report_rows(rows: list[dict]) -> dict[str, dict]:
    """GA4 runReport rows (dims: date, eventName, linkUrl) -> {canonical: {url, by_day}}.

    Per (day, url), the larger of the article_click and click counts wins.
    Internal links and empty URLs are skipped.
    """
    per: dict[tuple[str, str], dict[str, int]] = {}
    raw_url: dict[str, str] = {}
    for row in rows:
        dims = [d.get("value", "") for d in row.get("dimensionValues", [])]
        if len(dims) < 3:
            continue
        day_raw, event, link = dims[0], dims[1], dims[2]
        canon = canonical_url(link)
        if not canon or event not in EVENTS:
            continue
        if any(canon.startswith(f"https://{h}") for h in SITE_HOSTS):
            continue
        try:
            n = int(float(row.get("metricValues", [{}])[0].get("value", 0)))
        except (TypeError, ValueError):
            continue
        day = f"{day_raw[:4]}-{day_raw[4:6]}-{day_raw[6:8]}" if len(day_raw) == 8 else day_raw
        bucket = per.setdefault((canon, day), {})
        bucket[event] = bucket.get(event, 0) + n
        raw_url.setdefault(canon, link)

    out: dict[str, dict] = {}
    for (canon, day), by_event in per.items():
        entry = out.setdefault(canon, {"url": raw_url[canon], "by_day": {}})
        entry["by_day"][day] = max(by_event.values())
    return out


def merge_counts(existing: dict, fetched: dict, days: list[str]) -> dict:
    """Replace the fetched days in `existing["urls"]`; keep older days as stored.

    Days in `days` that GA4 returned nothing for are zeroed (cleared), so a
    re-fetch is idempotent. Totals are recomputed from by_day.
    """
    urls = {k: {"url": v.get("url", k), "by_day": dict(v.get("by_day", {}))}
            for k, v in (existing.get("urls") or {}).items()}
    window = set(days)
    for entry in urls.values():
        for d in list(entry["by_day"]):
            if d in window:
                del entry["by_day"][d]
    for canon, entry in fetched.items():
        tgt = urls.setdefault(canon, {"url": entry["url"], "by_day": {}})
        tgt["by_day"].update(entry["by_day"])
    for canon in list(urls):
        e = urls[canon]
        e["by_day"] = dict(sorted((d, n) for d, n in e["by_day"].items() if n))
        e["total"] = sum(e["by_day"].values())
        if not e["total"]:
            del urls[canon]
    return {"urls": dict(sorted(urls.items(), key=lambda kv: -kv[1]["total"]))}


def apply_clicks_to_history(history: list[dict], urls: dict) -> int:
    """Set `clicks` on history rows from click_counts urls. Returns rows changed."""
    changed = 0
    for row in history:
        canon = row.get("canonical_url") or canonical_url(row.get("url", ""))
        n = urls.get(canon, {}).get("total", 0)
        if row.get("clicks") != n:
            row["clicks"] = n
            changed += 1
    return changed


# ------------------------------------------------------------------- GA4 I/O

def _access_token(sa_json: str) -> str:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    creds = service_account.Credentials.from_service_account_info(json.loads(sa_json), scopes=[SCOPE])
    creds.refresh(Request())
    return creds.token


def fetch_rows(property_id: str, sa_json: str, days: int) -> list[dict]:
    import requests

    token = _access_token(sa_json)
    body = {
        "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "today"}],
        "dimensions": [{"name": "date"}, {"name": "eventName"}, {"name": "linkUrl"}],
        "metrics": [{"name": "eventCount"}],
        "dimensionFilter": {"filter": {"fieldName": "eventName",
                                       "inListFilter": {"values": list(EVENTS)}}},
        "limit": 100000,
    }
    resp = requests.post(API.format(pid=property_id), json=body, timeout=60,
                         headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.json().get("rows", [])


def _window(days: int) -> list[str]:
    today = date.today().toordinal()
    return [date.fromordinal(today - i).isoformat() for i in range(days + 1)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--top", type=int, default=0, help="print the top N stored URLs and exit")
    args = ap.parse_args()

    try:
        with open(CLICKS_PATH, encoding="utf-8") as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {"urls": {}}

    if args.top:
        for canon, e in list(existing.get("urls", {}).items())[: args.top]:
            print(f"{e['total']:6d}  {e['url']}")
        return 0

    pid = os.environ.get("GA4_PROPERTY_ID", "").strip()
    sa_json = os.environ.get("GA4_SERVICE_ACCOUNT_JSON", "").strip()
    if not pid or not sa_json:
        print("  Click counts: GA4_PROPERTY_ID / GA4_SERVICE_ACCOUNT_JSON not set, skipping.")
        return 0
    try:
        rows = fetch_rows(pid, sa_json, args.days)
    except ImportError:
        print("  Click counts: google-auth not installed, skipping.")
        return 0
    except Exception as exc:  # analytics must never break the daily run
        print(f"  Click counts: GA4 fetch failed ({type(exc).__name__}: {exc}), skipping.")
        return 0

    merged = merge_counts(existing, parse_report_rows(rows), _window(args.days))
    merged = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "property": pid, **merged}
    with open(CLICKS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=1, ensure_ascii=False)

    try:
        with open(HISTORY_PATH, encoding="utf-8") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []
    changed = apply_clicks_to_history(history, merged["urls"])
    if changed:
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"  Click counts: {len(rows)} GA4 rows, {len(merged['urls'])} URLs stored, "
          f"{changed} history rows updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
