import logging
import os
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from ingestion.db import IngestionRepository, RepositoryConfig
from ingestion.http_client import RateLimitedDiscogsClient

from settings import (
    get_api_pause,
    get_database_path,
    get_discogs_token,
    get_seed_username,
)

BASE_URL = "https://api.discogs.com"
DISCOGS_TOKEN = None
DEFAULT_SEED_USERNAME = None
DATABASE_PATH = None
_repo_config: RepositoryConfig | None = None

logger = logging.getLogger(__name__)

DISCOVERY_MAX_DEPTH = 3
MAX_LISTS_PER_USER = 5
POPULAR_USERS = [
    "rodneyfool",
    "stuporfly",
    "machine_funk",
    "boogiedowns",
    "rasputin",
    "discogscollector",
    "VinylVixen",
    "JazzMaster",
    "RockEnthusiast",
]
VISITED_USERS_FILE = Path(".discovered_users.log")
DISCOVERY_PAUSE = 1.0
_discogs_client: RateLimitedDiscogsClient | None = None


def init_runtime(token=None):
    global DISCOGS_TOKEN, DEFAULT_SEED_USERNAME, DATABASE_PATH, _repo_config, _discogs_client

    if token:
        DISCOGS_TOKEN = token

    if DISCOGS_TOKEN is None:
        DISCOGS_TOKEN = get_discogs_token()
    if DEFAULT_SEED_USERNAME is None:
        DEFAULT_SEED_USERNAME = get_seed_username()
    if DATABASE_PATH is None:
        DATABASE_PATH = get_database_path()

    if _repo_config is None:
        _repo_config = RepositoryConfig(path=Path(DATABASE_PATH))

    if _discogs_client is None:
        _discogs_client = RateLimitedDiscogsClient(token=DISCOGS_TOKEN)
    else:
        _discogs_client.token = DISCOGS_TOKEN

    _discogs_client.update_config(
        pause=API_PAUSE,
        adaptive_pause=API_ADAPTIVE_PAUSE,
        max_rate_limit_retries=MAX_RATE_LIMIT_RETRIES,
        rate_limit_cooldown=RATE_LIMIT_COOLDOWN,
    )


def _get_repo_config() -> RepositoryConfig:
    if _repo_config is None:
        init_runtime()
    assert _repo_config is not None
    return _repo_config


def _mock_api_response(status_code=200, json_data=None):
    class MockResponse:
        def __init__(self, code, payload):
            self.status_code = code
            self._payload = payload or {}
            self.headers = {}

        def json(self):
            return self._payload

        @property
        def text(self):
            return "" if self._payload is None else "x"

    return MockResponse(status_code, json_data)


def _test_get_user_neighbors():
    original_api_call = globals()["api_call"]

    def fake_api_call(url, params):
        if url.endswith("/following"):
            return _mock_api_response(
                json_data={"following": [{"username": "alice"}, {"username": "bob"}]}
            )
        if url.endswith("/followers"):
            return _mock_api_response(
                json_data={"followers": [{"username": "carol"}, {"username": "dave"}]}
            )
        if "/lists" in url:
            return _mock_api_response(
                json_data={
                    "lists": [
                        {"resource_url": "mock://list/1", "name": "List 1"},
                    ]
                }
            )
        if url.startswith("mock://list/1"):
            return _mock_api_response(
                json_data={
                    "contributors": [
                        {"username": "eve"},
                        {"username": "frank"},
                    ]
                }
            )
        return _mock_api_response()

    globals()["api_call"] = fake_api_call

    neighbors = get_user_neighbors("seed", remaining=4)
    assert neighbors == ["alice", "bob", "carol", "dave"], neighbors

    neighbors = get_user_neighbors("seed", remaining=6)
    assert neighbors == ["alice", "bob", "carol", "dave", "eve", "frank"], neighbors

    globals()["api_call"] = original_api_call


def _test_discover_users():
    original_api_call = globals()["api_call"]
    original_load = globals()["load_visited_users"]
    original_persist = globals()["persist_visited_users"]

    def fake_api_call(url, params):
        if url.endswith("/following"):
            return _mock_api_response(
                json_data={"following": [{"username": "u1"}, {"username": "u2"}]}
            )
        if url.endswith("/followers"):
            return _mock_api_response(json_data={"followers": [{"username": "u3"}]})
        return _mock_api_response(json_data={"lists": []})

    def fake_load():
        return set()

    captured = {}

    def fake_persist(visited):
        captured["visited"] = set(visited)

    globals()["api_call"] = fake_api_call
    globals()["load_visited_users"] = fake_load
    globals()["persist_visited_users"] = fake_persist

    users = discover_users("seed", max_users=4, depth=1)
    assert users[0] == "seed"
    assert set(users[1:]) <= {"u1", "u2", "u3"}
    assert "seed" in captured.get("visited", set())

    globals()["api_call"] = original_api_call
    globals()["load_visited_users"] = original_load
    globals()["persist_visited_users"] = original_persist


def run_tests():
    init_runtime(token="test-token")
    print("Ejecutando tests de discovery...")
    _test_get_user_neighbors()
    print("- get_user_neighbors OK")
    _test_discover_users()
    print("- discover_users OK")
    print("Todos los tests pasaron correctamente.")


def load_visited_users():
    if not VISITED_USERS_FILE.exists():
        return set()
    try:
        with VISITED_USERS_FILE.open("r", encoding="utf-8") as fh:
            return {line.strip().lower() for line in fh if line.strip()}
    except OSError:
        return set()


def persist_visited_users(visited):
    try:
        with VISITED_USERS_FILE.open("w", encoding="utf-8") as fh:
            for username in sorted(visited):
                fh.write(f"{username}\n")
    except OSError as exc:
        print(f"No se pudo guardar el cache de usuarios visitados: {exc}")


# Variables globales para control de skipping y rate limiting
FORCE_UPDATE = False
MIN_ITEMS_THRESHOLD = 50
API_PAUSE = get_api_pause()  # Pausa entre llamadas API en segundos
MAX_RATE_LIMIT_RETRIES = 5  # Número de intentos si se alcanza el límite de tasa
RATE_LIMIT_COOLDOWN = 60  # Tiempo de espera en segundos cuando se alcanza el límite
API_ADAPTIVE_PAUSE = False  # Pausas adaptativas basadas en la carga del servidor

# Compat wrappers para el nuevo cliente compartido


def _ensure_discogs_client() -> RateLimitedDiscogsClient:
    """Garantiza que exista una instancia del cliente rate-limited."""

    global _discogs_client

    if _discogs_client is None:
        init_runtime()

    if _discogs_client is None:
        raise RuntimeError("Cliente de Discogs no inicializado")

    return _discogs_client


def api_call(url, params=None):
    """Realiza una llamada GET usando el cliente con rate limiting compartido."""

    client = _ensure_discogs_client()
    prepared_params = dict(params or {})
    return client.get(url, params=prepared_params)


def _current_api_stats() -> tuple[int, int]:
    """Devuelve (total_calls, rate_limit_hits) del cliente actual."""

    if _discogs_client is None:
        return (0, 0)
    return (_discogs_client.total_calls, _discogs_client.rate_limit_hits)


def get_user_info(username):
    """Obtiene información detallada del usuario desde la API de Discogs"""
    url = f"{BASE_URL}/users/{username}"
    params = {"token": DISCOGS_TOKEN}

    try:
        # Usar la función api_call con manejo de límites de tasa
        r = api_call(url, params)

        if r and r.status_code == 200:
            user_data = r.json()
            return {
                "user_id": user_data.get("id", username),
                "username": username,
                "location": user_data.get("location", ""),
                "joined_date": user_data.get(
                    "registered", datetime.now().strftime("%Y-%m-%d")
                ),
            }
        elif r:
            # Si hay un error específico del usuario, registrarlo
            if r.status_code == 404:
                print(f"Usuario {username} no encontrado en Discogs")
                return None  # Retornar None explícitamente para usuario no encontrado
            else:
                try:
                    error_msg = (
                        r.json().get("message", "Error desconocido")
                        if r.text
                        else "Sin respuesta"
                    )
                    print(
                        f"Error obteniendo datos de usuario {username}: {error_msg} (código {r.status_code})"
                    )
                except ValueError:
                    print(
                        f"Error obteniendo datos de usuario {username}: código {r.status_code}"
                    )
        else:
            print(f"No se pudo obtener información del usuario {username}")

    except Exception as e:
        print(f"Error obteniendo información del usuario {username}: {e}")

    # Si falla pero no es un 404, devolvemos datos mínimos
    return {
        "user_id": username,
        "username": username,
        "location": "",
        "joined_date": datetime.now().strftime("%Y-%m-%d"),
    }


def user_exists(repo: IngestionRepository, user_id):
    """Verifica si un usuario ya existe en la base de datos"""

    return repo.user_exists(user_id)


def item_exists(repo: IngestionRepository, item_id):
    """Verifica si un ítem ya existe en la base de datos"""

    return repo.item_exists(item_id)


def interaction_exists(repo: IngestionRepository, user_id, item_id, interaction_type):
    """Verifica si una interacción específica ya existe en la base de datos"""

    return repo.interaction_exists(user_id, item_id, interaction_type)


def insert_user(repo: IngestionRepository, user_id, username, location, joined_date):
    repo.upsert_user(
        user_id=user_id,
        username=username,
        location=location,
        joined_date=joined_date,
    )


def insert_item(
    repo: IngestionRepository, item_id, title, artist, year, genre, style, image_url
):
    repo.upsert_item(
        item_id=item_id,
        title=title,
        artist=artist,
        year=year,
        genres=genre,
        styles=style,
        image_url=image_url,
    )


def insert_interaction(
    repo: IngestionRepository, user_id, item_id, interaction_type, rating, date_added
):
    repo.record_interaction(
        user_id=user_id,
        item_id=item_id,
        interaction_type=interaction_type,
        rating=rating,
        date_added=date_added,
    )


def get_collection(repo: IngestionRepository, username):
    """Obtiene la colección de discos de un usuario"""
    page = 1
    processed_count = 0
    skipped_count = 0
    print(f"\nProcesando colección del usuario: {username}")

    try:
        # Primero obtenemos y guardamos la información del usuario
        user_info = get_user_info(username)
        if user_info is None:
            print(
                f"No se pudo obtener información del usuario {username}. Saltando colección."
            )
            return

        user_id = user_info["user_id"]
        insert_user(
            repo,
            user_info["user_id"],
            user_info["username"],
            user_info["location"],
            user_info["joined_date"],
        )

        while True:
            url = f"{BASE_URL}/users/{username}/collection/folders/0/releases"
            params = {"token": DISCOGS_TOKEN, "page": page, "per_page": 50}

            try:
                # Usar función de API con manejo de límites de tasa
                r = api_call(url, params)

                if not r or r.status_code != 200:
                    if r:
                        try:
                            if r.text:
                                error_msg = r.json().get("message", "Error desconocido")
                                print("Error: {}".format(error_msg))
                            else:
                                print("Error: Sin respuesta del servidor")
                        except Exception as json_err:
                            print(
                                "Error: Código {}. No se pudo decodificar respuesta: {}".format(
                                    r.status_code, json_err
                                )
                            )
                    else:
                        print("Error: No se pudo completar la solicitud a la API")
                    break

                data = r.json()
                releases = data.get("releases", [])
                if not releases:
                    break

                page_processed = 0
                page_skipped = 0

                for rls in releases:
                    try:
                        release_id = rls["id"]

                        # Verificamos si esta interacción ya existe para evitar duplicados
                        if interaction_exists(repo, user_id, release_id, "collection"):
                            page_skipped += 1
                            skipped_count += 1
                            continue

                        # Si llegamos aquí, es porque necesitamos procesar este disco
                        title = rls["basic_information"]["title"]
                        artist = ", ".join(
                            [a["name"] for a in rls["basic_information"]["artists"]]
                        )
                        year = rls["basic_information"].get("year")
                        genres = ", ".join(rls["basic_information"].get("genres", []))
                        styles = ", ".join(rls["basic_information"].get("styles", []))

                        # Para el sistema de recomendación, usamos la fecha real cuando está disponible
                        date_added = rls.get(
                            "date_added", datetime.now().strftime("%Y-%m-%d")
                        )

                        # Intentamos obtener la valoración real del usuario (si está disponible en la API)
                        rating = rls.get("rating", None)

                        # URL de la imagen (puede no existir)
                        image_url = rls["basic_information"].get("cover_image")

                        # Guardar en DB solo con URL cuando el ítem no existe
                        if not item_exists(repo, release_id):
                            insert_item(
                                repo,
                                release_id,
                                title,
                                artist,
                                year,
                                genres,
                                styles,
                                image_url,
                            )

                        # Insertar interacción con valoración para el sistema de recomendación
                        insert_interaction(
                            repo,
                            user_id,
                            release_id,
                            "collection",
                            rating,
                            date_added,
                        )
                        page_processed += 1
                        processed_count += 1
                    except Exception as rls_err:
                        print(f"Error procesando release: {rls_err}")
                        continue

                repo.commit()
                print(
                    f"Página {page}: {page_processed} procesados, {page_skipped} saltados."
                )

                if data["pagination"]["page"] >= data["pagination"]["pages"]:
                    break
                page += 1
                time.sleep(API_PAUSE)  # Usar pausa configurable

            except Exception as e:
                print(f"Error de conexión: {e}")
                break

    except Exception as e:
        print(f"Error general procesando colección: {e}")

    print(
        f"Colección procesada: {processed_count} nuevos ítems, {skipped_count} ya existentes."
    )


def get_wantlist(repo: IngestionRepository, username):
    """Obtiene la lista de deseos del usuario"""
    page = 1
    processed_count = 0
    skipped_count = 0
    print(f"\nProcesando wantlist del usuario: {username}")

    try:
        # Asegúrate de que el usuario exista primero
        user_info = get_user_info(username)
        if user_info is None:
            print(
                f"No se pudo obtener información del usuario {username}. Saltando wantlist."
            )
            return

        user_id = user_info["user_id"]
        insert_user(
            repo,
            user_info["user_id"],
            user_info["username"],
            user_info["location"],
            user_info["joined_date"],
        )

        while True:
            try:
                url = f"{BASE_URL}/users/{username}/wants"
                params = {"token": DISCOGS_TOKEN, "page": page, "per_page": 50}

                # Usar función de API con manejo de límites de tasa
                r = api_call(url, params)

                if not r or r.status_code != 200:
                    if r:
                        try:
                            if r.text:
                                error_msg = r.json().get("message", "Error desconocido")
                                print("Error: {}".format(error_msg))
                            else:
                                print("Error: Sin respuesta del servidor")
                        except Exception as json_err:
                            print(
                                "Error: Código {}. No se pudo decodificar respuesta: {}".format(
                                    r.status_code, json_err
                                )
                            )
                    else:
                        print("Error: No se pudo completar la solicitud a la API")
                    break

                data = r.json()
                wants = data.get("wants", [])
                if not wants:
                    break

                page_processed = 0
                page_skipped = 0

                for want in wants:
                    try:
                        release_id = want["id"]

                        # Verificamos si esta interacción ya existe
                        if interaction_exists(repo, user_id, release_id, "wantlist"):
                            page_skipped += 1
                            skipped_count += 1
                            continue

                        basic_info = want["basic_information"]
                        title = basic_info["title"]
                        artist = ", ".join([a["name"] for a in basic_info["artists"]])
                        year = basic_info.get("year")
                        genres = ", ".join(basic_info.get("genres", []))
                        styles = ", ".join(basic_info.get("styles", []))

                        # Usamos la fecha real si está disponible
                        date_added = want.get(
                            "date_added", datetime.now().strftime("%Y-%m-%d")
                        )

                        # Solo procesamos el ítem si no existe
                        if not item_exists(repo, release_id):
                            # URL de la imagen
                            image_url = basic_info.get("cover_image")

                            # Guardar en DB solo con URL
                            insert_item(
                                repo,
                                release_id,
                                title,
                                artist,
                                year,
                                genres,
                                styles,
                                image_url,
                            )

                        # Para wantlist no hay rating, pero mantenemos una interacción especial
                        insert_interaction(
                            repo,
                            user_id,
                            release_id,
                            "wantlist",
                            None,
                            date_added,
                        )
                        page_processed += 1
                        processed_count += 1
                    except Exception as want_err:
                        print(f"Error procesando item de wantlist: {want_err}")
                        continue

                repo.commit()
                print(
                    f"Página {page} de wantlist: {page_processed} procesados, {page_skipped} saltados."
                )

                if data["pagination"]["page"] >= data["pagination"]["pages"]:
                    break
                page += 1
                time.sleep(API_PAUSE)  # Usar pausa configurable

            except Exception as e:
                print(f"Error de conexión en wantlist: {e}")
                break

    except Exception as e:
        print(f"Error general procesando wantlist: {e}")

    print(
        f"Wantlist procesada: {processed_count} nuevos ítems, {skipped_count} ya existentes."
    )


def get_user_submissions(repo: IngestionRepository, username, limit=20):
    """
    Obtiene contribuciones del usuario a la base de datos de Discogs
    Esto proporciona información valiosa sobre sus conocimientos y preferencias
    """
    print(f"\nBuscando contribuciones del usuario: {username}")
    url = f"{BASE_URL}/users/{username}/contributions"
    params = {"token": DISCOGS_TOKEN, "page": 1, "per_page": limit}

    try:
        r = api_call(url, params)
        if r and r.status_code == 200:
            data = r.json()
            contributions = data.get("contributions", [])

            if contributions:
                print(f"Procesando {len(contributions)} contribuciones...")

                # Obtenemos la info del usuario una sola vez
                user_info = get_user_info(username)
                if user_info is None:
                    print(
                        f"No se pudo obtener información del usuario {username}. Saltando contribuciones."
                    )
                    return

                user_id = user_info["user_id"]
                processed_count = 0
                skipped_count = 0

                # Para cada contribución, podemos registrar el interés del usuario
                for contrib in contributions:
                    entity_type = contrib.get("entity_type_name")
                    entity_id = contrib.get("entity_id")

                    if entity_type == "release" and entity_id:
                        # Verificamos si esta contribución ya existe
                        release_id = int(entity_id)
                        if interaction_exists(
                            repo, user_id, release_id, "contribution"
                        ):
                            skipped_count += 1
                            continue

                        # Solo si el ítem no existe, obtenemos sus detalles
                        if not item_exists(repo, release_id):
                            release_url = f"{BASE_URL}/releases/{entity_id}"
                            release_data = safe_api_json(
                                release_url,
                                params={"token": DISCOGS_TOKEN},
                                context=f"release {entity_id}",
                            )
                            if not release_data:
                                continue

                            title = release_data.get("title", "Unknown Title")
                            year = release_data.get("year")

                            artists = release_data.get("artists", [])
                            artist_names = [
                                a.get("name", "Unknown Artist") for a in artists
                            ]
                            artist = (
                                ", ".join(artist_names)
                                if artist_names
                                else "Unknown Artist"
                            )

                            genres = ", ".join(release_data.get("genres", []))
                            styles = ", ".join(release_data.get("styles", []))

                            images = release_data.get("images", [])
                            image_url = images[0].get("uri") if images else None

                            insert_item(
                                repo,
                                release_id,
                                title,
                                artist,
                                year,
                                genres,
                                styles,
                                image_url,
                            )

                            time.sleep(API_PAUSE)

                        # Guardar una interacción de tipo "contribution" para indicar que el usuario
                        # contribuyó con información sobre este ítem (alta afinidad/conocimiento)
                        date_added = datetime.now().strftime("%Y-%m-%d")
                        insert_interaction(
                            repo,
                            user_id,
                            release_id,
                            "contribution",
                            None,
                            date_added,
                        )
                        processed_count += 1

                repo.commit()
                print(
                    f"Contribuciones: {processed_count} nuevas, {skipped_count} ya existentes."
                )
                return True
            else:
                print("No se encontraron contribuciones.")
    except Exception as e:
        print(f"Error obteniendo contribuciones: {e}")

    return False


# Función para descubrir usuarios relacionados


def safe_api_json(url, params=None, context=""):
    params = dict(params or {})
    if "token" not in params:
        params["token"] = DISCOGS_TOKEN

    try:
        response = api_call(url, params)
        if response and response.status_code == 200:
            return response.json()
        if context:
            if response is None:
                message = f"No se recibió respuesta válida al obtener {context}."
            else:
                message = f"No se pudo obtener datos de {context} (status {response.status_code})."
            print(message)
            logger.warning(message)
    except Exception as exc:
        if context:
            print(f"Error obteniendo datos de {context}: {exc}")
            logger.exception("Error obteniendo datos de %s", context)
        else:
            logger.exception("Error obteniendo datos de %s", url)
            print(f"Error obteniendo datos de {url}: {exc}")
    return None


def get_user_neighbors(username, remaining):
    if remaining <= 0:
        return []

    neighbors = []
    seen = set()
    username_lower = username.lower()

    def add_candidate(candidate):
        if not candidate:
            return False
        candidate = candidate.strip()
        if not candidate:
            return False
        candidate_lower = candidate.lower()
        if candidate_lower == username_lower:
            return False
        if candidate_lower in seen:
            return False
        seen.add(candidate_lower)
        neighbors.append(candidate)
        return True

    per_page = min(max(remaining, 1), 50)

    for endpoint in ("following", "followers"):
        if len(neighbors) >= remaining:
            break
        data = safe_api_json(
            f"{BASE_URL}/users/{username}/{endpoint}",
            {"per_page": per_page},
            context=f"{endpoint} de {username}",
        )
        if not data:
            continue
        for user in data.get(endpoint, []):
            if len(neighbors) >= remaining:
                break
            add_candidate(user.get("username"))
        time.sleep(DISCOVERY_PAUSE)

    if len(neighbors) < remaining:
        lists_data = safe_api_json(
            f"{BASE_URL}/users/{username}/lists",
            {"per_page": MAX_LISTS_PER_USER},
            context=f"listas de {username}",
        )
        if lists_data:
            for list_item in lists_data.get("lists", [])[:MAX_LISTS_PER_USER]:
                if len(neighbors) >= remaining:
                    break
                list_url = list_item.get("resource_url")
                if not list_url:
                    continue
                list_data = safe_api_json(
                    list_url,
                    {"per_page": 50},
                    context=f"lista {list_item.get('name', '')} de {username}",
                )
                if not list_data:
                    continue
                for contributor in list_data.get("contributors", []):
                    if len(neighbors) >= remaining:
                        break
                    if isinstance(contributor, dict):
                        candidate = contributor.get("username")
                    else:
                        candidate = contributor
                    add_candidate(candidate)
                time.sleep(DISCOVERY_PAUSE)

    return neighbors[:remaining]


def discover_users(
    seed_username,
    max_users=5,
    depth=DISCOVERY_MAX_DEPTH,
    extra_seeds=None,
):
    visited = set(load_visited_users())
    result = []
    extra_queue = deque([s.strip() for s in extra_seeds or [] if s.strip()])

    def bfs_from_seed(start_username):
        if len(result) >= max_users:
            return
        queue = deque([(start_username, 0)])

        while queue and len(result) < max_users:
            username, level = queue.popleft()
            if not username:
                continue
            username_clean = username.strip()
            if not username_clean:
                continue
            username_lower = username_clean.lower()
            if username_lower in visited:
                continue
            visited.add(username_lower)
            result.append(username_clean)

            if len(result) >= max_users:
                break

            if level >= depth:
                continue

            remaining = max(max_users - len(result), 0)
            neighbors = get_user_neighbors(username_clean, remaining)
            for neighbor in neighbors:
                if neighbor:
                    queue.append((neighbor, level + 1))
            time.sleep(DISCOVERY_PAUSE)

    bfs_from_seed(seed_username)

    while len(result) < max_users and extra_queue:
        next_seed = extra_queue.popleft()
        if not next_seed:
            continue
        if next_seed.lower() in visited:
            continue
        print(f"Explorando seed adicional: {next_seed}")
        bfs_from_seed(next_seed)

    if len(result) < max_users:
        for fallback in POPULAR_USERS:
            fallback_lower = fallback.lower()
            if fallback_lower in visited:
                continue
            visited.add(fallback_lower)
            result.append(fallback)
            if len(result) >= max_users:
                break

    persist_visited_users(visited)
    print(f"Usuarios descubiertos: {result}")
    return result


# Función principal para poblar la base de datos
def count_user_data(repo: IngestionRepository, user_id):
    """Cuenta cuántas interacciones tiene un usuario en la base de datos"""

    return repo.count_user_interactions(user_id)


def populate_recommendation_system(seed_username="Xmipod", max_users=5):
    init_runtime()
    print("Iniciando población de base de datos para sistema de recomendación...")

    # Descubrir usuarios automáticamente
    users = discover_users(seed_username, max_users)

    with IngestionRepository(_get_repo_config()) as repo:
        for username in users:
            if not username:
                continue

            # Verificamos si el usuario existe y si tiene datos suficientes
            user_info = get_user_info(username)
            if user_info is None:
                print(f"El usuario {username} no existe en Discogs. Saltando...")
                continue

            user_id = user_info["user_id"]

            # Si el usuario ya existe y tiene más de 50 interacciones, podemos saltarlo
            interaction_count = (
                count_user_data(repo, user_id) if user_exists(repo, user_id) else 0
            )

            if user_exists(repo, user_id) and interaction_count > 50:
                print(
                    f"El usuario {username} ya tiene {interaction_count} interacciones. Saltando..."
                )
                continue

            print(
                f"Procesando usuario {username} ({interaction_count} interacciones existentes)"
            )

            # Obtener colección de discos
            get_collection(repo, username)

            # Obtener lista de deseos
            get_wantlist(repo, username)

            # Buscar contribuciones (opcional)
            get_user_submissions(repo, username)

            print(f"Datos del usuario {username} procesados completamente.")
            time.sleep(1)  # Pausa para evitar límites de la API

    print("\nBase de datos para recomendaciones generada correctamente.")


# Ejecutar
if __name__ == "__main__":
    init_runtime()
    import argparse

    # Configurar argumentos de línea de comandos para mayor flexibilidad
    parser = argparse.ArgumentParser(
        description="Poblar base de datos para sistema de recomendación musical"
    )
    parser.add_argument(
        "--seed",
        "-s",
        default="Xmipod",
        help="Usuario semilla para empezar la búsqueda",
    )
    parser.add_argument(
        "--max-users",
        "-m",
        type=int,
        default=5,
        help="Número máximo de usuarios a procesar",
    )
    parser.add_argument(
        "--extra-seeds",
        help="Lista separada por comas de seeds adicionales para discovery",
    )
    parser.add_argument(
        "--seeds-file",
        type=Path,
        help="Archivo con seeds (uno por línea) para discovery adicional",
    )
    parser.add_argument("--token", "-t", help="Token de Discogs (opcional)")
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Forzar actualización incluso si los datos ya existen",
    )
    parser.add_argument(
        "--min-items",
        type=int,
        default=50,
        help="Número mínimo de interacciones para considerar un usuario completo",
    )
    parser.add_argument(
        "--continue-from",
        help="Continuar desde este usuario (ignorará los usuarios anteriores)",
    )
    parser.add_argument(
        "--api-pause",
        type=int,
        help="Segundos de pausa entre llamadas a la API (default: 3)",
    )
    parser.add_argument(
        "--adaptive-pause",
        action="store_true",
        help="Activar pausa adaptativa basada en el estado del servidor",
    )

    args = parser.parse_args()

    # Actualizar token si se proporcionó uno en línea de comandos
    if args.token:
        DISCOGS_TOKEN = args.token

    # Establecer modo de forzar actualización
    FORCE_UPDATE = args.force
    MIN_ITEMS_THRESHOLD = args.min_items

    # Configurar pausa de API personalizada
    if args.api_pause is not None:
        API_PAUSE = args.api_pause
        print(f"Pausa de API configurada a {API_PAUSE} segundos")

    # Configurar modo de pausa adaptativa
    if args.adaptive_pause:
        API_ADAPTIVE_PAUSE = True
        print(
            "Pausa adaptativa ACTIVADA - se ajustará dinámicamente según el estado del servidor"
        )

    # Modificar populate_recommendation_system para usar las nuevas opciones
    def populate_recommendation_system_with_options(seed_username, max_users):
        """Versión modificada de populate_recommendation_system con soporte para skipeo de usuarios"""
        init_runtime()
        print("Iniciando población de base de datos para sistema de recomendación...")
        print(f"Modo forzado: {'ACTIVADO' if FORCE_UPDATE else 'DESACTIVADO'}")
        print(f"Pausa entre llamadas API: {API_PAUSE} segundos")

        # Descubrir usuarios automáticamente
        extra_seeds = []
        if args.extra_seeds:
            extra_seeds.extend([seed.strip() for seed in args.extra_seeds.split(",")])
        if args.seeds_file and args.seeds_file.exists():
            extra_seeds.extend(
                [seed.strip() for seed in args.seeds_file.read_text().splitlines()]
            )

        users = discover_users(seed_username, max_users, extra_seeds=extra_seeds)

        continue_target = args.continue_from.strip() if args.continue_from else None
        continue_processing = True
        discovered_lower: dict[str, str] = {}
        if continue_target:
            discovered_lower = {user.lower(): user for user in users}
            target_lower = continue_target.lower()
            if target_lower not in discovered_lower:
                print(
                    f"Advertencia: el usuario '{continue_target}' no fue descubierto en esta corrida; se procesarán todos los usuarios."
                )
            else:
                continue_processing = False
                print(f"Continuando desde usuario: {discovered_lower[target_lower]}")

        # Contador para mostrar progreso
        processed_count = 0
        total_users = len(users)

        with IngestionRepository(_get_repo_config()) as repo:
            try:
                for username in users:
                    if not username:
                        continue

                    if not continue_processing:
                        if (
                            continue_target
                            and username.lower() == continue_target.lower()
                        ):
                            continue_processing = True
                            print(f"Reanudando procesamiento en: {username}")
                        else:
                            print(
                                f"Saltando usuario {username} (esperando llegar a {continue_target or ''})"
                            )
                            continue

                    processed_count += 1
                    print(
                        f"\n[Usuario {processed_count}/{total_users}] Procesando {username}"
                    )

                    user_info = get_user_info(username)
                    if user_info is None:
                        print(
                            f"El usuario {username} no existe en Discogs. Saltando..."
                        )
                        continue

                    user_id = user_info["user_id"]
                    interaction_count = (
                        count_user_data(repo, user_id)
                        if user_exists(repo, user_id)
                        else 0
                    )

                    if (
                        user_exists(repo, user_id)
                        and interaction_count >= MIN_ITEMS_THRESHOLD
                        and not FORCE_UPDATE
                    ):
                        print(
                            f"El usuario {username} ya tiene {interaction_count} interacciones. Saltando..."
                        )
                        continue

                    print(
                        f"Procesando usuario {username} ({interaction_count} interacciones existentes)"
                    )

                    with open(".last_processed_user.txt", "w") as f:
                        f.write(username)

                    get_collection(repo, username)
                    get_wantlist(repo, username)
                    get_user_submissions(repo, username)

                    print(f"Datos del usuario {username} procesados completamente.")

                    total_calls, rate_limit_hits = _current_api_stats()
                    print(
                        "Estadísticas API: {} llamadas totales, {} límites alcanzados".format(
                            total_calls,
                            rate_limit_hits,
                        )
                    )

                    repo.commit()
                    time.sleep(API_PAUSE)

                if os.path.exists(".last_processed_user.txt"):
                    os.remove(".last_processed_user.txt")

            except KeyboardInterrupt:
                print("\n\nProceso interrumpido por el usuario.")
                print("Para continuar más tarde, ejecuta:")

                last_user = ""
                if os.path.exists(".last_processed_user.txt"):
                    with open(".last_processed_user.txt", "r") as f:
                        last_user = f.read().strip()

                if last_user:
                    print(
                        "python3 {} --seed '{}' --max-users {} --continue-from '{}'".format(
                            os.path.basename(__file__),
                            seed_username,
                            max_users,
                            last_user,
                        )
                    )

                repo.commit()

            except Exception as e:
                print(f"\nError inesperado: {e}")
                repo.commit()
                raise

            print("\nBase de datos para recomendaciones generada correctamente.")

    # Verificar si hay un archivo de último usuario procesado y no se especificó continue-from
    if not args.continue_from and os.path.exists(".last_processed_user.txt"):
        with open(".last_processed_user.txt", "r") as f:
            last_user = f.read().strip()
            if last_user:
                print(
                    "Encontrado archivo de último usuario procesado: {}. Ejecuta el script con --continue-from '{}' para reanudar.".format(
                        last_user,
                        last_user,
                    )
                )

    # Registrar tiempo de inicio para estadísticas
    start_time = datetime.now()

    # Llamar a la versión modificada con los argumentos de línea de comandos
    seed_username = args.seed or DEFAULT_SEED_USERNAME
    populate_recommendation_system_with_options(seed_username, args.max_users)

    # Mostrar estadísticas finales
    end_time = datetime.now()
    duration = end_time - start_time

    # Contar elementos en la base de datos
    with IngestionRepository(_get_repo_config()) as repo:
        cursor = repo.cursor
        users_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        items_count = cursor.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        interactions_count = cursor.execute(
            "SELECT COUNT(*) FROM interactions"
        ).fetchone()[0]

    # Mostrar estadísticas completas
    print("\n==== Estadísticas finales ====")
    print(f"Tiempo total de ejecución: {duration}")
    total_calls, rate_limit_hits = _current_api_stats()
    print(f"Llamadas a la API realizadas: {total_calls}")
    print(f"Límites de tasa alcanzados: {rate_limit_hits}")
    print(f"Total de usuarios en la base de datos: {users_count}")
    print(f"Total de items en la base de datos: {items_count}")
    print(f"Total de interacciones en la base de datos: {interactions_count}")
    print("=============================")
    print("\nProceso completado.")
