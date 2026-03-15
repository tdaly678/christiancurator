"""
scorer.py — uses Claude to score and tag articles in batches for efficiency.

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

BATCH_SIZE = 10  # articles per API call

BATCH_PROMPT = """\
You are a curator for a Christian news digest. Score and tag each article below.

For each article, return a JSON object with:
  - "score": integer 1-10 (how relevant and valuable this is for a Christian audience)
  - "tags": array of 1-3 lowercase topic strings (e.g. "theology", "culture", "missions", "politics", "church life", "apologetics")

Respond with ONLY a JSON array containing one object per article, in the same order.
No explanation, no markdown, just the raw JSON array.

Articles:
{articles}
"""


def score_batch(articles: list[dict]) -> list[dict]:
    """Score and tag a batch of articles in a single API call."""
    articles_text = "\n".join(
        f"{i+1}. Title: {a['title']}\n   Summary: {a['summary'][:200]}"
        for i, a in enumerate(articles)
    )
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role": "user", "content": BATCH_PROMPT.format(articles=articles_text)}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        if not raw:
            print(f"  Warning: empty response from API. Stop reason: {message.stop_reason}")
            raise ValueError("Empty response")
        results = json.loads(raw)
        for i, article in enumerate(articles):
            if i < len(results):
                article["score"] = results[i].get("score", 5)
                article["tags"] = results[i].get("tags", [])
            else:
                article["score"] = 5
                article["tags"] = []
    except Exception as e:
        print(f"  Batch scoring error: {e}")
        for article in articles:
            article["score"] = 5
            article["tags"] = []
    return articles


def score_articles(articles: list[dict]) -> list[dict]:
    """Score and tag all articles in batches. Returns sorted by score descending."""
    scored = []
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i:i + BATCH_SIZE]
        print(f"  Scoring articles {i+1}-{min(i+BATCH_SIZE, len(articles))}...")
        scored.extend(score_batch(batch))
    return sorted(scored, key=lambda a: a["score"] or 0, reverse=True)
