"""Database access helpers shared by Discogs ingestion scripts."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Sequence

from settings import get_database_path
from scraper import db as scraper_db


@dataclass(slots=True)
class RepositoryConfig:
    """Configuration for ingestion database utilities."""

    path: Path
    ensure_schema: bool = True


def _coerce_path(path: Optional[Path]) -> Path:
    if path is not None:
        return path
    return get_database_path()


@contextmanager
def open_connection(path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """Return a context-managed SQLite connection ensuring schema if requested."""

    db_path = _coerce_path(path)
    connection = sqlite3.connect(str(db_path))
    try:
        scraper_db.ensure_schema(connection)
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
    finally:
        connection.close()


class IngestionRepository:
    """High-level helper around sqlite3 for ingestion workflows."""

    def __init__(self, config: Optional[RepositoryConfig] = None) -> None:
        config = config or RepositoryConfig(path=_coerce_path(None))
        self._config = config
        self._connection: Optional[sqlite3.Connection] = None
        self._cursor: Optional[sqlite3.Cursor] = None

    def __enter__(self) -> "IngestionRepository":
        self._connection = sqlite3.connect(str(self._config.path))
        if self._config.ensure_schema:
            scraper_db.ensure_schema(self._connection)
        self._cursor = self._connection.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._connection is None:
            return
        try:
            if exc_type is None:
                self._connection.commit()
        finally:
            self._connection.close()
            self._connection = None
            self._cursor = None

    @property
    def cursor(self) -> sqlite3.Cursor:
        if self._cursor is None:
            raise RuntimeError("Repository cursor accessed outside of context")
        return self._cursor

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Repository connection accessed outside of context")
        return self._connection

    # --- lookups -----------------------------------------------------------------

    def user_exists(self, user_id: str) -> bool:
        self.cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None

    def item_exists(self, item_id: int) -> bool:
        self.cursor.execute("SELECT 1 FROM items WHERE item_id = ?", (item_id,))
        return self.cursor.fetchone() is not None

    def interaction_exists(
        self, user_id: str, item_id: int, interaction_type: str
    ) -> bool:
        self.cursor.execute(
            """
            SELECT 1
            FROM interactions
            WHERE user_id = ? AND item_id = ? AND interaction_type = ?
            """,
            (user_id, item_id, interaction_type),
        )
        return self.cursor.fetchone() is not None

    def count_user_interactions(self, user_id: str) -> int:
        self.cursor.execute(
            "SELECT COUNT(*) FROM interactions WHERE user_id = ?", (user_id,)
        )
        row = self.cursor.fetchone()
        return int(row[0]) if row else 0

    # --- write helpers -----------------------------------------------------------

    def upsert_user(
        self,
        *,
        user_id: str,
        username: str,
        location: Optional[str],
        joined_date: Optional[str],
    ) -> None:
        scraper_db.upsert_user(
            self.cursor,
            user_id=user_id,
            username=username,
            location=location,
            joined_date=joined_date,
        )

    def upsert_item(
        self,
        *,
        item_id: int,
        title: str,
        artist: str,
        year: Optional[int],
        genres: Sequence[str] | str,
        styles: Sequence[str] | str,
        image_url: Optional[str],
    ) -> None:
        if isinstance(genres, str):
            genres_iterable: Sequence[str] = [
                genre.strip() for genre in genres.split(",") if genre.strip()
            ]
        else:
            genres_iterable = genres

        if isinstance(styles, str):
            styles_iterable: Sequence[str] = [
                style.strip() for style in styles.split(",") if style.strip()
            ]
        else:
            styles_iterable = styles

        scraper_db.upsert_item(
            self.cursor,
            item_id=item_id,
            title=title,
            artists=artist,
            year=year,
            genres=genres_iterable,
            styles=styles_iterable,
            image_url=image_url,
        )

    def record_interaction(
        self,
        *,
        user_id: str,
        item_id: int,
        interaction_type: str,
        rating: Optional[float],
        date_added: Optional[str],
    ) -> None:
        scraper_db.record_interaction(
            self.cursor,
            user_id=user_id,
            item_id=item_id,
            interaction_type=interaction_type,
            rating=rating,
            date_added=date_added,
        )

    def commit(self) -> None:
        self.connection.commit()
