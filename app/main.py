from __future__ import annotations

import hashlib
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
import httpx

from app.cache import Cache
from app.converter import ConvertMode, DeterministicConverter, LLMConverter, PageData, format_links_markdown, parse_mode
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


def _size_bytes(content: str) -> int:
    return len(content.encode("utf-8"))


def _estimated_reduction(original_size: int, simplified_size: int) -> float:
    if original_size <= 0:
        return 0.0
    return round(((original_size - simplified_size) / original_size) * 100, 2)


def build_reader_html(url: str, text: str, metrics: dict[str, float], links_markdown: str = "") -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped_links = links_markdown.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""
    <html>
      <head><title>LoFiWeb Reader View</title></head>
      <body>
        <h1>Reader View</h1>
        <p><strong>Source:</strong> {url}</p>
        <h2>Bandwidth Report</h2>
        <ul>
          <li>Original downloaded HTML size: {int(metrics['original_html_size'])} bytes</li>
          <li>Extracted text size: {int(metrics['extracted_text_size'])} bytes</li>
          <li>Simplified reader HTML size: {int(metrics['simplified_reader_html_size'])} bytes</li>
          <li>Estimated reduction: {metrics['estimated_reduction_pct']}%</li>
        </ul>
        <pre style='white-space: pre-wrap; line-height: 1.4;'>{escaped}</pre>
        <h2>Source Links</h2>
        <pre style='white-space: pre-wrap; line-height: 1.4;'>{escaped_links or 'No links found in source content.'}</pre>
      </body>
    </html>
    """


async def get_page_data(url: str) -> tuple[PageData, str]:
    try:
        normalized = normalize_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    html = await fetch_html(normalized)
    text = extract_main_text(html)
    if not text:
        raise HTTPException(status_code=422, detail="Could not extract readable content")

    links = extract_links(html, normalized)
    return PageData(url=normalized, text=text, links=links), html


async def get_reader_text(url: str) -> str:
    normalized = normalize_url(url)
    cached = cache.get(normalized)
    if cached:
        return cached

    page_data, _html = await get_page_data(normalized)
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
    normalized = normalize_url(url)
    page_data, _html = await get_page_data(normalized)
    cache.set(normalized, page_data.text)
    text = page_data.text
    links_block = format_links_markdown(page_data.links)
    metrics = cache.get_metrics(normalized)
    if not metrics:
        metrics = {
            "original_html_size": 0,
            "extracted_text_size": _size_bytes(text),
            "simplified_reader_html_size": 0,
            "estimated_reduction_pct": 0.0,
        }
    meta = (
        f"# source_url: {normalized}\n"
        f"# original_html_size_bytes: {int(metrics['original_html_size'])}\n"
        f"# extracted_text_size_bytes: {int(metrics['extracted_text_size'])}\n"
        f"# simplified_reader_html_size_bytes: {int(metrics['simplified_reader_html_size'])}\n"
        f"# estimated_reduction_percent: {metrics['estimated_reduction_pct']}\n\n"
    )
    links_meta = (
        f"# source_links_markdown:\n{links_block}\n\n"
        if links_block
        else "# source_links_markdown: none\n\n"
    )
    return meta + links_meta + text


@app.get("/read", response_class=HTMLResponse)
async def read_endpoint(url: str = Query(..., description="Target page URL")) -> str:
    page_data, html = await get_page_data(url)

    base_metrics = {
        "original_html_size": _size_bytes(html),
        "extracted_text_size": _size_bytes(page_data.text),
    }
    links_markdown = format_links_markdown(page_data.links)
    provisional_metrics = {**base_metrics, "simplified_reader_html_size": 0, "estimated_reduction_pct": 0.0}
    reader_html = build_reader_html(page_data.url, page_data.text, provisional_metrics, links_markdown)

    simplified_size = _size_bytes(reader_html)
    reduction_pct = _estimated_reduction(base_metrics["original_html_size"], simplified_size)
    final_metrics = {
        **base_metrics,
        "simplified_reader_html_size": simplified_size,
        "estimated_reduction_pct": reduction_pct,
    }

    cache.set(page_data.url, page_data.text)
    cache.set_metrics(
        page_data.url,
        int(final_metrics["original_html_size"]),
        int(final_metrics["extracted_text_size"]),
        int(final_metrics["simplified_reader_html_size"]),
        float(final_metrics["estimated_reduction_pct"]),
    )

    return build_reader_html(page_data.url, page_data.text, final_metrics, links_markdown)


@app.get("/convert", response_class=PlainTextResponse)
async def convert_endpoint(
    url: str = Query(..., description="Target page URL"),
    mode: str = Query("clean_text", description="Conversion mode"),
) -> str:
    try:
        parsed_mode = parse_mode(mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    page_data, _html = await get_page_data(url)
    content_hash = hashlib.sha256(page_data.text.encode("utf-8")).hexdigest()
    cache_key = f"{page_data.url}|{parsed_mode.value}|{content_hash}"
    cached = cache.get_converted(cache_key)
    if cached:
        return cached

    converted = convert_content(page_data, parsed_mode)
    links_block = format_links_markdown(page_data.links)
    if parsed_mode != ConvertMode.KEY_LINKS and links_block:
        converted = f"{converted}\n\nSource Links:\n{links_block}"
    cache.set_converted(cache_key, page_data.url, parsed_mode.value, content_hash, converted)
    return converted
