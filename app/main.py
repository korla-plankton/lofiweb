from __future__ import annotations

import hashlib
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
import httpx

from app.cache import Cache
from app.converter import (
    ConvertMode,
    DeterministicConverter,
    LLMConverter,
    PageData,
    parse_mode,
)
from app.extractor import extract_links, extract_main_text

app = FastAPI(title="LoFiWeb MVP")
cache = Cache()
deterministic_converter = DeterministicConverter()
llm_converter = LLMConverter()


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must begin with http:// or https://")
    if not parsed.netloc:
        raise ValueError("URL is missing a hostname")
    cleaned = parsed._replace(fragment="")
    return urlunparse(cleaned)


async def fetch_html(url: str) -> str:
    timeout = httpx.Timeout(10.0)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Request timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Failed to fetch URL") from exc

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise HTTPException(status_code=415, detail="URL did not return HTML content")

    return response.text


async def get_page_data(url: str) -> PageData:
    try:
        normalized = normalize_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    html = await fetch_html(normalized)
    text = extract_main_text(html)
    if not text:
        raise HTTPException(status_code=422, detail="Could not extract readable content")

    links = extract_links(html, normalized)
    return PageData(url=normalized, text=text, links=links)


async def get_reader_text(url: str) -> str:
    normalized = normalize_url(url)
    cached = cache.get(normalized)
    if cached:
        return cached

    page_data = await get_page_data(normalized)
    cache.set(normalized, page_data.text)
    return page_data.text


def convert_content(page_data: PageData, mode: ConvertMode) -> str:
    if deterministic_converter.supports(mode):
        return deterministic_converter.convert(page_data, mode)

    if llm_converter.supports(mode):
        if not llm_converter.is_enabled():
            raise HTTPException(
                status_code=503,
                detail="LLM conversion mode requested but OPENAI_API_KEY is not set",
            )
        try:
            return llm_converter.convert(page_data, mode)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"LLM conversion failed: {exc}") from exc

    raise HTTPException(status_code=400, detail=f"Unsupported mode: {mode.value}")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """
    <html>
      <head><title>LoFiWeb</title></head>
      <body>
        <h1>LoFiWeb Reader</h1>
        <form action='/read' method='get'>
          <label for='url'>URL:</label>
          <input id='url' name='url' type='url' placeholder='https://example.com' required>
          <button type='submit'>Read</button>
        </form>
        <p>Use <code>/text?url=...</code> for plain text output.</p>
      </body>
    </html>
    """


@app.get("/text", response_class=PlainTextResponse)
async def text_endpoint(url: str = Query(..., description="Target page URL")) -> str:
    return await get_reader_text(url)


@app.get("/read", response_class=HTMLResponse)
async def read_endpoint(url: str = Query(..., description="Target page URL")) -> str:
    text = await get_reader_text(url)
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""
    <html>
      <head><title>LoFiWeb Reader View</title></head>
      <body>
        <h1>Reader View</h1>
        <p><strong>Source:</strong> {url}</p>
        <pre style='white-space: pre-wrap; line-height: 1.4;'>{escaped}</pre>
      </body>
    </html>
    """


@app.get("/convert", response_class=PlainTextResponse)
async def convert_endpoint(
    url: str = Query(..., description="Target page URL"),
    mode: str = Query("clean_text", description="Conversion mode"),
) -> str:
    try:
        parsed_mode = parse_mode(mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    page_data = await get_page_data(url)
    content_hash = hashlib.sha256(page_data.text.encode("utf-8")).hexdigest()
    cache_key = f"{page_data.url}|{parsed_mode.value}|{content_hash}"
    cached = cache.get_converted(cache_key)
    if cached:
        return cached

    converted = convert_content(page_data, parsed_mode)
    cache.set_converted(cache_key, page_data.url, parsed_mode.value, content_hash, converted)
    return converted
