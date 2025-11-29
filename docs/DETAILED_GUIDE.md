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
