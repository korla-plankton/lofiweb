from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ConvertMode(str, Enum):
    CLEAN_TEXT = "clean_text"
    BULLET_SUMMARY = "bullet_summary"
    ARTICLE_SUMMARY = "article_summary"
    KEY_LINKS = "key_links"
    INSTRUCTIONS_ONLY = "instructions_only"
    Q_AND_A_READY_CONTEXT = "q_and_a_ready_context"


@dataclass
class PageData:
    url: str
    text: str
    links: list[str]


SAFE_PROMPT_RULES = """You must follow these rules strictly:
- Preserve facts from the source content.
- Do not invent missing details.
- Preserve dates, prices, warnings, names, instructions, and links.
- If source content is unclear or missing, explicitly say so.
"""


class BaseConverter:
    def supports(self, mode: ConvertMode) -> bool:
        raise NotImplementedError

    def convert(self, data: PageData, mode: ConvertMode) -> str:
        raise NotImplementedError


class DeterministicConverter(BaseConverter):
    def supports(self, mode: ConvertMode) -> bool:
        return mode in {ConvertMode.CLEAN_TEXT, ConvertMode.KEY_LINKS}

    def convert(self, data: PageData, mode: ConvertMode) -> str:
        if mode == ConvertMode.CLEAN_TEXT:
            return data.text.strip()

        if mode == ConvertMode.KEY_LINKS:
            if not data.links:
                return "No links found in source content."
            unique_links = list(dict.fromkeys(link for link in data.links if link.strip()))
            return "\n".join(f"- {link}" for link in unique_links)

        raise ValueError(f"Unsupported deterministic mode: {mode}")


class LLMConverter(BaseConverter):
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")

    def is_enabled(self) -> bool:
        return bool(self.api_key)

    def supports(self, mode: ConvertMode) -> bool:
        return mode in {
            ConvertMode.BULLET_SUMMARY,
            ConvertMode.ARTICLE_SUMMARY,
            ConvertMode.INSTRUCTIONS_ONLY,
            ConvertMode.Q_AND_A_READY_CONTEXT,
        }

    def _prompt_for_mode(self, mode: ConvertMode) -> str:
        prompts = {
            ConvertMode.BULLET_SUMMARY: "Create a concise bullet summary.",
            ConvertMode.ARTICLE_SUMMARY: "Create a concise article-style summary with short paragraphs.",
            ConvertMode.INSTRUCTIONS_ONLY: "Extract only explicit actionable instructions in order.",
            ConvertMode.Q_AND_A_READY_CONTEXT: "Produce a compact Q&A-ready context preserving key entities, constraints, and facts.",
        }
        return prompts[mode]

    def convert(self, data: PageData, mode: ConvertMode) -> str:
        if not self.is_enabled():
            raise RuntimeError("LLM conversion is not enabled. Set OPENAI_API_KEY.")

        if not self.supports(mode):
            raise ValueError(f"Unsupported LLM mode: {mode}")

        # Use lazy import so deterministic modes work without SDK installed.
        import httpx

        model = os.getenv("LOFIWEB_LLM_MODEL", "gpt-4o-mini")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SAFE_PROMPT_RULES},
                {
                    "role": "user",
                    "content": (
                        f"Mode: {mode.value}\n"
                        f"Task: {self._prompt_for_mode(mode)}\n\n"
                        f"Source URL: {data.url}\n"
                        f"Source Links:\n" + "\n".join(data.links[:50]) + "\n\n"
                        f"Source Content:\n{data.text[:20000]}"
                    ),
                },
            ],
            "temperature": 0,
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload),
            )
            resp.raise_for_status()
            data_json = resp.json()
        return data_json["choices"][0]["message"]["content"].strip()


def converted_cache_key(url: str, mode: ConvertMode, source_text: str) -> str:
    digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    return f"{url}|{mode.value}|{digest}"


def parse_mode(mode: str) -> ConvertMode:
    try:
        return ConvertMode(mode)
    except ValueError as exc:
        valid = ", ".join(m.value for m in ConvertMode)
        raise ValueError(f"Invalid mode '{mode}'. Valid modes: {valid}") from exc
