import argparse
import sqlite3
import time
from pathlib import Path
from typing import Iterable, List

import requests

from settings import get_database_path, get_discogs_token, get_seed_username

BASE_URL = "https://api.discogs.com"

try:
    DISCOGS_TOKEN = get_discogs_token()
except RuntimeError as err:
    raise SystemExit(err)

DEFAULT_USERNAME = get_seed_username()
DATABASE_PATH = get_database_path()


def interaction_exists(
    cursor: sqlite3.Cursor, user_id: str, item_id: int, interaction_type: str
) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM interactions
        WHERE user_id = ? AND item_id = ? AND interaction_type = ?
        """,
        (user_id, item_id, interaction_type),
    )
    return cursor.fetchone() is not None


def insert_user(cursor: sqlite3.Cursor, user_id: str, username: str) -> None:
    cursor.execute(
        """
        INSERT OR IGNORE INTO users (user_id, username)
        VALUES (?, ?)
        """,
        (user_id, username),
    )


def insert_item(
    cursor: sqlite3.Cursor,
    item_id: int,
    title: str,
    artist: str,
    year: int | None,
    genre: str,
    style: str,
    image_url: str | None,
) -> None:
    cursor.execute(
        """
        INSERT OR IGNORE INTO items (item_id, title, artist, year, genre, style, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (item_id, title, artist, year, genre, style, image_url),
    )


def insert_interaction(
    cursor: sqlite3.Cursor,
    user_id: str,
    item_id: int,
    interaction_type: str,
    date_added: str,
) -> None:
    cursor.execute(
        """
        INSERT INTO interactions (user_id, item_id, interaction_type, date_added)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, item_id, interaction_type, date_added),
    )


def fetch_collection(cursor: sqlite3.Cursor, username: str, delay: float) -> int:
    collected = 0
    page = 1
    while True:
        url = f"{BASE_URL}/users/{username}/collection/folders/0/releases"
        params = {"token": DISCOGS_TOKEN, "page": page, "per_page": 50}
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            print("Error:", response.json())
            break

        data = response.json()
        releases = data.get("releases", [])
        if not releases:
            break

        for release in releases:
            release_id = release["id"]
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

            insert_user(cursor, username, username)
            insert_item(
                cursor, release_id, title, artist, year, genres, styles, image_url
            )

            if not interaction_exists(cursor, username, release_id, "collection"):
                insert_interaction(
                    cursor, username, release_id, "collection", date_added
                )
                collected += 1

        cursor.connection.commit()
        print(f"Página {page} procesada ({len(releases)} ítems).")

        if data["pagination"]["page"] >= data["pagination"]["pages"]:
            break
        page += 1
        time.sleep(delay)

    return collected


def process_user(username: str, delay: float = 1.0) -> None:
    username = username.strip()
    if not username:
        return

    print(f"\nProcesando colección para {username}")
    with sqlite3.connect(str(DATABASE_PATH)) as connection:
        cursor = connection.cursor()
        new_records = fetch_collection(cursor, username, delay=delay)
    print(f"Colección de {username} sincronizada. Nuevos registros: {new_records}")


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

    global DEFAULT_USERNAME

    total_new = 0
    processed = 0

    delay = max(args.delay, 0.0)

    processed = 0
    total_new = 0

    for username in iter_usernames(args.users or [], args.users_file):
        processed += 1

        with sqlite3.connect(str(DATABASE_PATH)) as connection:
            cursor = connection.cursor()
            print(f"\nProcesando colección para {username}")
            collected = fetch_collection(cursor, username, delay)
            total_new += collected
            print(
                f"Colección de {username} sincronizada. Nuevos registros: {collected}"
            )

        time.sleep(delay)

    print(
        f"\nProceso completado. Usuarios procesados: {processed}. Nuevos registros: {total_new}."
    )


if __name__ == "__main__":
    main()
