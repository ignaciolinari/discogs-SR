"""End-to-end scraping pipeline for Discogs HTML pages."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .db import (
    DatabaseConfig,
    connection_from_settings,
    ensure_schema,
    get_connection,
    record_interaction,
    upsert_item,
    upsert_user,
)
from .auth import CookieFileLoader, load_headers_from_file
from .http import DiscogsScraperSession
from .models import ReleaseDetail, ReleaseSummary, Review, UserProfile
from .parsers import (
    parse_release_detail,
    parse_release_user_list,
    parse_search_results,
    parse_user_profile,
)
from settings import (
    get_scraper_cookie_refresh,
    get_scraper_cookies_file,
    get_scraper_headers_file,
)

logger = logging.getLogger(__name__)

_SEARCH_PATH = "/search/"


@dataclass(slots=True)
class ScrapeStats:
    releases_processed: int
    items_added: int
    users_added: int
    interactions_added: int
    total_items: int
    total_users: int
    total_interactions: int


def _get_table_counts(cursor) -> tuple[int, int, int]:
    cursor.execute("SELECT COUNT(*) FROM users")
    users = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM items")
    items = int(cursor.fetchone()[0])
    cursor.execute("SELECT COUNT(*) FROM interactions")
    interactions = int(cursor.fetchone()[0])
    return users, items, interactions


class DiscogsScraperPipeline:
    """Scrape releases, users, and interactions from Discogs web interface."""

    def __init__(
        self,
        *,
        db_config: Optional[DatabaseConfig] = None,
        session: Optional[DiscogsScraperSession] = None,
        min_delay: float = 2.0,
        delay_jitter: float = 0.0,
        max_retries: int = 4,
        backoff_factor: float = 2.5,
        fetch_user_profiles: bool = True,
        fetch_extended_users: bool = True,
        max_user_pages: int = 3,
        cookies_file: Optional[Path] = None,
        cookies_refresh_seconds: Optional[float] = None,
        headers_file: Optional[Path] = None,
        debug_dump_dir: Optional[Path] = None,
    ) -> None:
        self.db_config = db_config or connection_from_settings()
        if session is not None:
            self.session = session
        else:
            cookie_loader: CookieFileLoader | None = None
            cookies_path = cookies_file or get_scraper_cookies_file()
            if cookies_path:
                refresh_seconds = (
                    cookies_refresh_seconds
                    if cookies_refresh_seconds is not None
                    else get_scraper_cookie_refresh()
                )
                if refresh_seconds is not None and refresh_seconds <= 0:
                    refresh_seconds = None

                cookie_loader = CookieFileLoader(
                    path=Path(cookies_path).expanduser(),
                    reload_interval=refresh_seconds,
                )
            else:
                logger.info(
                    "Scraping without authenticated cookies; Have/Want user lists "
                    "may remain empty. Pass --cookies-file or set DISCOGS_COOKIES_FILE "
                    "to enable authenticated requests."
                )

            # Check cookie expiration if we have a loader
            if cookie_loader and not cookie_loader.check_expiration():
                logger.error(
                    "=" * 60 + "\n"
                    "⚠️  COOKIES EXPIRADAS\n"
                    "=" * 60 + "\n"
                    "Las cookies de Cloudflare están expiradas.\n"
                    "El scraper NO podrá obtener usuarios de have/want.\n\n"
                    "Para actualizar las cookies:\n"
                    "  python3 refresh_cookies.py\n\n"
                    "O exporta cookies manualmente desde tu navegador.\n"
                    "=" * 60
                )

            extra_headers = None
            headers_path = headers_file or get_scraper_headers_file()
            if headers_path:
                try:
                    extra_headers = load_headers_from_file(
                        Path(headers_path).expanduser()
                    )
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning(
                        "Ignoring headers file %s due to error: %s",
                        headers_path,
                        exc,
                    )

            self.session = DiscogsScraperSession(
                min_delay=min_delay,
                delay_jitter=delay_jitter,
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                cookie_loader=cookie_loader,
                extra_headers=extra_headers,
            )
        self.fetch_user_profiles = fetch_user_profiles
        self.fetch_extended_users = fetch_extended_users
        self.max_user_pages = max(0, max_user_pages)
        self._known_users: set[str] = set()
        self._debug_dump_dir = debug_dump_dir.expanduser() if debug_dump_dir else None
        if self._debug_dump_dir is not None:
            self._debug_dump_dir.mkdir(parents=True, exist_ok=True)

    def crawl(
        self,
        *,
        search_url: str = _SEARCH_PATH,
        sort: str = "have,desc",
        release_type: str = "release",
        max_pages: int = 5,
        release_limit: Optional[int] = None,
        commit_every: int = 1,
    ) -> ScrapeStats:
        """Entry point to crawl search results and ingest releases.

        Args:
            search_url: Discogs search path.
            sort: sorting parameter accepted by Discogs search.
            release_type: search type filter.
            max_pages: maximum number of search pages to crawl.
            release_limit: overall release cap (across pages).
            commit_every: hacer commit cada N releases (default: 1 = después de cada release).
        Returns:
            Summary statistics for the scraping run.
        """

        processed = 0
        pending_release_ids: set[int] = set()

        # Manejo de interrupciones para hacer commit antes de salir
        import signal

        def signal_handler(signum, frame):
            logger.warning("Recibida señal de interrupción. Guardando progreso...")
            connection.commit()
            logger.info("Progreso guardado. Releases procesados: %s", processed)
            raise KeyboardInterrupt()

        with get_connection(self.db_config) as connection:
            ensure_schema(connection)
            cursor = connection.cursor()
            start_users, start_items, start_interactions = _get_table_counts(cursor)

            # Registrar handlers para SIGINT (Ctrl+C) y SIGTERM
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            for page_number in range(1, max_pages + 1):
                if release_limit is not None and processed >= release_limit:
                    break

                params = {
                    "sort": sort,
                    "type": release_type,
                    "page": page_number,
                    "per_page": 50,
                }

                logger.info("Fetching search page %s", page_number)
                response = self.session.get(search_url, params=params)
                logger.debug(
                    "Search page %s fetched -> status %s | url %s | %s bytes",
                    page_number,
                    response.status_code,
                    response.url,
                    len(response.text),
                )
                summaries = parse_search_results(response.text)
                if not summaries:
                    logger.warning(
                        "No releases detected on search page %s; dumping snapshot if enabled",
                        page_number,
                    )
                    self._dump_debug_html(
                        kind="search_page",
                        identifier=str(page_number),
                        html=response.text,
                    )
                    break

                for summary in summaries:
                    if summary.release_id in pending_release_ids:
                        continue
                    pending_release_ids.add(summary.release_id)

                    if release_limit is not None and processed >= release_limit:
                        break

                    try:
                        detail = self._fetch_release_detail(summary)
                    except RuntimeError as exc:
                        logger.warning(
                            "Failed to fetch release %s (%s): %s",
                            summary.release_id,
                            summary.url,
                            exc,
                        )
                        continue

                    self._persist_release(cursor, summary, detail)
                    processed += 1

                    # Commit periódico para no perder progreso
                    if commit_every > 0 and processed % commit_every == 0:
                        connection.commit()
                        logger.info(
                            "Checkpoint: Guardados %s releases hasta ahora (cada %s releases)",
                            processed,
                            commit_every,
                        )

            connection.commit()

            end_users, end_items, end_interactions = _get_table_counts(cursor)

        return ScrapeStats(
            releases_processed=processed,
            items_added=max(end_items - start_items, 0),
            users_added=max(end_users - start_users, 0),
            interactions_added=max(end_interactions - start_interactions, 0),
            total_items=end_items,
            total_users=end_users,
            total_interactions=end_interactions,
        )

    def _fetch_release_detail(self, summary: ReleaseSummary) -> ReleaseDetail:
        response = self.session.get(summary.url)
        detail = parse_release_detail(response.text)
        if not detail.release_id:
            detail.release_id = summary.release_id
        return detail

    def _persist_release(
        self,
        cursor,
        summary: ReleaseSummary,
        detail: ReleaseDetail,
    ) -> None:
        release_id = detail.release_id or summary.release_id
        upsert_item(
            cursor,
            item_id=release_id,
            title=detail.title or summary.title,
            artists=detail.artists or summary.artists,
            year=detail.year or summary.year,
            genres=detail.genres or [],
            styles=detail.styles or [],
            image_url=detail.image_url,
        )

        # Users who have the release
        for username in detail.have_users:
            self._record_collection(cursor, username, release_id)

        # Users who want the release
        for username in detail.want_users:
            self._record_wantlist(cursor, username, release_id)

        # Reviews with ratings
        for review in detail.reviews:
            if review.rating is None:
                continue
            self._record_review(cursor, review, release_id)

        if self.fetch_extended_users and self.max_user_pages:
            self._ingest_extended_users(
                cursor,
                release_id,
                existing_have=set(detail.have_users),
                existing_want=set(detail.want_users),
            )

    def _record_collection(self, cursor, username: str, release_id: int) -> None:
        user = self._ensure_user(cursor, username)
        record_interaction(
            cursor,
            user_id=user.user_id,
            item_id=release_id,
            interaction_type="collection",
            rating=None,
            date_added=None,
        )

    def _record_wantlist(self, cursor, username: str, release_id: int) -> None:
        user = self._ensure_user(cursor, username)
        record_interaction(
            cursor,
            user_id=user.user_id,
            item_id=release_id,
            interaction_type="wantlist",
            rating=None,
            date_added=None,
        )

    def _record_review(self, cursor, review: Review, release_id: int) -> None:
        user = self._ensure_user(cursor, review.username)
        date_added = (
            review.date.isoformat() if isinstance(review.date, datetime) else None
        )
        record_interaction(
            cursor,
            user_id=user.user_id,
            item_id=release_id,
            interaction_type="rating",
            rating=review.rating,
            date_added=date_added,
        )

    def _ensure_user(self, cursor, username: str) -> UserProfile:
        normalized = username.strip()
        if not normalized:
            raise ValueError("Empty username provided")

        lookup_key = normalized.lower()

        cursor.execute(
            """
            SELECT user_id, username, location, joined_date
            FROM users
            WHERE lower(user_id) = ? OR lower(username) = ?
            """,
            (lookup_key, lookup_key),
        )
        row = cursor.fetchone()
        if row:
            self._known_users.add(lookup_key)
            return UserProfile(
                username=row[1],
                user_id=row[0],
                location=row[2],
                join_date=None,
                collection_size=None,
                wantlist_size=None,
            )

        profile = (
            self._fetch_user_profile(normalized) if self.fetch_user_profiles else None
        )
        if profile is None:
            profile = UserProfile(
                username=normalized,
                user_id=normalized,
                location=None,
                join_date=None,
                collection_size=None,
                wantlist_size=None,
            )

        upsert_user(
            cursor,
            user_id=profile.user_id,
            username=profile.username,
            location=profile.location,
            joined_date=(
                profile.join_date.date().isoformat() if profile.join_date else None
            ),
        )
        self._known_users.add(profile.username.lower())
        if profile.user_id:
            self._known_users.add(profile.user_id.lower())
        return profile

    def _fetch_user_profile(self, username: str) -> Optional[UserProfile]:
        try:
            response = self.session.get(f"/user/{username}")
        except RuntimeError as exc:
            logger.warning("Could not fetch profile for %s: %s", username, exc)
            return None

        try:
            profile = parse_user_profile(response.text, username=username)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to parse profile for %s: %s", username, exc)
            return None

        return profile

    def _ingest_extended_users(
        self,
        cursor,
        release_id: int,
        *,
        existing_have: set[str],
        existing_want: set[str],
    ) -> None:
        have_lower = {u.lower() for u in existing_have}
        for username in self._fetch_user_list(release_id, "have"):
            key = username.lower()
            if key in have_lower:
                continue
            self._record_collection(cursor, username, release_id)
            have_lower.add(key)

        want_lower = {u.lower() for u in existing_want}
        for username in self._fetch_user_list(release_id, "want"):
            key = username.lower()
            if key in want_lower:
                continue
            self._record_wantlist(cursor, username, release_id)
            want_lower.add(key)

    def _fetch_user_list(self, release_id: int, interaction: str) -> list[str]:
        collected: list[str] = []
        seen: set[str] = set()

        for page in range(1, self.max_user_pages + 1):
            params = {"page": page, "per_page": 50}
            # Discogs usa /release/stats/{id} para mostrar usuarios, no /release/{id}/have o /want
            url = f"/release/stats/{release_id}"
            try:
                logger.debug(
                    "Fetching stats page %s for release %s (looking for %s users)",
                    page,
                    release_id,
                    interaction,
                )
                response = self.session.get(url, params=params)
            except RuntimeError as exc:
                logger.warning(
                    "Failed to fetch stats page %s for release %s: %s",
                    page,
                    release_id,
                    exc,
                )
                break

            usernames = parse_release_user_list(response.text)
            logger.debug(
                "Found %s usernames on stats page %s for release %s",
                len(usernames),
                page,
                release_id,
            )

            if not usernames:
                logger.warning(
                    "No usernames found on %s page %s for release %s; dumping HTML for debugging",
                    interaction,
                    page,
                    release_id,
                )
                self._dump_debug_html(
                    kind=f"{interaction}_page",
                    identifier=f"{release_id}_{page}",
                    html=response.text,
                )
                break

            new_names = [
                username for username in usernames if username.lower() not in seen
            ]
            if not new_names:
                logger.debug(
                    "All usernames on %s page %s for release %s are duplicates; stopping",
                    interaction,
                    page,
                    release_id,
                )
                break

            seen.update(name.lower() for name in new_names)
            collected.extend(new_names)
            logger.info(
                "Collected %s new usernames from %s page %s for release %s (total: %s)",
                len(new_names),
                interaction,
                page,
                release_id,
                len(collected),
            )

            if len(new_names) < len(usernames):
                # Page mostly duplicates; assume no more data
                logger.debug(
                    "Page %s has mostly duplicates; stopping %s fetch for release %s",
                    page,
                    interaction,
                    release_id,
                )
                break

        logger.info(
            "Total %s usernames collected for release %s: %s",
            interaction,
            release_id,
            len(collected),
        )
        return collected

    def _dump_debug_html(self, *, kind: str, identifier: str, html: str) -> None:
        if self._debug_dump_dir is None:
            return
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            filename = f"{kind}_{identifier}_{timestamp}.html"
            path = self._debug_dump_dir / filename
            path.write_text(html, encoding="utf-8")
            logger.debug("Dumped HTML snapshot to %s", path)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to dump HTML snapshot: %s", exc)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Discogs HTML pages and populate the local database.",
    )
    parser.add_argument(
        "--search-url",
        default=_SEARCH_PATH,
        help="Discogs search path to crawl (default: /search/).",
    )
    parser.add_argument(
        "--sort",
        default="have,desc",
        help="Sort parameter accepted by Discogs search (default: have,desc).",
    )
    parser.add_argument(
        "--release-type",
        default="release",
        help="Discogs search type filter (default: release).",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum number of search result pages to crawl.",
    )
    parser.add_argument(
        "--release-limit",
        type=int,
        default=None,
        help="Overall release cap across all pages (default: unlimited).",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=2.0,
        help="Minimum delay between HTTP requests in seconds.",
    )
    parser.add_argument(
        "--delay-jitter",
        type=float,
        default=0.0,
        help="Additional random delay jitter applied to each request.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=4,
        help="Maximum number of retries for transient HTTP failures.",
    )
    parser.add_argument(
        "--backoff-factor",
        type=float,
        default=2.5,
        help="Backoff multiplier applied between retries.",
    )
    parser.add_argument(
        "--max-user-pages",
        type=int,
        default=3,
        help="Number of additional user pages to fetch per release.",
    )
    parser.add_argument(
        "--cookies-file",
        type=Path,
        default=None,
        help=(
            "Path to a Discogs cookies export (JSON or Netscape) to authenticate "
            "requests. Defaults to the DISCOGS_COOKIES_FILE environment variable."
        ),
    )
    parser.add_argument(
        "--cookies-refresh-seconds",
        type=float,
        default=None,
        help=(
            "Seconds between automatic cookie reloads. Defaults to "
            "DISCOGS_COOKIES_REFRESH_SECONDS or 900. Set to 0 to disable."
        ),
    )
    parser.add_argument(
        "--headers-file",
        type=Path,
        default=None,
        help=(
            "Optional JSON file with HTTP headers to merge into every request. "
            "Defaults to the DISCOGS_HEADERS_FILE environment variable."
        ),
    )
    parser.add_argument(
        "--debug-dump-dir",
        type=Path,
        default=None,
        help=(
            "Directory to dump HTML snapshots when parsing fails. Useful for "
            "debugging layout changes."
        ),
    )
    parser.add_argument(
        "--skip-user-profiles",
        dest="fetch_user_profiles",
        action="store_false",
        help="Disable fetching user profile pages.",
    )
    parser.add_argument(
        "--no-extended-users",
        dest="fetch_extended_users",
        action="store_false",
        help="Disable fetching extended have/want user lists.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Optional explicit path to the SQLite database file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ...).",
    )
    parser.set_defaults(fetch_user_profiles=True, fetch_extended_users=True)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )

    db_config = None
    if args.db_path:
        db_config = DatabaseConfig(path=args.db_path)

    pipeline = DiscogsScraperPipeline(
        db_config=db_config,
        min_delay=args.min_delay,
        delay_jitter=args.delay_jitter,
        max_retries=args.max_retries,
        backoff_factor=args.backoff_factor,
        fetch_user_profiles=args.fetch_user_profiles,
        fetch_extended_users=args.fetch_extended_users,
        max_user_pages=args.max_user_pages,
        cookies_file=args.cookies_file,
        cookies_refresh_seconds=args.cookies_refresh_seconds,
        headers_file=args.headers_file,
        debug_dump_dir=args.debug_dump_dir,
    )

    stats = pipeline.crawl(
        search_url=args.search_url,
        sort=args.sort,
        release_type=args.release_type,
        max_pages=args.max_pages,
        release_limit=args.release_limit,
    )

    logger.info(
        "Scraping completed. Releases processed: %s | new items: %s | new users: %s | new interactions: %s",
        stats.releases_processed,
        stats.items_added,
        stats.users_added,
        stats.interactions_added,
    )
    logger.info(
        "Database totals -> items: %s | users: %s | interactions: %s",
        stats.total_items,
        stats.total_users,
        stats.total_interactions,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
