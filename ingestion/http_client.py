"""HTTP helpers with Discogs-aware rate limiting."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


@dataclass
class RateLimiterConfig:
    """Configuration parameters for the Discogs rate-limited client."""

    base_url: str = "https://api.discogs.com"
    pause: float = 1.0
    adaptive_pause: bool = False
    max_rate_limit_retries: int = 5
    rate_limit_cooldown: float = 60.0
    preventive_pause_every: int = 50
    preventive_pause_duration: float = 30.0
    timeout: float = 30.0


@dataclass
class RateLimitedDiscogsClient:
    """Small wrapper around ``requests`` that honors Discogs API rate limits."""

    token: Optional[str] = None
    config: RateLimiterConfig = field(default_factory=RateLimiterConfig)
    session: requests.Session | None = None

    _total_calls: int = field(default=0, init=False)
    _rate_limit_hits: int = field(default=0, init=False)
    _last_call_time: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.session is None:
            self.session = requests.Session()

    # ------------------------------------------------------------------
    # Public properties
    @property
    def total_calls(self) -> int:
        return self._total_calls

    @property
    def rate_limit_hits(self) -> int:
        return self._rate_limit_hits

    # ------------------------------------------------------------------
    # Configuration helpers
    def update_config(
        self,
        *,
        pause: Optional[float] = None,
        adaptive_pause: Optional[bool] = None,
        max_rate_limit_retries: Optional[int] = None,
        rate_limit_cooldown: Optional[float] = None,
        preventive_pause_every: Optional[int] = None,
        preventive_pause_duration: Optional[float] = None,
        timeout: Optional[float] = None,
    ) -> None:
        if pause is not None:
            self.config.pause = max(0.0, pause)
        if adaptive_pause is not None:
            self.config.adaptive_pause = adaptive_pause
        if max_rate_limit_retries is not None:
            self.config.max_rate_limit_retries = max(0, max_rate_limit_retries)
        if rate_limit_cooldown is not None:
            self.config.rate_limit_cooldown = max(0.0, rate_limit_cooldown)
        if preventive_pause_every is not None:
            self.config.preventive_pause_every = max(1, preventive_pause_every)
        if preventive_pause_duration is not None:
            self.config.preventive_pause_duration = max(0.0, preventive_pause_duration)
        if timeout is not None:
            self.config.timeout = max(0.0, timeout)

    # ------------------------------------------------------------------
    def get(
        self, url: str, *, params: Optional[Dict[str, Any]] = None
    ) -> Optional[requests.Response]:
        """Perform a GET request honoring Discogs rate limits.

        Args:
            url: Absolute or relative Discogs endpoint.
            params: Query string parameters.
        Returns:
            A ``requests.Response`` object on success, otherwise ``None``.
        """

        full_url = (
            url
            if url.lower().startswith("http")
            else urljoin(self.config.base_url, url)
        )
        params = dict(params or {})
        if self.token and "token" not in params:
            params["token"] = self.token

        self._perform_preventive_pause()
        self._respect_minimum_pause()

        retries = 0
        while retries <= self.config.max_rate_limit_retries:
            try:
                self._last_call_time = time.time()
                self._total_calls += 1

                response = self._session_get(full_url, params)
                if response is None:
                    return None

                if response.status_code == 429:
                    self._rate_limit_hits += 1
                    if retries >= self.config.max_rate_limit_retries:
                        logger.error(
                            "Máximo de reintentos por límite de tasa alcanzado para %s",
                            full_url,
                        )
                        return None

                    wait = self.config.rate_limit_cooldown * (2**retries)
                    logger.warning(
                        "Límite de tasa alcanzado para %s. Esperando %.1f segundos antes de reintentar (%s/%s)",
                        full_url,
                        wait,
                        retries + 1,
                        self.config.max_rate_limit_retries,
                    )
                    time.sleep(wait)
                    retries += 1
                    continue

                remaining = response.headers.get("X-Discogs-Ratelimit-Remaining")
                reset_time = response.headers.get("X-Discogs-Ratelimit-Reset")
                self._apply_dynamic_pause(remaining, reset_time)
                return response

            except requests.RequestException as exc:
                logger.error("Error de conexión al llamar %s: %s", full_url, exc)
                return None

        return None

    def get_json(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        context: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Convenience helper that returns the JSON payload or ``None``."""

        response = self.get(url, params=params)
        if response is None:
            return None

        if not 200 <= response.status_code < 300:
            if context:
                logger.warning(
                    "Respuesta no exitosa (%s) obteniendo %s",
                    response.status_code,
                    context,
                )
            return None

        try:
            return response.json()
        except ValueError:
            if context:
                logger.warning("No se pudo decodificar JSON para %s", context)
            return None

    # ------------------------------------------------------------------
    # Internals
    def _session_get(
        self, url: str, params: Dict[str, Any]
    ) -> Optional[requests.Response]:
        assert self.session is not None  # for type checkers
        return self.session.get(url, params=params, timeout=self.config.timeout)

    def _perform_preventive_pause(self) -> None:
        if (
            self._total_calls
            and self._total_calls % self.config.preventive_pause_every == 0
        ):
            logger.info(
                "Pausa preventiva después de %s llamadas (%.1f s)",
                self._total_calls,
                self.config.preventive_pause_duration,
            )
            time.sleep(self.config.preventive_pause_duration)

    def _respect_minimum_pause(self) -> None:
        if self._last_call_time is None:
            return
        elapsed = time.time() - self._last_call_time
        if elapsed < self.config.pause:
            time.sleep(self.config.pause - elapsed)

    def _apply_dynamic_pause(
        self, remaining: Optional[str], reset_time: Optional[str]
    ) -> None:
        pause = self.config.pause
        if self.config.adaptive_pause and remaining is not None:
            try:
                remaining_calls = int(remaining)
                if remaining_calls <= 10:
                    pause = max(pause, self.config.pause * 3, 10)
                elif remaining_calls <= 20:
                    pause = max(pause, self.config.pause * 2, 5)

                if reset_time and reset_time.isdigit():
                    reset_seconds = int(reset_time)
                    if reset_seconds < 60:
                        pause = max(pause, reset_seconds / 2)
            except ValueError:
                pass

        if pause > 0:
            time.sleep(pause)


__all__ = ["RateLimitedDiscogsClient", "RateLimiterConfig"]
