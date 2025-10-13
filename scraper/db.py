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
            source_release_id INTEGER,
            title TEXT,
            artist TEXT,
            genre TEXT,
            style TEXT,
            country TEXT,
            released TEXT,
            year INTEGER,
            image_url TEXT,
            format_summary TEXT,
            label_summary TEXT,
            community_have INTEGER DEFAULT 0,
            community_want INTEGER DEFAULT 0,
            community_rating_average REAL DEFAULT 0,
            community_rating_count INTEGER DEFAULT 0
        )
        """
    )

    # Optimización: una sola query PRAGMA en lugar de 11 llamadas individuales
    _ensure_columns(
        cursor,
        "items",
        [
            ("source_release_id", "INTEGER"),
            ("country", "TEXT"),
            ("released", "TEXT"),
            ("format_summary", "TEXT"),
            ("label_summary", "TEXT"),
            ("genre", "TEXT"),
            ("style", "TEXT"),
            ("community_have", "INTEGER DEFAULT 0"),
            ("community_want", "INTEGER DEFAULT 0"),
            ("community_rating_average", "REAL DEFAULT 0"),
            ("community_rating_count", "INTEGER DEFAULT 0"),
        ],
    )
    cursor.execute(
        "UPDATE items SET source_release_id = item_id WHERE source_release_id IS NULL"
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS labels (
            label_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT,
            profile TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS item_labels (
            item_id INTEGER NOT NULL,
            label_id INTEGER NOT NULL,
            catalog_number TEXT,
            PRIMARY KEY (item_id, label_id, catalog_number),
            FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
            FOREIGN KEY (label_id) REFERENCES labels(label_id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS genres (
            genre_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS item_genres (
            item_id INTEGER NOT NULL,
            genre_id INTEGER NOT NULL,
            PRIMARY KEY (item_id, genre_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
            FOREIGN KEY (genre_id) REFERENCES genres(genre_id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS styles (
            style_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS item_styles (
            item_id INTEGER NOT NULL,
            style_id INTEGER NOT NULL,
            PRIMARY KEY (item_id, style_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
            FOREIGN KEY (style_id) REFERENCES styles(style_id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS formats (
            format_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            description TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS item_formats (
            item_id INTEGER NOT NULL,
            format_id INTEGER NOT NULL,
            notes TEXT,
            PRIMARY KEY (item_id, format_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id) ON DELETE CASCADE,
            FOREIGN KEY (format_id) REFERENCES formats(format_id) ON DELETE CASCADE
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
            weight REAL DEFAULT 1.0,
            source TEXT,
            date_added TEXT,
            event_ts TEXT,
            review_text TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(item_id) REFERENCES items(item_id)
        )
        """
    )
    # Optimización: una sola query PRAGMA en lugar de 4 llamadas individuales
    _ensure_columns(
        cursor,
        "interactions",
        [
            ("weight", "REAL DEFAULT 1.0"),
            ("source", "TEXT"),
            ("event_ts", "TEXT"),
            ("review_text", "TEXT"),
        ],
    )
    _deduplicate_interactions(cursor)
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_interactions_user_item_type
        ON interactions(user_id, item_id, interaction_type)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_items_source_release
        ON items(source_release_id)
        """
    )
    connection.commit()


def _ensure_column(
    cursor: sqlite3.Cursor, table: str, column: str, column_type: str
) -> None:
    """Asegura que una columna existe en una tabla (versión legacy, usa _ensure_columns para mejor rendimiento)."""
    _ensure_columns(cursor, table, [(column, column_type)])


def _ensure_columns(
    cursor: sqlite3.Cursor, table: str, columns: list[tuple[str, str]]
) -> None:
    """Asegura que múltiples columnas existan en una tabla con una sola query PRAGMA.

    Args:
        cursor: Cursor de la conexión SQLite
        table: Nombre de la tabla
        columns: Lista de tuplas (nombre_columna, tipo_columna)

    Example:
        _ensure_columns(cursor, "items", [
            ("country", "TEXT"),
            ("released", "TEXT"),
            ("year", "INTEGER")
        ])
    """
    # Una sola consulta PRAGMA para obtener todas las columnas existentes
    cursor.execute(f"PRAGMA table_info({table})")
    existing_columns = {row[1] for row in cursor.fetchall()}

    # Añadir solo las columnas que faltan
    for column_name, column_type in columns:
        if column_name not in existing_columns:
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}"
            )


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
    source_release_id: int,
    title: str,
    artists: str,
    year: Optional[int],
    genres: Iterable[str],
    styles: Iterable[str],
    image_url: Optional[str],
    country: Optional[str],
    released: Optional[str],
    format_summary: Optional[str],
    label_summary: Optional[str],
) -> None:
    # Formato estándar: se almacenan como ", " (coma-espacio)
    # Al leer, el sistema acepta tanto "," como "|" para compatibilidad
    genres_text = ", ".join(sorted({genre for genre in genres if genre}))
    styles_text = ", ".join(sorted({style for style in styles if style}))

    cursor.execute(
        """
        INSERT INTO items (
            item_id,
            source_release_id,
            title,
            artist,
            year,
            genre,
            style,
            image_url,
            country,
            released,
            format_summary,
            label_summary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            source_release_id=COALESCE(excluded.source_release_id, items.source_release_id),
            title=CASE WHEN excluded.title IS NOT NULL AND excluded.title != '' THEN excluded.title ELSE items.title END,
            artist=CASE WHEN excluded.artist IS NOT NULL AND excluded.artist != '' THEN excluded.artist ELSE items.artist END,
            year=COALESCE(excluded.year, items.year),
            genre=excluded.genre,
            style=excluded.style,
            image_url=COALESCE(excluded.image_url, items.image_url),
            country=COALESCE(excluded.country, items.country),
            released=COALESCE(excluded.released, items.released),
            format_summary=COALESCE(excluded.format_summary, items.format_summary),
            label_summary=COALESCE(excluded.label_summary, items.label_summary)
        """,
        (
            item_id,
            source_release_id,
            title or "Unknown Title",
            artists or "Unknown Artist",
            year,
            genres_text,
            styles_text,
            image_url,
            country,
            released,
            format_summary,
            label_summary,
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
