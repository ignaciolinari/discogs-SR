# Discogs Recommender

Sistema experimental para recolectar datos públicos de Discogs y generar recomendaciones de discos. El catálogo completo de Discogs supera los ~18 millones de lanzamientos y ~8 millones de usuarios; este proyecto se enfoca en explorar una fracción  de ese universo.

## Características

- **Normalización canónica de identificadores**: Todas las interacciones se registran usando `master_id` cuando está disponible, consolidando múltiples ediciones del mismo álbum. El `release_id` original se preserva en `source_release_id`.
- **Sistema híbrido de recomendaciones**: Combina estrategias collaborative filtering (basado en pares de usuarios), content-based (perfiles de género/artista/estilo), y fallback por popularidad. Cambia dinámicamente según la señal disponible.
- **Ingesta completa**: Colecciones, wantlists y contribuciones desde la API de Discogs con descubrimiento automático de usuarios mediante BFS sobre followers/following.
- **Scraper HTML robusto**: Para superar límites de rate de la API, extrae datos enriquecidos (labels, formatos, país, ratings de reviews) con detección automática de masters.
- **Aplicación web en Flask** (`sr_discogs/app.py`) para experimentar con recomendaciones personalizadas.
- **Esquema SQLite normalizado** con tablas separadas para géneros, estilos, formatos y labels.
- **Hooks pre-commit** configurados para mantener calidad de código (Black, isort, flake8).
- **Cache de popularidad**: Sistema automático de ranking de ítems más populares para fallback y arranque en frío.
- **Herramientas de mantenimiento**: Scripts de auditoría de salud de BD y recuperación de datos faltantes.

## Estructura

```
DISCOGS-SR/
├── fill_db_recommendation_system.py  # Ingesta completa con descubrimiento de usuarios y CLI avanzada
├── settings.py                   # Helpers para configuración (tokens, rutas, pausas)
├── create_db                     # Script SQL con el esquema SQLite
├── run_scraper.py                # Wrapper inteligente para ejecutar el scraper con verificación de cookies
├── refresh_cookies_persistent.py # Mantiene navegador abierto para auto-refresh continuo de cookies
├── check_scraper_status.py       # Diagnóstico del sistema y verificación de estado
├── check_db_health.py            # Auditoría completa de salud de la base de datos
├── fix_unknown_titles.py         # Script de recuperación para items con títulos/artistas faltantes
├── monitor_progress.sh           # Script para monitoreo continuo del progreso
├── COMANDOS_UTILES.md            # Guía de comandos frecuentes y consultas SQL útiles
├── sr_discogs/
│   ├── app.py                    # Aplicación Flask
│   ├── recomendar.py             # Sistema híbrido de recomendaciones (collaborative + content-based + popularity)
│   ├── metricas.py               # Implementación de DCG / NDCG
│   └── templates/                # Vistas HTML
├── scraper/                      # Módulo completo para scraping HTML
│   ├── __init__.py
│   ├── pipeline.py               # Pipeline principal de scraping con normalización canónica
│   ├── auth.py                   # Gestión de autenticación y cookies
│   ├── http.py                   # Cliente HTTP con rate limiting y retries
│   ├── models.py                 # Modelos de datos (Release, User, Review, etc.)
│   ├── parsers.py                # Parsers HTML con extracción de master_id, labels, formatos
│   └── db.py                     # Funciones de base de datos con soporte master/release
├── ingestion/                    # Módulo para ingesta vía API de Discogs
│   ├── __init__.py
│   ├── db.py                     # Funciones de BD para ingesta con normalización canónica
│   └── http_client.py            # Cliente HTTP rate-limited para API
├── tests/                        # Tests unitarios y de integración
│   ├── __init__.py
│   ├── test_auth.py              # Tests para módulo de autenticación
│   ├── test_parsers.py           # Tests para parsers HTML (incluyendo master_id)
│   ├── test_recomendar.py        # Tests para sistema de recomendaciones
│   └── fixtures/                 # HTML de prueba para tests
├── legacy/                          # Scripts legacy (movidos aquí tras refactorización)
│   ├── fill_db_discogs_API.py    # Versión anterior del ingestor API
│   ├── scrape_discogs_site.py    # Versión anterior del scraper
│   └── refresh_cookies.py        # Versión de sesión única (reemplazada por persistente)
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
- `DISCOGS_API_PAUSE` (opcional): pausa base en segundos entre llamadas (default 1).
- `DISCOGS_COOKIES_FILE` (opcional): archivo de cookies (JSON o formato Netscape) para autenticarse al scrapear HTML.
- `DISCOGS_COOKIES_REFRESH_SECONDS` (opcional): intervalo en segundos para recargar automáticamente las cookies (default 900).
- `DISCOGS_HEADERS_FILE` (opcional): archivo JSON con headers extra a enviar en cada request del scraper HTML.
- `RECOMMENDER_MIN_RATING_PARES` (opcional): rating mínimo para considerar ítems en algoritmo de pares (default 4).
- `RECOMMENDER_MIN_INTERACCIONES_PARES` (opcional): mínimo de coincidencias entre usuarios para recomendar por pares (default 2).
- `RECOMMENDER_UMBRAL_CAMBIO_ESTRATEGIA` (opcional): número de valoraciones del usuario que determina el cambio de algoritmo de pares a perfiles (default 5).
- `RECOMMENDER_POPULARITY_CACHE_TTL` (opcional): TTL en segundos para la cache de popularidad (default 3600).

## Poblar la base

### Scripts disponibles

| Script | Uso principal | Qué ingesta | Cuándo usarlo |
|--------|---------------|-------------|----------------|
| `fill_db_recommendation_system.py` | Crawler completo con normalización canónica | Colección, wantlist, contribuciones + descubrimiento BFS/seeds | Correr sesiones largas, nutrir el dataset para recomendaciones |
| `run_scraper.py` o `python -m scraper.pipeline` | Scraper HTML con detección de masters | Releases populares, usuarios detectados (Have/Want), reviews, metadata extendida (labels, formatos, país) | Cuando el rate limit de la API resulta bloqueante o necesitas datos más ricos |

**Nota sobre normalización canónica**: Todos los scripts ahora detectan y utilizan `master_id` cuando está disponible, consolidando múltiples ediciones del mismo álbum bajo un único identificador canónico. El `release_id` original se preserva en `source_release_id` para trazabilidad.

#### Identificadores canónicos vs releases

- Cada ítem se persiste con un identificador canónico (`master_id` cuando existe; si no, se usa el `release_id`).
- Para mantener el rastro de la edición original, también se guarda `source_release_id` en la tabla de ítems. Esto permite volver al release específico para datos como formato o país.
- Todas las interacciones (colección, wantlist, contribuciones, etc.) se registran con el identificador canónico, de modo que múltiples ediciones del mismo álbum consoliden la señal.
- Scripts y pipelines que ingesten directamente deberían enviar siempre el `release_id` original; la capa de repositorio se encarga de traducirlo al master y almacenar ambos valores.

### Ingesta rápida desde seeds específicas

```bash
# Procesar solo seeds específicas sin descubrimiento de red
python fill_db_recommendation_system.py \
  --seed Xmipod \
  --extra-seeds usuario1,usuario2 \
  --disable-discovery \
  --api-pause 1
```

Esto procesa únicamente los usuarios provistos sin consultar followers/following (útil para poblar rápido perfiles específicos).

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

## Mantenimiento de la base de datos

### Auditoría de salud

Ejecuta una auditoría completa para verificar el estado de la base de datos:

```bash
python check_db_health.py
```

El script verifica:
- **Estadísticas generales**: Total de items, porcentaje válido/con problemas
- **Valores desconocidos**: Items con "Unknown Title" o "Unknown Artist"
- **Valores NULL/vacíos**: Títulos, artistas o años faltantes
- **Duplicados**: IDs duplicados y contenido potencialmente duplicado
- **Source Release IDs**: Integridad de la relación master/release
- **Calidad de datos**: Títulos cortos/largos, caracteres especiales
- **Distribución temporal**: Items por década
- **Ejemplos**: Muestra de items con problemas

### Recuperación de títulos faltantes

Si la auditoría detecta items con "Unknown Title" o "Unknown Artist", usa el script de recuperación:

```bash
# Con token de Discogs en el entorno
export DISCOGS_TOKEN="tu_token"
python fix_unknown_titles.py
```

El script:
1. Identifica items con títulos/artistas faltantes
2. Consulta la API de Discogs usando `source_release_id`
3. Actualiza la base de datos con la información recuperada
4. Respeta el rate limit (1.1s entre llamadas)

**Nota**: Algunos items pueden no recuperarse si el release fue eliminado de Discogs o tiene datos incompletos en la API.

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

El wrapper usa `refresh_cookies_persistent.py` internamente, que mantiene el navegador abierto para refresh automático.

#### Opción 2: Manual

```bash
python -m scraper.pipeline \
  --max-pages 5 \
  --release-limit 200 \
  --min-delay 2.5 \
  --delay-jitter 1.5 \
  --log-level INFO
```

El scraper ahora extrae automáticamente `master_id`, información de labels con catalog numbers, formatos detallados, país y fecha de lanzamiento.

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

Luego visitar `http://localhost:5000`. El login pide un `user_id` existente en la base; crea registros con `fill_db_recommendation_system.py` primero. La aplicación ahora usa el sistema híbrido de recomendaciones que selecciona automáticamente la mejor estrategia.

## Sistema de recomendaciones

El sistema implementa un enfoque **híbrido** que selecciona automáticamente la mejor estrategia según el perfil del usuario:

### Estrategias de recomendación

1. **Collaborative Filtering (Pares)**: Para usuarios con pocas valoraciones (≤5 por defecto), identifica discos que coaparecen frecuentemente con los favoritos del usuario en las colecciones de otros.

2. **Content-Based (Perfiles)**: Para usuarios con muchas valoraciones (>5), construye un perfil de preferencias ponderado por géneros, artistas, estilos y sellos, recomendando ítems similares.

3. **Popularity Fallback**: Cuando las estrategias anteriores no generan suficientes candidatos, recurre a los ítems más populares (por rating promedio e interacciones) que el usuario aún no conoce.

4. **Random**: Último recurso cuando ninguna otra estrategia produce resultados.

La estrategia se elige dinámicamente en cada llamada según la cantidad de valoraciones del usuario y los datos disponibles.

### Inicialización del recomendador

Antes del primer uso, inicializa la cache de popularidad:

```python
from sr_discogs import recomendar

# Construye/reconstruye la tabla de popularidad
recomendar.init_recomendador()
```

Esto se ejecuta automáticamente la primera vez y se regenera cada hora (configurable con `RECOMMENDER_POPULARITY_CACHE_TTL`).

### Uso desde la aplicación web

```bash
cd sr_discogs
python app.py
```

Visita `http://127.0.0.1:5000` en tu navegador. El sistema requiere usuarios e items en la base.

### Evaluación del sistema

Para evaluar el NDCG promedio sobre usuarios con suficiente historial:

```bash
cd sr_discogs
python recomendar.py
```

Este script evalúa sobre usuarios con ≥100 interacciones usando split 80/20 training/testing.

### Uso programático

```python
from sr_discogs import recomendar

# Crear usuario (si no existe)
recomendar.crear_usuario("mi_usuario")

# Registrar valoraciones (1-5, o 0 para "visto sin rating")
recomendar.insertar_interacciones(item_id=123, id_usuario="mi_usuario", rating=5)
recomendar.insertar_interacciones(item_id=456, id_usuario="mi_usuario", rating=4)

# Obtener recomendaciones (top 9) - selección automática de estrategia
recomendaciones = recomendar.recomendar("mi_usuario", N=9)
print(recomendaciones)  # Lista de item_ids canónicos recomendados

# Recomendaciones contextuales (relacionadas con un disco específico)
contextuales = recomendar.recomendar_contexto("mi_usuario", id_disco=789, N=3)

# Ver detalles de los ítems recomendados
datos = recomendar.datos_discos(recomendaciones)
for item in datos:
    print(f"{item['title']} - {item['artist']} ({item['year']})")
    print(f"  Géneros: {item['genre']}, Estilos: {item['style']}")
```

**Nota**: Todos los `item_id` devueltos son identificadores canónicos (master cuando existe). La función `_resolve_item_id()` normaliza automáticamente cualquier `release_id` al master correspondiente.

## Esquema de la base

```sql
-- Tabla users
user_id TEXT PRIMARY KEY
username TEXT
location TEXT
joined_date TEXT

-- Tabla items (releases normalizados a master)
item_id INTEGER PRIMARY KEY              -- Identificador canónico (master_id cuando existe, sino release_id)
source_release_id INTEGER                -- Release original desde el cual se obtuvo la info
title TEXT NOT NULL
artist TEXT
genre TEXT                               -- Lista separada por ", "
style TEXT                               -- Lista separada por ", "
country TEXT
released TEXT
year INTEGER
image_url TEXT
format_summary TEXT                      -- Resumen textual de formatos
label_summary TEXT                       -- Resumen textual de sellos
community_have INTEGER DEFAULT 0
community_want INTEGER DEFAULT 0
community_rating_average REAL DEFAULT 0
community_rating_count INTEGER DEFAULT 0

-- Tablas normalizadas para metadatos
labels (label_id, name, country, profile)
item_labels (item_id, label_id, catalog_number)
genres (genre_id, name)
item_genres (item_id, genre_id)
styles (style_id, name)
item_styles (item_id, style_id)
formats (format_id, name, quantity, description)
item_formats (item_id, format_id, notes)

-- Tabla interactions
interaction_id INTEGER PRIMARY KEY AUTOINCREMENT
user_id TEXT NOT NULL
item_id INTEGER NOT NULL                -- Siempre el identificador canónico
interaction_type TEXT                    -- "collection", "wantlist", "rating", "contribution"
rating REAL                              -- NULL = no calificado, 0 = visto sin rating, 1-5 = rating explícito
weight REAL DEFAULT 1.0
source TEXT
date_added TEXT
event_ts TEXT
review_text TEXT

-- Tabla top_items (cache de popularidad)
item_id INTEGER PRIMARY KEY
cantidad_interacciones INTEGER NOT NULL
promedio_rating REAL

-- Tabla recommender_metadata
key TEXT PRIMARY KEY
value TEXT
```

> **Nota sobre normalización canónica**: `item_id` representa siempre el identificador canónico (master cuando existe). El campo `source_release_id` preserva la edición concreta original, permitiendo volver al release específico para metadatos como formato, país o catalog number. Todas las interacciones se registran con el `item_id` canónico, consolidando la señal de múltiples ediciones del mismo álbum.

## Testing

El proyecto incluye tests unitarios para parsers, autenticación y sistema de recomendaciones:

```bash
# Todos los tests
python -m pytest tests/

# Tests específicos
python -m pytest tests/test_parsers.py -v
python -m pytest tests/test_recomendar.py -v

# Con coverage
python -m pytest tests/ --cov=scraper --cov=sr_discogs

# O con unittest
python -m unittest tests.test_parsers
python -m unittest tests.test_recomendar
```

Los fixtures HTML en `tests/fixtures/` se usan para validar parsers sin hacer requests reales.

## Migración y compatibilidad

Los scripts `fill_db_discogs_API.py`, `scrape_discogs_site.py` y `refresh_cookies.py` se movieron a `old/` tras la refactorización. El nuevo código es compatible hacia adelante pero puede requerir regenerar la base de datos para aprovechar todas las mejoras:

```bash
# Respaldar base existente
mkdir -p backups
cp data/discogs.db backups/discogs_$(date +%Y%m%d).db

# Opcional: recrear schema completo
sqlite3 data/discogs.db < create_db

# Re-ingestar datos con normalización canónica
python fill_db_recommendation_system.py --seed tu_usuario --max-users 10
```

Para más detalles sobre la migración, consulta `docs/MIGRATION_GUIDE.md` (si existe).

## Buenas prácticas

- Correr `pre-commit run --all-files` antes del primer commit.
- No commitear `cookies.json`, archivos `.db` ni `users.txt` (ignorados en `.gitignore`).
- Respetar los rate limits de Discogs (pausa mínima 1s entre requests de API, 2s+ para scraping HTML).
- Checkpoints automáticos: `fill_db_recommendation_system.py` guarda `.last_processed_user.txt` para retomar sin pérdida.
- Regenerar cache de popularidad periódicamente: `python -c "from sr_discogs import recomendar; recomendar.init_recomendador()"`.

## Diagnóstico y monitoreo

```bash
# Verificar estado del sistema
python check_scraper_status.py

# Monitoreo continuo (macOS/Linux)
./monitor_progress.sh
```

---

**Proyecto experimental**: Este repo es solo para aprendizaje y exploración académica. Respetá los términos de uso de Discogs y no cargués su infraestructura innecesariamente. La tasa de requests está intencionalmente limitada para ser respetuosa con los servidores.
