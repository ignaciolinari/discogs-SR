#!/usr/bin/env python3
"""Wrapper inteligente para ejecutar el scraper con verificación automática de cookies.

Este script:
1. Verifica que las cookies existan y estén válidas
2. Ofrece actualizar las cookies automáticamente si están expiradas
3. Ejecuta el scraper con configuración óptima
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def check_cookies_status(cookies_file: Path) -> tuple[bool, str]:
    """Verificar el estado de las cookies.

    Returns:
        (válidas, mensaje)
    """
    if not cookies_file.exists():
        return False, f"❌ {cookies_file} no existe"

    try:
        with open(cookies_file) as f:
            cookies = json.load(f)

        if not cookies:
            return False, "❌ Archivo de cookies vacío"

        cookie_list = (
            cookies if isinstance(cookies, list) else cookies.get("cookies", [])
        )

        # Check for Cloudflare cookie
        cf_cookie = None
        for cookie in cookie_list:
            if isinstance(cookie, dict) and cookie.get("name") == "__cf_bm":
                cf_cookie = cookie
                break

        if not cf_cookie:
            return (
                True,
                "⚠️  Cookie de Cloudflare no encontrada (puede funcionar sin ella)",
            )

        # Check expiration
        expires = cf_cookie.get("expires")
        if not expires:
            return True, "✓ Cookies válidas"

        # Parse expiration
        try:
            if isinstance(expires, str):
                exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            else:
                exp_dt = datetime.fromtimestamp(expires)

            now = datetime.now(exp_dt.tzinfo if exp_dt.tzinfo else None)

            if exp_dt <= now:
                return (
                    False,
                    f"❌ Cookie de Cloudflare EXPIRADA (expiró {exp_dt.strftime('%Y-%m-%d %H:%M:%S')})",
                )

            hours_left = (exp_dt - now).total_seconds() / 3600
            if hours_left < 0.5:
                return (
                    False,
                    f"⚠️  Cookie de Cloudflare expira en {hours_left * 60:.0f} minutos",
                )

            return True, f"✓ Cookies válidas (expiran en {hours_left:.1f} horas)"

        except Exception as e:
            return True, f"? No se pudo verificar expiración: {e}"

    except json.JSONDecodeError:
        return False, "❌ Archivo de cookies con formato inválido"
    except Exception as e:
        return False, f"❌ Error leyendo cookies: {e}"


def refresh_cookies_interactive(cookies_file: Path) -> bool:
    """Preguntar al usuario si quiere actualizar las cookies."""
    print()
    print("=" * 60)
    print("ACTUALIZACIÓN DE COOKIES REQUERIDA")
    print("=" * 60)
    print()
    print("Opciones:")
    print("  1. Actualizar automáticamente con Playwright (recomendado)")
    print("  2. Actualizar manualmente con extensión de navegador")
    print("  3. Continuar de todas formas")
    print("  4. Cancelar")
    print()

    choice = input("Selecciona una opción (1-4): ").strip()

    if choice == "1":
        # Check if playwright is installed
        try:
            import playwright  # noqa: F401

            print("\n✓ Playwright está instalado")
        except ImportError:
            print("\n❌ Playwright no está instalado")
            print("\nPara instalar:")
            print("  pip install playwright")
            print("  playwright install chromium")
            print()
            return False

        # Run refresh script
        print("\n🚀 Ejecutando actualización automática...")
        result = subprocess.run(
            ["python3", "refresh_cookies.py", "--output", str(cookies_file)],
            cwd=Path.cwd(),
        )

        return result.returncode == 0

    elif choice == "2":
        print()
        print("Para actualizar manualmente:")
        print("1. Instala una extensión de cookies (Cookie-Editor, EditThisCookie)")
        print("2. Visita https://www.discogs.com e inicia sesión")
        print("3. Exporta todas las cookies en formato JSON")
        print(f"4. Guarda el archivo como: {cookies_file}")
        print()
        input("Presiona Enter cuando hayas actualizado las cookies...")

        # Check again
        valid, msg = check_cookies_status(cookies_file)
        if valid:
            print(f"\n✓ {msg}")
            return True
        else:
            print(f"\n{msg}")
            return False

    elif choice == "3":
        print("\n⚠️  Continuando sin cookies válidas...")
        print(
            "El scraper podria no obtener usuarios de have/want si no se actualizan las cookies con otro script."
        )
        return True

    else:
        print("\n❌ Operación cancelada")
        return False


def run_scraper(args: argparse.Namespace) -> int:
    """Ejecutar el scraper con los argumentos proporcionados."""
    cmd = [
        "python3",
        "scrape_discogs_site.py",
        "--cookies-file",
        str(args.cookies_file),
        "--pages",
        str(args.pages),
        "--delay",
        str(args.delay),
        "--delay-jitter",
        str(args.jitter),
        "--log-level",
        args.log_level,
        "--commit-every",
        str(args.commit_every),
    ]

    if args.limit:
        cmd.extend(["--limit", str(args.limit)])

    if args.user_pages:
        cmd.extend(["--user-pages", str(args.user_pages)])

    if not args.fetch_profiles:
        cmd.append("--no-profile")

    if args.debug:
        cmd.extend(["--debug-dump-dir", "debug_html"])

    print()
    print("=" * 60)
    print("EJECUTANDO SCRAPER")
    print("=" * 60)
    print()
    print("Comando:", " ".join(cmd))
    print()

    result = subprocess.run(cmd, cwd=Path.cwd())
    return result.returncode


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Wrapper inteligente para ejecutar el scraper de Discogs"
    )

    # Cookie options
    parser.add_argument(
        "--cookies-file",
        type=Path,
        default=Path("cookies.json"),
        help="Ruta al archivo de cookies (default: cookies.json)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Forzar actualización de cookies antes de scrapear",
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="No verificar cookies antes de ejecutar (no recomendado)",
    )

    # Scraper options
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Número de páginas de búsqueda a procesar (default: 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Límite de releases a procesar (default: sin límite)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Delay entre requests en segundos (default: 3.0)",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=2.0,
        help="Jitter aleatorio añadido al delay (default: 2.0)",
    )
    parser.add_argument(
        "--user-pages",
        type=int,
        default=3,
        help="Páginas de usuarios a obtener por release (default: 3)",
    )
    parser.add_argument(
        "--no-profile",
        dest="fetch_profiles",
        action="store_false",
        help="No obtener perfiles individuales de usuarios (mucho más rápido)",
    )
    parser.set_defaults(fetch_profiles=True)
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de logging (default: INFO)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Guardar HTML de páginas problemáticas en debug_html/",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=1,
        help="Guardar progreso cada N releases (default: 1, cada release)",
    )

    args = parser.parse_args()

    print()
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 12 + "SCRAPER DISCOGS - WRAPPER" + " " * 21 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    # Check cookies
    if not args.no_check:
        print("🔍 Verificando cookies...")
        valid, msg = check_cookies_status(args.cookies_file)
        print(f"   {msg}")

        if not valid or args.force_refresh:
            if not refresh_cookies_interactive(args.cookies_file):
                print("\n❌ No se pudieron actualizar las cookies. Abortando.")
                return 1

    # Run scraper
    return run_scraper(args)


if __name__ == "__main__":
    sys.exit(main())
