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
