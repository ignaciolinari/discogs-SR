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
from .http import DiscogsScraperSession
from .models import ReleaseDetail, ReleaseSummary, Review, UserProfile
from .parsers import (
    parse_release_detail,
    parse_release_user_list,
    parse_search_results,
    parse_user_profile,
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
    ) -> None:
        self.db_config = db_config or connection_from_settings()
        self.session = session or DiscogsScraperSession(
            min_delay=min_delay,
            delay_jitter=delay_jitter,
            max_retries=max_retries,
            backoff_factor=backoff_factor,
        )
        self.fetch_user_profiles = fetch_user_profiles
        self.fetch_extended_users = fetch_extended_users
        self.max_user_pages = max(0, max_user_pages)
        self._known_users: set[str] = set()

    def crawl(
        self,
        *,
        search_url: str = _SEARCH_PATH,
        sort: str = "have,desc",
        release_type: str = "release",
        max_pages: int = 5,
        release_limit: Optional[int] = None,
    ) -> ScrapeStats:
        """Entry point to crawl search results and ingest releases.

        Args:
            search_url: Discogs search path.
            sort: sorting parameter accepted by Discogs search.
            release_type: search type filter.
            max_pages: maximum number of search pages to crawl.
            release_limit: overall release cap (across pages).
        Returns:
            Summary statistics for the scraping run.
        """

        processed = 0
        pending_release_ids: set[int] = set()

        with get_connection(self.db_config) as connection:
            ensure_schema(connection)
            cursor = connection.cursor()
            start_users, start_items, start_interactions = _get_table_counts(cursor)

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
                summaries = parse_search_results(response.text)
                if not summaries:
                    logger.info("No releases detected on search page %s", page_number)
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
            url = f"/release/{release_id}/{interaction}"
            try:
                response = self.session.get(url, params=params)
            except RuntimeError as exc:
                logger.debug(
                    "Skipping %s page %s for release %s: %s",
                    interaction,
                    page,
                    release_id,
                    exc,
                )
                break

            usernames = parse_release_user_list(response.text)
            if not usernames:
                break

            new_names = [
                username for username in usernames if username.lower() not in seen
            ]
            if not new_names:
                break

            seen.update(name.lower() for name in new_names)
            collected.extend(new_names)

            if len(new_names) < len(usernames):
                # Page mostly duplicates; assume no more data
                break

        return collected


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
