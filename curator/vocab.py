"""
vocab.py: allowlists for the tags and personas Claude returns from scoring.

The scorer prompt asks for values from these exact lists, but the model still
drifts ("church", "parents", "evangelism"). Anything outside the allowlist is
mapped through the alias table or dropped, and drops are counted so
score_articles() can log them once per run.
"""

import re
from collections import Counter

ALLOWED_TAGS = (
    "theology", "culture", "apologetics", "church life", "missions", "politics",
    "devotional", "news", "family", "prayer", "suffering", "work", "data",
)

ALLOWED_PERSONAS = ("pastor", "professional", "parent", "student", "women", "seeker")

TAG_ALIASES = {
    "church": "church life",
    "ministry": "church life",
    "ecclesiology": "church life",
    "worship": "church life",
    "evangelism": "missions",
    "mission": "missions",
    "global church": "missions",
    "political": "politics",
    "public life": "politics",
    "religious liberty": "politics",
    "devotion": "devotional",
    "spiritual formation": "devotional",
    "discipleship": "devotional",
    "doctrine": "theology",
    "bible": "theology",
    "scripture": "theology",
    "marriage": "family",
    "parenting": "family",
    "family life": "family",
    "grief": "suffering",
    "lament": "suffering",
    "vocation": "work",
    "faith and work": "work",
    "research": "data",
    "statistics": "data",
    "polling": "data",
    "survey": "data",
    "current events": "news",
    "ethics": "culture",
    "society": "culture",
}

PERSONA_ALIASES = {
    "pastors": "pastor",
    "church leader": "pastor",
    "church leaders": "pastor",
    "ministry leader": "pastor",
    "leaders": "pastor",
    "professionals": "professional",
    "parents": "parent",
    "students": "student",
    "college student": "student",
    "woman": "women",
    "seekers": "seeker",
    "skeptic": "seeker",
    "skeptics": "seeker",
}

MAX_PER_FIELD = 3

# Unknown values dropped this run, keyed by (field, value). Reset and reported by
# score_articles() so the log shows one line per run instead of one per article.
dropped = Counter()


def _norm(value) -> str:
    return re.sub(r"[\s_\-]+", " ", str(value or "")).strip().lower()


def _clean(values, allowed, aliases, field) -> list[str]:
    if isinstance(values, str):
        values = [values]
    out = []
    for raw in values or []:
        v = _norm(raw)
        if not v:
            continue
        v = v if v in allowed else aliases.get(v)
        if v is None:
            dropped[(field, _norm(raw))] += 1
            continue
        if v not in out:
            out.append(v)
    return out[:MAX_PER_FIELD]


def clean_tags(values) -> list[str]:
    return _clean(values, ALLOWED_TAGS, TAG_ALIASES, "tag")


def clean_personas(values) -> list[str]:
    return _clean(values, ALLOWED_PERSONAS, PERSONA_ALIASES, "persona")


def report_drops() -> None:
    """Print one summary line of dropped values, then reset the counter."""
    if dropped:
        parts = ", ".join(f"{f}:{v} x{n}" for (f, v), n in dropped.most_common())
        print(f"  Vocab allowlist: dropped {sum(dropped.values())} unknown values ({parts}).")
    dropped.clear()
