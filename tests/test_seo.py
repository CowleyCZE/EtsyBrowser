"""Testy parsování SEO textu a sestavení payloadu (bez síťových volání)."""

from automation import super_robot as sr

SAMPLE = """TITLE: Dark Academia Botanical Wall Art Set of 5 Printable Vintage Herbs Decor
DESCRIPTION: Transform your space with moody botanical prints.
Instant digital download.

Includes five artworks.
TAGS: wall art, printable, dark academia, botanical, herbs, vintage, moody, decor, digital, download, art set, poster, home
"""


def test_parse_plain_format():
    r = sr.parse_seo_text(SAMPLE)
    assert r["title"].startswith("Dark Academia Botanical")
    assert "Instant digital download." in r["description"]
    assert "Includes five artworks." in r["description"]
    assert "TAGS" not in r["description"]
    assert len(r["tags"]) == 13


def test_parse_markdown_bold_format():
    text = "**TITLE:** My Title\n**DESCRIPTION:** Body text\n**TAGS:** a, b, c\n"
    r = sr.parse_seo_text(text)
    assert r["title"] == "My Title"
    assert r["description"] == "Body text"
    assert r["tags"] == ["a", "b", "c"]


def test_missing_sections_are_empty():
    r = sr.parse_seo_text("nothing useful here")
    assert r == {"title": "", "description": "", "tags": []}


def test_title_truncated_to_140_on_word_boundary():
    long_title = "word " * 60
    r = sr.parse_seo_text(f"TITLE: {long_title}\nTAGS: a")
    assert len(r["title"]) <= 140
    assert not r["title"].endswith(" ")


def test_tags_limited_and_deduplicated():
    tags = ", ".join([f"tag{i}" for i in range(20)] + ["TAG1"])
    r = sr.parse_seo_text(f"TAGS: {tags}")
    assert len(r["tags"]) == 13
    assert len({t.lower() for t in r["tags"]}) == 13
    assert all(len(t) <= 20 for t in r["tags"])


def test_payload_contains_ai_disclosure_and_limits():
    data = {
        "title": "T" * 200,
        "description_generated": "Nice art",
        "seo_tags": ["x" * 30, "ok", "OK"],
        "pricing": {"amount": 9.9},
    }
    payload = sr.build_listing_payload(data, 123)
    assert len(payload["title"]) <= 140
    assert sr.AI_DISCLOSURE_TEXT.strip() in payload["description"]
    assert payload["taxonomy_id"] == 123
    assert payload["tags"].split(",") == ["x" * 20, "ok"]
    assert "is_digital" not in payload


def test_ai_disclosure_not_duplicated():
    data = {"title": "t", "description_generated": "Text" + sr.AI_DISCLOSURE_TEXT, "seo_tags": [], "pricing": {"amount": 5}}
    payload = sr.build_listing_payload(data, 1)
    assert payload["description"].count(sr.AI_DISCLOSURE_TEXT.strip()) == 1
