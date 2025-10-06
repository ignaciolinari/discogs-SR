# Discogs Recommender

Sistema experimental para recolectar datos públicos de la API de Discogs y generar recomendaciones básicas de discos.

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

### Colecciones puntuales

```bash
python fill_db_discogs_API.py --user Xmipod          # un usuario
python fill_db_discogs_API.py --users-file usuarios.txt --delay 2
```

El archivo `usuarios.txt` debe contener un username por línea.

### Modo completo para el sistema de recomendaciones

```bash
python fill_db_recommendation_system.py \
  --seed Xmipod \
  --max-users 5 \
  --api-pause 3
```

Parámetros útiles:

- `--token`: token alternativo (sobre-escribe la variable de entorno).
- `--force`: reprocesa usuarios aunque ya tengan datos.
- `--continue-from`: retoma desde un usuario guardado en `.last_processed_user.txt` (auto generado si se interrumpe el proceso).
- `--adaptive-pause`: activa pausas adaptativas según headers de rate limit.

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

- Corré `pre-commit run --all-files` antes del primer commit.
- No compartas `discogs.db` ni tu token; ambos están ignorados por git.
- Usa ramas feature + PRs para cambios grandes.

## Próximos pasos

- Mejorar algoritmos de recomendación (filtrado colaborativo, contenido, etc.).
- Crear tests automáticos para los scripts de ingesta y web.
- Agregar dashboards simples para monitorear cobertura de datos.
