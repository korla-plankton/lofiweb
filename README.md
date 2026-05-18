# LoFiWeb MVP

LoFiWeb is a low-bandwidth web reader/proxy prototype.

It fetches a target URL server-side, extracts readable text, optionally converts it to other low-bandwidth formats, caches results in SQLite, and returns either lightweight HTML (`/read`) or plain text (`/text`, `/convert`).

## Features

- FastAPI service with a simple homepage form (`GET /`)
- Reader endpoint (`GET /read?url=...`)
- Plain text endpoint (`GET /text?url=...`)
- Conversion endpoint (`GET /convert?url=...&mode=...`)
- Server-side fetching via `httpx`
- Deterministic extraction using `trafilatura`, with BeautifulSoup fallback
- Deterministic conversion for:
  - `clean_text`
  - `key_links`
- Optional OpenAI-compatible LLM conversion (enabled only when `OPENAI_API_KEY` is set) for:
  - `bullet_summary`
  - `article_summary`
  - `instructions_only`
  - `q_and_a_ready_context`
- SQLite caching:
  - extracted text by normalized URL
  - converted output by URL + mode + content hash

## Safe prompting rules for LLM modes

The app enforces these instructions in LLM conversion prompts:

- Preserve facts from the page.
- Do not invent missing details.
- Preserve dates, prices, warnings, names, instructions, and links.
- State when source content is unclear.

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
- http://127.0.0.1:8000/convert?url=https://example.com&mode=clean_text

## Conversion modes

- `clean_text`
- `bullet_summary`
- `article_summary`
- `key_links`
- `instructions_only`
- `q_and_a_ready_context`

## Optional OpenAI-compatible configuration

```bash
export OPENAI_API_KEY=your_key
# Optional overrides
export OPENAI_BASE_URL=https://api.openai.com/v1
export LOFIWEB_LLM_MODEL=gpt-4o-mini
```

If `OPENAI_API_KEY` is missing and an LLM mode is requested, `/convert` returns `503`.

## Testing

```bash
pytest
```
