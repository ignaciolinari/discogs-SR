# Discogs-SR (DEPRECADO)

> Este proyecto quedó en pausa: el scraping sobre Discogs funcionaba con Playwright y la API, pero nunca se cristalizó el recomendador final. La base ya no se actualiza, aunque la estructura permanece para retomar más adelante.

## Estado actual

- **Scraping y crawling**: la estrategia original superaba los controles básicos de Cloudflare, pero era demasiado lenta para escalar, especialmente al intentar capturar ratings detallados.
- **Sistema de recomendaciones**: queda como prototipo; los componentes principales (`sr_discogs/`, `scraper/`, `ingestion/`) siguen siendo útiles como referencia.
- **¿Qué se puede retomar?** revisar `scripts/fill_db_recommendation_system.py`, retomar la ingesta incremental y volver a la carpeta `docs/` para actualizar los pasos pendientes.

## Organización

- `scripts/`: herramientas de mantenimiento, auditoría, scraping y crawling (cookies, monitor, auditoría de BD, etc.).
- `db/schema.sql`: esquema completo de la base SQLite.
- `scraper/` y `ingestion/`: módulos centrales de scraping HTML y consultas a la API.
- `sr_discogs/`: aplicación Flask usada para validar recomendaciones.
- `tests/`: parsers, autenticación y lógica del recomendador con fixtures.
- `legacy/`: scripts antiguos (API + scraper originales) y utilidades heredadas.
- `docs/`: documentación extendida; arranca por `docs/DETAILED_GUIDE.md` y agrega nuevos apuntes cuando avances.
- `settings.py`: configuración compartida (tokens, rutas, pausas).

## ¿Qué hacer si se retoma?

1. Leer `docs/DETAILED_GUIDE.md` para comprender el flujo completo.
2. Regenerar cookies y bases (`scripts/refresh_cookies_persistent.py`, `db/schema.sql`).
3. Reejecutar los tests (`python -m pytest tests/`) y validar componentes nuevos antes de modificar la lógica del recomendador.

Para detalles históricos y comandos prolongados, recurre a `docs/DETAILED_GUIDE.md`.

