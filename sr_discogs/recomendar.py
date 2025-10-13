# version: 2.1 -- recomendaciones híbridas para discos

import random
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

try:
    from settings import get_database_path, get_recommender_config
except ModuleNotFoundError:  # pragma: no cover - fallback para ejecución directa
    base_dir = Path(__file__).resolve().parents[1]
    if str(base_dir) not in sys.path:
        sys.path.append(str(base_dir))
    from settings import get_database_path, get_recommender_config

try:
    from sr_discogs import metricas
except ModuleNotFoundError:  # pragma: no cover - fallback para ejecución directa
    import metricas

DATABASE_FILE = str(get_database_path())
RECOMMENDER_CONFIG = get_recommender_config()

# Configuración del sistema de recomendaciones híbrido
MIN_RATING_PARES = RECOMMENDER_CONFIG["min_rating_pares"]
MIN_INTERACCIONES_PARES = RECOMMENDER_CONFIG["min_interacciones_pares"]
MIN_RATING_PERFIL = RECOMMENDER_CONFIG["min_rating_perfil"]
MIN_APARICIONES_PERFIL = RECOMMENDER_CONFIG["min_apariciones_perfil"]

# UMBRAL_CAMBIO_ESTRATEGIA: Determina cuándo cambiar de collaborative filtering
# (algoritmo de pares) a content-based (perfiles de usuario).
# - Con pocos ítems valorados (≤ umbral): usa pares porque hay más señal relativa
# - Con muchos ítems (> umbral): usa perfiles porque captura mejor las preferencias generales
# Default: 5. Este valor empírico equilibra entre:
#   * Cold start: usuarios con pocas valoraciones se benefician de pares
#   * Diversidad: usuarios con muchas valoraciones obtienen recomendaciones más variadas vía perfiles
UMBRAL_CAMBIO_ESTRATEGIA = RECOMMENDER_CONFIG["umbral_cambio_estrategia"]

POPULARITY_CACHE_TTL_SECONDS = RECOMMENDER_CONFIG["popularity_cache_ttl_seconds"]

# Nombres de tablas del sistema (centralizados para facilitar mantenimiento)
TABLE_USERS = "users"
TABLE_ITEMS = "items"
TABLE_INTERACTIONS = "interactions"
TOP_ITEMS_TABLE = "top_items"
METADATA_TABLE = "recommender_metadata"

# Claves de metadatos
TOP_ITEMS_REFRESH_KEY = "top_items_last_refresh"


def normalize_rating(value):
    """Normaliza ratings a escala entera 0-5.

    Semántica de valores:
    - None → 0: representa "visto pero sin calificación explícita"
    - 0 → 0: representa "sin rating" o "visto sin valoración"
    - 1-5 → 1-5: calificaciones explícitas del usuario

    IMPORTANTE: En las consultas SQL se usa NULLIF(rating, 0) para excluir
    ratings implícitos de los promedios, considerando solo calificaciones explícitas.

    Args:
        value: Valor a normalizar (puede ser None, int, float, o string)

    Returns:
        int: Rating normalizado en escala 0-5
    """

    if value is None:
        return 0

    try:
        rating = int(float(value))
    except (TypeError, ValueError):
        return 0

    if rating <= 0:
        return 0

    return min(rating, 5)


def sql_execute(query: str, params: Sequence | None = None):
    """Ejecuta operaciones de escritura en la base de datos."""

    with sqlite3.connect(DATABASE_FILE) as con:
        cur = con.cursor()
        if params:
            res = cur.execute(query, params)
        else:
            res = cur.execute(query)
        con.commit()
        return res


def sql_select(query: str, params: Sequence | None = None) -> List[sqlite3.Row]:
    """Ejecuta consultas y devuelve filas como diccionarios."""

    with sqlite3.connect(DATABASE_FILE) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        if params:
            res = cur.execute(query, params)
        else:
            res = cur.execute(query)
        return res.fetchall()


@lru_cache(maxsize=10_000)
def _resolve_item_id_cached(raw_id: str) -> int | None:
    try:
        candidate = int(raw_id)
    except (TypeError, ValueError):
        return None

    rows = sql_select(
        "SELECT item_id FROM items WHERE item_id = ? LIMIT 1;", [candidate]
    )
    if rows:
        return rows[0]["item_id"]

    rows = sql_select(
        "SELECT item_id FROM items WHERE source_release_id = ? LIMIT 1;",
        [candidate],
    )
    if rows:
        return rows[0]["item_id"]

    return None


def _resolve_item_id(raw_id) -> int | None:
    if raw_id is None:
        return None
    return _resolve_item_id_cached(str(raw_id))


def _resolve_item_ids(ids: Sequence | None) -> List[int]:
    if not ids:
        return []

    resolved: List[int] = []
    seen = set()
    for raw_id in ids:
        canonical_id = _resolve_item_id(raw_id)
        if canonical_id is None or canonical_id in seen:
            continue
        resolved.append(canonical_id)
        seen.add(canonical_id)
    return resolved


def _split_feature_values(value) -> List[str]:
    """Normaliza cadenas con listas de géneros/estilos/artistas.

    El formato estándar en la BD es ", " (coma-espacio), pero esta función
    acepta también "|" para compatibilidad con datos históricos o externos.

    Args:
        value: String con valores separados por "," o "|", o None

    Returns:
        Lista de strings sin espacios adicionales

    Examples:
        >>> _split_feature_values("Electronic, House, Techno")
        ['Electronic', 'House', 'Techno']
        >>> _split_feature_values("Rock|Pop|Jazz")
        ['Rock', 'Pop', 'Jazz']
    """

    if not value:
        return []

    tokens = []
    for raw in str(value).replace("|", ",").split(","):
        token = raw.strip()
        if token:
            tokens.append(token)
    return tokens


def crear_usuario(id_usuario: str):
    query = (
        f"INSERT INTO {TABLE_USERS}(user_id, username) VALUES (?, ?) "
        "ON CONFLICT DO NOTHING;"
    )
    sql_execute(query, [id_usuario, id_usuario])


def usuario_existe(id_usuario: str) -> bool:
    if not id_usuario:
        return False
    query = f"SELECT 1 FROM {TABLE_USERS} WHERE user_id = ?;"
    return bool(sql_select(query, [id_usuario]))


def insertar_interacciones(id_disco: int | str, id_usuario: str, rating):
    if not id_usuario:
        return
    canonical_id = _resolve_item_id(id_disco)
    if canonical_id is None:
        return
    rating_value = normalize_rating(rating)

    query_check = (
        "SELECT interaction_id FROM interactions WHERE item_id = ? AND user_id = ?;"
    )
    existing = sql_select(query_check, [canonical_id, id_usuario])

    if existing:
        query = "UPDATE interactions SET rating = ? WHERE item_id = ? AND user_id = ?;"
        sql_execute(query, [rating_value, canonical_id, id_usuario])
    else:
        interaction_type = "rating" if rating_value and rating_value > 0 else "view"
        query = (
            "INSERT INTO interactions(item_id, user_id, interaction_type, rating, "
            "date_added) VALUES (?, ?, ?, ?, date('now'));"
        )
        sql_execute(query, [canonical_id, id_usuario, interaction_type, rating_value])


def reset_usuario(id_usuario: str):
    query = "DELETE FROM interactions WHERE user_id = ?;"
    sql_execute(query, [id_usuario])


def obtener_disco(id_disco: int | str):
    canonical_id = _resolve_item_id(id_disco)
    if canonical_id is None:
        return None
    query = f"SELECT * FROM {TABLE_ITEMS} WHERE item_id = ?;"
    filas = sql_select(query, [canonical_id])
    return filas[0] if filas else None


def items_valorados(id_usuario: str) -> List[int]:
    if not id_usuario:
        return []
    query = "SELECT item_id FROM interactions WHERE user_id = ? AND rating > 0;"
    rows = sql_select(query, [id_usuario])
    return [row["item_id"] for row in rows]


def items_vistos(id_usuario: str) -> List[int]:
    if not id_usuario:
        return []
    query = "SELECT item_id FROM interactions WHERE user_id = ? AND rating = 0;"
    rows = sql_select(query, [id_usuario])
    return [row["item_id"] for row in rows]


def items_desconocidos(id_usuario: str) -> List[int]:
    if not id_usuario:
        return []
    query = (
        "SELECT item_id FROM items WHERE item_id NOT IN ("
        "SELECT item_id FROM interactions WHERE user_id = ?)"
    )
    rows = sql_select(query, [id_usuario])
    return [row["item_id"] for row in rows]


def datos_discos(id_discos: Sequence[int | str]) -> List[sqlite3.Row]:
    if not id_discos:
        return []
    canonical_ids = _resolve_item_ids(id_discos)
    if not canonical_ids:
        return []
    placeholders = ",".join(["?"] * len(canonical_ids))
    query = f"SELECT DISTINCT * FROM items WHERE item_id IN ({placeholders});"
    rows = sql_select(query, canonical_ids)
    rows_by_id = {row["item_id"]: row for row in rows}
    return [rows_by_id[item_id] for item_id in canonical_ids if item_id in rows_by_id]


def _obtener_ratings_usuario(
    id_usuario: str, id_discos: Sequence[int | str]
) -> Dict[int, int]:
    """Devuelve un diccionario item_id → rating normalizado para un usuario."""

    if not id_usuario or not id_discos:
        return {}
    placeholders = ",".join(["?"] * len(id_discos))
    query = (
        f"SELECT item_id, rating FROM interactions "
        f"WHERE user_id = ? AND item_id IN ({placeholders});"
    )
    rows = sql_select(query, [id_usuario, *id_discos])
    return {row["item_id"]: normalize_rating(row["rating"]) for row in rows}


def init_recomendador():
    """Reconstruye la cache de popularidad usada por el fallback Top-N."""

    sql_execute(f"DROP TABLE IF EXISTS {TOP_ITEMS_TABLE};")
    sql_execute(
        f"CREATE TABLE IF NOT EXISTS {METADATA_TABLE} (key TEXT PRIMARY KEY, value TEXT);"
    )
    sql_execute(
        f"""
        CREATE TABLE {TOP_ITEMS_TABLE} AS
        SELECT
            item_id,
            COUNT(*) AS cantidad_interacciones,
            AVG(NULLIF(rating, 0)) AS promedio_rating
        FROM interactions
        WHERE rating IS NOT NULL
        GROUP BY item_id;
        """
    )
    sql_execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TOP_ITEMS_TABLE}_rank ON {TOP_ITEMS_TABLE} (promedio_rating DESC, cantidad_interacciones DESC);"
    )
    _set_metadata_value(TOP_ITEMS_REFRESH_KEY, datetime.now(timezone.utc).isoformat())


def _get_metadata_value(key: str) -> str | None:
    try:
        rows = sql_select(
            f"SELECT value FROM {METADATA_TABLE} WHERE key = ? LIMIT 1;", [key]
        )
    except sqlite3.OperationalError:
        return None
    if not rows:
        return None
    return rows[0]["value"]


def _set_metadata_value(key: str, value: str) -> None:
    sql_execute(
        f"CREATE TABLE IF NOT EXISTS {METADATA_TABLE} (key TEXT PRIMARY KEY, value TEXT);"
    )
    sql_execute(
        f"INSERT INTO {METADATA_TABLE}(key, value) VALUES (?, ?) "
        f"ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
        [key, value],
    )


def _asegurar_cache_popularidad():
    """Reconstruye la tabla de popularidad si no existe o está expirada."""

    try:
        sql_select(f"SELECT 1 FROM {TOP_ITEMS_TABLE} LIMIT 1;")
    except sqlite3.OperationalError:
        init_recomendador()
        return

    if POPULARITY_CACHE_TTL_SECONDS <= 0:
        return

    last_refresh_str = _get_metadata_value(TOP_ITEMS_REFRESH_KEY)
    if not last_refresh_str:
        init_recomendador()
        return

    try:
        last_refresh = datetime.fromisoformat(last_refresh_str)
    except ValueError:
        init_recomendador()
        return

    if last_refresh.tzinfo is None:
        last_refresh = last_refresh.replace(tzinfo=timezone.utc)

    elapsed = (datetime.now(timezone.utc) - last_refresh).total_seconds()
    if elapsed >= POPULARITY_CACHE_TTL_SECONDS:
        init_recomendador()


def recomendar_azar(
    id_usuario: str,
    discos_relevantes: Sequence[int],
    discos_desconocidos: Sequence[int],
    N: int = 9,
) -> List[int]:
    """Selecciona discos al azar como último recurso."""

    if N <= 0 or not discos_desconocidos:
        return []
    N = min(N, len(discos_desconocidos))
    return random.sample(list(discos_desconocidos), N)


def recomendar_top_n(
    id_usuario: str,
    discos_relevantes: Sequence[int],
    discos_desconocidos: Sequence[int],
    N: int = 9,
) -> List[int]:
    """Recupera los discos más populares aún no explorados por la persona usuaria."""

    if not discos_desconocidos:
        return []

    _asegurar_cache_popularidad()

    base_query = f"SELECT item_id FROM {TOP_ITEMS_TABLE}"
    condiciones: List[str] = []
    params: List[str | int] = []

    if discos_relevantes:
        placeholders = ",".join(["?"] * len(discos_relevantes))
        condiciones.append(f"item_id NOT IN ({placeholders})")
        params.extend(discos_relevantes)

    placeholders_desconocidos = ",".join(["?"] * len(discos_desconocidos))
    condiciones.append(f"item_id IN ({placeholders_desconocidos})")
    params.extend(discos_desconocidos)

    if condiciones:
        base_query += " WHERE " + " AND ".join(condiciones)

    base_query += " ORDER BY promedio_rating DESC, cantidad_interacciones DESC LIMIT ?;"
    params.append(N)

    rows = sql_select(base_query, params)
    recomendacion = [row["item_id"] for row in rows]

    if len(recomendacion) < N:
        faltantes = N - len(recomendacion)
        candidatos = [item for item in discos_desconocidos if item not in recomendacion]
        if candidatos:
            recomendacion.extend(
                random.sample(candidatos, min(faltantes, len(candidatos)))
            )

    return recomendacion[:N]


def recomendar_pares(
    id_usuario: str,
    discos_relevantes: Sequence[int],
    discos_desconocidos: Sequence[int],
    N: int = 9,
) -> List[int]:
    """Prioriza discos que coaparecen con los favoritos de la persona usuaria."""

    if not discos_relevantes or not discos_desconocidos:
        return []

    placeholders_relevantes = ",".join(["?"] * len(discos_relevantes))
    placeholders_desconocidos = ",".join(["?"] * len(discos_desconocidos))

    query = f"""
        SELECT
            i2.item_id AS item_id,
            COUNT(*) AS coincidencias,
            AVG(NULLIF(i2.rating, 0)) AS promedio_rating
        FROM interactions AS i1
        JOIN interactions AS i2
            ON i1.user_id = i2.user_id
        WHERE i1.item_id IN ({placeholders_relevantes})
          AND i2.item_id IN ({placeholders_desconocidos})
          AND i2.item_id != i1.item_id
          AND i1.rating >= ?
        GROUP BY i2.item_id
        HAVING coincidencias >= ?
        ORDER BY coincidencias DESC, promedio_rating DESC
        LIMIT ?;
    """

    params: List[str | int] = [*discos_relevantes, *discos_desconocidos]
    params.extend([MIN_RATING_PARES, MIN_INTERACCIONES_PARES, N])

    rows = sql_select(query, params)
    return [row["item_id"] for row in rows]


def _construir_perfil(
    discos_info: Iterable[sqlite3.Row],
    ratings: Dict[int, int],
    claves_posibles: Sequence[str],
) -> Counter:
    """Construye contadores de preferencia filtrados por ratings mínimos."""

    contador: Counter = Counter()
    for row in discos_info:
        item_id = row["item_id"]
        rating = ratings.get(item_id)
        if rating is None or rating < MIN_RATING_PERFIL:
            continue

        for key in claves_posibles:
            if key in row.keys():
                valores = _split_feature_values(row[key])
                if valores:
                    contador.update(valores)
                break

    return Counter({k: v for k, v in contador.items() if v >= MIN_APARICIONES_PERFIL})


def recomendar_perfiles(
    id_usuario: str,
    discos_relevantes: Sequence[int],
    discos_desconocidos: Sequence[int],
    N: int = 9,
) -> List[int]:
    """Pondera afinidades por género/artista basadas en calificaciones altas."""

    if not discos_desconocidos:
        return []

    discos_relevantes_info = datos_discos(discos_relevantes)
    ratings = _obtener_ratings_usuario(id_usuario, discos_relevantes)

    if not discos_relevantes_info or not ratings:
        return []

    perfiles = {
        "generos": _construir_perfil(
            discos_relevantes_info, ratings, ["genre", "genres"]
        ),
        "estilos": _construir_perfil(
            discos_relevantes_info, ratings, ["style", "styles"]
        ),
        "artistas": _construir_perfil(
            discos_relevantes_info, ratings, ["artist", "artists", "artist_name"]
        ),
        "sellos": _construir_perfil(
            discos_relevantes_info, ratings, ["label", "labels"]
        ),
    }

    if not any(perfiles.values()):
        return []

    totales = {
        clave: max(sum(contador.values()), 1) for clave, contador in perfiles.items()
    }

    discos_desconocidos_info = datos_discos(discos_desconocidos)
    puntuaciones: List[tuple[int, float]] = []

    for row in discos_desconocidos_info:
        item_id = row["item_id"]
        puntaje = 0.0

        for clave, llaves in (
            ("generos", ["genre", "genres"]),
            ("estilos", ["style", "styles"]),
            ("artistas", ["artist", "artists", "artist_name"]),
            ("sellos", ["label", "labels"]),
        ):
            contador = perfiles[clave]
            if not contador:
                continue
            total = totales[clave]
            for key in llaves:
                if key in row.keys():
                    valores = _split_feature_values(row[key])
                    for valor in valores:
                        puntaje += contador.get(valor, 0) / total
                    break

        if puntaje > 0:
            puntuaciones.append((item_id, puntaje))

    puntuaciones.sort(key=lambda item: item[1], reverse=True)
    return [item_id for item_id, _ in puntuaciones[:N]]


def recomendar(
    id_usuario: str,
    discos_relevantes: Sequence[int | str] | None = None,
    discos_desconocidos: Sequence[int | str] | None = None,
    N: int = 9,
) -> List[int]:
    """Coordina la selección del mejor algoritmo según la señal disponible."""

    if not id_usuario:
        return []

    if discos_relevantes is None:
        discos_relevantes_seq: Sequence[int | str] = items_valorados(id_usuario)
    else:
        discos_relevantes_seq = discos_relevantes
    discos_relevantes_ids = _resolve_item_ids(discos_relevantes_seq)

    if discos_desconocidos is None:
        discos_desconocidos_seq: Sequence[int | str] = items_desconocidos(id_usuario)
    else:
        discos_desconocidos_seq = discos_desconocidos
    discos_desconocidos_ids = _resolve_item_ids(discos_desconocidos_seq)

    if not discos_desconocidos_ids:
        return []

    if len(discos_relevantes_ids) == 0:
        recomendacion = recomendar_top_n(
            id_usuario, discos_relevantes_ids, discos_desconocidos_ids, N
        )
        if recomendacion:
            return recomendacion
    elif len(discos_relevantes_ids) <= UMBRAL_CAMBIO_ESTRATEGIA:
        recomendacion = recomendar_pares(
            id_usuario, discos_relevantes_ids, discos_desconocidos_ids, N
        )
        if recomendacion:
            return recomendacion
    else:
        recomendacion = recomendar_perfiles(
            id_usuario, discos_relevantes_ids, discos_desconocidos_ids, N
        )
        if recomendacion:
            return recomendacion

    recomendacion = recomendar_top_n(
        id_usuario, discos_relevantes_ids, discos_desconocidos_ids, N
    )
    if recomendacion:
        return recomendacion

    return recomendar_azar(
        id_usuario, discos_relevantes_ids, discos_desconocidos_ids, N
    )


def recomendar_contexto(
    id_usuario: str,
    id_disco: int | str,
    discos_relevantes: Sequence[int | str] | None = None,
    discos_desconocidos: Sequence[int | str] | None = None,
    N: int = 3,
) -> List[int]:
    """Genera recomendaciones relacionadas contextualizando en torno a un disco dado."""

    if not id_usuario:
        return []

    contexto_id = _resolve_item_id(id_disco)
    if contexto_id is None:
        return []

    vistos = set(_resolve_item_ids(items_vistos(id_usuario)))

    if discos_relevantes is None:
        discos_relevantes_seq: Sequence[int | str] = items_valorados(id_usuario)
    else:
        discos_relevantes_seq = discos_relevantes
    discos_relevantes_ids = _resolve_item_ids(discos_relevantes_seq)

    if discos_desconocidos is None:
        discos_desconocidos_seq: Sequence[int | str] = items_desconocidos(id_usuario)
    else:
        discos_desconocidos_seq = discos_desconocidos
    discos_desconocidos_ids = _resolve_item_ids(discos_desconocidos_seq)

    candidatos = [
        item_id
        for item_id in discos_desconocidos_ids
        if item_id != contexto_id and item_id not in vistos
    ]

    if not candidatos:
        return []

    recomendacion = recomendar_pares(id_usuario, discos_relevantes_ids, candidatos, N)
    if not recomendacion:
        recomendacion = recomendar_perfiles(
            id_usuario, discos_relevantes_ids, candidatos, N
        )
    if not recomendacion:
        recomendacion = recomendar_top_n(
            id_usuario, discos_relevantes_ids, candidatos, N
        )
    if not recomendacion:
        recomendacion = recomendar_azar(
            id_usuario, discos_relevantes_ids, candidatos, N
        )

    return recomendacion[:N]


def test(id_usuario: str) -> float:
    """Evalúa el pipeline con un split simple y la métrica NDCG."""

    discos_relevantes = items_valorados(id_usuario)
    discos_desconocidos = items_vistos(id_usuario) + items_desconocidos(id_usuario)

    if len(discos_relevantes) < 2:
        return 0.0

    random.shuffle(discos_relevantes)

    corte = int(len(discos_relevantes) * 0.8)
    discos_relevantes_training = discos_relevantes[:corte]
    discos_relevantes_testing = discos_relevantes[corte:] + discos_desconocidos

    recomendacion = recomendar(
        id_usuario,
        discos_relevantes_training,
        discos_relevantes_testing,
        20,
    )

    ratings = _obtener_ratings_usuario(id_usuario, recomendacion)
    relevance_scores = [ratings.get(item_id, 0) for item_id in recomendacion]
    return metricas.normalized_discounted_cumulative_gain(relevance_scores)


if __name__ == "__main__":
    init_recomendador()

    id_usuarios = sql_select(
        "SELECT user_id FROM users WHERE ("
        "SELECT count(*) FROM interactions WHERE user_id = users.user_id"
        ") >= 100 LIMIT 50;"
    )
    id_usuarios = [row["user_id"] for row in id_usuarios]

    scores = []
    for id_usuario in id_usuarios:
        score = test(id_usuario)
        scores.append(score)
        print(f"{id_usuario} >> {score:.6f}")

    if scores:
        print(f"NDCG: {sum(scores) / len(scores):.6f}")
    else:
        print("NDCG: 0.000000")
