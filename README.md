# Discogs Recommender

Sistema experimental para recolectar datos públicos de la API de Discogs y generar recomendaciones de discos. El catálogo completo de Discogs supera los ~16 millones de lanzamientos y ~8 millones de usuarios; este proyecto se enfoca en explorar una fracción  de ese universo.

## Características

- Ingesta de colecciones, wantlists y contribuciones desde Discogs usando los scripts `fill_db_discogs_API.py` y `fill_db_recommendation_system.py`.
- Aplicación web en Flask (`sr_discogs/app.py`) para experimentar con recomendaciones aleatorias sobre la base.
- Esquema SQLite sencillo (`create_db`) con usuarios, ítems e interacciones.
- Hooks pre-commit configurados (`.pre-commit-config.yaml`) para mantener estilo (Black, isort, flake8, etc.).

## Estructura

```
Recomendar/
├── fill_db_discogs_API.py        # CLI simple para poblar colecciones de usuarios puntuales
├── fill_db_recommendation_system.py  # Ingesta completa con descubrimiento de usuarios y CLI avanzada
├── settings.py                   # Helpers para configuración (tokens, rutas, pausas)
├── create_db                     # Script SQL con el esquema SQLite
├── sr_discogs/
│   ├── app.py                    # Aplicación Flask
│   ├── recomendar.py             # Lógica de recomendaciones (por ahora aleatoria)
│   ├── metricas.py               # Implementación de DCG / NDCG
│   └── templates/                # Vistas HTML
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

Cuando la API no alcanza por límites de rate o porque queremos ratings de reviews públicas, podés usar el scraper HTML:

```bash
python scrape_discogs_site.py \
  --pages 5 \
  --limit 200 \
  --delay 2.5 \
  --log-level INFO
```

El scraper recorre resultados de búsqueda ordenados por `Have`, visita cada release y extrae:

- Metadatos del release (artistas, año, géneros, carátula).
- Usuarios vinculados en las secciones _Have_ / _Want_ (se almacenan como `interaction_type = collection` o `wantlist`).
- Reviews con rating (se guarda `interaction_type = rating` y el puntaje de 1-5).
- Información básica del perfil del usuario (ubicación, fecha de alta, tamaño de colección/wantlist cuando se muestra públicamente).

Parámetros útiles:

- `--no-profile`: salta la visita a páginas de usuario si solo necesitás las interacciones.
- `--database /ruta/otra.db`: escribe en una base alternativa.
- `--search-url`: permite arrancar desde cualquier consulta de Discogs, ej. `/search/?genre=house&type=release`.

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

## Próximos pasos

- Mejorar algoritmos de recomendación (filtrado colaborativo, contenido, etc.).
- Crear tests automáticos para los scripts de ingesta y web.
- Agregar dashboards simples para monitorear cobertura de datos.

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
