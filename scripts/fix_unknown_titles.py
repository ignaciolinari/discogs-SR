#!/usr/bin/env python3
"""Script para recuperar títulos de items marcados como 'Unknown Title'."""

import sqlite3
import time

import requests

from settings import get_database_path, get_discogs_token

try:
    DISCOGS_TOKEN = get_discogs_token()
except RuntimeError:
    print("❌ Error: DISCOGS_TOKEN no está configurado")
    print("   Exporta tu token: export DISCOGS_TOKEN='tu_token'")
    exit(1)

BASE_URL = "https://api.discogs.com"
DATABASE_PATH = get_database_path()


def get_unknown_items(limit=50):
    """Obtiene items sin título válido."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT item_id, source_release_id, title, artist
            FROM items
            WHERE title = 'Unknown Title' OR artist = 'Unknown Artist'
            LIMIT ?
            """,
            [limit],
        )
        return cursor.fetchall()


def fetch_release_info(release_id):
    """Obtiene información de un release desde la API."""
    url = f"{BASE_URL}/releases/{release_id}"
    params = {"token": DISCOGS_TOKEN}

    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print(f"  ⚠️  Release {release_id} no encontrado (404)")
            return None
        else:
            print(f"  ⚠️  Error {response.status_code} para release {release_id}")
            return None
    except Exception as e:
        print(f"  ❌ Error al consultar release {release_id}: {e}")
        return None


def update_item(item_id, title, artist):
    """Actualiza un item en la base de datos."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE items
            SET title = ?, artist = ?
            WHERE item_id = ?
            """,
            [title, artist, item_id],
        )
        conn.commit()


def main():
    print("=" * 70)
    print("RECUPERACIÓN DE TÍTULOS FALTANTES")
    print("=" * 70)
    print()

    items = get_unknown_items(limit=100)

    if not items:
        print("✓ No hay items sin título")
        return

    print(f"Encontrados {len(items)} items sin título válido")
    print("Consultando API de Discogs para recuperar información...")
    print()

    updated = 0
    failed = 0

    for item in items:
        item_id = item["item_id"]
        source_release_id = item["source_release_id"] or item_id

        print(
            f"[{updated + failed + 1}/{len(items)}] Item {item_id} (release {source_release_id})...",
            end=" ",
        )

        data = fetch_release_info(source_release_id)

        if data:
            title = data.get("title", "Unknown Title")
            artists = data.get("artists", [])
            artist = (
                ", ".join([a.get("name", "Unknown Artist") for a in artists])
                if artists
                else "Unknown Artist"
            )

            if (
                title
                and title != "Unknown Title"
                and artist
                and artist != "Unknown Artist"
            ):
                update_item(item_id, title, artist)
                print(f"✓ Actualizado: {title} - {artist}")
                updated += 1
            else:
                print("⚠️  Sin datos válidos")
                failed += 1
        else:
            failed += 1

        # Pausa para respetar rate limit
        time.sleep(1.1)

    print()
    print("=" * 70)
    print(f"✓ Proceso completado: {updated} actualizados, {failed} sin resolver")
    print("=" * 70)


if __name__ == "__main__":
    main()
