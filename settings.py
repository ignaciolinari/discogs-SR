"""Centralized configuration helpers for Discogs recommendation project."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


DATA_DIR.mkdir(exist_ok=True)


def get_database_path() -> Path:
    """Return the database path configured via env or default location."""

    env_path = os.getenv("DATABASE_PATH")
    if env_path:
        resolved_path = Path(env_path).expanduser()
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        return resolved_path

    default_path = DATA_DIR / "discogs.db"
    if default_path.exists():
        return default_path

    legacy_path = BASE_DIR / "discogs.db"
    if legacy_path.exists():
        return legacy_path

    return default_path


def get_discogs_token(optional: bool = False) -> Optional[str]:
    """Return Discogs API token.

    Args:
        optional: When True, allow missing token (returns None).

    Raises:
        RuntimeError: If token is required and not configured.
    """

    token = os.getenv("DISCOGS_TOKEN")
    if token:
        return token

    if optional:
        return None

    raise RuntimeError(
        "DISCOGS_TOKEN is not configured. Export it in your shell or conda environment."
    )


def get_seed_username(default: str = "Xmipod") -> str:
    """Return seed username for bootstrap operations."""

    return os.getenv("DISCOGS_SEED_USERNAME", default)


def get_api_pause(default: int = 1) -> int:
    """Return default pause between API calls in seconds."""

    env_value = os.getenv("DISCOGS_API_PAUSE")
    if not env_value:
        return default

    try:
        pause = int(env_value)
        return pause if pause > 0 else default
    except ValueError:
        return default


__all__ = [
    "BASE_DIR",
    "DATA_DIR",
    "get_database_path",
    "get_discogs_token",
    "get_seed_username",
    "get_api_pause",
    "get_scraper_cookies_file",
    "get_scraper_cookie_refresh",
    "get_scraper_headers_file",
]


def get_scraper_cookies_file() -> Optional[Path]:
    """Return the path to a cookies export for web scraping."""

    env_path = os.getenv("DISCOGS_COOKIES_FILE")
    if not env_path:
        return None
    return Path(env_path).expanduser()


def get_scraper_cookie_refresh(default: float = 900.0) -> float:
    """Return refresh interval (seconds) for reloading scraper cookies."""

    env_value = os.getenv("DISCOGS_COOKIES_REFRESH_SECONDS")
    if not env_value:
        return default
    try:
        refresh = float(env_value)
        return refresh if refresh > 0 else default
    except ValueError:
        return default


def get_scraper_headers_file() -> Optional[Path]:
    """Return an optional JSON file with extra headers for scraping."""

    env_path = os.getenv("DISCOGS_HEADERS_FILE")
    if not env_path:
        return None
    return Path(env_path).expanduser()
