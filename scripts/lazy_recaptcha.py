#!/usr/bin/env python3
"""Load reCAPTCHA only when the signup form is used (S1 report, section 6).

The homepage, digest and About signup forms loaded
https://www.google.com/recaptcha/api.js at startup: render-blocking, with a
third-party cookie that cost the homepage its Best Practices score. Topic
pages already load it on first focus of the form (docs/assets/topic.js).

This rewrites the shared signup script in place: the <script src> tag is
removed, the form loads the script on its first ``focusin``, and submit loads
it too and waits up to 10 seconds for it before reporting an error.
Idempotent. Dry run by default; --apply writes.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [
    "frontend/template.html",
    "frontend/digest_template.html",
    "docs/about/index.html",
    "docs/index.html",
    "docs/digest/index.html",
]

TAG_RE = re.compile(
    r"    <!-- reCAPTCHA v3 \(invisible\)\. Badge hidden via CSS; required disclaimer text is shown near the form above\. -->\n"
    r"    <script src=\"https://www\.google\.com/recaptcha/api\.js\?render=[\w-]+\"></script>\n"
)
NEW_COMMENT = (
    "    <!-- reCAPTCHA v3 (invisible), loaded on first focus of the form (or on submit), "
    "not at startup. Badge hidden via CSS; required disclaimer text is shown near the form above. -->\n"
)

ANCHOR = "        var originalBtnText = submitBtn.textContent;\n"
LOADER = """        var captchaLoaded = false;
        function loadCaptcha() {
          if (captchaLoaded) return;
          captchaLoaded = true;
          var s = document.createElement('script');
          s.src = 'https://www.google.com/recaptcha/api.js?render=' + RECAPTCHA_SITE_KEY;
          s.async = true;
          document.head.appendChild(s);
        }
        form.addEventListener('focusin', loadCaptcha);
"""

OLD_WAIT = """          if (typeof grecaptcha === 'undefined' || !grecaptcha.ready) {
            showError('Verification is still loading. Please try again in a moment.');
            resetButton();
            return;
          }

          grecaptcha.ready(function () {
"""
NEW_WAIT = """          loadCaptcha();
          var tries = 0;
          (function waitForCaptcha() {
          if (typeof grecaptcha === 'undefined' || !grecaptcha.ready) {
            if (++tries > 50) {
              showError('Verification is still loading. Please try again in a moment.');
              resetButton();
              return;
            }
            return setTimeout(waitForCaptcha, 200);
          }

          grecaptcha.ready(function () {
"""
OLD_TAIL = "          });\n        });\n      })();\n    </script>"
NEW_TAIL = "          });\n          })();\n        });\n      })();\n    </script>"


def make_lazy(html: str) -> str:
    if "function loadCaptcha()" in html:
        return html
    if not TAG_RE.search(html) or ANCHOR not in html or OLD_WAIT not in html:
        return html
    start = html.index(OLD_WAIT)
    tail = html.find(OLD_TAIL, start)
    if tail < 0:
        return html
    html = html[:tail] + NEW_TAIL + html[tail + len(OLD_TAIL):]
    html = html.replace(OLD_WAIT, NEW_WAIT, 1)
    html = html.replace(ANCHOR, ANCHOR + LOADER, 1)
    return TAG_RE.sub(NEW_COMMENT, html, count=1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    for rel in FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8")
        new = make_lazy(html)
        state = "already lazy" if "function loadCaptcha()" in html else ("rewritten" if new != html else "NO MATCH")
        if new != html and args.apply:
            path.write_text(new, encoding="utf-8")
        print(f"{rel}: {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
