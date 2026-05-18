from __future__ import annotations

from urllib.parse import urljoin

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


def extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue
        full_url = urljoin(base_url, href)
        links.append(full_url)
    return links
