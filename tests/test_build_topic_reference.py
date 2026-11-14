"""Tests for scripts/build_topic_reference.py (definition box and FAQ with FAQPage schema).

Fixture copy below is made up for the renderer; real data lives in data/topic_reference/.
"""

import copy
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_topic_reference as btr  # noqa: E402

PAGE = """<html><head>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Article", "datePublished": "2026-04-01", "dateModified": "2026-04-17"}
</script>
<script type="application/ld+json" data-cc-marker="AEO-FAQPAGE-SCHEMA">
{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": "Old?"}]}
</script><!-- CC-TOPIC-ASSETS:START -->
<link rel="stylesheet" href="/assets/topic.css?v=1"/>
<!-- CC-TOPIC-ASSETS:END -->
</head><body><main class="cc-prose"><div class="cc-topic-hero"><h1>T</h1>
<p class="cc-last-updated">Last updated: April 17, 2026</p></div><section class="cc-tldr" id="tldr"><p>tl;dr</p></section>
<section class="cc-synthesis" id="synthesis"><p>s</p></section>
<!-- CC-TOPIC-VOICES:START --><aside></aside><!-- CC-TOPIC-VOICES:END -->
</main></body></html>"""


def data():
    return {
        "slug": "example",
        "date_modified": "2026-11-14",
        "definition": {
            "question": "What is the example?",
            "html": '<p>An example is a thing. See <a href="#faq">the FAQ</a>.</p>',
            "also_known_as": ["sample", "instance"],
        },
        "faq": {
            "title": "Example, Briefly Answered",
            "place": {"before": "<!-- CC-TOPIC-VOICES:START -->"},
            "items": [
                {"q": "What is one?", "a": 'One is <a href="https://example.org/one">a number</a>.'},
                {"q": "What is two?", "a": "Two is &quot;one more&quot; than one."},
                {"q": "Where are the facts?", "a": 'See <a href="#synthesis">the synthesis</a>.'},
            ],
        },
        "sources": [{"id": "ex", "publisher": "Example", "title": "Example page",
                     "url": "https://example.org/", "fetched": "2026-11-14"}],
    }


def build(d=None, page=PAGE):
    return btr.build_page(page, d or data())


def test_valid_fixture_passes():
    assert btr.validate(data(), "example", PAGE) == []


def test_definition_goes_before_tldr_with_aka():
    out = build()
    i_def, i_tldr = out.index(btr.DEF_START), out.index('<section class="cc-tldr"')
    assert i_def < i_tldr
    block = out[i_def:out.index(btr.DEF_END)]
    assert 'id="definition"' in block
    assert "Also known as:</strong> sample, instance." in block


def test_faq_visible_and_schema_match():
    out = build()
    assert out.index(btr.FAQ_START) < out.index("<!-- CC-TOPIC-VOICES:START -->")
    m = btr.FAQ_SCHEMA_RE.search(out)
    schema = json.loads(re.sub(r"^<script[^>]*>|</script>$", "", m.group(0)))
    assert schema["@type"] == "FAQPage"
    names = [q["name"] for q in schema["mainEntity"]]
    assert names == ["What is one?", "What is two?", "Where are the facts?"]
    # Plain text answers in the schema, HTML on the page.
    assert schema["mainEntity"][0]["acceptedAnswer"]["text"] == "One is a number."
    assert schema["mainEntity"][1]["acceptedAnswer"]["text"] == 'Two is "one more" than one.'
    for name in names:
        assert f'<h3 class="cc-faq-q">{name}</h3>' in out
    assert out.count('data-cc-marker="AEO-FAQPAGE-SCHEMA"') == 1


def test_dates_and_css():
    out = build()
    assert '"dateModified": "2026-11-14"' in out
    assert '"datePublished": "2026-04-01"' in out
    assert "Last updated: November 14, 2026" in out
    assert out.index(btr.CSS_START) < out.index("<!-- CC-TOPIC-ASSETS:START -->")


def test_idempotent():
    once = build()
    assert build(page=once) == once


def test_rebuild_replaces_in_place():
    once = build()
    d = data()
    d["faq"]["items"][0]["a"] = "One is the first number."
    twice = build(d, once)
    assert twice.count(btr.FAQ_START) == 1
    assert "One is the first number." in twice
    assert "One is a number." not in twice


def test_schema_inserted_when_missing():
    page = btr.FAQ_SCHEMA_RE.sub("", PAGE)
    out = build(page=page)
    assert out.count('data-cc-marker="AEO-FAQPAGE-SCHEMA"') == 1


@pytest.mark.parametrize("mutate, needle", [
    (lambda d: d["faq"]["items"][0].__setitem__("a", "A dash — here."), "dash"),
    (lambda d: d["faq"]["items"][0].__setitem__("a", '<a href="https://x.org/?utm_source=y">x</a>'), "tracking"),
    (lambda d: d["definition"].__setitem__("html", "<p>The Quiet Revival report.</p>"), "Quiet Revival"),
    (lambda d: d["faq"].__setitem__("items", d["faq"]["items"][:2]), "at least 3"),
    (lambda d: d["faq"]["items"][1].__setitem__("q", "Not a question"), "question"),
    (lambda d: d["faq"]["items"][2].__setitem__("a", '<a href="#nowhere">x</a>'), "no target"),
    (lambda d: d["faq"]["items"][2].__setitem__("a", '<a href="http://insecure.org">x</a>'), "https"),
    (lambda d: d["sources"][0].__setitem__("fetched", ""), "fetched"),
    (lambda d: d.__setitem__("date_modified", "Nov 14"), "date_modified"),
    (lambda d: d["faq"].__setitem__("place", {"before": "<!-- NOT-THERE -->"}), "not on the page"),
    (lambda d: d["faq"]["items"][0].__setitem__("a", "We read 450 feeds."), "feed count"),
])
def test_validator_refuses(mutate, needle):
    d = copy.deepcopy(data())
    mutate(d)
    errs = btr.validate(d, "example", PAGE)
    assert any(needle in e for e in errs), errs


def test_flagged_names_refused():
    d = data()
    d["faq"]["items"][0]["a"] = "As Jane Example argues."
    errs = btr.validate(d, "example", PAGE, flagged=["Jane Example"])
    assert any("flagged" in e for e in errs)


def test_committed_data_validates_against_page():
    for path in sorted((REPO_ROOT / "data" / "topic_reference").glob("*.json")):
        slug = path.stem
        d = json.loads(path.read_text(encoding="utf-8"))
        page = (REPO_ROOT / "docs" / "topics" / slug / "index.html").read_text(encoding="utf-8")
        assert btr.validate(d, slug, page, btr.load_flagged(slug)) == []
        # The committed page is current: rebuilding changes nothing.
        assert btr.build_page(page, d) == page
