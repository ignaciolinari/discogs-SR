# version: 1.0 -- recomendaciones al azar para discos

import os
import random
import sqlite3

import metricas

DATABASE_FILE = os.path.dirname(__file__) + "/datos/discogs.db"

###


def sql_execute(query, params=None):
    con = sqlite3.connect(DATABASE_FILE)
    cur = con.cursor()
    if params:
        res = cur.execute(query, params)
    else:
        res = cur.execute(query)

    con.commit()
    con.close()
    return res


def sql_select(query, params=None):
    con = sqlite3.connect(DATABASE_FILE)
    con.row_factory = sqlite3.Row  # esto es para que devuelva registros en el fetchall
    cur = con.cursor()
    if params:
        res = cur.execute(query, params)
    else:
        res = cur.execute(query)

    ret = res.fetchall()
    con.close()
    return ret


###


def crear_usuario(id_usuario):
    query = (
        "INSERT INTO users(user_id, username) VALUES (?, ?) " "ON CONFLICT DO NOTHING;"
    )
    sql_execute(query, [id_usuario, id_usuario])
    return


def insertar_interacciones(id_disco, id_usuario, rating):
    # Primero verificar si ya existe una interacción para este usuario y disco
    query_check = (
        "SELECT interaction_id FROM interactions WHERE item_id = ? AND user_id = ?;"
    )
    existing = sql_select(query_check, [id_disco, id_usuario])

    if existing:
        # Si existe, actualizar el rating
        query = (
            "UPDATE interactions SET rating = ?, interaction_type = 'rating' "
            "WHERE item_id = ? AND user_id = ?;"
        )
        sql_execute(query, [rating, id_disco, id_usuario])
    else:
        # Si no existe, insertar nuevo
        query = (
            "INSERT INTO interactions(item_id, user_id, interaction_type, rating, "
            "date_added) VALUES (?, ?, ?, ?, date('now'));"
        )
        sql_execute(query, [id_disco, id_usuario, "rating", rating])
    return


def reset_usuario(id_usuario):
    query = "DELETE FROM interactions WHERE user_id = ?;"
    sql_execute(query, [id_usuario])
    return


def obtener_disco(id_disco):
    query = "SELECT * FROM items WHERE item_id = ?;"
    disco = sql_select(query, [id_disco])[0]
    return disco


def items_valorados(id_usuario):
    query = "SELECT item_id FROM interactions " "WHERE user_id = ? AND rating > 0"
    rows = sql_select(query, [id_usuario])
    return [i["item_id"] for i in rows]


def items_vistos(id_usuario):
    query = "SELECT item_id FROM interactions " "WHERE user_id = ? AND rating = 0"
    rows = sql_select(query, [id_usuario])
    return [i["item_id"] for i in rows]


def items_desconocidos(id_usuario):
    query = (
        "SELECT item_id FROM items WHERE item_id NOT IN ("
        "SELECT item_id FROM interactions WHERE user_id = ? AND rating IS NOT NULL"
        ")"
    )
    rows = sql_select(query, [id_usuario])
    return [i["item_id"] for i in rows]


def datos_discos(id_discos):
    if not id_discos:
        return []
    placeholders = ",".join(["?"] * len(id_discos))
    query = "SELECT DISTINCT * FROM items WHERE item_id IN ({})".format(placeholders)
    discos = sql_select(query, id_discos)
    return discos


###


def recomendar_azar(id_usuario, discos_relevantes, discos_desconocidos, N=9):
    if len(discos_desconocidos) < N:
        N = len(discos_desconocidos)
    if N == 0:
        return []
    id_discos = random.sample(discos_desconocidos, N)
    return id_discos


def recomendar(id_usuario, discos_relevantes=None, discos_desconocidos=None, N=9):
    if not discos_relevantes:
        discos_relevantes = items_valorados(id_usuario)

    if not discos_desconocidos:
        discos_desconocidos = items_desconocidos(id_usuario)

    return recomendar_azar(id_usuario, discos_relevantes, discos_desconocidos, N)


def recomendar_contexto(
    id_usuario, id_disco, discos_relevantes=None, discos_desconocidos=None, N=3
):
    if not discos_relevantes:
        discos_relevantes = items_valorados(id_usuario)

    if not discos_desconocidos:
        discos_desconocidos = items_desconocidos(id_usuario)

    return recomendar_azar(id_usuario, discos_relevantes, discos_desconocidos, N)


###


def test(id_usuario):
    discos_relevantes = items_valorados(id_usuario)
    discos_desconocidos = items_vistos(id_usuario) + items_desconocidos(id_usuario)

    random.shuffle(discos_relevantes)

    corte = int(len(discos_relevantes) * 0.8)
    discos_relevantes_training = discos_relevantes[:corte]
    discos_relevantes_testing = discos_relevantes[corte:] + discos_desconocidos

    recomendacion = recomendar(
        id_usuario, discos_relevantes_training, discos_relevantes_testing, 20
    )

    relevance_scores = []
    for id_disco in recomendacion:
        res = sql_select(
            "SELECT rating FROM interactions WHERE user_id = ? AND item_id = ?;",
            [id_usuario, id_disco],
        )
        if res is not None and len(res) > 0:
            rating = res[0][0]
        else:
            rating = 0

        relevance_scores.append(rating)
    score = metricas.normalized_discounted_cumulative_gain(relevance_scores)
    return score


if __name__ == "__main__":
    id_usuarios = sql_select(
        "SELECT user_id FROM users WHERE ("
        "SELECT count(*) FROM interactions WHERE user_id = users.user_id"
        ") >= 100 limit 50;"
    )
    id_usuarios = [i["user_id"] for i in id_usuarios]

    scores = []
    for id_usuario in id_usuarios:
        score = test(id_usuario)
        scores.append(score)
        print("{} >> {:.6f}".format(id_usuario, score))

    print("NDCG: {:.6f}".format(sum(scores) / len(scores)))
