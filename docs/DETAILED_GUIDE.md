# Discogs Recommender

> **Deprecado** pero mantenido como referencia: el scraping con Playwright y la API funcionaba, pero nunca se consolidó un sistema de recomendaciones listo para producción. La arquitectura sigue disponible para retomar, experimentar o documentar nuevas hipótesis.

## Propósito y recorrido

El objetivo original era recolectar interacciones públicas (colección, wantlist, contribuciones) y combinarlas con un scraper HTML para capturar metadatos ricos. Esto permitía alimentar un recomendador híbrido que elegía entre filtrado colaborativo, perfiles de contenido y fallback por popularidad. Aunque la ingestión completa llegó a funcionar, la velocidad—especialmente al extraer ratings específicos—no fue suficiente y el proyecto quedó en pausa.

## Estructura del repositorio

```
DISCOGS-SR/
├── scripts/                # Auditorías, scraping, cookies y utilidades operativas
├── db/
│   └── schema.sql          # SQL del esquema SQLite
├── scraper/                # Scraper HTML con detección de master_id y normalización canónica
├── ingestion/              # Cliente y helpers para la API oficial de Discogs
├── sr_discogs/             # Aplicación Flask experimental y el recomendador híbrido
├── tests/                  # Parsers, autenticación y lógica del recomendador con fixtures
├── legacy/                 # Scripts antiguos (API, scraper y cookies manuales)
├── docs/                   # Documentación adicional (este archivo incluido)
├── settings.py             # Configuración común (tokens, rutas, pausas adaptativas)
├── requirements.txt        # Dependencias mínimas
├── LICENSE
├── .pre-commit-config.yaml
└── .gitignore
```

El directorio `scripts/` agrupa los comandos operativos que antes estaban distribuidos en la raíz. Mantén esa carpeta como punto de partida para auditorías, scraping e ingestión.

## Scripts clave

| Script | Qué hace | Ejemplo de ejecución |
|--------|----------|----------------------|
| `scripts/fill_db_recommendation_system.py` | Crawler híbrido con descubrimiento BFS, ingesta de colecciones/wantlists/contribuciones y normalización canónica. | `python scripts/fill_db_recommendation_system.py --seed Xmipod --max-users 10 --api-pause 1` |
| `scripts/run_scraper.py` | Wrapper inteligente del scraper HTML (cookies, checkpoints, logging, detección de master). | `python scripts/run_scraper.py --pages 5 --limit 50 --commit-every 5` |
| `scripts/refresh_cookies_persistent.py` | Mantiene un navegador abierto con Playwright y refresca las cookies (`__cf_bm`) cada 25 minutos. | `python scripts/refresh_cookies_persistent.py --interval 1500` |
| `scripts/check_scraper_status.py` | Monitorea cookies, estadísticas de la DB y advertencias de scraping. | `python scripts/check_scraper_status.py` o `./scripts/monitor_progress.sh` para polling continuo. |
| `scripts/check_db_health.py` | Auditoría de la base (títulos desconocidos, duplicados, calendario, relaciones master/release). | `python scripts/check_db_health.py` |
| `scripts/fix_unknown_titles.py` | Repara registros con títulos o artistas faltantes consultando el endpoint de releases con `source_release_id`. | `python scripts/fix_unknown_titles.py` |
| `scripts/monitor_progress.sh` | Script auxiliar que ejecuta `check_scraper_status` cada 5 segundos en macOS/Linux para sesiones largas. | `./scripts/monitor_progress.sh` |

## Base de datos

- La base por defecto es `data/discogs.db` (creada automáticamente si no existe). No se versionan `.db` locales en Git.
- El esquema SQLite vive en `db/schema.sql`. Regenerarlo es tan simple como `sqlite3 data/discogs.db < db/schema.sql`.
- Todas las sesiones y utilidades comparten `settings.get_database_path()` para evitar múltiples archivos.

## Configuración y variables de entorno

| Variable | Propósito | Valor típico |
|----------|-----------|--------------|
| `DISCOGS_TOKEN` | Token personal para la API. Obligatorio para ingestas y correcciones. | `tu_token` |
| `DISCOGS_SEED_USERNAME` | Usuario inicial para descubrimiento (seed). | `Xmipod` |
| `DATABASE_PATH` | Ruta absoluta a la base si no se usa `data/discogs.db`. | `/ruta/absoluta/discogs.db` |
| `DISCOGS_API_PAUSE` | Pausa base entre llamadas a la API (default 1s). | `1` |
| `DISCOGS_COOKIES_FILE` | Cookies JSON/Netscape para el scraper sin Playwright. | `cookies.json` |
| `DISCOGS_COOKIES_REFRESH_SECONDS` | Intervalo de refresco automático de cookies (default 900s). | `900` |
| `DISCOGS_HEADERS_FILE` | Headers extra para las requests HTML. | `headers.json` |
| `RECOMMENDER_...` | Parámetros del recomendador híbrido (thresholds, TTL, etc.). | ver `settings.py` |

Las variables se exportan manualmente o con `conda env config vars set VAR=valor`. No se utiliza `.env`.

## Scraper e ingesta

- `scraper/` contiene el pipeline que visita releases, detecta `master_id`, explora listas Have/Want, extrae formatos, labels y metadata extendida.
- `ingestion/` se enfoca en la API oficial (colecciones, wantlists, contribuciones) y lee de `settings` para respetar pausas y rutas.
- La normalización canónica convierte todos los `release_id` en `master_id` cuando existe y guarda `source_release_id` para trazabilidad.
- El crawler exploraba followers/following del seed y contributors de listas públicas; los usuarios visitados se registran en `.discovered_users.log`.

## Aplicación web

La carpeta `sr_discogs/` contiene una app Flask de prueba:

- `app.py` expone login mínimo y muestra recomendaciones combinadas.
- `recomendar.py` implementa las estrategias (collaborative, content-based, popularity, random) y expone helpers como `recomendar.recomendar()` y `recomendar.init_recomendador()` que regenere caches.
- `metricas.py` incluye funciones de evaluación (NDCG, DCG).
- Las plantillas HTML se encuentran en `sr_discogs/templates/`.

Para probarla: `cd sr_discogs && python app.py` y abrir `http://localhost:5000`.

## Testing

- `python -m pytest tests/` ejecuta todos los tests.
- `python -m pytest tests/test_parsers.py -v` y `python -m pytest tests/test_recomendar.py -v` cubren parsers y recomendador respectivamente.
- Los fixtures en `tests/fixtures/` contienen HTML de releases, modal have/want y páginas de usuario para validar sin hacer requests reales.
- También se pueden ejecutar con `python -m unittest tests.test_parsers` o `tests.test_recomendar` si se prefiere el formato estándar.

## Legado y notas adicionales

- `legacy/` almacena versiones anteriores de los scripts de scraper, la API y gestores manuales de cookies.
- `COMANDOS_UTILES.md` (si existe) contiene atajos y consultas SQL que se usaban para tareas repetidas.
- `docs/` es el lugar adecuado para anotar ideas nuevas, planes de reanudación o análisis del scraping.

## Qué tener en cuenta si se retoma

1. La obtención de ratings explícitos era difícil; el scraper solo extraía interacciones Have/Want y algunos metadatos ricos.
2. Cloudflare se esquivaba con Playwright cada 25-30 minutos (`scripts/refresh_cookies_persistent.py`), pero las sesiones podían caducar si no se monitoreaban.
3. El crawling completo era lento (muchos usuarios y releases), así que conviene arrancar por seeds limitados y medir antes de escalar.
4. Regenerar la base (`db/schema.sql`) y limpiar `.discovered_users.log` ayuda a reproducir el pipeline desde cero.
5. Antes de añadir nuevas capas, volver a ejecutar los tests y validar `scripts/check_scraper_status.py` asegura que el entorno está razonablemente sano.

## Checklist de reanudación (operativo)

- Entorno reproducible: definir versión de Python (y si se puede, fijar dependencias con versiones/pins) para evitar roturas por upgrades.
- Config mínima: exportar `DISCOGS_TOKEN`; opcionalmente `DATABASE_PATH`, `DISCOGS_API_PAUSE`.
- DB desde cero: recrear `data/discogs.db` con `db/schema.sql` antes de ejecutar pipelines largos.
- Cookies/Cloudflare: asumir que lo “frágil” es el scraping HTML; monitorear sesiones y refrescar cookies con `scripts/refresh_cookies_persistent.py`.
- Escalado gradual: empezar con límites bajos (pocos usuarios/páginas) y medir tiempos/errores antes de aumentar.
- Observabilidad: usar `scripts/check_scraper_status.py` y anotar en `docs/` cambios de heurísticas, headers y tiempos.
- Respeto de límites: mantener pausas y backoff para no bloquear el token o la sesión.

---

# Discogs Recommender (English)

> **Deprecated** but kept as reference: scraping with Playwright and the API worked, but a production-ready recommender was never consolidated. The architecture is still available to resume, experiment, or document new hypotheses.

## Purpose and history

The original goal was to collect public interactions (collection, wantlist, contributions) and combine them with an HTML scraper to capture richer metadata. This was meant to feed a hybrid recommender that could switch between collaborative filtering, content profiles, and a popularity fallback. While the end-to-end ingestion pipeline did work, the speed—especially when trying to extract explicit ratings—was not sufficient, and the project was paused.

## Repository structure

```
DISCOGS-SR/
├── scripts/                # Audits, scraping, cookies and operational utilities
├── db/
│   └── schema.sql          # SQLite schema SQL
├── scraper/                # HTML scraper (master_id detection, canonical normalization)
├── ingestion/              # Discogs official API client + helpers
├── sr_discogs/             # Experimental Flask app and hybrid recommender
├── tests/                  # Parsers, authentication and recommender logic with fixtures
├── legacy/                 # Older scripts (API, scraper, manual cookies)
├── docs/                   # Additional documentation (this file included)
├── settings.py             # Shared configuration (tokens, paths, adaptive pauses)
├── requirements.txt        # Minimal dependencies
├── LICENSE
├── .pre-commit-config.yaml
└── .gitignore
```

The `scripts/` directory is the operational entry point for audits, scraping, and ingestion.

## Key scripts

| Script | What it does | Example run |
|--------|--------------|-------------|
| `scripts/fill_db_recommendation_system.py` | Hybrid crawler (BFS discovery), collection/wantlist/contributions ingestion, and canonical normalization. | `python scripts/fill_db_recommendation_system.py --seed Xmipod --max-users 10 --api-pause 1` |
| `scripts/run_scraper.py` | Smart wrapper around the HTML scraper (cookies, checkpoints, logging, master detection). | `python scripts/run_scraper.py --pages 5 --limit 50 --commit-every 5` |
| `scripts/refresh_cookies_persistent.py` | Keeps a Playwright browser open and refreshes cookies (`__cf_bm`) every ~25 minutes. | `python scripts/refresh_cookies_persistent.py --interval 1500` |
| `scripts/check_scraper_status.py` | Monitors cookies, DB stats, and scraping warnings. | `python scripts/check_scraper_status.py` or `./scripts/monitor_progress.sh` for continuous polling. |
| `scripts/check_db_health.py` | Database audit (unknown titles, duplicates, timelines, master/release relations). | `python scripts/check_db_health.py` |
| `scripts/fix_unknown_titles.py` | Repairs records with missing titles/artists by calling the releases endpoint with `source_release_id`. | `python scripts/fix_unknown_titles.py` |
| `scripts/monitor_progress.sh` | Helper script that runs `check_scraper_status` every 5 seconds on macOS/Linux for long sessions. | `./scripts/monitor_progress.sh` |

## Database

- Default DB is `data/discogs.db` (auto-created if missing). Local `.db` files are not versioned.
- SQLite schema is in `db/schema.sql`. Recreate with `sqlite3 data/discogs.db < db/schema.sql`.
- All sessions and utilities share `settings.get_database_path()` to avoid multiple DB files.

## Configuration and environment variables

| Variable | Purpose | Typical value |
|----------|---------|---------------|
| `DISCOGS_TOKEN` | Personal API token. Required for ingestion and fixes. | `your_token` |
| `DISCOGS_SEED_USERNAME` | Seed user for discovery. | `Xmipod` |
| `DATABASE_PATH` | Absolute DB path if not using `data/discogs.db`. | `/absolute/path/discogs.db` |
| `DISCOGS_API_PAUSE` | Base pause between API calls (default 1s). | `1` |
| `DISCOGS_COOKIES_FILE` | Cookies file (JSON/Netscape) for scraping without Playwright. | `cookies.json` |
| `DISCOGS_COOKIES_REFRESH_SECONDS` | Auto-refresh interval for cookies (default 900s). | `900` |
| `DISCOGS_HEADERS_FILE` | Extra headers for HTML requests. | `headers.json` |
| `RECOMMENDER_...` | Hybrid recommender parameters (thresholds, TTL, etc.). | see `settings.py` |

Variables are exported manually or via `conda env config vars set VAR=value`. A `.env` file is not used.

## Scraper and ingestion

- `scraper/` contains the pipeline that visits releases, detects `master_id`, explores Have/Want lists, and extracts formats, labels, and richer metadata.
- `ingestion/` focuses on the official API (collections, wantlists, contributions) and reads from `settings` to respect pauses and paths.
- Canonical normalization converts `release_id` into `master_id` when available, and stores `source_release_id` for traceability.
- The crawler explored followers/following of the seed and contributors of public lists; visited users were stored in `.discovered_users.log`.

## Web application

The `sr_discogs/` folder contains an experimental Flask app:

- `app.py` exposes a minimal login and displays combined recommendations.
- `recomendar.py` implements strategies (collaborative, content-based, popularity, random) and exposes helpers like `recomendar.recomendar()` and `recomendar.init_recomendador()` to rebuild caches.
- `metricas.py` includes evaluation functions (NDCG, DCG).
- HTML templates are in `sr_discogs/templates/`.

To try it: `cd sr_discogs && python app.py` and open `http://localhost:5000`.

## Testing

- `python -m pytest tests/` runs the full test suite.
- `python -m pytest tests/test_parsers.py -v` and `python -m pytest tests/test_recomendar.py -v` cover parsers and the recommender.
- Fixtures in `tests/fixtures/` contain release HTML, Have/Want modals, and user pages to validate logic without real network requests.
- You can also use `python -m unittest tests.test_parsers` or `tests.test_recomendar` if you prefer standard unittest.

## Legacy and additional notes

- `legacy/` stores older versions of scraper/API scripts and manual cookie tooling.
- `COMANDOS_UTILES.md` (if present) contains shortcuts and SQL queries used for repeated tasks.
- `docs/` is the right place to write down new ideas, resumption plans, or scraping analysis.

## What to keep in mind if you resume

1. Extracting explicit ratings was difficult; the scraper mainly captured Have/Want interactions plus some richer metadata.
2. Cloudflare was bypassed via Playwright every 25–30 minutes (`scripts/refresh_cookies_persistent.py`), but sessions could expire if not monitored.
3. Full crawling was slow (many users and releases), so start with small seeds and measure before scaling.
4. Recreating the DB (`db/schema.sql`) and clearing `.discovered_users.log` helps reproduce the pipeline from scratch.
5. Before adding new layers, re-run tests and validate `scripts/check_scraper_status.py` to ensure the environment is reasonably healthy.

## Resumption checklist (operational)

- Reproducible env: lock down a Python version (and ideally pin dependency versions) to avoid breakage from upgrades.
- Minimal config: export `DISCOGS_TOKEN`; optionally `DATABASE_PATH`, `DISCOGS_API_PAUSE`.
- Fresh DB: recreate `data/discogs.db` from `db/schema.sql` before long runs.
- Cookies/Cloudflare: assume HTML scraping is the fragile part; monitor sessions and refresh cookies via `scripts/refresh_cookies_persistent.py`.
- Gradual scaling: start with low limits (few users/pages) and measure time/errors before increasing.
- Observability: rely on `scripts/check_scraper_status.py` and document heuristic/header/timing changes in `docs/`.
- Rate limiting: keep pauses/backoff to reduce the chance of token/session issues.
