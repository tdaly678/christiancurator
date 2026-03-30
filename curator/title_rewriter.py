"""
title_rewriter.py — uses Claude to rewrite article titles for a Christian audience.

Goal: make titles more engaging and clear without being clickbait.
The original title is preserved; the rewritten version is stored separately.
"""

import os
import time
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

REWRITE_PROMPT = """\
You are an editor for a Christian news digest. Rewrite the following article title
to be clear, engaging, and suitable for a thoughtful Christian reader.
- Keep it under 12 words
- Avoid sensationalism and clickbait
- Preserve the meaning of the original — do NOT invent a new topic
- The rewritten title must accurately reflect the article summary below
- Return ONLY the rewritten title, nothing else.

Original title: {title}
Article summary: {summary}
"""

MAX_RETRIES = 4
RETRY_DELAYS = [5, 15, 30, 60]


def rewrite_title(article: dict) -> dict:
    """Rewrite a single article title using Claude, with retry on 529 overload."""
    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        try:
            summary = article.get("summary") or ""
            # Strip HTML tags from summary for cleaner context
            import re
            summary_text = re.sub(r"<[^>]+>", "", summary).strip()[:300]
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=60,
                messages=[{"role": "user", "content": REWRITE_PROMPT.format(title=article["title"], summary=summary_text)}],
            )
            article["rewritten_title"] = message.content[0].text.strip().strip('"')
            return article
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt <= MAX_RETRIES:
                print(f"  Title rewrite overloaded (attempt {attempt}/{MAX_RETRIES}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"  Title rewrite error for '{article['title']}': {e}")
                article["rewritten_title"] = article["title"]
                return article
        except Exception as e:
            print(f"  Title rewrite error for '{article['title']}': {e}")
            article["rewritten_title"] = article["title"]
            return article
    article["rewritten_title"] = article["title"]
    return article


def rewrite_titles(articles: list[dict]) -> list[dict]:
    """Rewrite titles for all articles."""
    return [rewrite_title(a) for a in articles]
