#!/usr/bin/env python3
"""Script para actualizar cookies de Discogs usando un navegador automatizado.

Este script abre un navegador, permite al usuario iniciar sesión manualmente,
y luego exporta las cookies a cookies.json.
"""

import json
import sys
from pathlib import Path


def refresh_cookies_playwright(
    output_file: Path = Path("cookies.json"),
    headless: bool = False,
    wait_seconds: int = 60,
) -> bool:
    """Actualizar cookies usando Playwright.

    Args:
        output_file: Ruta donde guardar las cookies
        headless: Si True, el navegador se ejecuta sin interfaz visual
        wait_seconds: Segundos a esperar antes de capturar cookies

    Returns:
        True si las cookies se guardaron exitosamente
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright no está instalado.")
        print("\nPara instalar:")
        print("  pip install playwright")
        print("  playwright install chromium")
        return False

    print("=" * 60)
    print("ACTUALIZACIÓN AUTOMÁTICA DE COOKIES - Playwright")
    print("=" * 60)
    print()
    print("Este script va a:")
    print("1. Abrir un navegador Chrome")
    print("2. Navegar a Discogs.com")
    print("3. Esperar a que inicies sesión")
    print(f"4. Guardar las cookies en {output_file}")
    print()

    if not headless:
        print("⚠️  El navegador se abrirá en modo visible.")
        print(f"   Tienes {wait_seconds} segundos para iniciar sesión.")
        print()
        input("Presiona Enter para continuar...")

    try:
        with sync_playwright() as p:
            # Launch browser
            print("\n🌐 Abriendo navegador...")
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            # Navigate to Discogs
            print("📡 Navegando a Discogs.com...")
            page.goto("https://www.discogs.com")

            # Wait for user to login
            print()
            print("=" * 60)
            print("👤 POR FAVOR, INICIA SESIÓN EN EL NAVEGADOR")
            print("=" * 60)
            print()
            print("1. Haz click en 'Log In' / 'Iniciar Sesión'")
            print("2. Ingresa tus credenciales")
            print("3. Navega por el sitio un poco (opcional pero recomendado)")
            print("4. Espera a que este script capture las cookies automáticamente")
            print()
            print(f"⏱️  Esperando {wait_seconds} segundos...")

            # Wait
            page.wait_for_timeout(wait_seconds * 1000)

            # Get cookies
            print("\n🍪 Capturando cookies...")
            cookies = context.cookies()

            if not cookies:
                print("❌ No se encontraron cookies")
                browser.close()
                return False

            print(f"✓ Capturadas {len(cookies)} cookies")

            # Check for important cookies
            cookie_names = [c["name"] for c in cookies]
            important = ["session", "sid", "__cf_bm"]
            missing = [name for name in important if name not in cookie_names]

            if missing:
                print(f"⚠️  Faltan cookies importantes: {', '.join(missing)}")
                print("   Es posible que no hayas iniciado sesión correctamente.")
                response = input("\n¿Guardar de todas formas? (s/n): ")
                if response.lower() != "s":
                    browser.close()
                    return False

            # Save cookies
            print(f"\n💾 Guardando cookies en {output_file}...")
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w") as f:
                json.dump(cookies, f, indent=2)

            print("✓ Cookies guardadas exitosamente")

            # Show cookie info
            for cookie_name in important:
                if cookie_name in cookie_names:
                    cookie = next(c for c in cookies if c["name"] == cookie_name)
                    if "expires" in cookie:
                        from datetime import datetime

                        exp = datetime.fromtimestamp(cookie["expires"])
                        print(
                            f"  {cookie_name}: expira {exp.strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    else:
                        print(f"  {cookie_name}: ✓")

            browser.close()
            return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def refresh_cookies_selenium(
    output_file: Path = Path("cookies.json"),
    headless: bool = False,
    wait_seconds: int = 60,
) -> bool:
    """Actualizar cookies usando Selenium (alternativa a Playwright).

    Args:
        output_file: Ruta donde guardar las cookies
        headless: Si True, el navegador se ejecuta sin interfaz visual
        wait_seconds: Segundos a esperar antes de capturar cookies

    Returns:
        True si las cookies se guardaron exitosamente
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service  # noqa: F401
    except ImportError:
        print("❌ Selenium no está instalado.")
        print("\nPara instalar:")
        print("  pip install selenium")
        print("  # También necesitas ChromeDriver: brew install chromedriver")
        return False

    print("=" * 60)
    print("ACTUALIZACIÓN AUTOMÁTICA DE COOKIES - Selenium")
    print("=" * 60)
    print()

    if not headless:
        print(
            f"⚠️  El navegador se abrirá. Tienes {wait_seconds} segundos para iniciar sesión."
        )
        input("Presiona Enter para continuar...")

    try:
        # Setup Chrome options
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1280,720")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Launch browser
        print("\n🌐 Abriendo navegador...")
        driver = webdriver.Chrome(options=chrome_options)

        # Navigate to Discogs
        print("📡 Navegando a Discogs.com...")
        driver.get("https://www.discogs.com")

        # Wait for user to login
        print()
        print("=" * 60)
        print("👤 POR FAVOR, INICIA SESIÓN EN EL NAVEGADOR")
        print("=" * 60)
        print(f"\n⏱️  Esperando {wait_seconds} segundos...")

        import time

        time.sleep(wait_seconds)

        # Get cookies
        print("\n🍪 Capturando cookies...")
        cookies = driver.get_cookies()

        if not cookies:
            print("❌ No se encontraron cookies")
            driver.quit()
            return False

        print(f"✓ Capturadas {len(cookies)} cookies")

        # Save cookies
        print(f"\n💾 Guardando cookies en {output_file}...")
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(cookies, f, indent=2)

        print("✓ Cookies guardadas exitosamente")

        driver.quit()
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Actualizar cookies de Discogs usando un navegador automatizado"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("cookies.json"),
        help="Ruta del archivo de cookies (default: cookies.json)",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=60,
        help="Segundos a esperar antes de capturar cookies (default: 60)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecutar navegador sin interfaz visual (no recomendado)",
    )
    parser.add_argument(
        "--selenium",
        action="store_true",
        help="Usar Selenium en lugar de Playwright",
    )

    args = parser.parse_args()

    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "REFRESH COOKIES DISCOGS" + " " * 20 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    if args.selenium:
        success = refresh_cookies_selenium(
            output_file=args.output,
            headless=args.headless,
            wait_seconds=args.wait,
        )
    else:
        success = refresh_cookies_playwright(
            output_file=args.output,
            headless=args.headless,
            wait_seconds=args.wait,
        )

    if success:
        print()
        print("=" * 60)
        print("✅ ÉXITO")
        print("=" * 60)
        print()
        print("Cookies actualizadas. Ahora puedes ejecutar el scraper:")
        print()
        print("  python3 scrape_discogs_site.py \\")
        print(f"    --cookies-file {args.output} \\")
        print("    --pages 5 \\")
        print("    --limit 50 \\")
        print("    --log-level INFO")
        print()
        sys.exit(0)
    else:
        print()
        print("=" * 60)
        print("❌ ERROR")
        print("=" * 60)
        print()
        print("No se pudieron actualizar las cookies.")
        print("Intenta manualmente con una extensión del navegador.")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
