"""
apply_voice_enrichment.py — surgically enrich existing /voices/<slug>/index.html pages
with the 2026-07-13 research, WITHOUT re-rendering from the generator template.

Why in-place (not a full re-render): the live voice pages carry a Topics mega-nav and
an email box that were backfilled after voice_generator.py's template was written. A full
render from the current template would strip them. So this script edits each page's soup
directly (same approach as scripts/apply_aeo_upgrades.py) and touches only:

  1. Bio paragraphs (p.cc-voice-bio) + <meta name/og description> — refreshed from voices_data.
  2. Hero role (.cc-voice-role) and the "Writes for" meta row — updated when data is fresher.
  3. A "Quick facts" box (.cc-qf) inserted after the hero — denomination / tradition /
     current role / known for. Rendered only for voices that have this data.
  4. An FAQ section (.cc-faq) before the "All Voices" back-link — from the voice's faqs[].
  5. Person JSON-LD (data-cc-marker=CC-PERSON-SCHEMA) for every enriched voice.
  6. FAQPage JSON-LD (data-cc-marker=AEO-FAQPAGE-SCHEMA) for voices that have faqs[].

Data source: docs/voices_data.json (already merged by merge_voice_research.py). The set of
pages touched = voices whose entry has any of {bio-was-updated, faqs, denomination,
tradition, current_role, known_for}. In practice this script is driven by an explicit slug
list so it only rewrites the ~140 research voices; pass --all to enrich every eligible voice.

Idempotent: re-running produces identical output (inserted blocks are removed and rebuilt).

Run:
    cd christiancurator
    python scripts/apply_voice_enrichment.py                 # the research slug list
    python scripts/apply_voice_enrichment.py r-albert-mohler-jr paul-david-tripp
    python scripts/apply_voice_enrichment.py --all
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
VOICES_DIR = DOCS_DIR / "voices"
VOICES_DATA_PATH = DOCS_DIR / "voices_data.json"
SITE_URL = "https://www.christiancurator.com"

PERSON_MARKER = "CC-PERSON-SCHEMA"
FAQ_MARKER = "AEO-FAQPAGE-SCHEMA"

ENRICH_CSS = """
    .cc-qf{background:#fff;border:1px solid #e0ddd8;border-radius:5px;padding:1.1rem 1.4rem;margin:0 0 2rem;}
    .cc-qf-label{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;margin-bottom:0.7rem;}
    .cc-qf-item{display:flex;gap:1rem;padding:0.5rem 0;border-bottom:1px solid #f0ede8;align-items:baseline;}
    .cc-qf-item:last-child{border-bottom:none;padding-bottom:0;}
    .cc-qf-item:first-of-type{padding-top:0;}
    .cc-qf-key{font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#aaa;min-width:96px;flex-shrink:0;}
    .cc-qf-val{font-size:14px;color:#333;line-height:1.55;}
    .cc-faq{margin-top:2.5rem;padding-top:1.75rem;border-top:2px solid #e0ddd8;}
    .cc-faq-label{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;margin-bottom:0.5rem;}
    .cc-faq-title{font-family:'Lora',Georgia,serif;font-size:22px;font-weight:600;margin-bottom:1.25rem;color:#1a1a1a;}
    .cc-faq-item{margin-bottom:1.4rem;}
    .cc-faq-item:last-child{margin-bottom:0;}
    .cc-faq-q{font-family:'Lora',Georgia,serif;font-size:16px;font-weight:600;line-height:1.35;margin-bottom:0.35rem;color:#1a1a1a;}
    .cc-faq-a{font-size:15px;color:#333;line-height:1.7;}
""".rstrip()

# Quick-facts rows: (data key, visible label). "current_role" is skipped for deceased.
QF_ROWS = [
    ("denomination", "Denomination"),
    ("tradition", "Tradition"),
    ("current_role", "Current role"),
    ("known_for", "Known for"),
]


def _load_voices() -> dict:
    return {e["slug"]: e for e in json.loads(VOICES_DATA_PATH.read_text(encoding="utf-8"))}


def _ensure_css(soup: BeautifulSoup) -> None:
    style = soup.find("style")
    if not style or not style.string:
        return
    if ".cc-qf{" in style.string:
        return
    style.string = style.string.rstrip() + "\n" + ENRICH_CSS + "\n"


def _split_paragraphs(text: str) -> list[str]:
    import re
    return [p.strip() for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]


def _update_bio(soup: BeautifulSoup, bio: str) -> None:
    paras = _split_paragraphs(bio)
    if not paras:
        return
    existing = soup.select("p.cc-voice-bio")
    if not existing:
        return
    anchor = existing[0]
    new_nodes = []
    for p in paras:
        tag = soup.new_tag("p", attrs={"class": "cc-voice-bio"})
        tag.string = p
        anchor.insert_before(tag)
        new_nodes.append(tag)
    for old in existing:
        old.decompose()


def _update_role(soup: BeautifulSoup, role: str) -> None:
    if not role:
        return
    el = soup.select_one(".cc-voice-role")
    if el:
        el.string = role


def _update_writes_for(soup: BeautifulSoup, affiliation: str) -> None:
    if not affiliation:
        return
    for item in soup.select(".cc-voice-meta .cc-meta-item"):
        label = item.select_one(".cc-meta-label")
        val = item.select_one(".cc-meta-value")
        if label and val and label.get_text(strip=True).lower() == "writes for":
            val.string = affiliation
            return


def _update_meta_descriptions(soup: BeautifulSoup, bio: str) -> None:
    if not bio:
        return
    short = bio[:160]
    med = bio[:200]
    for attrs, content in (
        ({"name": "description"}, short),
        ({"property": "og:description"}, med),
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag is not None:
            tag["content"] = content


def _insert_quick_facts(soup: BeautifulSoup, entry: dict) -> None:
    for old in soup.select(".cc-qf"):
        old.decompose()
    deceased = bool(entry.get("deceased"))
    rows = []
    for key, label in QF_ROWS:
        if key == "current_role" and deceased:
            continue
        val = entry.get(key)
        if val:
            rows.append((label, str(val).strip()))
    if not rows:
        return
    hero = soup.select_one(".cc-voice-hero")
    if not hero:
        return
    box = soup.new_tag("div", attrs={"class": "cc-qf"})
    lab = soup.new_tag("div", attrs={"class": "cc-qf-label"})
    lab.string = "Quick Facts"
    box.append(lab)
    for label, val in rows:
        item = soup.new_tag("div", attrs={"class": "cc-qf-item"})
        k = soup.new_tag("span", attrs={"class": "cc-qf-key"})
        k.string = label
        v = soup.new_tag("span", attrs={"class": "cc-qf-val"})
        v.string = val
        item.append(k)
        item.append(v)
        box.append(item)
    hero.insert_after(box)


def _insert_faq(soup: BeautifulSoup, faqs: list[dict], name: str) -> None:
    for old in soup.select(".cc-faq"):
        old.decompose()
    if not faqs:
        return
    back = soup.select_one("a.cc-back-link")
    section = soup.new_tag("section", attrs={"class": "cc-faq"})
    lab = soup.new_tag("div", attrs={"class": "cc-faq-label"})
    lab.string = "Frequently Asked Questions"
    section.append(lab)
    title = soup.new_tag("h2", attrs={"class": "cc-faq-title"})
    title.string = f"Frequently Asked Questions about {name}"
    section.append(title)
    for qa in faqs:
        item = soup.new_tag("div", attrs={"class": "cc-faq-item"})
        q = soup.new_tag("h3", attrs={"class": "cc-faq-q"})
        q.string = qa["q"]
        a = soup.new_tag("p", attrs={"class": "cc-faq-a"})
        a.string = qa["a"]
        item.append(q)
        item.append(a)
        section.append(item)
    if back is not None:
        back.insert_before(section)
    else:
        main = soup.select_one("main")
        (main or soup.body).append(section)


def _remove_marker_scripts(soup: BeautifulSoup, marker: str) -> None:
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if s.get("data-cc-marker") == marker:
            s.decompose()


def _insert_person_schema(soup: BeautifulSoup, entry: dict) -> None:
    _remove_marker_scripts(soup, PERSON_MARKER)
    slug = entry["slug"]
    data = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": entry["name"],
        "url": f"{SITE_URL}/voices/{slug}/",
    }
    if entry.get("bio"):
        data["description"] = entry["bio"]
    if entry.get("role"):
        data["jobTitle"] = entry["role"]
    if entry.get("affiliation"):
        data["affiliation"] = {"@type": "Organization", "name": entry["affiliation"]}
    same_as = [u for u in [entry.get("website")] if u]
    if same_as:
        data["sameAs"] = same_as
    tag = soup.new_tag(
        "script",
        attrs={"type": "application/ld+json", "data-cc-marker": PERSON_MARKER},
    )
    tag.string = "\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    soup.find("head").append(tag)


def _insert_faq_schema(soup: BeautifulSoup, faqs: list[dict]) -> None:
    _remove_marker_scripts(soup, FAQ_MARKER)
    if not faqs:
        return
    items = [
        {
            "@type": "Question",
            "name": qa["q"],
            "acceptedAnswer": {"@type": "Answer", "text": qa["a"]},
        }
        for qa in faqs
    ]
    data = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": items}
    tag = soup.new_tag(
        "script",
        attrs={"type": "application/ld+json", "data-cc-marker": FAQ_MARKER},
    )
    tag.string = "\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    soup.find("head").append(tag)


def process(slug: str, entry: dict) -> str:
    page = VOICES_DIR / slug / "index.html"
    if not page.exists():
        return f"skip (no page): {slug}"
    html = page.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    _ensure_css(soup)
    _update_bio(soup, entry.get("bio", ""))
    _update_role(soup, entry.get("role", ""))
    _update_writes_for(soup, entry.get("affiliation", ""))
    _update_meta_descriptions(soup, entry.get("bio", ""))
    _insert_quick_facts(soup, entry)
    faqs = entry.get("faqs") or []
    _insert_faq(soup, faqs, entry["name"])
    _insert_person_schema(soup, entry)
    _insert_faq_schema(soup, faqs)

    new_html = str(soup)
    if new_html != html:
        page.write_text(new_html, encoding="utf-8")
        extras = []
        if entry.get("denomination") or entry.get("tradition") or entry.get("current_role") or entry.get("known_for"):
            extras.append("quickfacts")
        if faqs:
            extras.append(f"faq×{len(faqs)}")
        extras.append("person-schema")
        return f"updated: {slug} ({', '.join(extras)})"
    return f"unchanged: {slug}"


def _eligible(entry: dict) -> bool:
    return bool(
        entry.get("faqs")
        or entry.get("denomination")
        or entry.get("tradition")
        or entry.get("current_role")
        or entry.get("known_for")
    )


def main(argv: list[str]) -> None:
    voices = _load_voices()

    if "--all" in argv:
        slugs = sorted(s for s, e in voices.items() if _eligible(e))
    elif len(argv) > 1:
        slugs = argv[1:]
    else:
        # Default: the 2026-07-13 research set = the enrichment slug list file if present,
        # else every eligible voice (quick-facts always eligible; bio-only voices are
        # enriched too so they get Person schema).
        list_path = Path(__file__).resolve().parent / "voice_enrichment_slugs.txt"
        if list_path.exists():
            slugs = [ln.strip() for ln in list_path.read_text().splitlines() if ln.strip()]
        else:
            slugs = sorted(voices.keys())

    updated = unchanged = skipped = 0
    for slug in slugs:
        entry = voices.get(slug)
        if entry is None:
            print(f"skip (not in voices_data): {slug}")
            skipped += 1
            continue
        result = process(slug, entry)
        print(result)
        if result.startswith("updated"):
            updated += 1
        elif result.startswith("unchanged"):
            unchanged += 1
        else:
            skipped += 1

    print(f"\nDone. updated={updated} unchanged={unchanged} skipped={skipped}")


if __name__ == "__main__":
    main(sys.argv)
