# LoFiWeb MVP

LoFiWeb is a low-bandwidth web reader/proxy prototype.

It fetches a target URL server-side, extracts readable text, caches it in SQLite, and returns either lightweight HTML (`/read`) or plain text (`/text`).

## Features

- FastAPI service with a simple homepage form (`GET /`)
- Reader endpoint (`GET /read?url=...`)
- Plain text endpoint (`GET /text?url=...`)
- Server-side fetching via `httpx`
- Deterministic extraction using `trafilatura`, with BeautifulSoup fallback
- SQLite caching by normalized URL
- Basic error handling:
  - invalid URLs
  - timeouts
  - non-HTML responses
  - failed extraction

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Run

```bash
uvicorn app.main:app --reload
```

Open:

- http://127.0.0.1:8000/
- http://127.0.0.1:8000/read?url=https://example.com
- http://127.0.0.1:8000/text?url=https://example.com

## Testing

```bash
pytest
```

## Notes for next phase

There is a clean seam for future post-processing in `get_reader_text` (e.g. summarization, format conversion). Keep deterministic extraction as the primary step.
