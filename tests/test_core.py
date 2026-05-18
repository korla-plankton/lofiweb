from __future__ import annotations

from pathlib import Path

import pytest

from app.cache import Cache
from app.converter import ConvertMode, DeterministicConverter, PageData, parse_mode
from app.extractor import extract_links, extract_main_text
from app.main import normalize_url


def test_normalize_url_removes_fragment() -> None:
    assert normalize_url("https://example.com/path#frag") == "https://example.com/path"


def test_normalize_url_rejects_invalid_scheme() -> None:
    with pytest.raises(ValueError):
        normalize_url("ftp://example.com")


def test_cache_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    cache = Cache(str(db_path))
    cache.set("https://example.com", "hello")
    assert cache.get("https://example.com") == "hello"


def test_converted_cache_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    cache = Cache(str(db_path))
    cache.set_converted("key", "https://example.com", "clean_text", "hash", "converted")
    assert cache.get_converted("key") == "converted"


def test_extraction_fallback_when_trafilatura_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.extractor.trafilatura.extract", lambda *_args, **_kwargs: None)
    html = "<html><body><h1>Title</h1><p>Hello world</p><script>bad()</script></body></html>"
    result = extract_main_text(html)
    assert "Title" in result
    assert "Hello world" in result
    assert "bad()" not in result


def test_extract_links() -> None:
    html = '<a href="/a">A</a><a href="https://example.org/b">B</a>'
    links = extract_links(html, "https://example.com/path")
    assert links == ["https://example.com/a", "https://example.org/b"]


def test_deterministic_converter_modes() -> None:
    converter = DeterministicConverter()
    page = PageData(url="https://example.com", text="Hello", links=["https://a", "https://a", "https://b"])
    assert converter.convert(page, ConvertMode.CLEAN_TEXT) == "Hello"
    assert converter.convert(page, ConvertMode.KEY_LINKS) == "- https://a\n- https://b"


def test_parse_mode_invalid() -> None:
    with pytest.raises(ValueError):
        parse_mode("bogus")
