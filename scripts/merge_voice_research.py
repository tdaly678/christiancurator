"""
merge_voice_research.py — one-shot merge of the 2026-07-13 research into voices_data.json.

Sources (research-2026-07-13/, kept outside the repo working tree):
  - bio_batch_results.json   : 92 resolved bios (+8 unresolved, skipped) with
                               bio / affiliation / role / website.
  - quick_facts_results.json : 50 top-GSC-demand voices with denomination,
                               tradition, current_role, affiliation, known_for,
                               website, deceased, faqs[].

Merge policy (idempotent — safe to re-run):
  bio_batch  -> bio (overwrite), affiliation/role/website (overwrite when non-empty).
  quick_facts-> new fields denomination/tradition/known_for/current_role/deceased/faqs;
               affiliation/website overwrite when non-empty. Short `role` (used in the
               hero + card) is left untouched — the descriptive current_role lives in the
               new quick-facts block.

Slugs not already present in voices_data.json are skipped (e.g. the junk email slug
esticegmailcom-elizabeth-stice, intentionally removed to .trash_voices this session).

Run:
    cd christiancurator
    python scripts/merge_voice_research.py            # uses ../research-2026-07-13
    python scripts/merge_voice_research.py /path/to/research_dir
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VOICES_DATA_PATH = REPO_ROOT / "docs" / "voices_data.json"

# Fields carried over from quick_facts into each voice entry.
QF_NEW_FIELDS = ("denomination", "tradition", "known_for", "current_role", "deceased")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> None:
    research_dir = Path(argv[1]) if len(argv) > 1 else REPO_ROOT.parent / "research-2026-07-13"
    bio_path = research_dir / "bio_batch_results.json"
    qf_path = research_dir / "quick_facts_results.json"
    if not bio_path.exists() or not qf_path.exists():
        sys.exit(f"Research files not found under {research_dir}")

    voices = _load(VOICES_DATA_PATH)
    by_slug = {e["slug"]: e for e in voices}

    bios = _load(bio_path)
    quick_facts = _load(qf_path)

    bio_applied = bio_skipped = 0
    for e in bios:
        if e.get("unresolved"):
            continue
        slug = e["slug"]
        target = by_slug.get(slug)
        if target is None:
            bio_skipped += 1
            print(f"  bio skip (not in voices_data): {slug}")
            continue
        if e.get("bio"):
            target["bio"] = e["bio"].strip()
        if e.get("affiliation"):
            target["affiliation"] = e["affiliation"].strip()
        if e.get("role"):
            target["role"] = e["role"].strip()
        if e.get("website"):
            target["website"] = e["website"].strip()
        bio_applied += 1

    qf_applied = qf_skipped = 0
    for e in quick_facts:
        slug = e["slug"]
        target = by_slug.get(slug)
        if target is None:
            qf_skipped += 1
            print(f"  quick-facts skip (not in voices_data): {slug}")
            continue
        for f in QF_NEW_FIELDS:
            if f in e and e[f] not in (None, ""):
                target[f] = e[f]
        # faqs: keep only well-formed {q, a} pairs
        faqs = [
            {"q": q["q"].strip(), "a": q["a"].strip()}
            for q in (e.get("faqs") or [])
            if q.get("q") and q.get("a")
        ]
        if faqs:
            target["faqs"] = faqs
        if e.get("affiliation"):
            target["affiliation"] = e["affiliation"].strip()
        if e.get("website"):
            target["website"] = e["website"].strip()
        qf_applied += 1

    VOICES_DATA_PATH.write_text(
        json.dumps(voices, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"\nMerged. bios applied={bio_applied} skipped={bio_skipped}; "
        f"quick-facts applied={qf_applied} skipped={qf_skipped}; "
        f"total voices={len(voices)}"
    )


if __name__ == "__main__":
    main(sys.argv)
