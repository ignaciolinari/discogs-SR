#!/usr/bin/env python3
"""Actualizar cookies reutilizando una sesión persistente de navegador.

Este script mantiene el navegador abierto y periódicamente captura cookies
frescas SIN necesidad de volver a iniciar sesión.
"""

import json
import time
from pathlib import Path
from datetime import datetime


def refresh_with_persistent_session(
    output_file: Path = Path("cookies.json"),
    refresh_interval: int = 1500,  # 25 minutos
    browser_data_dir: Path = Path(".browser_session"),
):
    """Mantener un navegador con sesión persistente y refrescar cookies.

    Args:
        output_file: Archivo donde guardar las cookies
        refresh_interval: Segundos entre cada refresh (default: 25 min)
        browser_data_dir: Directorio para guardar datos del navegador
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright no está instalado")
        print("   pip install playwright")
        print("   playwright install chromium")
        return False

    browser_data_dir = browser_data_dir.expanduser()
    browser_data_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("REFRESH AUTOMÁTICO CON SESIÓN PERSISTENTE")
    print("=" * 60)
    print()
    print("Este script va a:")
    print("1. Abrir un navegador Chrome con sesión guardada")
    print("2. Mantenerlo abierto en background")
    print(f"3. Capturar cookies frescas cada {refresh_interval//60} minutos")
    print("4. El scraper las detectará y recargará automáticamente")
    print()
    print("⚠️  IMPORTANTE:")
    print("   - Inicia sesión en Discogs la PRIMERA VEZ que se abra")
    print("   - La sesión se guardará para los próximos refresh")
    print("   - Mantén este script corriendo mientras el scraper funciona")
    print("   - Presiona Ctrl+C para detener")
    print()
    input("Presiona Enter para continuar...")

    try:
        with sync_playwright() as p:
            print("\n🌐 Abriendo navegador con sesión persistente...")

            # Crear contexto persistente (guarda cookies, local storage, etc)
            context = p.chromium.launch_persistent_context(
                str(browser_data_dir),
                headless=False,  # Visible para debugging
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            )

            page = context.pages[0] if context.pages else context.new_page()

            print("📡 Navegando a Discogs...")
            page.goto("https://www.discogs.com")

            # Primera vez: esperar a que el usuario inicie sesión
            print()
            print("=" * 60)
            print("👤 INICIA SESIÓN EN EL NAVEGADOR (solo la primera vez)")
            print("=" * 60)
            print()
            print("Esperando 60 segundos para que inicies sesión...")
            print("(Esta ventana se puede minimizar después)")
            print()

            time.sleep(60)

            # Loop infinito: refrescar cookies periódicamente
            refresh_count = 0
            while True:
                refresh_count += 1
                print(
                    f"\n🍪 Refresh #{refresh_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )

                # Refrescar la página para obtener cookies nuevas
                print("   Refrescando página...")
                page.reload(wait_until="domcontentloaded")

                # Capturar cookies
                cookies = context.cookies()

                if not cookies:
                    print("   ❌ No se encontraron cookies")
                    continue

                # Verificar cookies importantes
                cookie_names = [c["name"] for c in cookies]
                important = ["session", "sid", "__cf_bm"]

                print(f"   ✓ Capturadas {len(cookies)} cookies")
                for cookie_name in important:
                    if cookie_name in cookie_names:
                        cookie = next(c for c in cookies if c["name"] == cookie_name)
                        if "expires" in cookie:
                            exp = datetime.fromtimestamp(cookie["expires"])
                            print(
                                f"     {cookie_name}: expira {exp.strftime('%H:%M:%S')}"
                            )
                        else:
                            print(f"     {cookie_name}: ✓")

                # Guardar cookies
                print(f"   💾 Guardando en {output_file}...")
                with open(output_file, "w") as f:
                    json.dump(cookies, f, indent=2)

                print("   ✅ Cookies actualizadas exitosamente")
                print(f"   ⏱️  Próximo refresh en {refresh_interval//60} minutos...")

                # Esperar hasta el próximo refresh
                time.sleep(refresh_interval)

    except KeyboardInterrupt:
        print("\n\n⚠️  Detenido por usuario")
        print("Sesión del navegador guardada para la próxima vez")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Refrescar cookies automáticamente con sesión persistente"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("cookies.json"),
        help="Archivo de salida (default: cookies.json)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1500,
        help="Segundos entre refresh (default: 1500 = 25 min)",
    )
    parser.add_argument(
        "--browser-dir",
        type=Path,
        default=Path(".browser_session"),
        help="Directorio para datos del navegador (default: .browser_session)",
    )

    args = parser.parse_args()

    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "AUTO-REFRESH COOKIES (PERSISTENTE)" + " " * 13 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    refresh_with_persistent_session(
        output_file=args.output,
        refresh_interval=args.interval,
        browser_data_dir=args.browser_dir,
    )


if __name__ == "__main__":
    main()
