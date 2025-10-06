import os
import sqlite3
import time
from datetime import datetime

import requests

from settings import (
    get_api_pause,
    get_database_path,
    get_discogs_token,
    get_seed_username,
)

BASE_URL = "https://api.discogs.com"

try:
    DISCOGS_TOKEN = get_discogs_token()
except RuntimeError as err:
    raise SystemExit(err)

DEFAULT_SEED_USERNAME = get_seed_username()
DATABASE_PATH = get_database_path()

# Conexión DB
con = sqlite3.connect(str(DATABASE_PATH))
cursor = con.cursor()


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


def user_exists(user_id):
    """Verifica si un usuario ya existe en la base de datos"""
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None


def item_exists(item_id):
    """Verifica si un ítem ya existe en la base de datos"""
    cursor.execute("SELECT 1 FROM items WHERE item_id = ?", (item_id,))
    return cursor.fetchone() is not None


def interaction_exists(user_id, item_id, interaction_type):
    """Verifica si una interacción específica ya existe en la base de datos"""
    # Si estamos en modo forzado, siempre retornamos False para procesar todo
    if FORCE_UPDATE:
        return False

    cursor.execute(
        """
    SELECT 1 FROM interactions
    WHERE user_id = ? AND item_id = ? AND interaction_type = ?
    """,
        (user_id, item_id, interaction_type),
    )
    return cursor.fetchone() is not None


def insert_user(user_id, username, location, joined_date):
    cursor.execute(
        """
    INSERT OR IGNORE INTO users (user_id, username, location, joined_date)
    VALUES (?, ?, ?, ?)
    """,
        (user_id, username, location, joined_date),
    )


def insert_item(item_id, title, artist, year, genre, style, image_url):
    cursor.execute(
        """
    INSERT OR IGNORE INTO items (item_id, title, artist, year, genre, style, image_url)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (item_id, title, artist, year, genre, style, image_url),
    )


def insert_interaction(user_id, item_id, interaction_type, rating, date_added):
    # Evitamos duplicar interacciones
    if not interaction_exists(user_id, item_id, interaction_type):
        cursor.execute(
            """
        INSERT INTO interactions (user_id, item_id, interaction_type, rating, date_added)
        VALUES (?, ?, ?, ?, ?)
        """,
            (user_id, item_id, interaction_type, rating, date_added),
        )


def get_collection(username):
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
                        if interaction_exists(user_id, release_id, "collection"):
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
                        if not item_exists(release_id):
                            insert_item(
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
                            user_id, release_id, "collection", rating, date_added
                        )
                        page_processed += 1
                        processed_count += 1
                    except Exception as rls_err:
                        print(f"Error procesando release: {rls_err}")
                        continue

                con.commit()
                print(
                    f"Página {page}: {page_processed} procesados, {page_skipped} saltados."
                )

                if data["pagination"]["page"] >= data["pagination"]["pages"]:
                    break
                page += 1
                time.sleep(API_PAUSE)  # Usar pausa configurable

            except requests.exceptions.RequestException as e:
                print(f"Error de conexión: {e}")
                break

    except Exception as e:
        print(f"Error general procesando colección: {e}")

    print(
        f"Colección procesada: {processed_count} nuevos ítems, {skipped_count} ya existentes."
    )


def get_wantlist(username):
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
                        if interaction_exists(user_id, release_id, "wantlist"):
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
                        if not item_exists(release_id):
                            # URL de la imagen
                            image_url = basic_info.get("cover_image")

                            # Guardar en DB solo con URL
                            insert_item(
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
                            user_id, release_id, "wantlist", None, date_added
                        )
                        page_processed += 1
                        processed_count += 1
                    except Exception as want_err:
                        print(f"Error procesando item de wantlist: {want_err}")
                        continue

                con.commit()
                print(
                    f"Página {page} de wantlist: {page_processed} procesados, {page_skipped} saltados."
                )

                if data["pagination"]["page"] >= data["pagination"]["pages"]:
                    break
                page += 1
                time.sleep(API_PAUSE)  # Usar pausa configurable

            except requests.exceptions.RequestException as e:
                print(f"Error de conexión en wantlist: {e}")
                break

    except Exception as e:
        print(f"Error general procesando wantlist: {e}")

    print(
        f"Wantlist procesada: {processed_count} nuevos ítems, {skipped_count} ya existentes."
    )


def get_user_submissions(username, limit=20):
    """
    Obtiene contribuciones del usuario a la base de datos de Discogs
    Esto proporciona información valiosa sobre sus conocimientos y preferencias
    """
    print(f"\nBuscando contribuciones del usuario: {username}")
    url = f"{BASE_URL}/users/{username}/contributions"
    params = {"token": DISCOGS_TOKEN, "page": 1, "per_page": limit}

    try:
        r = requests.get(url, params=params)
        if r.status_code == 200:
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
                        if interaction_exists(user_id, release_id, "contribution"):
                            skipped_count += 1
                            continue

                        # Solo si el ítem no existe, obtenemos sus detalles
                        if not item_exists(release_id):
                            # Obtener detalles de este release
                            release_url = f"{BASE_URL}/releases/{entity_id}"
                            try:
                                r_detail = requests.get(
                                    release_url, params={"token": DISCOGS_TOKEN}
                                )
                                if r_detail.status_code == 200:
                                    release_data = r_detail.json()

                                    # Extraer información clave
                                    title = release_data.get("title", "Unknown Title")
                                    year = release_data.get("year")

                                    # Extraer artista(s)
                                    artists = release_data.get("artists", [])
                                    artist_names = [
                                        a.get("name", "Unknown Artist") for a in artists
                                    ]
                                    artist = (
                                        ", ".join(artist_names)
                                        if artist_names
                                        else "Unknown Artist"
                                    )

                                    # Géneros y estilos
                                    genres = ", ".join(release_data.get("genres", []))
                                    styles = ", ".join(release_data.get("styles", []))

                                    # Imagen
                                    images = release_data.get("images", [])
                                    image_url = images[0].get("uri") if images else None

                                    # Guardar como ítem en la base de datos
                                    insert_item(
                                        release_id,
                                        title,
                                        artist,
                                        year,
                                        genres,
                                        styles,
                                        image_url,
                                    )

                                    # No hacer demasiadas peticiones seguidas
                                    time.sleep(1)
                            except Exception as e:
                                print(f"Error procesando contribución {entity_id}: {e}")
                                continue

                        # Guardar una interacción de tipo "contribution" para indicar que el usuario
                        # contribuyó con información sobre este ítem (alta afinidad/conocimiento)
                        date_added = datetime.now().strftime("%Y-%m-%d")
                        insert_interaction(
                            user_id, release_id, "contribution", None, date_added
                        )
                        processed_count += 1

                con.commit()
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
def discover_users(seed_username, max_users=5):
    """
    Descubre usuarios relacionados con colecciones públicas basados en un usuario semilla
    Utiliza diversas estrategias para encontrar usuarios con gustos similares
    """
    discovered_users = [seed_username]
    processed_users = set(discovered_users)

    # Método 1: Usuarios seguidos por el usuario semilla
    url = f"{BASE_URL}/users/{seed_username}/following"
    params = {"token": DISCOGS_TOKEN, "per_page": max_users}

    try:
        # Usar función de API con manejo de límites de tasa
        r = api_call(url, params)

        if r and r.status_code == 200:
            data = r.json()
            for user in data.get("following", []):
                if (
                    len(discovered_users) < max_users
                    and user["username"] not in processed_users
                ):
                    discovered_users.append(user["username"])
                    processed_users.add(user["username"])
    except Exception as e:
        print(f"Error buscando usuarios seguidos: {e}")

    # Método 2: Usuarios que siguen al usuario semilla
    if len(discovered_users) < max_users:
        url = f"{BASE_URL}/users/{seed_username}/followers"
        try:
            # Usar función de API con manejo de límites de tasa
            r = api_call(url, params)

            if r and r.status_code == 200:
                data = r.json()
                for user in data.get("followers", []):
                    if (
                        len(discovered_users) < max_users
                        and user["username"] not in processed_users
                    ):
                        discovered_users.append(user["username"])
                        processed_users.add(user["username"])
        except Exception as e:
            print(f"Error buscando seguidores: {e}")

    # Método 3: Usuarios con items en común en su colección
    if len(discovered_users) < max_users:
        try:
            # Obtener unos pocos items de la colección del usuario semilla
            collection_url = (
                f"{BASE_URL}/users/{seed_username}/collection/folders/0/releases"
            )
            r = requests.get(
                collection_url, params={"token": DISCOGS_TOKEN, "per_page": 5}
            )
            if r.status_code == 200:
                for release in r.json().get("releases", []):
                    # Para cada release, buscar quién más lo tiene en su colección
                    release_id = release["id"]
                    release_url = f"{BASE_URL}/marketplace/stats/{release_id}"
                    r2 = requests.get(release_url, params={"token": DISCOGS_TOKEN})

                    if r2.status_code == 200 and len(discovered_users) < max_users:
                        # Aquí podríamos obtener usuarios que también tienen este disco, pero
                        # la API de Discogs no ofrece directamente esta información
                        # Usaremos una búsqueda alternativa en la próxima estrategia
                        pass
                    time.sleep(1)  # Pausar para no exceder límites API
        except Exception as e:
            print(f"Error buscando por colecciones en común: {e}")

    # Método 4: Búsqueda por listas compartidas
    if len(discovered_users) < max_users:
        try:
            url = f"{BASE_URL}/users/{seed_username}/lists"
            r = requests.get(url, params={"token": DISCOGS_TOKEN})
            if r.status_code == 200:
                data = r.json()
                for list_item in data.get("lists", []):
                    if len(discovered_users) >= max_users:
                        break

                    list_url = list_item.get("resource_url")
                    if list_url:
                        r2 = requests.get(list_url, params={"token": DISCOGS_TOKEN})
                        if r2.status_code == 200:
                            # Buscar contribuidores en la lista
                            for user_info in r2.json().get("contributors", []):
                                if (
                                    isinstance(user_info, dict)
                                    and "username" in user_info
                                ):
                                    username = user_info["username"]
                                    if (
                                        username not in processed_users
                                        and len(discovered_users) < max_users
                                    ):
                                        discovered_users.append(username)
                                        processed_users.add(username)
        except Exception as e:
            print(f"Error buscando en listas compartidas: {e}")

    # Método 5: Si no encontramos suficientes, usar usuarios populares
    if len(discovered_users) < max_users:
        popular_users = [
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

        for user in popular_users:
            if user not in processed_users and len(discovered_users) < max_users:
                # Verificar que el usuario existe y tiene colección pública
                verify_url = f"{BASE_URL}/users/{user}"
                try:
                    r = requests.get(verify_url, params={"token": DISCOGS_TOKEN})
                    if r.status_code == 200:
                        discovered_users.append(user)
                        processed_users.add(user)
                except requests.RequestException:
                    continue

    print(f"Usuarios descubiertos: {discovered_users}")
    return discovered_users


# Función principal para poblar la base de datos
def count_user_data(user_id):
    """Cuenta cuántas interacciones tiene un usuario en la base de datos"""
    cursor.execute("SELECT COUNT(*) FROM interactions WHERE user_id = ?", (user_id,))
    return cursor.fetchone()[0]


def populate_recommendation_system(seed_username="Xmipod", max_users=5):
    print("Iniciando población de base de datos para sistema de recomendación...")

    # Descubrir usuarios automáticamente
    users = discover_users(seed_username, max_users)

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
        interaction_count = count_user_data(user_id) if user_exists(user_id) else 0

        if user_exists(user_id) and interaction_count > 50:
            print(
                f"El usuario {username} ya tiene {interaction_count} interacciones. Saltando..."
            )
            continue

        print(
            f"Procesando usuario {username} ({interaction_count} interacciones existentes)"
        )

        # Obtener colección de discos
        get_collection(username)

        # Obtener lista de deseos
        get_wantlist(username)

        # Buscar contribuciones (opcional)
        get_user_submissions(username)

        print(f"Datos del usuario {username} procesados completamente.")
        time.sleep(1)  # Pausa para evitar límites de la API

    print("\nBase de datos para recomendaciones generada correctamente.")


# Variables globales para control de skipping
FORCE_UPDATE = False
MIN_ITEMS_THRESHOLD = 50
API_PAUSE = get_api_pause()  # Pausa entre llamadas API en segundos
MAX_RATE_LIMIT_RETRIES = (
    5  # Número de intentos si se alcanza el límite de tasa (aumentado)
)
RATE_LIMIT_COOLDOWN = (
    60  # Tiempo de espera en segundos cuando se alcanza el límite de tasa (aumentado)
)
API_ADAPTIVE_PAUSE = False  # Pausas adaptativas basadas en la carga del servidor

# Contadores globales para monitorear uso de la API
API_CALLS_COUNT = 0
RATE_LIMIT_HITS = 0
LAST_API_CALL_TIME = None


def calculate_dynamic_pause(remaining=None, reset_time=None):
    """Calcula una pausa dinámica basada en el estado de límite de tasa"""
    global API_CALLS_COUNT, LAST_API_CALL_TIME

    # Pausa base
    pause = API_PAUSE

    # Si la pausa adaptativa está activada y tenemos información de límites
    if API_ADAPTIVE_PAUSE and remaining is not None:
        try:
            remaining = int(remaining)

            # Ajustar la pausa de forma inversamente proporcional a las llamadas restantes
            if remaining <= 10:
                pause = max(
                    10, API_PAUSE * 3
                )  # Pausa extendida cuando quedan pocas llamadas
            elif remaining <= 20:
                pause = max(5, API_PAUSE * 2)  # Pausa moderada

            # Si además tenemos información del tiempo de reinicio
            if reset_time and reset_time.isdigit():
                reset_seconds = int(reset_time)
                if reset_seconds < 60:  # Si estamos cerca del reinicio del contador
                    pause = max(
                        pause, reset_seconds / 2
                    )  # Esperar una parte del tiempo hasta el reinicio

        except (ValueError, TypeError):
            pass  # Si hay error en la conversión, usar la pausa base

    # Pausa preventiva periódica
    if API_CALLS_COUNT > 0 and API_CALLS_COUNT % 40 == 0:
        pause = max(pause, 15)  # Pausa extendida cada 40 llamadas

    return pause


def api_call(url, params):
    """Realiza una llamada a la API con manejo automático de límites de tasa"""
    global API_CALLS_COUNT, RATE_LIMIT_HITS, LAST_API_CALL_TIME

    # Verificar si estamos haciendo demasiadas llamadas en poco tiempo
    if API_CALLS_COUNT > 0 and API_CALLS_COUNT % 50 == 0:
        print(f"Pausa preventiva después de {API_CALLS_COUNT} llamadas a la API...")
        time.sleep(30)  # Pausa preventiva cada 50 llamadas

    # Si es la primera llamada, no hay espera inicial
    if LAST_API_CALL_TIME is not None:
        # Calcular tiempo transcurrido desde la última llamada
        elapsed = time.time() - LAST_API_CALL_TIME

        # Si no ha pasado suficiente tiempo, esperar
        if elapsed < API_PAUSE:
            time.sleep(API_PAUSE - elapsed)

    retries = 0
    while retries <= MAX_RATE_LIMIT_RETRIES:
        try:
            # Actualizar tiempo de la última llamada
            LAST_API_CALL_TIME = time.time()

            # Incrementar contador de llamadas
            API_CALLS_COUNT += 1

            # Realizar la llamada a la API
            r = requests.get(url, params=params, timeout=30)

            # Verificar headers relacionados con límites de tasa si están disponibles
            remaining = r.headers.get("X-Discogs-Ratelimit-Remaining")
            reset_time = r.headers.get("X-Discogs-Ratelimit-Reset")

            # Mostrar información de límites si está disponible
            if remaining:
                if int(remaining) < 10:
                    print(
                        f"¡Advertencia! Solo quedan {remaining} solicitudes disponibles."
                    )

                    if reset_time:
                        print("Límite se reiniciará en {} segundos.".format(reset_time))

            # Determinar pausa dinámica basada en el estado de límites
            dynamic_pause = calculate_dynamic_pause(remaining, reset_time)

            # Manejar límites de tasa
            if r.status_code == 429:  # Código de límite de tasa excedido
                RATE_LIMIT_HITS += 1
                retries += 1

                if retries <= MAX_RATE_LIMIT_RETRIES:
                    # Aumentar el tiempo de espera exponencialmente con cada reintento
                    wait_time = RATE_LIMIT_COOLDOWN * (2 ** (retries - 1))
                    print(
                        "Límite de tasa alcanzado ({}). Esperando {} segundos "
                        "antes de reintentar...".format(
                            RATE_LIMIT_HITS,
                            wait_time,
                        )
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    print("Máximo de reintentos alcanzado. Cancelando solicitud.")
                    return None

            # Si es exitoso, esperar un tiempo dinámico para no sobrecargar la API
            time.sleep(dynamic_pause)
            return r

        except requests.exceptions.RequestException as e:
            print(f"Error de conexión: {e}")
            return None

    return None


# Ejecutar
if __name__ == "__main__":
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
        print("Iniciando población de base de datos para sistema de recomendación...")
        print(f"Modo forzado: {'ACTIVADO' if FORCE_UPDATE else 'DESACTIVADO'}")
        print(f"Pausa entre llamadas API: {API_PAUSE} segundos")

        # Descubrir usuarios automáticamente
        users = discover_users(seed_username, max_users)

        # Comprobar si debemos continuar desde un usuario específico
        continue_processing = True
        if args.continue_from:
            continue_processing = False
            print(f"Buscando usuario para continuar: {args.continue_from}")

        # Contador para mostrar progreso
        processed_count = 0
        total_users = len(users)

        try:
            for username in users:
                if not username:
                    continue

                # Si estamos en modo continuar y no hemos llegado al usuario deseado, saltamos
                if not continue_processing:
                    if username == args.continue_from:
                        continue_processing = True
                        print(f"Continuando desde usuario: {username}")
                    else:
                        print(
                            f"Saltando usuario {username} (esperando llegar a {args.continue_from})"
                        )
                        continue

                processed_count += 1
                print(
                    f"\n[Usuario {processed_count}/{total_users}] Procesando {username}"
                )

                # Verificamos si el usuario existe y si tiene datos suficientes
                user_info = get_user_info(username)
                if user_info is None:
                    print(f"El usuario {username} no existe en Discogs. Saltando...")
                    continue

                user_id = user_info["user_id"]

                # Si el usuario ya existe y tiene suficientes interacciones, podemos saltarlo
                # a menos que estemos en modo FORCE_UPDATE
                interaction_count = (
                    count_user_data(user_id) if user_exists(user_id) else 0
                )

                if (
                    user_exists(user_id)
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

                # Guardar el usuario actual en caso de interrupción
                with open(".last_processed_user.txt", "w") as f:
                    f.write(username)

                # Obtener colección de discos
                get_collection(username)

                # Obtener lista de deseos
                get_wantlist(username)

                # Buscar contribuciones (opcional)
                get_user_submissions(username)

                print(f"Datos del usuario {username} procesados completamente.")

                # Mostrar estadísticas de la API
                print(
                    "Estadísticas API: {} llamadas totales, {} límites alcanzados".format(
                        API_CALLS_COUNT,
                        RATE_LIMIT_HITS,
                    )
                )

                con.commit()  # Garantizar que todos los datos se guarden después de cada usuario
                time.sleep(API_PAUSE)  # Pausa entre usuarios

            # Al terminar exitosamente, borramos el archivo de último usuario procesado
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

            # Asegurar que los cambios se guarden antes de salir
            con.commit()

        except Exception as e:
            # Manejar cualquier otra excepción
            print(f"\nError inesperado: {e}")
            # Asegurar que los cambios se guarden antes de salir
            con.commit()
            raise

        print("\nBase de datos para recomendaciones generada correctamente.")

    # Verificar si hay un archivo de último usuario procesado y no se especificó continue-from
    if not args.continue_from and os.path.exists(".last_processed_user.txt"):
        with open(".last_processed_user.txt", "r") as f:
            last_user = f.read().strip()
            if last_user:
                print(f"Encontrado archivo de último usuario procesado: {last_user}")
                continuar = input(
                    "¿Deseas continuar desde este usuario? (s/n): "
                ).lower()
                if continuar.startswith("s"):
                    args.continue_from = last_user
                    print(f"Continuando desde el usuario: {last_user}")

    # Registrar tiempo de inicio para estadísticas
    start_time = datetime.now()

    # Llamar a la versión modificada con los argumentos de línea de comandos
    seed_username = args.seed or DEFAULT_SEED_USERNAME
    populate_recommendation_system_with_options(seed_username, args.max_users)

    # Mostrar estadísticas finales
    end_time = datetime.now()
    duration = end_time - start_time

    # Contar elementos en la base de datos
    cursor = con.cursor()
    users_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    items_count = cursor.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    interactions_count = cursor.execute("SELECT COUNT(*) FROM interactions").fetchone()[
        0
    ]

    # Cerrar conexión a la base de datos
    con.close()

    # Mostrar estadísticas completas
    print("\n==== Estadísticas finales ====")
    print(f"Tiempo total de ejecución: {duration}")
    print(f"Llamadas a la API realizadas: {API_CALLS_COUNT}")
    print(f"Límites de tasa alcanzados: {RATE_LIMIT_HITS}")
    print(f"Total de usuarios en la base de datos: {users_count}")
    print(f"Total de items en la base de datos: {items_count}")
    print(f"Total de interacciones en la base de datos: {interactions_count}")
    print("=============================")
    print("\nProceso completado.")
