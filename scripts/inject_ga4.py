#!/usr/bin/env python3
"""Inject the site's GA4 tag into static pages that are missing it.

Content-preserving and idempotent: a page that already references
googletagmanager is left untouched. The tag is inserted on its own lines
directly after the page's canonical <link>, falling back to just before
</head> if a page has no canonical.

Usage:
    python scripts/inject_ga4.py docs/topics docs/daily        # apply
    python scripts/inject_ga4.py --dry-run docs/topics          # report only
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

GA_ID = "G-3NJ5DSPFXL"
GA_BLOCK = f"""<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA_ID}');
</script>
"""

CANONICAL_RE = re.compile(r'<link[^>]*rel="canonical"[^>]*>[ \t]*\n?')


def inject(html: str) -> str | None:
    if "googletagmanager.com/gtag" in html:
        return None
    m = CANONICAL_RE.search(html)
    if m:
        head = html[: m.end()]
        if not head.endswith("\n"):
            head += "\n"
        return head + GA_BLOCK + html[m.end():]
    idx = html.find("</head>")
    if idx == -1:
        return None
    sep = "" if html[:idx].endswith("\n") else "\n"
    return html[:idx] + sep + GA_BLOCK + html[idx:]


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    roots = [Path(a) for a in argv if a != "--dry-run"]
    changed = skipped = 0
    for root in roots:
        for path in sorted(root.rglob("index.html")):
            html = path.read_text(encoding="utf-8")
            new = inject(html)
            if new is None:
                skipped += 1
                continue
            changed += 1
            if not dry:
                path.write_text(new, encoding="utf-8")
    print(f"{'would inject' if dry else 'injected'}: {changed}  already present/skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
