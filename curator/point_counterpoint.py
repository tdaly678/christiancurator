"""
point_counterpoint.py: uses Claude to pair articles that genuinely disagree
(thesis A vs. thesis B) for The Debate module.

Returns a list of pairings: [{"point": article_a, "counterpoint": article_b, "topic": str,
"thesis_a": str, "thesis_b": str}]

Claude sees title, source, perspective, cluster, tags and a short snippet per
candidate, then every proposed pair must pass validate_pair() before it is used.
An empty list is the right answer on most days: layout.py omits The Debate when
there are no pairs, and that beats showing two reports of the same story.

Rejected examples (2026-10-30 live page), covered by tests/test_point_counterpoint.py:
  * Pew's "Religion Remains Stable..." vs. Christian Post's write-up of the same Pew study
  * two news reports of the UMC / Highland Park disaffiliation fight
"""

from __future__ import annotations

import os
import re
import json
from difflib import SequenceMatcher

from dotenv import load_dotenv

from curator.ai_health import record_failure

load_dotenv()

MAX_PAIRS = 2          # layout.DEBATE_MAX_PAIRS also caps; keep them in step
MAX_CANDIDATES = 24
SNIPPET_CHARS = 220

# Perspectives that describe reporting rather than an argued position.
_REPORTING = {"news", "neutral"}
_STANCES = {"supportive", "critical"}

# Capitalised words that appear in many unrelated Christian headlines and so say
# nothing about whether two pieces cover the same story.
_COMMON_CAPS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with", "at", "by",
    "from", "is", "are", "why", "how", "what", "when", "who", "new", "after", "as",
    "god", "jesus", "christ", "christian", "christians", "christianity", "church",
    "churches", "bible", "biblical", "gospel", "faith", "evangelical", "evangelicals",
    "pastor", "pastors", "us", "u.s.", "america", "american", "americans", "news",
    "report", "study", "podcast", "video", "opinion", "says", "says,", "this", "that",
}

_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


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
You pick pairs for "The Debate", a side-by-side module on an evangelical news
front page. A pair is two articles that ARGUE OPPOSITE ANSWERS to the same
question: article A defends thesis X, article B defends a thesis that rejects
or contradicts X. A reader should finish both and feel the disagreement.

Accept a pair only if ALL of these hold:
  1. Each article takes a position (argues, advocates, critiques). Two straight
     news reports do not qualify unless they clearly take opposite sides.
  2. The two positions contradict each other on the same question, not merely
     the same subject.
  3. They are not the same story: not the same study, poll, statement, lawsuit,
     vote or event described by two outlets with the same take, and not a
     primary source paired with coverage of it.
  4. They come from different sources.

Do NOT pair: two outlets summarising one Pew/Barna/Lifeway report; two reports of
one denominational dispute; a news story and a reaction that agrees with it;
"related coverage" of one topic. When in doubt, leave it out. Most days have
zero or one real pair, and an empty array is a good answer.

Return at most {max_pairs} pairs as a JSON array, strongest first:
  {{"point_index": <int>, "counterpoint_index": <int>,
    "topic": "<the question both answer, phrased as a question, max 12 words>",
    "thesis_a": "<one sentence: what A argues>",
    "thesis_b": "<one sentence: what B argues, contradicting A>"}}

Respond with ONLY the JSON array.

Articles:
{article_list}
"""


def _plain(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"https?://\S+", " ", text)
    return " ".join(text.split())


def _snippet(a: dict) -> str:
    """Short description from fields the article already carries; never invented."""
    for key in ("description", "summary", "excerpt", "full_content"):
        s = _plain(a.get(key) or "")
        if len(s) >= 40:
            return s[:SNIPPET_CHARS].rsplit(" ", 1)[0] + ("…" if len(s) > SNIPPET_CHARS else "")
    return ""


def _title(a: dict) -> str:
    return a.get("rewritten_title") or a.get("title") or ""


def _tags(a: dict) -> list:
    tags = a.get("tags") or []
    return tags if isinstance(tags, list) else [str(tags)]


def _describe(i: int, a: dict) -> str:
    lines = [f"[{i}] {_title(a)}", f"    source: {a.get('source_name', 'unknown')}"]
    if a.get("perspective"):
        lines.append(f"    perspective: {a['perspective']}")
    meta = [m for m in (a.get("topic_cluster"), ", ".join(_tags(a))) if m]
    if meta:
        lines.append(f"    cluster/tags: {' | '.join(meta)}")
    snip = _snippet(a)
    if snip:
        lines.append(f"    snippet: {snip}")
    return "\n".join(lines)


def _proper_nouns(a: dict) -> set:
    """Distinctive capitalised tokens in title + snippet (people, bodies, places)."""
    text = f"{_title(a)} {_snippet(a)}"
    words = re.findall(r"[A-Z][\w'.&-]+", text)
    return {w.lower().strip(".'") for w in words if w.lower().strip(".'") not in _COMMON_CAPS
            and len(w) > 2}


def _norm_title(a: dict) -> str:
    return re.sub(r"[^a-z0-9 ]", "", _title(a).lower())


def _off_focus(a: dict) -> bool:
    """Catholic-specific or mainline polity items (curator/scorer.py caps) never
    headline The Debate. Checks the title too, so cached pairings that carry only
    title + url are caught."""
    from curator.scorer import is_mainline_polity
    return bool(a.get("catholic_capped") or a.get("mainline_capped")
                or is_mainline_polity(a.get("title", "")))


def validate_pair(a: dict, b: dict, pairing: dict | None = None) -> str | None:
    """Return a rejection reason, or None when the pair is a real debate."""
    pairing = pairing or {}
    if not a or not b or a is b:
        return "missing article"
    if (a.get("canonical_url") or a.get("url")) == (b.get("canonical_url") or b.get("url")):
        return "same url"
    if a.get("source_name") and a.get("source_name") == b.get("source_name"):
        return "same source"
    if _off_focus(a) or _off_focus(b):
        return "off evangelical focus"

    pa, pb = a.get("perspective"), b.get("perspective")
    opposed = {pa, pb} == _STANCES
    if pa and pb:
        if pa in _REPORTING and pb in _REPORTING:
            return "both straight reporting"
        if pa == pb:
            return "same stance"

    if SequenceMatcher(None, _norm_title(a), _norm_title(b)).ratio() >= 0.6:
        return "near-identical headlines"

    na, nb = _proper_nouns(a), _proper_nouns(b)
    shared = na & nb
    if shared and not opposed:
        overlap = len(shared) / max(1, min(len(na), len(nb)))
        if len(shared) >= 2 or overlap >= 0.5:
            return f"same story ({', '.join(sorted(shared)[:3])})"

    ta, tb = (pairing.get("thesis_a") or "").strip(), (pairing.get("thesis_b") or "").strip()
    if pairing and (not ta or not tb):
        return "no stated theses"
    if ta and tb and SequenceMatcher(None, ta.lower(), tb.lower()).ratio() >= 0.7:
        return "theses agree"
    return None


def build_point_counterpoint(articles: list[dict]) -> list[dict]:
    """Ask Claude for genuine thesis-vs-thesis pairs among the top articles."""
    candidates = [a for a in articles
                  if (a.get("score") or 0) >= 6 and a.get("role") != "media"
                  and not _off_focus(a)][:MAX_CANDIDATES]
    if len(candidates) < 2:
        return []

    article_list = "\n".join(_describe(i, a) for i, a in enumerate(candidates))

    try:
        message = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=900,
            messages=[{"role": "user", "content": MATCH_PROMPT.format(
                article_list=article_list, max_pairs=MAX_PAIRS)}],
        )
        pairings_raw = json.loads(_extract_json(message.content[0].text.strip()))
    except Exception as e:
        print(f"  Point/counterpoint error: {e}")
        record_failure("point_counterpoint", e)
        return []

    pairings, used = [], set()
    for p in pairings_raw if isinstance(pairings_raw, list) else []:
        pi, ci = p.get("point_index"), p.get("counterpoint_index")
        if not isinstance(pi, int) or not isinstance(ci, int):
            continue
        if not (0 <= pi < len(candidates) and 0 <= ci < len(candidates)) or pi == ci:
            continue
        a, b = candidates[pi], candidates[ci]
        reason = validate_pair(a, b, p)
        if not reason and (a.get("url") in used or b.get("url") in used):
            reason = "article already paired"
        if reason:
            print(f"  Debate pair rejected ({reason}): {_title(a)[:50]} | {_title(b)[:50]}")
            continue
        pairings.append({
            "point": a,
            "counterpoint": b,
            "topic": p.get("topic", ""),
            "thesis_a": p.get("thesis_a", ""),
            "thesis_b": p.get("thesis_b", ""),
        })
        used |= {a.get("url"), b.get("url")}
        if len(pairings) >= MAX_PAIRS:
            break
    return pairings
