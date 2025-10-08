#!/usr/bin/env python3
"""Script para verificar el estado del scraper y diagnosticar problemas."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from settings import get_database_path


def check_cookies():
    """Verificar el estado de las cookies."""
    cookies_file = Path("cookies.json")

    print("=" * 60)
    print("COOKIES")
    print("=" * 60)

    if not cookies_file.exists():
        print("❌ cookies.json NO existe")
        print("   Necesitas exportar cookies de tu navegador.")
        return False

    try:
        with open(cookies_file) as f:
            cookies = json.load(f)

        if not cookies:
            print("❌ cookies.json está vacío")
            return False

        print(f"✓ cookies.json existe con {len(cookies)} cookies")

        # Check for important cookies
        cookie_names = [c.get("name") for c in cookies if isinstance(c, dict)]

        important_cookies = ["session", "sid", "__cf_bm"]
        for cookie_name in important_cookies:
            if cookie_name in cookie_names:
                # Find the cookie
                cookie = next(c for c in cookies if c.get("name") == cookie_name)
                expires = cookie.get("expires")

                if expires:
                    if isinstance(expires, str):
                        try:
                            # Parse ISO format
                            exp_date = datetime.fromisoformat(
                                expires.replace("Z", "+00:00")
                            )
                            now = datetime.now(exp_date.tzinfo)

                            if exp_date > now:
                                hours_left = (exp_date - now).total_seconds() / 3600
                                if hours_left > 1:
                                    print(
                                        f"  ✓ {cookie_name}: expira en {hours_left:.1f} horas"
                                    )
                                else:
                                    print(
                                        f"  ⚠️  {cookie_name}: expira en {hours_left * 60:.0f} minutos"
                                    )
                            else:
                                print(f"  ❌ {cookie_name}: EXPIRADA")
                        except Exception:
                            print(f"  ? {cookie_name}: presente")
                    else:
                        print(f"  ✓ {cookie_name}: presente")
                else:
                    print(f"  ✓ {cookie_name}: presente (sin expiración)")
            else:
                print(f"  ⚠️  {cookie_name}: NO encontrada")

        return True

    except json.JSONDecodeError:
        print("❌ cookies.json tiene formato JSON inválido")
        return False
    except Exception as e:
        print(f"❌ Error leyendo cookies: {e}")
        return False


def check_database():
    """Verificar el estado de la base de datos."""
    print("\n" + "=" * 60)
    print("BASE DE DATOS")
    print("=" * 60)

    try:
        db_path = get_database_path()
        print(f"Ruta: {db_path}")

        if not db_path.exists():
            print("❌ Base de datos NO existe")
            return False

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Count tables
        cursor.execute("SELECT COUNT(*) FROM users")
        users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM items")
        items = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM interactions")
        interactions = cursor.fetchone()[0]

        print("\nContenido:")
        print(f"  Items: {items:,}")
        print(f"  Usuarios: {users:,}")
        print(f"  Interacciones: {interactions:,}")

        if users > 0 and interactions > 0:
            ratio = interactions / users
            print(f"  Ratio interacciones/usuario: {ratio:.1f}")

            if ratio > 500:
                print("  ⚠️  Ratio muy alto - puede haber muchos usuarios sin guardar")

        # Check interaction types
        cursor.execute(
            """
            SELECT interaction_type, COUNT(*)
            FROM interactions
            GROUP BY interaction_type
        """
        )

        print("\nTipos de interacciones:")
        for tipo, count in cursor.fetchall():
            print(f"  {tipo}: {count:,}")

        # Check for users without interactions
        cursor.execute(
            """
            SELECT COUNT(*) FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM interactions i WHERE i.user_id = u.user_id
            )
        """
        )
        orphan_users = cursor.fetchone()[0]

        if orphan_users > 0:
            print(f"\n⚠️  {orphan_users} usuarios sin interacciones")

        # Check for interactions without users (should not happen)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT i.user_id)
            FROM interactions i
            LEFT JOIN users u ON i.user_id = u.user_id
            WHERE u.user_id IS NULL
        """
        )
        orphan_interactions = cursor.fetchone()[0]

        if orphan_interactions > 0:
            print(
                f"❌ {orphan_interactions} usuarios en interacciones NO están en tabla users"
            )

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error accediendo a base de datos: {e}")
        return False


def check_debug_files():
    """Verificar archivos de debug."""
    print("\n" + "=" * 60)
    print("ARCHIVOS DE DEBUG")
    print("=" * 60)

    debug_dir = Path("debug_html")

    if not debug_dir.exists():
        print("ℹ️  Directorio debug_html no existe")
        print("   Usa --debug-dump-dir debug_html para guardar HTML durante scraping")
        return

    html_files = list(debug_dir.glob("*.html"))

    if not html_files:
        print("ℹ️  No hay archivos HTML en debug_html/")
        return

    print(f"✓ {len(html_files)} archivos HTML guardados:")

    for html_file in sorted(html_files)[:10]:  # Show first 10
        size_kb = html_file.stat().st_size / 1024
        print(f"  - {html_file.name} ({size_kb:.1f} KB)")

    if len(html_files) > 10:
        print(f"  ... y {len(html_files) - 10} más")


def main():
    """Run all checks."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "DIAGNÓSTICO DEL SCRAPER DE DISCOGS" + " " * 13 + "║")
    print("╚" + "=" * 58 + "╝")

    cookies_ok = check_cookies()
    db_ok = check_database()
    check_debug_files()

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)

    if cookies_ok and db_ok:
        print("✓ Sistema parece estar funcionando correctamente")

        if not cookies_ok:
            print("\n⚠️  RECOMENDACIÓN: Actualiza las cookies desde tu navegador")

    else:
        print("❌ Se detectaron problemas:")
        if not cookies_ok:
            print("  - Cookies faltantes o expiradas")
        if not db_ok:
            print("  - Problemas con la base de datos")

    print("\nPara más información, consulta README.md")
    print()


if __name__ == "__main__":
    main()
