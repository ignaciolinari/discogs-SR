"""Authentication helpers for Discogs web scraping."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import requests
from requests.cookies import RequestsCookieJar

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CookieFileLoader:
    """Load cookies from disk and refresh them periodically.

    The loader supports JSON exports (list of cookie dicts or mapping name->value)
    and the legacy Netscape ``cookies.txt`` format. Updated files are picked up
    automatically based on modification time and optional refresh interval.
    """

    path: Path
    reload_interval: Optional[float] = 900.0
    default_domain: str = ".discogs.com"

    _cached_jar: RequestsCookieJar | None = field(default=None, init=False)
    _last_mtime: float | None = field(default=None, init=False)
    _last_refresh: float | None = field(default=None, init=False)
    _warned_missing: bool = field(default=False, init=False)
    _warned_expired: bool = field(default=False, init=False)

    def apply(self, session: requests.Session, *, force: bool = False) -> None:
        """Update ``session.cookies`` with the latest cookies from disk."""

        jar = self._get_cookie_jar(force=force)
        if jar is None:
            return
        session.cookies.update(jar)

    def check_expiration(self) -> bool:
        """Check if critical cookies are expired.

        Returns:
            True if cookies are valid, False if expired or missing
        """
        if not self.path.exists():
            return False

        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw.strip())

            # Convert to list of dicts
            if isinstance(data, Mapping):
                if "cookies" in data and isinstance(data["cookies"], list):
                    cookies = data["cookies"]
                else:
                    return True  # Can't check expiration for simple name:value format
            elif isinstance(data, list):
                cookies = data
            else:
                return True

            # Check Cloudflare cookie
            import time as time_module

            now = time_module.time()

            for cookie in cookies:
                if not isinstance(cookie, Mapping):
                    continue

                name = cookie.get("name")
                if name == "__cf_bm":
                    # Check if expired
                    expires = cookie.get("expires")
                    if expires:
                        # expires can be timestamp or ISO string
                        if isinstance(expires, (int, float)):
                            exp_timestamp = expires
                        elif isinstance(expires, str):
                            try:
                                from datetime import datetime

                                exp_dt = datetime.fromisoformat(
                                    expires.replace("Z", "+00:00")
                                )
                                exp_timestamp = exp_dt.timestamp()
                            except Exception:
                                continue
                        else:
                            continue

                        if exp_timestamp < now:
                            if not self._warned_expired:
                                logger.warning(
                                    "Cloudflare cookie __cf_bm has EXPIRED. "
                                    "Run 'python3 refresh_cookies.py' to update cookies."
                                )
                                self._warned_expired = True
                            return False

            return True

        except Exception as exc:
            logger.debug("Could not check cookie expiration: %s", exc)
            return True  # Assume valid if we can't check

    # ------------------------------------------------------------------
    def _get_cookie_jar(self, *, force: bool) -> RequestsCookieJar | None:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            if not self._warned_missing:
                logger.warning(
                    "Cookie file %s not found; scraping will proceed anonymously.",
                    self.path,
                )
                self._warned_missing = True
            return None

        need_refresh = force or self._cached_jar is None
        now = time.monotonic()

        if self.reload_interval is not None and self.reload_interval <= 0:
            self.reload_interval = None

        if (
            not need_refresh
            and self._last_mtime is not None
            and mtime != self._last_mtime
        ):
            need_refresh = True
        if (
            not need_refresh
            and self.reload_interval is not None
            and self._last_refresh is not None
            and now - self._last_refresh >= self.reload_interval
        ):
            need_refresh = True

        if not need_refresh:
            return self._cached_jar

        try:
            jar = self._load_from_disk()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to load cookies from %s: %s", self.path, exc)
            return self._cached_jar

        self._cached_jar = jar
        self._last_mtime = mtime
        self._last_refresh = now
        self._warned_missing = False
        logger.info("Loaded %s cookies from %s", len(jar), self.path)
        return jar

    # ------------------------------------------------------------------
    def _load_from_disk(self) -> RequestsCookieJar:
        raw = self.path.read_text(encoding="utf-8")
        stripped = raw.strip()
        if not stripped:
            raise ValueError("Cookie file is empty")

        if stripped.startswith("{") or stripped.startswith("["):
            data = json.loads(stripped)
            return self._load_from_json(data)

        return self._load_from_netscape(stripped.splitlines())

    def _load_from_json(self, data: Any) -> RequestsCookieJar:
        jar = RequestsCookieJar()

        if isinstance(data, Mapping):
            if "cookies" in data and isinstance(data["cookies"], list):
                entries = data["cookies"]
            else:
                entries = [
                    {"name": key, "value": value}
                    for key, value in data.items()
                    if isinstance(key, str)
                ]
        elif isinstance(data, list):
            entries = data
        else:
            raise ValueError("Unsupported JSON structure for cookies")

        added = 0
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue

            name = entry.get("name")
            value = entry.get("value")
            if not name or value is None:
                continue

            domain = entry.get("domain") or self.default_domain
            path = entry.get("path") or "/"
            secure = bool(entry.get("secure", False))
            rest = {}
            if entry.get("httpOnly") or entry.get("http_only"):
                rest["HttpOnly"] = True

            jar.set(
                str(name),
                str(value),
                domain=str(domain),
                path=str(path),
                secure=secure,
                rest=rest,
            )
            added += 1

        if added == 0:
            raise ValueError("No cookies parsed from JSON file")

        return jar

    def _load_from_netscape(self, lines: Iterable[str]) -> RequestsCookieJar:
        jar = RequestsCookieJar()
        added = 0

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) != 7:
                continue

            domain, _, path, secure_flag, _, name, value = parts
            secure = secure_flag.upper() == "TRUE"
            jar.set(
                name,
                value,
                domain=domain or self.default_domain,
                path=path or "/",
                secure=secure,
            )
            added += 1

        if added == 0:
            raise ValueError("No cookies parsed from Netscape format")

        return jar


def load_headers_from_file(path: Path) -> dict[str, str]:
    """Load additional HTTP headers from a JSON mapping."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("Headers file must contain a JSON object")
    return {str(key): str(value) for key, value in data.items()}


__all__ = ["CookieFileLoader", "load_headers_from_file"]
