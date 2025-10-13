import argparse
import logging
import time
from pathlib import Path
from typing import Iterable, List

import requests

from ingestion.db import IngestionRepository, RepositoryConfig
from settings import get_database_path, get_discogs_token, get_seed_username

BASE_URL = "https://api.discogs.com"

logger = logging.getLogger(__name__)

try:
    DISCOGS_TOKEN = get_discogs_token()
except RuntimeError as err:
    raise SystemExit(err)

DEFAULT_USERNAME = get_seed_username()
DATABASE_PATH = get_database_path()


def fetch_collection(repo: IngestionRepository, username: str, delay: float) -> int:
    collected = 0
    page = 1
    while True:
        url = f"{BASE_URL}/users/{username}/collection/folders/0/releases"
        params = {"token": DISCOGS_TOKEN, "page": page, "per_page": 50}
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            logger.error(
                "Error %s obteniendo colección de %s: %s",
                response.status_code,
                username,
                response.json(),
            )
            break

        data = response.json()
        releases = data.get("releases", [])
        if not releases:
            break

        for release in releases:
            release_id = release["id"]
            master_id = release["basic_information"].get("master_id")
            canonical_id = master_id or release_id
            title = release["basic_information"]["title"]
            artist = ", ".join(
                [
                    artist_info["name"]
                    for artist_info in release["basic_information"]["artists"]
                ]
            )
            year = release["basic_information"].get("year")
            genres = ", ".join(release["basic_information"].get("genres", []))
            styles = ", ".join(release["basic_information"].get("styles", []))
            date_added = release["date_added"]

            image_url = release["basic_information"].get("cover_image")

            repo.upsert_user(
                user_id=username,
                username=username,
                location=None,
                joined_date=None,
            )
            repo.upsert_item(
                item_id=canonical_id,
                source_release_id=release_id,
                title=title,
                artist=artist,
                year=year,
                genres=genres,
                styles=styles,
                image_url=image_url,
            )

            if not repo.interaction_exists(username, canonical_id, "collection"):
                repo.record_interaction(
                    user_id=username,
                    item_id=canonical_id,
                    interaction_type="collection",
                    rating=None,
                    date_added=date_added,
                )
                collected += 1

        repo.commit()
        logger.info(
            "Página %s procesada (%s ítems) para %s", page, len(releases), username
        )

        if data["pagination"]["page"] >= data["pagination"]["pages"]:
            break
        page += 1
        time.sleep(delay)

    return collected


def process_user(username: str, delay: float = 1.0) -> int:
    username = username.strip()
    if not username:
        return 0

    logger.info("Procesando colección para %s", username)
    db_path = DATABASE_PATH or get_database_path()
    repo_config = RepositoryConfig(path=db_path)
    with IngestionRepository(repo_config) as repo:
        new_records = fetch_collection(repo, username, delay=delay)
    logger.info(
        "Colección de %s sincronizada. Nuevos registros: %s", username, new_records
    )
    return new_records


def iter_usernames(users: List[str], file_path: Path | None) -> Iterable[str]:
    if users:
        for user in users:
            yield user
        return

    if file_path and file_path.exists():
        with file_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                yield line.strip()
        return

    yield DEFAULT_USERNAME


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarga colecciones de usuarios desde la API de Discogs"
    )
    parser.add_argument(
        "--user",
        "-u",
        dest="users",
        action="append",
        help="Usuario(s) de Discogs a sincronizar (puede usarse varias veces)",
    )
    parser.add_argument(
        "--users-file",
        type=Path,
        help="Ruta a archivo de texto con un usuario por línea",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Pausa en segundos entre páginas (default: 1.0)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    global DEFAULT_USERNAME

    total_new = 0
    processed = 0

    delay = max(args.delay, 0.0)

    processed = 0
    total_new = 0

    for username in iter_usernames(args.users or [], args.users_file):
        processed += 1
        collected = process_user(username, delay)
        total_new += collected
        time.sleep(delay)

    logger.info(
        "Proceso completado. Usuarios procesados: %s. Nuevos registros: %s.",
        processed,
        total_new,
    )


if __name__ == "__main__":
    main()
