"""HTTP helper utilities for Discogs web scraping."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urljoin

import requests

try:  # pragma: no cover - optional dependency
    import cloudscraper  # type: ignore
except ImportError:  # pragma: no cover - handled gracefully
    cloudscraper = None

BASE_URL = "https://www.discogs.com"

_DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


@dataclass(slots=True)
class HttpResponse:
    """Lightweight HTTP response representation."""

    url: str
    status_code: int
    text: str
    headers: Dict[str, str]

    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class DiscogsScraperSession:
    """Requests session wrapper with rate-limiting and retry handling."""

    def __init__(
        self,
        *,
        min_delay: float = 1.5,
        delay_jitter: float = 0.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        timeout: int = 30,
        user_agent: Optional[str] = None,
    ) -> None:
        if cloudscraper is not None:
            self._session = cloudscraper.create_scraper()
        else:
            self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": user_agent or random.choice(_DEFAULT_USER_AGENTS),
                "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        self.min_delay = min_delay
        self.delay_jitter = max(0.0, delay_jitter)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.timeout = timeout
        self._last_request_time: float | None = None

    def get(self, url: str, *, params: Optional[dict] = None) -> HttpResponse:
        """Fetch a page honoring rate limits and retry policy."""

        absolute_url = urljoin(BASE_URL, url)
        retries = 0

        while True:
            self._respect_delay()
            try:
                response = self._session.get(
                    absolute_url,
                    params=params,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if retries >= self.max_retries:
                    raise RuntimeError(
                        f"Failed to fetch {absolute_url}: {exc}"
                    ) from exc
                self._backoff_sleep(retries)
                retries += 1
                continue

            self._last_request_time = time.monotonic()

            if 200 <= response.status_code < 300:
                return HttpResponse(
                    url=response.url,
                    status_code=response.status_code,
                    text=response.text,
                    headers=dict(response.headers),
                )

            if response.status_code in {403, 429, 500, 502, 503, 504}:
                if retries >= self.max_retries:
                    raise RuntimeError(
                        f"Received status {response.status_code} from {absolute_url} after retries"
                    )
                self._backoff_sleep(retries)
                retries += 1
                continue

            raise RuntimeError(
                f"Unexpected status {response.status_code} while fetching {absolute_url}"
            )

    def _respect_delay(self) -> None:
        if self._last_request_time is None:
            return
        elapsed = time.monotonic() - self._last_request_time
        target_delay = self.min_delay
        if self.delay_jitter > 0:
            target_delay += random.uniform(0, self.delay_jitter)
        if elapsed < target_delay:
            time.sleep(target_delay - elapsed)

    def _backoff_sleep(self, retries: int) -> None:
        delay = self.min_delay * (self.backoff_factor**retries)
        time.sleep(delay)
