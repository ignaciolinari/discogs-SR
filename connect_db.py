import sqlite3
from textwrap import dedent

import settings


def open_connection():
    """Return a SQLite connection using the shared project settings."""

    return sqlite3.connect(str(settings.get_database_path()))


def fetch_one(cursor, query, params=None):
    cursor.execute(query, params or ())
    row = cursor.fetchone()
    return row[0] if row else 0


def describe_database():
    with open_connection() as con:
        cursor = con.cursor()

        total_users = fetch_one(cursor, "SELECT COUNT(*) FROM users")
        total_items = fetch_one(cursor, "SELECT COUNT(*) FROM items")
        total_interactions = fetch_one(cursor, "SELECT COUNT(*) FROM interactions")

        distinct_interaction_types = fetch_one(
            cursor,
            "SELECT COUNT(DISTINCT interaction_type) FROM interactions",
        )

        top_users = cursor.execute(
            dedent(
                """
                SELECT u.username, COUNT(*) AS n
                FROM interactions i
                JOIN users u ON u.user_id = i.user_id
                GROUP BY u.username
                ORDER BY n DESC
                LIMIT 10
                """
            )
        ).fetchall()

        top_items = cursor.execute(
            dedent(
                """
                SELECT items.title, items.artist, COUNT(*) AS n,
                       AVG(interactions.rating) AS avg_rating
                FROM interactions
                JOIN items ON items.item_id = interactions.item_id
                GROUP BY items.item_id
                ORDER BY n DESC
                LIMIT 10
                """
            )
        ).fetchall()

    return {
        "total_users": total_users,
        "total_items": total_items,
        "total_interactions": total_interactions,
        "distinct_interaction_types": distinct_interaction_types,
        "top_users": top_users,
        "top_items": top_items,
    }


def print_report(stats):
    print("==== Discogs DB snapshot ====")
    print(f"Usuarios totales        : {stats['total_users']:,}")
    print(f"Items totales           : {stats['total_items']:,}")
    print(f"Interacciones totales   : {stats['total_interactions']:,}")
    print(f"Tipos de interacción    : {stats['distinct_interaction_types']}")

    print("\nTop 10 usuarios por interacciones:")
    for username, count in stats["top_users"]:
        print(f"  {username:<25} {count:>6}")

    print("\nTop 10 ítems por apariciones:")
    for title, artist, count, avg_rating in stats["top_items"]:
        label = f"{title} — {artist}" if artist else title
        avg = f"{avg_rating:.2f}" if avg_rating is not None else "-"
        print(f"  {label:<60} {count:>6}  (rating prom.: {avg})")


if __name__ == "__main__":
    print_report(describe_database())
