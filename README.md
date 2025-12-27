# Discogs-SR (DEPRECADO)

> Este proyecto quedó en pausa: el scraping sobre Discogs funcionaba con Playwright y la API, pero nunca se cristalizó el recomendador final. La base ya no se actualiza, aunque la estructura permanece para retomar más adelante.

---

# Discogs-SR (DEPRECATED)

> This project was paused: scraping Discogs via Playwright and the API worked, but the final recommender was never fully consolidated. The database is no longer updated, although the structure remains available to pick up later.

## Estado actual

- **Scraping y crawling**: la estrategia original superaba los controles básicos de Cloudflare, pero era demasiado lenta para escalar, especialmente al intentar capturar ratings detallados.
- **Sistema de recomendaciones**: queda como prototipo; los componentes principales (`sr_discogs/`, `scraper/`, `ingestion/`) siguen siendo útiles como referencia.
- **¿Qué se puede retomar?** revisar `scripts/fill_db_recommendation_system.py`, retomar la ingesta incremental y volver a la carpeta `docs/` para actualizar los pasos pendientes.

## Current status

- **Scraping and crawling**: the original strategy could get past basic Cloudflare controls, but it was too slow to scale—especially when trying to capture detailed ratings.
- **Recommendation system**: left as a prototype; the main components (`sr_discogs/`, `scraper/`, `ingestion/`) are still useful as reference.
- **What could be resumed?** Review `scripts/fill_db_recommendation_system.py`, bring back incremental ingestion, and revisit `docs/` to update any pending steps.

## Organización

- `scripts/`: herramientas de mantenimiento, auditoría, scraping y crawling (cookies, monitor, auditoría de BD, etc.).
- `db/schema.sql`: esquema completo de la base SQLite.
- `scraper/` y `ingestion/`: módulos centrales de scraping HTML y consultas a la API.
- `sr_discogs/`: aplicación Flask usada para validar recomendaciones.
- `tests/`: parsers, autenticación y lógica del recomendador con fixtures.
- `legacy/`: scripts antiguos (API + scraper originales) y utilidades heredadas.
- `docs/`: documentación extendida (ver [`DETAILED_GUIDE.md`](docs/DETAILED_GUIDE.md))
- `settings.py`: configuración compartida (tokens, rutas, pausas).

## Repository layout

- `scripts/`: maintenance, auditing, scraping and crawling tools (cookies, monitoring, DB audits, etc.).
- `db/schema.sql`: full SQLite schema.
- `scraper/` and `ingestion/`: core modules for HTML scraping and Discogs API usage.
- `sr_discogs/`: Flask app used to validate recommendations.
- `tests/`: parsers, authentication, and recommender logic with fixtures.
- `legacy/`: older scripts (original API + scraper) and legacy utilities.
- `docs/`: extended documentation (see [`DETAILED_GUIDE.md`](docs/DETAILED_GUIDE.md)).
- `settings.py`: shared configuration (tokens, paths, pauses).

## ¿Qué hacer si se retoma?

1. Leer [`docs/DETAILED_GUIDE.md`](docs/DETAILED_GUIDE.md) para comprender el flujo completo.
2. Regenerar cookies y bases (`scripts/refresh_cookies_persistent.py`, `db/schema.sql`).
3. Reejecutar los tests (`python -m pytest tests/`) y validar componentes nuevos antes de modificar la lógica del recomendador.

## Checklist de reanudación (práctico)

1. Crear un entorno limpio e instalar dependencias (`python -m venv .venv` + `pip install -r requirements.txt`).
2. Exportar variables mínimas: `DISCOGS_TOKEN` y (opcional) `DATABASE_PATH`.
3. Crear/regenerar la base: `sqlite3 data/discogs.db < db/schema.sql`.
4. Preparar cookies (si se usa scraping HTML): correr `scripts/refresh_cookies_persistent.py` y dejar `scripts/check_scraper_status.py` monitoreando.
5. Ejecutar tests: `python -m pytest tests/`.
6. Hacer un “dry run” pequeño (pocos usuarios/páginas) antes de escalar: `scripts/run_scraper.py` y/o `scripts/fill_db_recommendation_system.py` con límites bajos.
7. Registrar cambios de comportamiento y supuestos en `docs/` (rate limits, headers/cookies, heurísticas de parsers).

## If you resume the project

1. Read [`docs/DETAILED_GUIDE.md`](docs/DETAILED_GUIDE.md) (this file is bilingual) to understand the full pipeline.
2. Regenerate cookies and databases (`scripts/refresh_cookies_persistent.py`, `db/schema.sql`).
3. Re-run tests (`python -m pytest tests/`) and validate new components before changing recommender logic.

## Resumption checklist (practical)

1. Create a clean environment and install dependencies (`python -m venv .venv` + `pip install -r requirements.txt`).
2. Export minimal env vars: `DISCOGS_TOKEN` and (optionally) `DATABASE_PATH`.
3. Create/regenerate the DB: `sqlite3 data/discogs.db < db/schema.sql`.
4. Prepare cookies (if doing HTML scraping): run `scripts/refresh_cookies_persistent.py` and keep `scripts/check_scraper_status.py` monitoring.
5. Run tests: `python -m pytest tests/`.
6. Do a small “dry run” (few users/pages) before scaling: `scripts/run_scraper.py` and/or `scripts/fill_db_recommendation_system.py` with low limits.
7. Write down behavior changes and assumptions in `docs/` (rate limits, headers/cookies, parser heuristics).

