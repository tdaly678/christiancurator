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

Revived Nov 22 2026 (S2; the module had rendered nothing since Oct 31):
  * candidates are chosen on max(importance, base importance, depth) >= 6,
    so argued essays (high depth, modest news value) reach Claude; argued
    pieces are listed first.
  * validate_pair() lets two pieces that name the same people or bodies pair
    when Claude stated two different theses and neither side is a news
    report. Same source, same stance, both reporting, and news plus reaction
    are still rejected.
  * every rejection (here and in frontend/layout.py) is logged and written
    to the job summary (GITHUB_STEP_SUMMARY) by write_debate_summary().
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
MIN_AXIS = 6.0         # max(importance, depth) a candidate needs
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

# What the last build_point_counterpoint() call saw, for the job summary.
LAST_RUN: dict = {}


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
"related coverage" of one topic. Two opinion or theology essays that name the
same people, bodies or events DO qualify when they argue opposite answers:
that is what a debate looks like. Look hardest among the articles marked
supportive or critical and the essays. If no pair meets the bar, return [].

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

    ta, tb = (pairing.get("thesis_a") or "").strip(), (pairing.get("thesis_b") or "").strip()
    if pairing and (not ta or not tb):
        return "no stated theses"
    if ta and tb and SequenceMatcher(None, ta.lower(), tb.lower()).ratio() >= 0.7:
        return "theses agree"

    na, nb = _proper_nouns(a), _proper_nouns(b)
    shared = na & nb
    # Real debates name the same people and bodies. Two stated, different
    # theses from two pieces that take a position and are not news reports
    # are a debate even when they share names; a news story plus a reaction
    # to it is not.
    argued = bool(ta and tb) and "news" not in (pa, pb) and bool({pa, pb} & _STANCES)
    if shared and not opposed and not argued:
        overlap = len(shared) / max(1, min(len(na), len(nb)))
        if len(shared) >= 2 or overlap >= 0.5:
            return f"same story ({', '.join(sorted(shared)[:3])})"
    return None


def axis_score(a: dict) -> float:
    """The stronger of the two editorial axes: importance (final, or Claude's
    base value) and depth. Essays rarely score high on importance."""
    vals = [a.get("importance"), a.get("final_score"), a.get("score"),
            a.get("base_importance"), a.get("depth")]
    return max((float(v) for v in vals if isinstance(v, (int, float))), default=0.0)


_STANCE_ORDER = {"supportive": 0, "critical": 0, "neutral": 1, "news": 2}


def debate_candidates(articles: list[dict], limit: int = MAX_CANDIDATES) -> list[dict]:
    """Articles Claude may pair: max(importance, depth) >= MIN_AXIS, not
    media, off focus or shown yesterday. Argued pieces first, then by axis."""
    pool = [a for a in articles
            if axis_score(a) >= MIN_AXIS and a.get("role") != "media"
            and a.get("url") and not a.get("shown_yesterday") and not _off_focus(a)]
    pool.sort(key=lambda a: (_STANCE_ORDER.get(a.get("perspective"), 1), -axis_score(a)))
    return pool[:limit]


def rejection_note(a: dict, b: dict, reason: str) -> dict:
    return {"reason": reason, "a": _title(a)[:80], "a_source": a.get("source_name", ""),
            "b": _title(b)[:80], "b_source": b.get("source_name", "")}


def build_point_counterpoint(articles: list[dict]) -> list[dict]:
    """Ask Claude for genuine thesis-vs-thesis pairs among the top articles."""
    candidates = debate_candidates(articles)
    LAST_RUN.clear()
    LAST_RUN.update({"candidates": len(candidates), "proposed": 0, "accepted": 0,
                     "rejected": [], "error": ""})
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
        LAST_RUN["error"] = f"{type(e).__name__}: {e}"[:200]
        return []

    pairings, used = [], set()
    proposals = ([p for p in pairings_raw if isinstance(p, dict)]
                 if isinstance(pairings_raw, list) else [])
    LAST_RUN["proposed"] = len(proposals)
    for p in proposals:
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
            LAST_RUN["rejected"].append(rejection_note(a, b, reason))
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
    LAST_RUN["accepted"] = len(pairings)
    return pairings


def debate_summary_lines(layout: dict | None = None) -> list[str]:
    """Markdown lines for the job summary: what Claude saw and proposed, and
    every pair rejected here or by the homepage layout, with the reason."""
    run = LAST_RUN or {}
    shown = len((layout or {}).get("debate") or [])
    lines = ["## The Debate", ""]
    if run:
        lines.append(f"Candidates sent to Claude: {run.get('candidates', 0)}. "
                     f"Pairs proposed: {run.get('proposed', 0)}. "
                     f"Passed validation: {run.get('accepted', 0)}.")
        if run.get("error"):
            lines.append(f"Claude call failed: {run['error']}")
    lines.append(f"Pairs on the page: {shown}.")
    notes = list(run.get("rejected") or []) + list((layout or {}).get("debate_notes") or [])
    if notes:
        lines += ["", "| Rejected | Side A | Side B |", "|---|---|---|"]
        for n in notes:
            a = f"{n['a']} ({n['a_source']})".replace("|", "/")
            b = f"{n['b']} ({n['b_source']})".replace("|", "/")
            lines.append(f"| {n['reason']} | {a} | {b} |")
    return lines + [""]


def write_debate_summary(layout: dict | None = None, path: str | None = None) -> None:
    """Print the Debate report and append it to the GitHub job summary
    (GITHUB_STEP_SUMMARY) when that is set."""
    lines = debate_summary_lines(layout)
    for line in lines:
        if line:
            print(f"  {line}")
    path = path or os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as e:
            print(f"  (debate summary not written: {e})")
