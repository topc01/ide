import pytest
from ide_server.sessions_fs import (
    SessionError, normalize_id, new_id, parse_frontmatter, write_frontmatter, render_template,
)


def test_normalize_id_slugs_ticket_ids():
    assert normalize_id("FIN-123") == "fin-123"
    assert normalize_id("  Mi Ticket #7 ") == "mi-ticket-7"


@pytest.mark.parametrize("raw", ["", "---", "templates", "x" * 64])
def test_normalize_id_rejects(raw):
    with pytest.raises(SessionError) as e:
        normalize_id(raw)
    assert e.value.code == "invalid_id"


def test_new_id_skips_existing():
    seen = []
    sid = new_id(lambda s: (seen.append(s), len(seen) < 3)[1])
    assert sid.startswith("s-") and len(sid) == 7 and len(seen) == 3


def test_frontmatter_roundtrip_with_urls():
    text = write_frontmatter({"status": "ready", "notion_url": "https://n.so/a:b"}, "## Scope\n")
    meta, body = parse_frontmatter(text)
    assert meta == {"status": "ready", "notion_url": "https://n.so/a:b"}
    assert body == "## Scope\n"


def test_frontmatter_absent_returns_empty():
    assert parse_frontmatter("hola") == ({}, "hola")


def test_frontmatter_newlines_in_values_are_flattened():
    meta, _ = parse_frontmatter(write_frontmatter({"title": "a\nb"}, ""))
    assert meta["title"] == "a b"


@pytest.mark.parametrize("text", ["---\nstatus: x\n", "---\nsin dos puntos\n---\n"])
def test_frontmatter_broken(text):
    with pytest.raises(SessionError) as e:
        parse_frontmatter(text)
    assert e.value.code == "bad_frontmatter"


def test_render_template_ok_and_missing():
    assert render_template("T {{id}}: {{ title }}", {"id": "x", "title": "y"}) == "T x: y"
    with pytest.raises(SessionError) as e:
        render_template("{{a}} {{b}}", {"a": 1})
    assert e.value.code == "missing_vars" and "b" in str(e.value)
