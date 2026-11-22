#!/usr/bin/env python3
"""Draw the site favicons from the brand mark (S1 report, section 6).

The mark is the social profile image Tom picked (B1 option B,
.christian-orchestrator/brand/proposals/profile-b-800.png): cream Lora "CC" on
brand green. At favicon sizes the thin ring disappears, so the small icons
are the green field and the letters only, drawn large.

Writes:
  docs/favicon.ico            16, 32 and 48 px
  docs/favicon-32x32.png      32 px
  docs/apple-touch-icon.png   180 px (square, iOS rounds the corners)

Needs Pillow (not in requirements.txt; not part of the daily workflow).
Fonts are in data/fonts (OFL).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
FONT = ROOT / "data" / "fonts" / "Lora-Variable.ttf"
GREEN = "#2C4A2E"
CREAM = "#faf9f7"
BASE = 512


def mark(letter_width: float) -> Image.Image:
    """Green square with cream "CC" filling ``letter_width`` of the width."""
    img = Image.new("RGB", (BASE, BASE), GREEN)
    d = ImageDraw.Draw(img)
    size = 400
    font = ImageFont.truetype(str(FONT), size)
    font.set_variation_by_name("SemiBold")
    l, t, r, b = d.textbbox((0, 0), "CC", font=font)
    size = int(size * (BASE * letter_width) / (r - l))
    font = ImageFont.truetype(str(FONT), size)
    font.set_variation_by_name("SemiBold")
    l, t, r, b = d.textbbox((0, 0), "CC", font=font)
    d.text((BASE / 2 - (l + r) / 2, BASE / 2 - (t + b) / 2), "CC", font=font, fill=CREAM)
    return img


def main() -> int:
    small = mark(0.86)
    touch = mark(0.62)
    small.resize((32, 32), Image.LANCZOS).save(DOCS / "favicon-32x32.png", optimize=True)
    small.save(DOCS / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    touch.resize((180, 180), Image.LANCZOS).save(DOCS / "apple-touch-icon.png", optimize=True)
    for name in ("favicon.ico", "favicon-32x32.png", "apple-touch-icon.png"):
        print(f"wrote docs/{name} ({(DOCS / name).stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
