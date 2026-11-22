"""Contrast and tap-target fixes shared by every page type (S1 report, section 5).

Lighthouse flagged secondary text (bylines, breadcrumbs, lane labels, the
tagline, nav items, "Updated") as light gray at 10 to 11 px on #faf9f7, and
nav, breadcrumb and footer links as under 24 px tall.

- ``fix_css(text)`` raises every light gray text color (#777 to #bbb) to
  ``SECONDARY`` (#6b6b6b, about 5.3:1 on #faf9f7) and, in the same rule, any
  font size under 12 px to 12 px. Pseudo-element rules (arrows, bullets) and
  border or background colors are left alone. It works on plain CSS, on HTML
  with <style> blocks or style="" attributes, and on Python source where CSS
  braces are doubled inside f-strings. Idempotent.
- ``A11Y_BLOCK`` is a small CSS block, between ``/* CC-A11Y:START */`` and
  ``/* CC-A11Y:END */``, that gives nav links a 44 px tap height and
  breadcrumb, footer and byline links at least 24 px. ``inject_block(html)``
  adds or refreshes it at the end of the last <style> in <head>, so it
  wins over earlier rules of the same specificity.
"""
from __future__ import annotations

import re

SECONDARY = "#6b6b6b"
GRAY_TEXT = r"#(?:777|777777|888|888888|999|999999|aaa|aaaaaa|bbb|bbbbbb)"
_COLOR_RE = re.compile(r"(?<![-\w])(color\s*:\s*)" + GRAY_TEXT + r"\b", re.I)
_SEP_COLOR_RE = re.compile(r"(?<![-\w])(color\s*:\s*)#(?:ccc|cccccc)\b", re.I)
_PX_RE = re.compile(r"(font-size\s*:\s*)(\d+(?:\.\d+)?)px")
_REM_RE = re.compile(r"(font-size\s*:\s*)(0?\.\d+)(rem|em)")
# selector (on the same line), opening brace (single or doubled), body, close
_RULE_RE = re.compile(r"([^{}\n]*?)(\{\{|\{)([^{}]*?)(\}\}|\})")
_STYLE_ATTR_RE = re.compile(r'(style=")([^"]*)(")')


def _bump_sizes(body: str) -> str:
    body = _PX_RE.sub(lambda m: m.group(1) + ("12px" if float(m.group(2)) < 12 else m.group(2) + "px"), body)
    return _REM_RE.sub(lambda m: m.group(1) + ("0.75" + m.group(3) if float(m.group(2)) < 0.75
                                               else m.group(2) + m.group(3)), body)


def _fix_body(selector: str, body: str) -> str:
    if "::" in selector or ":after" in selector or ":before" in selector:
        return body
    gray = _COLOR_RE.search(body)
    sep = "sep" in selector and _SEP_COLOR_RE.search(body)
    if not (gray or sep or SECONDARY in body.lower()):
        return body
    body = _COLOR_RE.sub(lambda m: m.group(1) + SECONDARY, body)
    if sep:
        body = _SEP_COLOR_RE.sub(lambda m: m.group(1) + SECONDARY, body)
    return _bump_sizes(body)


def fix_css(text: str) -> str:
    """Apply the contrast and minimum-size rule to CSS rules and style attributes."""
    text = _RULE_RE.sub(lambda m: m.group(1) + m.group(2) + _fix_body(m.group(1), m.group(3)) + m.group(4), text)
    return _STYLE_ATTR_RE.sub(lambda m: m.group(1) + _fix_body("", m.group(2)) + m.group(3), text)


A11Y_START = "/* CC-A11Y:START */"
A11Y_END = "/* CC-A11Y:END */"
A11Y_CSS = (
    ".cc-nav{padding-top:0;padding-bottom:0;}"
    ".cc-nav a,.cc-nav-dropdown-toggle{display:inline-flex;align-items:center;min-height:44px;}"
    ".cc-nav a.active,.cc-nav a[aria-current=\"page\"],.cc-nav a.cc-nav-topics[aria-current=\"page\"]{border-bottom:0;padding-bottom:0;"
    "text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:5px;}"
    ".cc-nav-dropdown-menu a{display:block;min-height:0;padding-top:10px;padding-bottom:10px;}"
    ".cc-breadcrumb a,.cc-footer a,.cc-footer-nav a,.cc-section-meta a,.cc-back,.cc-back-link,"
    ".cc-hub-jump a{display:inline-block;padding-top:3px;padding-bottom:3px;}"
    ".cc-hub-topic a{display:inline-block;padding:2px 0;}"
)
A11Y_BLOCK = A11Y_START + A11Y_CSS + A11Y_END
_BLOCK_RE = re.compile(re.escape(A11Y_START) + r".*?" + re.escape(A11Y_END), re.S)


def inject_block(html: str) -> str:
    """Add or refresh A11Y_BLOCK at the end of the last <style> in <head>."""
    head_end = html.find("</head>")
    if head_end < 0:
        return html
    head = html[:head_end]
    if A11Y_START in head:
        return _BLOCK_RE.sub(A11Y_BLOCK, head, count=1) + html[head_end:]
    close = head.rfind("</style>")
    if close < 0:
        return html
    return head[:close] + A11Y_BLOCK + "\n" + head[close:] + html[head_end:]


def fix_page(html: str) -> str:
    """fix_css on the <head>, style attributes in the body, then inject_block."""
    head_end = html.find("</head>")
    if head_end < 0:
        return html
    head = fix_css(html[:head_end])
    body = _STYLE_ATTR_RE.sub(lambda m: m.group(1) + _fix_body("", m.group(2)) + m.group(3), html[head_end:])
    return inject_block(head + body)
