from __future__ import annotations

from bs4 import BeautifulSoup
import trafilatura


def extract_main_text(html: str) -> str:
    extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
    if extracted and extracted.strip():
        return extracted.strip()

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()

    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    return text.strip()
