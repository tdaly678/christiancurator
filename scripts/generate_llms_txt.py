"""
generate_llms_txt.py — Generate docs/llms.txt from topics_data.py.

The llms.txt file is a proposed standard (https://llmstxt.org/) that acts
as a welcome mat for LLMs / answer engines. It's a markdown file that
summarizes the site and links to the most important URLs with short
descriptions so AI systems can quickly understand what's on offer.

This script is the source-of-truth generator: re-run it whenever
topics_data.py changes and the llms.txt will stay in sync.

Usage:
    cd christiancurator
    python scripts/generate_llms_txt.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from frontend.topics_data import TOPICS  # noqa: E402

SITE_URL = "https://www.christiancurator.com"
OUT_PATH = REPO_ROOT / "docs" / "llms.txt"

# Preserve intentional ordering across the site
CATEGORY_ORDER = [
    "Core Theology",
    "Church Life",
    "Spiritual Formation",
    "Culture & Society",
]

HEADER = f"""# Christian Curator

> Christian Curator is a daily-updated evangelical content curation site. Each morning we publish a digest of the best evangelical writing from across the web, organized around the questions evangelicals are actually asking. Deep-dive topic pages present multiple evangelical perspectives on theological and cultural debates in a fair, biblically-grounded, educational way.

- Site: {SITE_URL}
- Audience: Evangelical Protestants, pastors, seminary students, curious readers
- Approach: Fair presentation of multiple evangelical positions; neutral, educational tone
- Publisher: Christian Curator Editorial
"""

DAILY_CONTENT = f"""
## Daily Content

- [Today's Digest]({SITE_URL}/digest/): Today's curated roundup of the best evangelical writing from across the web
- [Archive]({SITE_URL}/archive/): Past daily digests, searchable by date
- [Voices]({SITE_URL}/voices/): Authors and publications featured across our curation
- [Pastors & Church Leaders]({SITE_URL}/voices/pastors/), [Theologians & Scholars]({SITE_URL}/voices/theologians-scholars/), [Writers & Authors]({SITE_URL}/voices/writers/), [Apologists]({SITE_URL}/voices/apologists/), [Bible Teachers]({SITE_URL}/voices/bible-teachers/), [Journalists]({SITE_URL}/voices/journalists/), [Ministry Leaders]({SITE_URL}/voices/ministry-leaders/), [Speakers & Creators]({SITE_URL}/voices/speakers-creators/): Voice profiles by category
- [About Christian Curator]({SITE_URL}/about/): Our mission, editorial methodology, statement of faith, and founder bio (Tom Daly, Teaching Pastor at Lancaster Evangelical Free Church)
"""

FOOTER = """
## About

Christian Curator was founded by Tom Daly, a Teaching Pastor at Lancaster Evangelical Free Church (LEFC) who is also a longtime entrepreneur and engineer. The site stands within the historic, orthodox Christian tradition (Apostles' and Nicene Creeds) and the Protestant evangelical tradition (Reformation solas, authority of Scripture). We curate broadly across evangelicalism — Reformed, Baptist, Anglican, Pentecostal, and non-denominational voices — rather than representing a single camp.

Every deep-dive topic page includes: a TL;DR answer to the central debate question, key questions evangelicals ask, a presentation of multiple evangelical positions, a synthesis, an FAQ, and the ten most recent curated articles on the topic. Pages are updated as new articles are curated. All content is generated and maintained by Christian Curator Editorial.
"""


def build_llms_txt() -> str:
    # Group topics by category, preserving category ordering
    by_category: dict[str, list[dict]] = {c: [] for c in CATEGORY_ORDER}
    for t in TOPICS:
        cat = t["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(t)

    lines: list[str] = [HEADER.rstrip(), "", "## Deep Dive Topics", ""]
    for cat in CATEGORY_ORDER:
        topics = by_category.get(cat, [])
        if not topics:
            continue
        lines.append(f"### {cat}")
        lines.append("")
        for t in topics:
            slug = t["slug"]
            name = t["name"]
            hook = t["hook"].strip()
            url = f"{SITE_URL}/topics/{slug}/"
            lines.append(f"- [{name}]({url}): {hook}")
        lines.append("")

    lines.append(DAILY_CONTENT.strip())
    lines.append("")
    lines.append(FOOTER.strip())
    lines.append("")
    return "\n".join(lines)


def main():
    content = build_llms_txt()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(content, encoding="utf-8")
    topic_count = len(TOPICS)
    print(f"Wrote {OUT_PATH} ({len(content)} bytes, {topic_count} topics)")


if __name__ == "__main__":
    main()
