# Discogs Recommender

Sistema experimental para recolectar datos públicos de Discogs y generar recomendaciones de discos. El catálogo completo de Discogs supera los ~18 millones de lanzamientos y ~8 millones de usuarios; este proyecto se enfoca en explorar una fracción  de ese universo.

## Características

- Ingesta de colecciones, wantlists y contribuciones desde Discogs usando los scripts `fill_db_discogs_API.py` y `fill_db_recommendation_system.py`.
- Aplicación web en Flask (`sr_discogs/app.py`) para experimentar con recomendaciones aleatorias sobre la base.
- Esquema SQLite sencillo (`create_db`) con usuarios, ítems e interacciones.
- Hooks pre-commit configurados (`.pre-commit-config.yaml`) para mantener estilo (Black, isort, flake8, etc.).
- Scraper HTML invocable como módulo (`python -m scraper.pipeline`) con resumen automático de nuevos ítems/usuarios/interacciones y totales de la base.

## Estructura

```
DISCOGS-SR/
├── fill_db_discogs_API.py        # CLI simple para poblar colecciones de usuarios puntuales
├── fill_db_recommendation_system.py  # Ingesta completa con descubrimiento de usuarios y CLI avanzada
├── settings.py                   # Helpers para configuración (tokens, rutas, pausas)
├── create_db                     # Script SQL con el esquema SQLite
├── run_scraper.py                # Wrapper inteligente para ejecutar el scraper con verificación de cookies
├── refresh_cookies.py            # Actualización automática de cookies con Playwright (sesión única)
├── refresh_cookies_persistent.py # Mantiene navegador abierto para auto-refresh continuo
├── check_scraper_status.py       # Diagnóstico del sistema y verificación de estado
├── monitor_progress.sh           # Script para monitoreo continuo del progreso
├── sr_discogs/
│   ├── app.py                    # Aplicación Flask
│   ├── recomendar.py             # Lógica de recomendaciones
│   ├── metricas.py               # Implementación de DCG / NDCG
│   └── templates/                # Vistas HTML
├── scraper/                      # Módulo completo para scraping HTML
│   ├── __init__.py
│   ├── pipeline.py               # Pipeline principal de scraping
│   ├── auth.py                   # Gestión de autenticación y cookies
│   ├── http.py                   # Cliente HTTP con rate limiting y retries
│   ├── models.py                 # Modelos de datos para scraping
│   ├── parsers.py                # Parsers HTML para extraer datos
│   └── db.py                     # Funciones de base de datos específicas para scraping
├── ingestion/                    # Módulo para ingesta vía API de Discogs
│   ├── __init__.py
│   ├── db.py                     # Funciones de BD para ingesta
│   └── http_client.py            # Cliente HTTP rate-limited para API
├── tests/                        # Tests unitarios y de integración
│   ├── __init__.py
│   ├── test_auth.py              # Tests para módulo de autenticación
│   ├── test_parsers.py           # Tests para parsers HTML
│   └── fixtures/                 # HTML de prueba para tests
├── requirements.txt              # Dependencias mínimas de runtime
├── .pre-commit-config.yaml       # Hooks de formato/lint
└── .gitignore
```

La base de datos por defecto se guarda en `data/discogs.db` (creada automáticamente si no existe). Los `.db` locales y directorios de entornos están ignorados en git.

## Requisitos

- Python 3.10+ (probado con 3.11).
- Entorno administrado con `conda` (recomendado) o `venv`.
- Token personal de Discogs.

Instalación de dependencias mínimas:

```bash
pip install -r requirements.txt
```

Para los hooks de desarrollo: `pip install pre-commit black isort flake8 flake8-bugbear` (o vía conda) y luego `pre-commit install`.

## Configuración

Las rutas a la base y el token se resuelven vía `settings.py`. Todos los componentes usan `get_database_path()` para abrir el mismo archivo SQLite. Si no exportás `DATABASE_PATH`, se crea `data/discogs.db` automáticamente.

```bash
export DISCOGS_TOKEN="tu_token"
export DATABASE_PATH="/ruta/absoluta/a/discogs.db"  # opcional
```

Las variables se leen del entorno (no se usa `.env`). Ejemplo con conda:

```bash
conda env config vars set DISCOGS_TOKEN="tu_token"
conda env config vars set DISCOGS_SEED_USERNAME="Xmipod"      # opcional
conda env config vars set DATABASE_PATH="$CONDA_PREFIX/data/discogs.db"  # opcional
conda deactivate && conda activate recomendar
```

Variables relevantes:

- `DISCOGS_TOKEN` (obligatorio): token personal para la API.
- `DISCOGS_SEED_USERNAME` (opcional): usuario inicial para descubrimiento.
- `DATABASE_PATH` (opcional): ruta absoluta a la base SQLite.
- `DISCOGS_API_PAUSE` (opcional): pausa base en segundos entre llamadas (default 2).
- `DISCOGS_COOKIES_FILE` (opcional): archivo de cookies (JSON o formato Netscape) para autenticarse al scrapear HTML.
- `DISCOGS_COOKIES_REFRESH_SECONDS` (opcional): intervalo en segundos para recargar automáticamente las cookies (default 900).
- `DISCOGS_HEADERS_FILE` (opcional): archivo JSON con headers extra a enviar en cada request del scraper HTML.

## Poblar la base

### Scripts disponibles

| Script | Uso principal | Qué ingesta | Cuándo usarlo |
|--------|---------------|-------------|----------------|
| `fill_db_discogs_API.py` | CLI liviano | Solo colección (folder 0) de usuarios puntuales | Poblar rápido perfiles para demo o debugging |
| `fill_db_recommendation_system.py` | Crawler completo | Colección, wantlist, contribuciones + descubrimiento BFS | Correr sesiones largas, nutrir el dataset para recomendaciones |
| `scrape_discogs_site.py` | Scraper HTML | Releases populares, usuarios detectados (Have/Want) y reviews con rating | Cuando el rate limit de la API resulta bloqueante |

Ambos scripts escriben en la misma base configurada por `get_database_path()`.

### Colecciones puntuales (script simple)

```bash
python fill_db_discogs_API.py --user Xmipod          # un usuario
python fill_db_discogs_API.py --users-file usuarios.txt --delay 2
```

El archivo `usuarios.txt` debe contener un username por línea.

### Modo completo para el sistema de recomendaciones (crawler)

```bash
python fill_db_recommendation_system.py \
  --seed Xmipod \
  --max-users 5 \
  --api-pause 1
```

Parámetros útiles:

- `--token`: token alternativo (sobre-escribe la variable de entorno).
- `--force`: reprocesa usuarios aunque ya tengan datos (actualiza interacciones existentes).
- `--min-items`: salta usuarios con pocas interacciones previas.
- `--continue-from`: retoma desde un usuario guardado en `.last_processed_user.txt` (auto generado si se interrumpe el proceso).
- `--adaptive-pause`: activa pausas adaptativas según headers de rate limit.
- `--max-users`: controla cuántos usuarios descubre/procesa a partir del seed.

#### ¿Cómo descubre nuevos usuarios?

La API de Discogs **no expone** quién más tiene/quiere un release, por lo que no podemos saltar automáticamente de un disco a otro usuario. El crawler usa lo que sí está disponible:

- followers y following del seed (hasta `DISCOVERY_MAX_DEPTH`, por defecto 2 niveles).
- contribuyentes de listas públicas del usuario.
- un pool de seeds adicionales (`--extra-seeds` / `--seeds-file`) para seguir explorando cuando la vecindad se agota.

Cada usuario visitado queda registrado en `.discovered_users.log` para evitar reprocesarlos en corridas futuras (borrá ese archivo si querés reiniciar la exploración). Si Discogs agrega endpoints con colección compartida por release, se puede extender la estrategia fácilmente.

#### Ejecución prolongada

Para dejarlo corriendo varias horas con logging:

```bash
mkdir -p logs
export DISCOGS_TOKEN="tu_token"
nohup python fill_db_recommendation_system.py \
  --seed Xmipod \
  --max-users 50 \
  --force \
  --min-items 30 \
  --api-pause 1 \
  --adaptive-pause \
  > logs/recommendation_ingest.log 2>&1 &
```

- Revisá el progreso con `tail -f logs/recommendation_ingest.log`.
- Interrumpí con `Ctrl+C` si está en primer plano. En background: `pkill -f fill_db_recommendation_system.py` (macOS/Linux).
- El archivo `.last_processed_user.txt` permite retomar con `--continue-from`.

Para correr en primer plano (sin `nohup` ni background) simplemente omite `nohup` y el `&` final.

### Scraping vía HTML (sin API)

Cuando la API no alcanza por límites de rate o porque queremos ratings de reviews públicas, podés usar el scraper HTML.

#### Opción 1: Wrapper inteligente (recomendado)

El script `run_scraper.py` verifica automáticamente las cookies y ofrece actualizarlas si están expiradas:

```bash
# Uso básico (verifica cookies automáticamente)
python3 run_scraper.py --pages 5 --limit 50

# Con actualización forzada de cookies
python3 run_scraper.py --force-refresh --pages 10
```

#### Opción 2: Manual

```bash
python -m scraper.pipeline \
  --max-pages 5 \
  --release-limit 200 \
  --min-delay 2.5 \
  --delay-jitter 1.5 \
  --log-level INFO
```

El scraper recorre resultados de búsqueda ordenados por `Have`, visita cada release y extrae:

- Metadatos del release (artistas, año, géneros, carátula).
- Usuarios vinculados en las secciones _Have_ / _Want_ (se almacenan como `interaction_type = collection` o `wantlist`).
- Información básica del perfil del usuario (ubicación, fecha de alta, tamaño de colección/wantlist cuando se muestra públicamente).

**Notas técnicas:**
- El scraper HTML **no obtiene ratings explícitos**. Solo obtiene interacciones have/want, que son suficientes para sistemas de recomendación basados en filtrado colaborativo.
- Las listas de usuarios se obtienen desde `/release/stats/{id}` de Discogs.
- Requiere cookies válidas (Cloudflare `__cf_bm` expira cada ~30 min).
- Usa certificados SSL de `certifi` para evitar errores CERTIFICATE_VERIFY_FAILED.

#### Gestión automática de cookies

El scraper necesita cookies válidas para obtener usuarios de las listas Have/Want. Las cookies de Cloudflare expiran cada ~30 minutos, por lo que necesitas actualizarlas regularmente.

**Actualización automática con Playwright:**

```bash
# Instalar Playwright (solo una vez)
pip install playwright
playwright install chromium

# Actualizar cookies automáticamente (sesión única)
python3 refresh_cookies.py
```

El script abre un navegador Chrome, espera a que inicies sesión (60 segundos), y guarda las cookies en `cookies.json`.

**Para sesiones largas (varias horas):**

```bash
# Mantener sesión de navegador y auto-refresh cada 25 minutos
python3 refresh_cookies_persistent.py --interval 1500
```

Este script mantiene el navegador abierto y actualiza las cookies automáticamente cada 25 minutos. Útil para sesiones de toda la noche sin intervención manual.

**Verificar estado de las cookies:**

```bash
python3 check_scraper_status.py
```

Este script muestra:
- Estado de las cookies (válidas/expiradas)
- Estadísticas de la base de datos
- Archivos HTML de debug guardados
- Advertencias si algo no está bien

**Monitorear progreso en tiempo real:**

```bash
# macOS/Linux
./monitor_progress.sh

# Manualmente cada N segundos
watch -n 5 python3 check_scraper_status.py
```

Útil para sesiones largas, muestra el progreso cada 5 segundos sin interrumpir el scraper.

**Actualización manual (alternativa):**

1. Instala una extensión de cookies: Cookie-Editor, EditThisCookie, etc.
2. Visita https://www.discogs.com e inicia sesión
3. Exporta todas las cookies en formato JSON
4. Guarda el archivo como `cookies.json`

**Uso integrado:**

El wrapper `run_scraper.py` verifica automáticamente si las cookies están expiradas y ofrece actualizarlas antes de ejecutar el scraper:

```bash
# Verifica y actualiza cookies automáticamente si es necesario
python3 run_scraper.py --pages 5 --limit 50

# Fuerza actualización de cookies antes de scrapear
python3 run_scraper.py --force-refresh --pages 10
```

#### Sistema de Checkpoints (Commits Periódicos)

El scraper guarda progreso periódicamente para evitar pérdida de datos:

```bash
# Guardar después de cada release (más seguro, recomendado)
python3 run_scraper.py --pages 5 --limit 50 --commit-every 1

# Guardar cada 10 releases (más rápido, para sesiones largas)
python3 run_scraper.py --pages 20 --limit 200 --commit-every 10
```

**Manejo de interrupciones:**
- Si presionas Ctrl+C: el scraper guarda todo el progreso automáticamente antes de salir
- Si se corta la conexión: solo pierdes el release en proceso, el resto está guardado
- Sin `--commit-every`: solo guarda al final (riesgo de perder horas de trabajo)

#### Sesiones Largas (Toda la Noche)

Para sesiones de varias horas sin intervención:

**Terminal 1: Auto-refresh de cookies (ejecutar primero)**
```bash
python3 refresh_cookies_persistent.py --interval 1500
```

**Terminal 2: Scraper con checkpoints**
```bash
python3 run_scraper.py \
  --pages 30 \
  --limit 500 \
  --no-profile \
  --commit-every 10 \
  --delay 3 \
  --delay-jitter 2
```

**Terminal 3: Monitor (opcional)**
```bash
./monitor_progress.sh
```

Parámetros útiles:

- `--no-profile`: salta la visita a páginas de usuario (10x más rápido, solo guarda interacciones).
- `--commit-every N`: guarda cada N releases (esencial para sesiones largas).
- `--database /ruta/otra.db`: escribe en una base alternativa.
- `--search-url`: permite arrancar desde cualquier consulta de Discogs, ej. `/search/?genre=house&type=release`.
- `--release-limit`, `--max-pages`, `--min-delay`, `--delay-jitter`, `--max-retries`, `--backoff-factor`: control fino del crawling y las pausas.

Al finalizar imprime dos líneas con el resumen:

```
[INFO] Scraping completed. Releases processed: 120 | new items: 95 | new users: 48 | new interactions: 310
[INFO] Database totals -> items: 45734 | users: 142 | interactions: 47627
```

El script antiguo `scrape_discogs_site.py` continúa disponible como envoltorio del pipeline para usos existentes.

#### Scripts de Utilidad

**Diagnóstico del sistema:**
```bash
python3 check_scraper_status.py
```
Muestra: estado de cookies, estadísticas de BD, ratio interacciones/usuarios, archivos de debug.

**Monitoreo continuo:**
```bash
./monitor_progress.sh  # macOS/Linux
```
Ejecuta check_scraper_status.py cada 5 segundos para seguir el progreso en tiempo real.

**Actualización de cookies:**
```bash
# Manual (abre navegador, login, cierra)
python3 refresh_cookies.py

# Persistente (mantiene navegador abierto, auto-refresh)
python3 refresh_cookies_persistent.py --interval 1500
```

**Wrapper inteligente:**
```bash
python3 run_scraper.py [opciones]
```
Verifica cookies, ofrece actualizar si expiraron, ejecuta scraper con configuración óptima.

> **Nota**: el scraper usa pauses adaptativas y `User-Agent` rotativo básico, pero respetar robots y límites de Discogs sigue siendo responsabilidad del operador. Si el sitio devuelve 403/429 el proceso se detiene tras varios reintentos.

## Ejecutar la app web

```bash
cd sr_discogs
python app.py
```

Luego visitar `http://localhost:5000`. El login pide un `user_id` existente en la base; crea registros con `fill_db_discogs_API.py` o `fill_db_recommendation_system.py` primero.

## Esquema de la base

```sql
-- Tabla users
user_id TEXT PRIMARY KEY
username TEXT
location TEXT
joined_date TEXT

-- Tabla items
item_id INTEGER PRIMARY KEY
title TEXT
artist TEXT
year INTEGER
genre TEXT
style TEXT
image_url TEXT

-- Tabla interactions
interaction_id INTEGER PRIMARY KEY AUTOINCREMENT
user_id TEXT
item_id INTEGER
interaction_type TEXT
rating INTEGER
date_added TEXT
```

## Buenas prácticas

- Correr `pre-commit run --all-files` antes del primer commit.
- No compartir `discogs.db` ni tu token; ambos están ignorados por git.

## Pruebas

Las utilidades de discovery incluyen un harness básico:

```bash
export DISCOGS_TOKEN="tu_token"
python -c "import fill_db_recommendation_system as m; m.init_runtime(); m.run_tests()"
```

Esto valida los mocks de `get_user_neighbors` y `discover_users`. Podés pasar el token directo: `m.init_runtime(token="tu_token")` si preferís no exportarlo.

Para probar los parsers HTML sin salir a la web:

```bash
python -m unittest tests.test_parsers
```
