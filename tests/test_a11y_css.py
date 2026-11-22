"""Contrast and tap-target CSS (S1 report, section 5)."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from frontend.a11y_css import A11Y_BLOCK, A11Y_START, fix_css, fix_page, inject_block

GRAY_TEXT_RE = re.compile(r"(?<![-\w])color\s*:\s*#(?:777|888|999|aaa|bbb)\b", re.I)


def test_gray_text_raised_and_small_size_bumped():
    css = ".cc-src { font-size: 11px; color: #888; }\n.cc-meta{font-size:0.7rem;color:#aaa}"
    out = fix_css(css)
    assert ".cc-src { font-size: 12px; color: #6b6b6b; }" in out
    assert "font-size:0.75rem;color:#6b6b6b" in out
    assert fix_css(out) == out


def test_leaves_borders_backgrounds_pseudo_and_colored_labels():
    css = (".a { border: 1px solid #aaa; background-color: #888; color: #1a1a1a; font-size: 10px; }\n"
           ".b::after { content: '>'; font-size: 10px; color: #888; }\n"
           ".c { font-size: 10px; color: #2C4A2E; }")
    assert fix_css(css) == css


def test_python_fstring_braces():
    src = '    .cc-breadcrumb{{font-size:11px;color:#aaa;}}\n'
    assert fix_css(src) == '    .cc-breadcrumb{{font-size:12px;color:#6b6b6b;}}\n'


def test_breadcrumb_separator():
    assert "color: #6b6b6b" in fix_css(".cc-breadcrumb-sep { margin: 0 6px; color: #ccc; }")
    assert fix_css(".cc-hr { color: #ccc; }") == ".cc-hr { color: #ccc; }"


def test_inject_block_is_idempotent_and_in_last_head_style():
    html = "<head><style>a{}</style><style>b{}</style></head><body><style>c{}</style></body>"
    out = inject_block(html)
    assert out.count(A11Y_START) == 1
    assert out.index(A11Y_START) > out.index("b{}") and out.index(A11Y_START) < out.index("</head>")
    assert inject_block(out) == out
    assert fix_page(fix_page(html)) == fix_page(html)


def test_nav_tap_height_in_block():
    assert "min-height:44px" in A11Y_BLOCK


def test_templates_have_no_light_gray_text():
    for name in ("template.html", "digest_template.html", "archive_template.html", "daily_template.html"):
        text = (ROOT / "frontend" / name).read_text(encoding="utf-8")
        assert not GRAY_TEXT_RE.search(text), name
        assert A11Y_START in text, name


def test_topic_css_overrides_present():
    css = (ROOT / "docs" / "assets" / "topic.css").read_text(encoding="utf-8")
    assert A11Y_START.split()[1] in css
    assert "body .cc-breadcrumb { color: #6b6b6b; font-size: 12px; }" in css
    assert not GRAY_TEXT_RE.search(css.split("@media print")[0])
