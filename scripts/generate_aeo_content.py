"""
generate_aeo_content.py

One-off AEO content generator. For each of the 70 topic pages:
  - Reads the topic's index.html and extracts the 5 existing Key Questions
  - Calls Claude to generate:
      tldr              — 40-60 word plain-English answer to the topic's hook
      meta_description  — ~150 char SEO meta description (answers the hook)
      faq_answers       — dict {question: 50-80 word answer} for each key question
  - Writes results to output/aeo_enrichment.json

Run once before apply_aeo_upgrades.py.

Usage:
    cd christiancurator
    python scripts/generate_aeo_content.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Load .env manually (no python-dotenv dep needed)
env_path = REPO_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from anthropic import Anthropic  # noqa: E402
from frontend.topics_data import TOPICS  # noqa: E402

DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"
OUT_PATH = REPO_ROOT / "output" / "aeo_enrichment.json"

client = Anthropic()
MODEL = "claude-sonnet-4-5-20250929"  # solid quality, fast enough

PROMPT_TEMPLATE = """You are writing AEO (Answer Engine Optimization) content for an evangelical Christian \
educational website (christiancurator.com). The site presents multiple evangelical perspectives \
on theological and cultural topics in a fair, respectful, biblically-grounded way.

Topic: {name}
Category: {category}
Hook (the central debate question this page answers): {hook}
Summary: {summary}

Existing key questions on this page (write answers for each):
{questions_block}

Generate THREE outputs as strict JSON (no preamble, no markdown fences, just the JSON object):

{{
  "tldr": "A 40-60 word plain-English answer to the hook question. Must directly answer the question in the first sentence so answer engines can quote it verbatim. Neutral, educational tone. Acknowledges evangelical debate where relevant.",
  "meta_description": "A meta description of 140-160 characters that directly answers the hook question and makes a reader want to click. No quote marks inside the text.",
  "faq_answers": {{
    "<question 1 text exactly as given>": "50-80 word answer that is factually accurate, acknowledges multiple evangelical positions where they exist, and is quotable by AI search engines.",
    "<question 2 text>": "...",
    "<question 3 text>": "...",
    "<question 4 text>": "...",
    "<question 5 text>": "..."
  }}
}}

Rules:
- Each FAQ question key MUST match the question text exactly (including punctuation).
- Do NOT include HTML entities like &amp; or &rsquo; — use plain characters.
- Answers should be educational and fair to multiple evangelical positions.
- tldr must be 40-60 words, measured by counting whitespace-separated tokens.
- meta_description must be 140-160 characters including spaces.
- Return ONLY the JSON object, nothing else.
"""


def extract_key_questions(slug: str) -> list[str]:
    html_path = TOPICS_DIR / slug / "index.html"
    if not html_path.exists():
        return []
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    kq = soup.select_one(".cc-key-questions ul")
    if not kq:
        return []
    return [li.get_text(strip=True) for li in kq.select("li")]


def generate_for_topic(topic: dict) -> tuple[str, dict]:
    slug = topic["slug"]
    questions = extract_key_questions(slug)
    if not questions:
        return slug, {"error": "no key questions found"}

    questions_block = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    prompt = PROMPT_TEMPLATE.format(
        name=topic["name"],
        category=topic["category"],
        hook=topic["hook"],
        summary=topic.get("summary", topic["hook"]),
        questions_block=questions_block,
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    # Strip accidental code fences
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return slug, {"error": f"json parse failed: {e}", "raw": raw[:500]}
    data["_questions_on_page"] = questions
    return slug, data


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text())
            print(f"Loaded {len(existing)} existing enrichments — will skip those.")
        except Exception:
            pass

    todo = [t for t in TOPICS if t["slug"] not in existing or "error" in existing.get(t["slug"], {})]
    print(f"Generating for {len(todo)} topics (out of {len(TOPICS)} total)...")

    results = dict(existing)
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(generate_for_topic, t): t for t in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            topic = futures[fut]
            try:
                slug, data = fut.result()
                results[slug] = data
                status = "OK" if "error" not in data else f"ERR: {data['error']}"
                print(f"[{i}/{len(todo)}] {slug}: {status}")
            except Exception as e:
                print(f"[{i}/{len(todo)}] {topic['slug']}: EXCEPTION {e}")
                results[topic["slug"]] = {"error": str(e)}
            # Persist after each to allow resuming
            OUT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    print(f"\nWrote {OUT_PATH}")
    ok = sum(1 for v in results.values() if "error" not in v)
    print(f"{ok}/{len(results)} topics successfully enriched.")


if __name__ == "__main__":
    main()
