"""reCAPTCHA loads on first focus of the signup form, not at startup (S1 report, section 6)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.lazy_recaptcha import FILES, make_lazy

STARTUP_TAG = '<script src="https://www.google.com/recaptcha/api.js'


def test_pages_and_templates_load_recaptcha_lazily():
    for rel in FILES:
        html = (ROOT / rel).read_text(encoding="utf-8")
        assert STARTUP_TAG not in html, rel
        assert "form.addEventListener('focusin', loadCaptcha);" in html, rel
        assert "loadCaptcha();" in html, rel


def test_make_lazy_is_idempotent():
    html = (ROOT / "frontend" / "template.html").read_text(encoding="utf-8")
    assert make_lazy(html) == html
