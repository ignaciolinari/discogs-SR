from flask import Flask, make_response, redirect, render_template, request

import recomendar

app = Flask(__name__)


@app.get("/")
def get_index():
    return render_template("login.html")


@app.post("/")
def post_index():
    id_usuario = request.form.get("id_usuario", None)

    if id_usuario:  # si me mandaron el id_usuario
        recomendar.crear_usuario(id_usuario)

        # mando al usuario a la página de recomendaciones
        res = make_response(redirect("/recomendaciones"))

        # pongo el id_usuario en una cookie para recordarlo
        res.set_cookie(
            "id_usuario",
            id_usuario,
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
        )
        return res

    # sino, le muestro el formulario de login
    return render_template("login.html")


@app.get("/recomendaciones")
def get_recomendaciones():
    id_usuario = request.cookies.get("id_usuario")

    if not recomendar.usuario_existe(id_usuario):
        return redirect("/")

    id_discos = recomendar.recomendar(id_usuario)

    # pongo discos vistos con rating = 0
    for id_disco in id_discos:
        recomendar.insertar_interacciones(id_disco, id_usuario, 0)

    discos_recomendados = recomendar.datos_discos(id_discos)

    # Filtrar discos sin título o artista válidos
    discos_recomendados = [
        disco
        for disco in discos_recomendados
        if disco["title"]
        and disco["title"].strip()
        and disco["artist"]
        and disco["artist"].strip()
    ]

    cant_valorados = len(recomendar.items_valorados(id_usuario))
    cant_vistos = len(recomendar.items_vistos(id_usuario))

    return render_template(
        "recomendaciones.html",
        discos_recomendados=discos_recomendados,
        id_usuario=id_usuario,
        cant_valorados=cant_valorados,
        cant_vistos=cant_vistos,
    )


@app.get("/recomendaciones/<string:id_disco>")
def get_recomendaciones_disco(id_disco):
    id_usuario = request.cookies.get("id_usuario")

    if not recomendar.usuario_existe(id_usuario):
        return redirect("/")

    id_discos = recomendar.recomendar_contexto(id_usuario, id_disco)

    # pongo discos vistos con rating = 0
    for id_disco_rec in id_discos:
        recomendar.insertar_interacciones(id_disco_rec, id_usuario, 0)

    discos_recomendados = recomendar.datos_discos(id_discos)

    # Filtrar discos sin título o artista válidos
    discos_recomendados = [
        disco
        for disco in discos_recomendados
        if disco["title"]
        and disco["title"].strip()
        and disco["artist"]
        and disco["artist"].strip()
    ]

    cant_valorados = len(recomendar.items_valorados(id_usuario))
    cant_vistos = len(recomendar.items_vistos(id_usuario))

    disco = recomendar.obtener_disco(id_disco)
    if disco is None:
        return redirect("/recomendaciones")

    return render_template(
        "recomendaciones_disco.html",
        disco=disco,
        discos_recomendados=discos_recomendados,
        id_usuario=id_usuario,
        cant_valorados=cant_valorados,
        cant_vistos=cant_vistos,
    )


@app.post("/recomendaciones")
def post_recomendaciones():
    id_usuario = request.cookies.get("id_usuario")

    if not recomendar.usuario_existe(id_usuario):
        return redirect("/")

    # inserto los ratings enviados como interacciones
    for id_disco in request.form.keys():
        rating = int(request.form[id_disco])
        if rating > 0:  # 0 es que no puntuó
            recomendar.insertar_interacciones(id_disco, id_usuario, rating)

    return make_response(redirect("/recomendaciones"))


@app.get("/reset")
def get_reset():
    id_usuario = request.cookies.get("id_usuario")

    if not recomendar.usuario_existe(id_usuario):
        return redirect("/")

    recomendar.reset_usuario(id_usuario)

    return make_response(redirect("/recomendaciones"))


if __name__ == "__main__":
    app.run()
