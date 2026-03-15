"""
title_rewriter.py — uses Claude to rewrite article titles for a Christian audience.

Goal: make titles more engaging and clear without being clickbait.
The original title is preserved; the rewritten version is stored separately.
"""

import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

REWRITE_PROMPT = """\
You are an editor for a Christian news digest. Rewrite the following article title
to be clear, engaging, and suitable for a thoughtful Christian reader.
- Keep it under 12 words
- Avoid sensationalism and clickbait
- Preserve the meaning of the original
- Return ONLY the rewritten title, nothing else.

Original title: {title}
"""


def rewrite_title(article: dict) -> dict:
    """Rewrite a single article title using Claude."""
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{"role": "user", "content": REWRITE_PROMPT.format(title=article["title"])}],
        )
        article["rewritten_title"] = message.content[0].text.strip().strip('"')
    except Exception as e:
        print(f"  Title rewrite error for '{article['title']}': {e}")
        article["rewritten_title"] = article["title"]
    return article


def rewrite_titles(articles: list[dict]) -> list[dict]:
    """Rewrite titles for all articles."""
    return [rewrite_title(a) for a in articles]
