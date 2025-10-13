#!/usr/bin/env python3
"""Wrapper inteligente para ejecutar el scraper con verificación automática de cookies.

Este script asume que ya corriste `refresh_cookies_persistent.py` en otra terminal
para mantener un navegador autenticado y generar cookies frescas. Con eso en mente:
1. Verifica que las cookies existan y estén válidas
2. Si detecta problemas, te guía para volver al script persistente antes de seguir
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
                    True,
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
    """Guía para que la persona usuaria refresque las cookies con el script persistente."""
    print()
    print("=" * 60)
    print("ACTUALIZACIÓN DE COOKIES REQUERIDA")
    print("=" * 60)
    print()
    print("Opciones:")
    print("  1. Ya corrí refresh_cookies_persistent.py, volver a verificar")
    print("  2. Continuar de todas formas (no recomendado)")
    print("  3. Cancelar")
    print()

    print("⚠️  Asegurate de ejecutar en otra terminal:")
    print("    python3 refresh_cookies_persistent.py --output", cookies_file)
    print(
        "    (El script mantiene un navegador abierto hasta que confirmes que las cookies están listas)"
    )
    print()

    choice = input("Selecciona una opción (1-3): ").strip()

    if choice == "1":
        input(
            "Presiona Enter cuando el script persistente haya actualizado las cookies..."
        )

        # Check again
        valid, msg = check_cookies_status(cookies_file)
        print(f"\n{msg}")
        return valid

    elif choice == "2":
        print()
        print("⚠️  Continuando sin cookies válidas...")
        print(
            "El scraper podria no obtener usuarios de have/want si no se mantienen las cookies activas."
        )
        return True

    else:
        print("\n❌ Operación cancelada")
        print("Si cambiás de idea, ejecutá primero refresh_cookies_persistent.py.")
        return False


def run_scraper(args: argparse.Namespace) -> int:
    """Ejecutar el scraper con los argumentos proporcionados."""
    cmd = [
        "python3",
        "-m",
        "scraper.pipeline",
        "--cookies-file",
        str(args.cookies_file),
        "--max-pages",
        str(max(args.pages, 1)),
        "--min-delay",
        str(max(args.delay, 0.0)),
        "--delay-jitter",
        str(max(args.jitter, 0.0)),
        "--log-level",
        args.log_level,
        "--commit-every",
        str(max(args.commit_every, 1)),
    ]

    if args.limit:
        cmd.extend(["--release-limit", str(max(args.limit, 1))])

    if args.user_pages:
        cmd.extend(["--max-user-pages", str(max(args.user_pages, 0))])

    if not args.fetch_profiles:
        cmd.append("--skip-user-profiles")

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
