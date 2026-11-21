#!/usr/bin/env python3
"""
add_topics_nav.py

Write the "Topics" dropdown into every nav bar site-wide.

Layout after patch:
  Home | Topics ▾ | Resources ▾

Desktop: Topics ▾ opens five hand-picked featured topics
(frontend/topics_hub.py FEATURED) and a bold last line "All N topics"
linking /topics/, where N is the live topic count computed at build time.
Phones (700px and below): the dropdown is replaced by a plain "Topics" link
to /topics/. The link carries `hidden` so a page without the CSS below never
shows two Topics items.

Sources:
  • frontend/topics_hub.py (featured picks, labels) and docs/topics/ (count).
  • Idempotent via HTML/CSS comment markers. Safe to re-run.

Targets:
  1. frontend/template.html, digest_template.html, archive_template.html,
     daily_template.html     (Jinja templates; voice pages copy template.html)
  2. frontend/__init__.py    (Python-list nav block in render_archive_index)
  3. docs/**/*.html          (already-rendered static pages)

Tests: tests/test_topics_hub.py (the templates must match build_topics_html()).
"""

from __future__ import annotations

import html as html_mod
import re
import sys
from pathlib import Path

# Make frontend importable when run from project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from frontend.topics_hub import FEATURED, nav_label, topic_count  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Markers
# ─────────────────────────────────────────────────────────────────────────────
HTML_START = "<!-- CC-TOPICS-DROPDOWN:START -->"
HTML_END = "<!-- CC-TOPICS-DROPDOWN:END -->"
CSS_START = "/* CC-NAV-TOPICS-SUBMENU:START */"
CSS_END = "/* CC-NAV-TOPICS-SUBMENU:END */"

# ─────────────────────────────────────────────────────────────────────────────
# Build the nav block
# ─────────────────────────────────────────────────────────────────────────────


def build_topics_html(indent: str = "      ", count: int | None = None) -> str:
    """Return the full idempotent HTML block for the Topics dropdown.

    `indent` is the leading whitespace for the outer <div>, matching the
    formatting of sibling nav items in the target file. `count` defaults to
    the number of live topic pages in docs/topics/.
    """
    n = topic_count() if count is None else count
    lines: list[str] = []
    lines.append(f'{indent}{HTML_START}')
    lines.append(f'{indent}<div class="cc-nav-dropdown cc-nav-dropdown-topics">')
    lines.append(f'{indent}  <a class="cc-nav-topics-link" href="/topics/" hidden>Topics</a>')
    lines.append(f'{indent}  <button class="cc-nav-dropdown-toggle" aria-haspopup="true">Topics</button>')
    lines.append(f'{indent}  <div class="cc-nav-dropdown-menu cc-nav-dropdown-menu-topics">')
    for slug in FEATURED:
        label = html_mod.escape(nav_label(slug), quote=False)
        lines.append(f'{indent}    <a href="/topics/{slug}/">{label}</a>')
    lines.append(f'{indent}    <a class="cc-nav-topics-all" href="/topics/">All {n} topics</a>')
    lines.append(f'{indent}  </div>')
    lines.append(f'{indent}</div>')
    lines.append(f'{indent}{HTML_END}')
    return "\n".join(lines) + "\n"


# CSS for the Topics dropdown. The generic .cc-nav-dropdown rules on each page
# open the panel on hover / focus; these rules restyle its links and swap the
# dropdown for the plain link on phones.
TOPICS_CSS_RULES = [
    ".cc-nav-dropdown-menu-topics{left:0;transform:none;min-width:230px;padding:8px 0;}",
    ".cc-nav-dropdown-menu-topics a{font-size:13.5px;font-weight:500;letter-spacing:0;text-transform:none;color:#333;padding:7px 18px;}",
    ".cc-nav-dropdown-menu-topics a:hover{color:#2C4A2E;background:#f7f5f2;}",
    ".cc-nav-dropdown-menu-topics a.cc-nav-topics-all{font-weight:700;color:#1a1a1a;border-top:1px solid #e0ddd8;margin-top:6px;padding-top:10px;}",
    "@media (max-width:700px){.cc-nav-topics-link[hidden]{display:block;line-height:normal;}.cc-nav-dropdown-topics>.cc-nav-dropdown-toggle,.cc-nav-dropdown-topics>.cc-nav-dropdown-menu-topics{display:none !important;}}",
]

TOPICS_CSS = (
    f"    {CSS_START}\n"
    + "".join(f"    {r}\n" for r in TOPICS_CSS_RULES)
    + f"    {CSS_END}\n"
)

# Same CSS for __init__.py (a Python list of strings at an 8-space indent).
TOPICS_CSS_LINES_INIT = (
    [f"        '    {CSS_START}',"]
    + [f"        '    {r}'," for r in TOPICS_CSS_RULES]
    + [f"        '    {CSS_END}',"]
)

# ─────────────────────────────────────────────────────────────────────────────
# Patch helpers
# ─────────────────────────────────────────────────────────────────────────────

# Matches the existing Resources dropdown div (handles both '...' and "..." attrs).
# Anchors on a <div class=".cc-nav-dropdown..."> that contains ">Resources</button>".
RESOURCES_DROPDOWN_RE = re.compile(
    r"""(?P<indent>[ \t]*)<div\s+class=["']cc-nav-dropdown["'][^>]*>\s*\n"""
    r"""[ \t]*<button\s+class=["']cc-nav-dropdown-toggle["'][^>]*>\s*Resources\s*</button>""",
    re.IGNORECASE,
)

# Matches any existing CC-TOPICS-DROPDOWN block (for idempotent replacement).
# Includes leading whitespace on the START line so replacement text (which
# carries its own indent) doesn't double-indent on re-runs.
HTML_BLOCK_RE = re.compile(
    r"[ \t]*" + re.escape(HTML_START) + r"[\s\S]*?" + re.escape(HTML_END) + r"\n?",
)

# Matches any existing CC-NAV-TOPICS-SUBMENU CSS block (leading ws included).
CSS_BLOCK_RE = re.compile(
    r"[ \t]*" + re.escape(CSS_START) + r"[\s\S]*?" + re.escape(CSS_END) + r"\n?",
)

# Anchor where we insert CSS if not present: right after the existing
# `.cc-nav-dropdown-menu a:hover { ... }` rule in the template's <style> block.
CSS_INSERT_ANCHOR_RE = re.compile(
    r"(\.cc-nav-dropdown-menu a:hover\s*\{[^}]*\}\s*\n)",
)


def _patch_html(text: str) -> tuple[str, bool, bool]:
    """Return (new_text, html_changed, css_changed)."""
    html_changed = False
    css_changed = False

    # ── HTML: ensure Topics block is present & current ─────────────────────
    if HTML_BLOCK_RE.search(text):
        # Replace the existing block contents in place.
        match = RESOURCES_DROPDOWN_RE.search(text)
        indent = match.group("indent") if match else "      "
        new_block = build_topics_html(indent=indent)
        new_text = HTML_BLOCK_RE.sub(new_block.rstrip("\n") + "\n", text)
        if new_text != text:
            text = new_text
            html_changed = True
    else:
        # Insert before the Resources dropdown.
        match = RESOURCES_DROPDOWN_RE.search(text)
        if match:
            indent = match.group("indent")
            new_block = build_topics_html(indent=indent)
            text = text[: match.start()] + new_block + text[match.start() :]
            html_changed = True

    # ── CSS: ensure submenu CSS is present & current ───────────────────────
    if CSS_BLOCK_RE.search(text):
        new_text = CSS_BLOCK_RE.sub(TOPICS_CSS.rstrip("\n") + "\n", text)
        if new_text != text:
            text = new_text
            css_changed = True
    else:
        m = CSS_INSERT_ANCHOR_RE.search(text)
        if m:
            text = text[: m.end()] + "\n" + TOPICS_CSS + text[m.end() :]
            css_changed = True

    return text, html_changed, css_changed


def _patch_init_py(path: Path) -> tuple[bool, bool]:
    """Patch the archive-index nav block that lives as a Python list of str.

    Strategy: find the line `"          <button class='cc-nav-dropdown-toggle'>Resources</button>",`
    and its enclosing `<div class='cc-nav-dropdown'>` line; insert the Topics
    dropdown as a list of stringified HTML lines before that div. CSS is
    inserted inline into the <style> list right after the
    `.cc-nav-dropdown-menu a.active` rule.
    """
    text = path.read_text()
    original = text
    html_changed = False
    css_changed = False

    # --- HTML injection (Python-list form) ------------------------------------
    init_html_marker_start = f"        '        {HTML_START}',"
    init_html_marker_end = f"        '        {HTML_END}',"
    has_existing_html = init_html_marker_start in text

    topics_html_lines = build_topics_html(indent="        ").strip("\n").splitlines()
    # Convert HTML lines to Python-list-string form. Use double quotes outside,
    # single quotes inside (the dropdown HTML uses double quotes for attrs).
    py_html_lines = []
    for ln in topics_html_lines:
        # Escape any double quotes within HTML? Our generated HTML uses
        # double-quoted attrs, so wrap the line in single quotes instead.
        if "'" in ln:
            py_html_lines.append(f'        {ln!r},')
        else:
            py_html_lines.append(f"        '{ln}',")

    if has_existing_html:
        # Replace existing block between the marker lines.
        pattern = re.compile(
            re.escape(init_html_marker_start) + r"[\s\S]*?" + re.escape(init_html_marker_end) + r"\n",
        )
        replacement = "\n".join(py_html_lines) + "\n"
        new_text = pattern.sub(replacement, text)
        if new_text != text:
            text = new_text
            html_changed = True
    else:
        # Insert before the existing '<div class="cc-nav-dropdown">...Resources' block.
        anchor = "        \"        <div class='cc-nav-dropdown'>\","
        if anchor in text:
            insertion = "\n".join(py_html_lines) + "\n"
            text = text.replace(anchor, insertion + anchor, 1)
            html_changed = True

    # --- CSS injection (Python-list form) -------------------------------------
    # Detect any prior CSS block (old 4-space or new 8-space Python indent).
    css_block_re = re.compile(
        r"[ \t]*'    " + re.escape(CSS_START) + r"',\n"
        r"[\s\S]*?"
        r"[ \t]*'    " + re.escape(CSS_END) + r"',\n",
    )
    if css_block_re.search(text):
        replacement = "\n".join(TOPICS_CSS_LINES_INIT) + "\n"
        new_text = css_block_re.sub(replacement, text)
        if new_text != text:
            text = new_text
            css_changed = True
    else:
        anchor = "        '    .cc-nav-dropdown-menu a.active{color:#1a1a1a;}',"
        if anchor in text:
            insertion = anchor + "\n" + "\n".join(TOPICS_CSS_LINES_INIT)
            text = text.replace(anchor, insertion, 1)
            css_changed = True

    if text != original:
        path.write_text(text)
    return html_changed, css_changed


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    project_root = ROOT
    docs = project_root / "docs"
    frontend = project_root / "frontend"

    files_to_patch: list[Path] = []
    files_to_patch.extend(sorted(frontend.glob("*.html")))
    files_to_patch.extend(sorted(docs.rglob("*.html")))

    total = len(files_to_patch)
    html_patched = 0
    css_patched = 0
    skipped_no_anchor = 0

    for path in files_to_patch:
        try:
            text = path.read_text()
        except Exception as e:
            print(f"  ! skip (read error): {path}: {e}")
            continue

        # Skip files that don't have the existing nav at all.
        if "cc-nav-dropdown-toggle" not in text or ">Resources</button>" not in text:
            continue

        new_text, h_changed, c_changed = _patch_html(text)
        if new_text != text:
            path.write_text(new_text)
        if h_changed:
            html_patched += 1
        if c_changed:
            css_patched += 1
        if not h_changed and HTML_START not in new_text:
            skipped_no_anchor += 1

    # Patch the Python-list nav inside frontend/__init__.py separately.
    init_py = frontend / "__init__.py"
    init_h, init_c = _patch_init_py(init_py)

    print(f"Scanned: {total} HTML files")
    print(f"  HTML inserted/updated: {html_patched}")
    print(f"  CSS  inserted/updated: {css_patched}")
    print(f"  Skipped (no Resources anchor found): {skipped_no_anchor}")
    print(f"frontend/__init__.py: html_changed={init_h}, css_changed={init_c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
