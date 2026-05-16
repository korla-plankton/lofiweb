from __future__ import annotations

from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
import httpx

from app.cache import Cache
from app.extractor import extract_main_text

app = FastAPI(title="LoFiWeb MVP")
cache = Cache()


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


async def get_reader_text(url: str) -> str:
    try:
        normalized = normalize_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cached = cache.get(normalized)
    if cached:
        return cached

    html = await fetch_html(normalized)
    text = extract_main_text(html)
    if not text:
        raise HTTPException(status_code=422, detail="Could not extract readable content")

    cache.set(normalized, text)
    return text


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
