"""
point_counterpoint.py — uses Claude to identify and pair articles that represent
opposing perspectives on the same issue.

Returns a list of pairings: [{"point": article_a, "counterpoint": article_b, "topic": str}]
"""

import os
import re
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _extract_json(text: str) -> str:
    """Extract JSON from a response that may contain markdown fences or extra text."""
    # Prefer the last ```json ... ``` block (Claude sometimes self-corrects after an error)
    matches = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if matches:
        return matches[-1].strip()
    # Fall back to stripping any leading/trailing fences
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text)
    return text.strip()

MATCH_PROMPT = """\
You are a curator for a Christian news digest. Below is a list of article titles
with their index numbers. Identify pairs of articles that represent meaningfully
different or opposing perspectives on the same topic.

Return a JSON array of pairings. Each pairing should be:
  {{"point_index": <int>, "counterpoint_index": <int>, "topic": "<brief topic label>"}}

If no good pairings exist, return an empty array [].
Respond with ONLY the JSON array.

Articles:
{article_list}
"""


def build_point_counterpoint(articles: list[dict]) -> list[dict]:
    """Ask Claude to find point/counterpoint pairs among the top articles."""
    # Only consider top-scored articles to keep the prompt short
    candidates = [a for a in articles if (a.get("score") or 0) >= 6][:20]

    if len(candidates) < 2:
        return []

    article_list = "\n".join(
        f"{i}: {a['rewritten_title'] or a['title']}"
        for i, a in enumerate(candidates)
    )

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": MATCH_PROMPT.format(article_list=article_list)}],
        )
        raw = message.content[0].text.strip()
        raw = _extract_json(raw)
        pairings_raw = json.loads(raw)

        pairings = []
        for p in pairings_raw:
            pi, ci = p.get("point_index"), p.get("counterpoint_index")
            if pi is not None and ci is not None and pi < len(candidates) and ci < len(candidates):
                pairings.append({
                    "point": candidates[pi],
                    "counterpoint": candidates[ci],
                    "topic": p.get("topic", ""),
                })
        return pairings

    except Exception as e:
        print(f"  Point/counterpoint error: {e}")
        return []
