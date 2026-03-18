"""
output package — writes articles.json and index.html.
"""

import json
import os
from pathlib import Path
from datetime import date

OUTPUT_DIR = Path(__file__).parent
OUTPUT_JSON_PATH = OUTPUT_DIR / "articles.json"
YESTERDAY_JSON_PATH = Path(__file__).parent.parent / "docs" / "yesterday.json"
HISTORY_JSON_PATH = Path(__file__).parent.parent / "docs" / "article_history.json"


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


def load_shown_urls() -> set:
    """Load URLs of articles shown on previous days only.

    Articles shown today are excluded so re-running the pipeline on the same
    day doesn't penalise freshly published stories.
    """
    today = date.today().isoformat()
    try:
        with open(HISTORY_JSON_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
            return {entry["url"] for entry in history if entry.get("date_shown") != today}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_article_history(articles: list[dict]):
    """Append today's shown articles to the persistent history file."""
    try:
        with open(HISTORY_JSON_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []

    existing_urls = {entry["url"] for entry in history}
    today = date.today().isoformat()

    for a in articles:
        url = a.get("url", "")
        if url and url not in existing_urls:
            history.append({
                "url": url,
                "title": a.get("rewritten_title") or a.get("title", ""),
                "source_name": a.get("source_name", ""),
                "date_shown": today,
                "final_score": a.get("final_score", 0),
                "tags": a.get("tags", []),
                "clicks": 0,  # placeholder for future GA integration
            })

    with open(HISTORY_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"  Article history updated: {len(history)} total articles tracked.")


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
