"""
widen_voice_pages.py — One-off migration to apply the hybrid width pattern
(980px outer / 740px content) to existing voice pages.

The voice_generator template has been updated going forward; this script
retrofits the 179 pages that were generated under the old 680px layout.

What it does on each voice page:
  1. Replace `.cc-root{max-width:680px;...}` with the 980px version +
     add `main.cc-prose{max-width:740px;...}` rule.
  2. Change `<main>` to `<main class="cc-prose">` (once per page).

Idempotent: the regex changes do nothing on already-migrated pages.

Run:
    cd christiancurator
    python scripts/widen_voice_pages.py
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VOICES_DIR = REPO_ROOT / "docs" / "voices"

OLD_ROOT = r"\.cc-root\{max-width:680px;margin:0 auto;padding:0 20px 4rem;\}"
NEW_ROOT = (
    ".cc-root{max-width:980px;margin:0 auto;padding:0 20px 3rem;}"
    "main.cc-prose{max-width:740px;margin:0 auto;padding-top:1.5rem;}"
)


def process(path: Path) -> str:
    html = path.read_text(encoding="utf-8")
    orig = html

    # Update .cc-root CSS if still 680 and no cc-prose rule yet
    if "main.cc-prose" not in html:
        html = re.sub(OLD_ROOT, lambda _m: NEW_ROOT, html, count=1)

    # Add class="cc-prose" to the <main> opening tag, only if missing
    if "<main class=\"cc-prose\"" not in html and 'class="cc-prose"' not in html:
        html = re.sub(r"<main(\s*)>", r'<main\1 class="cc-prose">', html, count=1)

    if html == orig:
        return "no change"
    path.write_text(html, encoding="utf-8")
    return "updated"


def main():
    pages = sorted(VOICES_DIR.glob("*/index.html"))
    updated = 0
    for p in pages:
        status = process(p)
        if status == "updated":
            updated += 1
    print(f"Voices: updated {updated}/{len(pages)} pages.")


if __name__ == "__main__":
    main()
