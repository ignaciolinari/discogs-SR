#!/usr/bin/env python3
"""Script para auditoría completa de la base de datos."""

import sqlite3

from settings import get_database_path

DATABASE_PATH = get_database_path()


def print_header(title):
    """Imprime un encabezado formateado."""
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_section(title):
    """Imprime una sección."""
    print()
    print(f"📊 {title}")
    print("-" * 70)


def get_db_stats():
    """Obtiene estadísticas generales de la base de datos."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # Total de items
        total = cursor.execute("SELECT COUNT(*) FROM items").fetchone()[0]

        # Items con datos válidos
        valid = cursor.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE title IS NOT NULL
              AND title != ''
              AND title != 'Unknown Title'
              AND artist IS NOT NULL
              AND artist != ''
              AND artist != 'Unknown Artist'
            """
        ).fetchone()[0]

        return {"total": total, "valid": valid}


def check_unknown_values():
    """Verifica items con valores desconocidos."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # Unknown titles
        unknown_titles = cursor.execute(
            "SELECT COUNT(*) FROM items WHERE title = 'Unknown Title'"
        ).fetchone()[0]

        # Unknown artists
        unknown_artists = cursor.execute(
            "SELECT COUNT(*) FROM items WHERE artist = 'Unknown Artist'"
        ).fetchone()[0]

        # Ambos unknown
        both_unknown = cursor.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE title = 'Unknown Title' AND artist = 'Unknown Artist'
            """
        ).fetchone()[0]

        return {
            "unknown_titles": unknown_titles,
            "unknown_artists": unknown_artists,
            "both_unknown": both_unknown,
        }


def check_null_or_empty():
    """Verifica valores NULL o vacíos."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # Títulos NULL o vacíos
        null_titles = cursor.execute(
            "SELECT COUNT(*) FROM items WHERE title IS NULL OR title = ''"
        ).fetchone()[0]

        # Artistas NULL o vacíos
        null_artists = cursor.execute(
            "SELECT COUNT(*) FROM items WHERE artist IS NULL OR artist = ''"
        ).fetchone()[0]

        # Años NULL
        null_years = cursor.execute(
            "SELECT COUNT(*) FROM items WHERE year IS NULL"
        ).fetchone()[0]

        # Años inválidos (< 1900 o > año actual)
        invalid_years = cursor.execute(
            "SELECT COUNT(*) FROM items WHERE year < 1900 OR year > 2026"
        ).fetchone()[0]

        return {
            "null_titles": null_titles,
            "null_artists": null_artists,
            "null_years": null_years,
            "invalid_years": invalid_years,
        }


def check_duplicates():
    """Verifica duplicados en la base de datos."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # Duplicados exactos por item_id
        duplicate_ids = cursor.execute(
            """
            SELECT item_id, COUNT(*) as count
            FROM items
            GROUP BY item_id
            HAVING count > 1
            """
        ).fetchall()

        # Posibles duplicados por título y artista (mismo contenido)
        duplicate_content = cursor.execute(
            """
            SELECT title, artist, COUNT(*) as count
            FROM items
            WHERE title IS NOT NULL
              AND title != ''
              AND title != 'Unknown Title'
            GROUP BY LOWER(title), LOWER(artist)
            HAVING count > 1
            ORDER BY count DESC
            LIMIT 10
            """
        ).fetchall()

        return {
            "duplicate_ids": duplicate_ids,
            "duplicate_content": duplicate_content,
        }


def check_source_release_ids():
    """Verifica integridad de source_release_id."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        # Items sin source_release_id
        missing_source = cursor.execute(
            "SELECT COUNT(*) FROM items WHERE source_release_id IS NULL"
        ).fetchone()[0]

        # Items donde item_id == source_release_id (releases directos)
        direct_releases = cursor.execute(
            "SELECT COUNT(*) FROM items WHERE item_id = source_release_id"
        ).fetchone()[0]

        # Items donde item_id != source_release_id (masters con release)
        masters_with_release = cursor.execute(
            "SELECT COUNT(*) FROM items WHERE item_id != source_release_id"
        ).fetchone()[0]

        return {
            "missing_source": missing_source,
            "direct_releases": direct_releases,
            "masters_with_release": masters_with_release,
        }


def check_data_quality():
    """Verifica calidad general de los datos."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Títulos muy cortos (potencialmente problemáticos)
        short_titles = cursor.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE title IS NOT NULL
              AND title != 'Unknown Title'
              AND LENGTH(title) < 2
            """
        ).fetchone()[0]

        # Títulos muy largos (potencialmente problemáticos)
        long_titles = cursor.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE title IS NOT NULL
              AND LENGTH(title) > 200
            """
        ).fetchone()[0]

        # Items con caracteres especiales problemáticos
        special_chars = cursor.execute(
            """
            SELECT COUNT(*) FROM items
            WHERE title LIKE '%�%' OR artist LIKE '%�%'
            """
        ).fetchone()[0]

        # Distribución por década
        decades = cursor.execute(
            """
            SELECT
                (year / 10) * 10 as decade,
                COUNT(*) as count
            FROM items
            WHERE year IS NOT NULL AND year >= 1900 AND year <= 2026
            GROUP BY decade
            ORDER BY decade DESC
            LIMIT 10
            """
        ).fetchall()

        return {
            "short_titles": short_titles,
            "long_titles": long_titles,
            "special_chars": special_chars,
            "decades": decades,
        }


def get_sample_issues():
    """Obtiene ejemplos de items con problemas."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Ejemplos de unknown
        unknown_samples = cursor.execute(
            """
            SELECT item_id, source_release_id, title, artist, year
            FROM items
            WHERE title = 'Unknown Title' OR artist = 'Unknown Artist'
            LIMIT 5
            """
        ).fetchall()

        return {"unknown_samples": unknown_samples}


def main():
    """Función principal."""
    print_header("🔍 AUDITORÍA DE BASE DE DATOS - Discogs")
    print(f"📁 Base de datos: {DATABASE_PATH}")

    # Estadísticas generales
    print_section("Estadísticas Generales")
    stats = get_db_stats()
    print(f"  Total de items:          {stats['total']:,}")
    print(
        f"  Items válidos:           {stats['valid']:,} ({stats['valid']/stats['total']*100:.2f}%)"
    )
    print(
        f"  Items con problemas:     {stats['total']-stats['valid']:,} ({(stats['total']-stats['valid'])/stats['total']*100:.2f}%)"
    )

    # Valores desconocidos
    print_section("Valores Desconocidos")
    unknown = check_unknown_values()
    print(f"  Unknown Title:           {unknown['unknown_titles']:,}")
    print(f"  Unknown Artist:          {unknown['unknown_artists']:,}")
    print(f"  Ambos Unknown:           {unknown['both_unknown']:,}")

    # Valores NULL o vacíos
    print_section("Valores NULL o Vacíos")
    nulls = check_null_or_empty()
    print(f"  Títulos NULL/vacíos:     {nulls['null_titles']:,}")
    print(f"  Artistas NULL/vacíos:    {nulls['null_artists']:,}")
    print(f"  Años NULL:               {nulls['null_years']:,}")
    print(f"  Años inválidos:          {nulls['invalid_years']:,}")

    if nulls["null_titles"] > 0 or nulls["null_artists"] > 0:
        print("  ⚠️  ADVERTENCIA: Hay valores NULL/vacíos que deben ser corregidos")

    # Duplicados
    print_section("Duplicados")
    duplicates = check_duplicates()
    print(f"  IDs duplicados:          {len(duplicates['duplicate_ids'])}")

    if duplicates["duplicate_ids"]:
        print("  ⚠️  ADVERTENCIA: Hay item_ids duplicados!")
        for item_id, count in duplicates["duplicate_ids"][:5]:
            print(f"     - ID {item_id}: {count} veces")

    print(f"  Contenido duplicado:     {len(duplicates['duplicate_content'])} grupos")
    if duplicates["duplicate_content"]:
        print("  📝 Top duplicados por contenido:")
        for title, artist, count in duplicates["duplicate_content"][:5]:
            display_title = (title[:40] + "...") if len(title) > 40 else title
            display_artist = (artist[:30] + "...") if len(artist) > 30 else artist
            print(f"     - {display_title} / {display_artist}: {count}x")

    # Source Release IDs
    print_section("Source Release IDs")
    source = check_source_release_ids()
    print(f"  Sin source_release_id:   {source['missing_source']:,}")
    print(
        f"  Releases directos:       {source['direct_releases']:,} ({source['direct_releases']/stats['total']*100:.1f}%)"
    )
    print(
        f"  Masters con release:     {source['masters_with_release']:,} ({source['masters_with_release']/stats['total']*100:.1f}%)"
    )

    # Calidad de datos
    print_section("Calidad de Datos")
    quality = check_data_quality()
    print(f"  Títulos muy cortos (<2): {quality['short_titles']:,}")
    print(f"  Títulos muy largos:      {quality['long_titles']:,}")
    print(f"  Caracteres especiales:   {quality['special_chars']:,}")

    if quality["decades"]:
        print("\n  📅 Distribución por década:")
        for row in quality["decades"]:
            decade = row[0] if isinstance(row, tuple) else row["decade"]
            count = row[1] if isinstance(row, tuple) else row["count"]
            bar = "█" * int(count / stats["total"] * 50)
            print(f"     {decade}s: {count:>6,} {bar}")

    # Ejemplos de problemas
    print_section("Ejemplos de Items con Problemas")
    samples = get_sample_issues()

    if samples["unknown_samples"]:
        print("  🔍 Muestra de items con valores Unknown:")
        for item in samples["unknown_samples"]:
            print(
                f"     ID {item['item_id']:>8} | {item['title'][:30]:30} | {item['artist'][:25]:25}"
            )
    else:
        print("  ✅ No hay items con valores Unknown")

    # Resumen final
    print_header("📋 RESUMEN")

    issues = []
    if nulls["null_titles"] > 0 or nulls["null_artists"] > 0:
        issues.append(
            f"❌ {nulls['null_titles'] + nulls['null_artists']} valores NULL/vacíos"
        )
    if len(duplicates["duplicate_ids"]) > 0:
        issues.append(f"❌ {len(duplicates['duplicate_ids'])} IDs duplicados")
    if unknown["unknown_titles"] > 0:
        issues.append(f"⚠️  {unknown['unknown_titles']} Unknown Titles")
    if unknown["unknown_artists"] > 0:
        issues.append(f"⚠️  {unknown['unknown_artists']} Unknown Artists")
    if quality["special_chars"] > 0:
        issues.append(f"⚠️  {quality['special_chars']} items con caracteres especiales")

    if issues:
        print("\n  Problemas detectados:")
        for issue in issues:
            print(f"    {issue}")
    else:
        print("\n  ✅ ¡Base de datos en excelente estado!")

    health_score = (stats["valid"] / stats["total"]) * 100
    print(f"\n  🏥 Salud de la base de datos: {health_score:.2f}%")

    if health_score >= 99:
        print("     Excelente 🌟")
    elif health_score >= 95:
        print("     Muy buena ✅")
    elif health_score >= 90:
        print("     Buena 👍")
    elif health_score >= 80:
        print("     Regular ⚠️")
    else:
        print("     Necesita atención ❌")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
