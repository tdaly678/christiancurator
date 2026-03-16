"""
output package — writes articles.json and index.html.
"""

import json
import os
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent
OUTPUT_JSON_PATH = OUTPUT_DIR / "articles.json"
YESTERDAY_JSON_PATH = Path(__file__).parent.parent / "docs" / "yesterday.json"


def save_yesterday(articles: list[dict]):
    """Save today's top 3 non-world-news articles to docs/yesterday.json for tomorrow's digest."""
    top3 = [
        {
            "title": a.get("rewritten_title") or a.get("title", ""),
            "url": a.get("url", ""),
            "source_name": a.get("source_name", ""),
            "tags": a.get("tags", []),
        }
        for a in articles
        if a.get("source_type") != "world_news"
    ][:3]
    with open(YESTERDAY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(top3, f, indent=2, ensure_ascii=False)
    print(f"  Saved top 3 to {YESTERDAY_JSON_PATH}")


def load_yesterday() -> list[dict]:
    """Load yesterday's top 3 articles if available."""
    try:
        with open(YESTERDAY_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_output(articles: list[dict], pairings: list[dict]):
    """Write articles and pairings to articles.json."""
    payload = {
        "articles": articles,
        "pairings": [
            {
                "topic": p["topic"],
                "point_title": p["point"].get("rewritten_title") or p["point"]["title"],
                "point_url": p["point"]["url"],
                "counterpoint_title": p["counterpoint"].get("rewritten_title") or p["counterpoint"]["title"],
                "counterpoint_url": p["counterpoint"]["url"],
            }
            for p in pairings
        ],
    }
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"  Wrote {len(articles)} articles to {OUTPUT_JSON_PATH}")
