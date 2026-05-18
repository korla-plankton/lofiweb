from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


class Cache:
    def __init__(self, db_path: str = "lofiweb_cache.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS page_cache (
                    url TEXT PRIMARY KEY,
                    content TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS converted_cache (
                    cache_key TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    content TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS page_metrics (
                    url TEXT PRIMARY KEY,
                    original_html_size INTEGER NOT NULL,
                    extracted_text_size INTEGER NOT NULL,
                    simplified_reader_html_size INTEGER NOT NULL,
                    estimated_reduction_pct REAL NOT NULL
                )
                """
            )

    def get(self, url: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content FROM page_cache WHERE url = ?", (url,)
            ).fetchone()
        return row[0] if row else None

    def set(self, url: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO page_cache(url, content) VALUES (?, ?)
                ON CONFLICT(url) DO UPDATE SET content = excluded.content
                """,
                (url, content),
            )

    def get_converted(self, cache_key: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content FROM converted_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        return row[0] if row else None

    def set_converted(self, cache_key: str, url: str, mode: str, content_hash: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO converted_cache(cache_key, url, mode, content_hash, content)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    url = excluded.url,
                    mode = excluded.mode,
                    content_hash = excluded.content_hash,
                    content = excluded.content
                """,
                (cache_key, url, mode, content_hash, content),
            )

    def get_metrics(self, url: str) -> Optional[dict[str, float]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT original_html_size, extracted_text_size, simplified_reader_html_size, estimated_reduction_pct
                FROM page_metrics WHERE url = ?
                """,
                (url,),
            ).fetchone()
        if not row:
            return None
        return {
            "original_html_size": row[0],
            "extracted_text_size": row[1],
            "simplified_reader_html_size": row[2],
            "estimated_reduction_pct": row[3],
        }

    def set_metrics(
        self,
        url: str,
        original_html_size: int,
        extracted_text_size: int,
        simplified_reader_html_size: int,
        estimated_reduction_pct: float,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO page_metrics(url, original_html_size, extracted_text_size, simplified_reader_html_size, estimated_reduction_pct)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    original_html_size = excluded.original_html_size,
                    extracted_text_size = excluded.extracted_text_size,
                    simplified_reader_html_size = excluded.simplified_reader_html_size,
                    estimated_reduction_pct = excluded.estimated_reduction_pct
                """,
                (url, original_html_size, extracted_text_size, simplified_reader_html_size, estimated_reduction_pct),
            )
