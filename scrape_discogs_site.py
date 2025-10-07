"""Command line tool to scrape Discogs HTML pages and populate the local DB."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from scraper.pipeline import DiscogsScraperPipeline
from scraper.db import DatabaseConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Discogs web pages (search, releases, users) to populate the recommender DB.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=3,
        help="Maximum number of search result pages to crawl (default: 3).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on the total number of releases to ingest.",
    )
    parser.add_argument(
        "--sort",
        default="have,desc",
        help="Sort parameter used by Discogs search (default: have,desc).",
    )
    parser.add_argument(
        "--type",
        default="release",
        help="Search type filter (default: release).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Minimum delay in seconds between HTTP requests (default: 2.0).",
    )
    parser.add_argument(
        "--delay-jitter",
        type=float,
        default=1.5,
        help="Máximo jitter aleatorio añadido al delay base en segundos (default: 1.5).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=4,
        help="Maximum number of retries per request when rate limited (default: 4).",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=2.5,
        help="Exponential backoff factor when retrying (default: 2.5).",
    )
    parser.add_argument(
        "--search-url",
        default="/search/",
        help="Relative search path to start crawling (default: /search/).",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="Optional path to override the SQLite database location.",
    )
    parser.add_argument(
        "--no-profile",
        dest="fetch_profiles",
        action="store_false",
        help="Skip fetching user profile pages (faster but less metadata).",
    )
    parser.set_defaults(fetch_profiles=True)
    parser.add_argument(
        "--no-extended-users",
        dest="fetch_extended_users",
        action="store_false",
        help="No intentes expandir las listas de have/want más allá de lo visible en la página.",
    )
    parser.set_defaults(fetch_extended_users=True)
    parser.add_argument(
        "--user-pages",
        type=int,
        default=3,
        help="Número máximo de páginas extra a consultar para have/want (default: 3).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    db_config = (
        DatabaseConfig(path=args.database) if args.database is not None else None
    )

    pipeline = DiscogsScraperPipeline(
        db_config=db_config,
        min_delay=max(args.delay, 0.1),
        delay_jitter=max(args.delay_jitter, 0.0),
        max_retries=args.max_retries,
        backoff_factor=args.backoff,
        fetch_user_profiles=args.fetch_profiles,
        fetch_extended_users=args.fetch_extended_users,
        max_user_pages=max(args.user_pages, 0),
    )

    stats = pipeline.crawl(
        search_url=args.search_url,
        sort=args.sort,
        release_type=args.type,
        max_pages=max(args.pages, 1),
        release_limit=args.limit,
    )

    logging.info(
        "Scraping completed. Releases ingested: %s | new items: %s | new users: %s | new interactions: %s",
        stats.releases_processed,
        stats.items_added,
        stats.users_added,
        stats.interactions_added,
    )
    logging.info(
        "Database totals -> items: %s | users: %s | interactions: %s",
        stats.total_items,
        stats.total_users,
        stats.total_interactions,
    )


if __name__ == "__main__":
    main()
