"""Database helpers for storing scraped Discogs data."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from settings import get_database_path


@dataclass(slots=True)
class DatabaseConfig:
    path: Path


@contextmanager
def get_connection(config: DatabaseConfig):
    connection = sqlite3.connect(str(config.path))
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def ensure_schema(connection: sqlite3.Connection) -> None:
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            location TEXT,
            joined_date TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            item_id INTEGER PRIMARY KEY,
            title TEXT,
            artist TEXT,
            year INTEGER,
            genre TEXT,
            style TEXT,
            image_url TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS interactions (
            interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            item_id INTEGER,
            interaction_type TEXT,
            rating REAL,
            date_added TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(item_id) REFERENCES items(item_id)
        )
        """
    )
    _deduplicate_interactions(cursor)
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_interactions_unique
        ON interactions(user_id, item_id, interaction_type)
        """
    )
    connection.commit()


def _deduplicate_interactions(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        DELETE FROM interactions
        WHERE rowid NOT IN (
            SELECT MAX(rowid)
            FROM interactions
            GROUP BY user_id, item_id, interaction_type
        )
        """
    )


def upsert_user(
    cursor: sqlite3.Cursor,
    *,
    user_id: str,
    username: str,
    location: Optional[str],
    joined_date: Optional[str],
) -> None:
    cursor.execute(
        """
        INSERT INTO users (user_id, username, location, joined_date)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            location=COALESCE(excluded.location, users.location),
            joined_date=COALESCE(excluded.joined_date, users.joined_date)
        """,
        (user_id, username, location, joined_date),
    )


def upsert_item(
    cursor: sqlite3.Cursor,
    *,
    item_id: int,
    title: str,
    artists: str,
    year: Optional[int],
    genres: Iterable[str],
    styles: Iterable[str],
    image_url: Optional[str],
) -> None:
    cursor.execute(
        """
        INSERT INTO items (item_id, title, artist, year, genre, style, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            title=excluded.title,
            artist=excluded.artist,
            year=COALESCE(excluded.year, items.year),
            genre=excluded.genre,
            style=excluded.style,
            image_url=COALESCE(excluded.image_url, items.image_url)
        """,
        (
            item_id,
            title,
            artists,
            year,
            ", ".join(sorted(set(genres))),
            ", ".join(sorted(set(styles))),
            image_url,
        ),
    )


def record_interaction(
    cursor: sqlite3.Cursor,
    *,
    user_id: str,
    item_id: int,
    interaction_type: str,
    rating: Optional[float],
    date_added: Optional[str],
) -> None:
    cursor.execute(
        """
        INSERT INTO interactions (user_id, item_id, interaction_type, rating, date_added)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, item_id, interaction_type) DO UPDATE SET
            rating=excluded.rating,
            date_added=COALESCE(excluded.date_added, interactions.date_added)
        """,
        (user_id, item_id, interaction_type, rating, date_added),
    )


def connection_from_settings() -> DatabaseConfig:
    return DatabaseConfig(path=get_database_path())
