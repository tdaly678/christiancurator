"""
scorer.py — uses Claude to score and tag each article for relevance and topic.

Each article receives:
  - score: int 1-10 (relevance to Christian audience)
  - tags:  list of topic strings (e.g. ["theology", "culture", "politics"])
"""

import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SCORE_PROMPT = """\
You are a curator for a Christian news digest. Given an article title and summary,
return a JSON object with:
  - "score": integer 1–10 (how relevant and valuable this is for a Christian audience)
  - "tags": array of 1–3 lowercase topic strings (e.g. "theology", "culture", "missions", "politics", "church life", "apologetics")

Respond with ONLY the JSON object. No explanation.

Article title: {title}
Article summary: {summary}
"""


def score_article(article: dict) -> dict:
    """Score and tag a single article using Claude."""
    prompt = SCORE_PROMPT.format(
        title=article["title"],
        summary=article["summary"][:500],  # truncate long summaries
    )
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        result = json.loads(message.content[0].text.strip())
        article["score"] = result.get("score", 5)
        article["tags"] = result.get("tags", [])
    except Exception as e:
        print(f"  Scoring error for '{article['title']}': {e}")
        article["score"] = 5
        article["tags"] = []
    return article


def score_articles(articles: list[dict]) -> list[dict]:
    """Score and tag all articles. Returns sorted by score descending."""
    scored = [score_article(a) for a in articles]
    return sorted(scored, key=lambda a: a["score"] or 0, reverse=True)
