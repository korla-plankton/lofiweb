from __future__ import annotations

from pathlib import Path

import pytest
from app.cache import Cache
from app.extractor import extract_main_text
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


def test_extraction_fallback_when_trafilatura_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.extractor.trafilatura.extract", lambda *_args, **_kwargs: None)
    html = "<html><body><h1>Title</h1><p>Hello world</p><script>bad()</script></body></html>"
    result = extract_main_text(html)
    assert "Title" in result
    assert "Hello world" in result
    assert "bad()" not in result


def test_extraction_empty_result() -> None:
    text = extract_main_text("<html><body></body></html>")
    assert text == ""
