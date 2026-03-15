"""
output package — writes articles.json and index.html.
"""

import json
import os
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent
OUTPUT_JSON_PATH = OUTPUT_DIR / "articles.json"


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
