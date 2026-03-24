"""
send_email.py — send the daily email using cached pipeline output.

Use this when you ran main.py --no-email and are ready to send,
or to re-send after making edits to the site.

Usage:
    python send_email.py
"""

import json
from pathlib import Path
from curator.email_sender import send_email
from frontend import load_research_articles
from output import load_yesterday

OUTPUT_JSON = Path("output/articles.json")


def main():
    if not OUTPUT_JSON.exists():
        print("Error: output/articles.json not found. Run main.py first.")
        return

    with open(OUTPUT_JSON) as f:
        data = json.load(f)

    articles = data.get("articles", data) if isinstance(data, dict) else data
    fetched_at = (articles[0].get("fetched_at", "unknown")[:10]
                  if articles else "unknown")
    print(f"=== Sending Daily Email ===")
    print(f"  Using articles from: {fetched_at}")
    print(f"  Article count: {len(articles)}")

    yesterday_articles = load_yesterday()
    research_articles = load_research_articles()

    # Reconstruct daily_summary from articles.json if stored there
    daily_summary = data.get("daily_summary") if isinstance(data, dict) else None

    send_email(articles, yesterday_articles, daily_summary=daily_summary,
               research_articles=research_articles)
    print("=== Email Sent ===")


if __name__ == "__main__":
    main()
