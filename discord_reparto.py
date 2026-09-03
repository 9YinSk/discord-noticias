#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_reparto.py — en cuánto se dividió la gente, con números que son ciertos.

Una noticia con un titular y un enlace no engancha. Lo que engancha es saber que
**el 67% salió encantado y el 31% puso el grito en el cielo**, y por qué cada
uno. Eso es lo que se prepara aquí.

La regla de la casa, y es lo único que importa de este archivo:

    **La IA etiqueta opiniones de una en una. Los porcentajes los cuenta Python.**

Nunca se le pide a un modelo «dime qué porcentaje aprobó»: eso es pedirle que se
invente una estadística, y se la inventa — con una seguridad preciosa. Lo que se
le pide es lo que sí sabe hacer: leer un comentario y decir si va a favor, en
contra o le da igual. Contar los votos es una división, y una división no se
alucina.

De dónde salen los números, por orden de calidad:

  1. **Las notas de AniList.** Miles de personas que ya puntuaron del 10 al 100.
     No hay que interpretarlas: 70 o más es que gustó, 50-60 es tibio, 40 o
     menos es que no. Es la mejor fuente que hay y no gasta ni una llamada a la
     IA.
  2. **Las reseñas de Steam.** La tienda publica cuántas son positivas y cuántas
     negativas, de verdad, en su API. Ahí no hay tibios --Steam no los
     admite--, así que se dice en dos trozos y no se finge un tercero.
  3. **Los comentarios de Reddit.** Cuando hay hilo. Aquí sí clasifica la IA,
     uno por uno, y luego se cuentan.

Y si no hay ninguna de las tres, **no hay reparto**. Se dice que no se sabe y
queda la encuesta para que lo diga la gente de aquí. Un porcentaje inventado
aguanta bien una semana; el día que alguien lo comprueba se cae la sección
entera, y con ella la confianza en todo lo demás que publicamos.

    python discord_reparto.py "Frieren" --tema anime
"""
import argparse
import json
import os
import re
import sys
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Cuántas opiniones hacen falta para que un porcentaje signifique algo. Con 7
# comentarios, uno solo mueve el resultado 14 puntos: eso no es «cómo se dividió
# internet», es ruido con decimales.
MINIMO = 12


def _pct(cuenta):
    """Tres porcentajes que suman 100 exactos.

    Redondear cada uno por su cuenta da 33+33+33=99, y un reparto que no suma
    cien se ve mal en la barra y peor en el texto. El sobrante va al que más
    decimal perdió.
    """
    total = sum(cuenta)
    if not total:
        return (0, 0, 0)
    crudo = [c * 100 / total for c in cuenta]
    ent = [int(x) for x in crudo]
    orden = sorted(range(len(crudo)), key=lambda i: crudo[i] - ent[i], reverse=True)
    for k in range(100 - sum(ent)):
        ent[orden[k % len(orden)]] += 1
    return tuple(ent)


def de_anilist(notas):
    """El reparto salido de las notas que ya puso la gente en AniList.

    `notas` es [(score, cuántos), ...] con score de 10 en 10. Los cortes:
    **70+ gustó, 50-60 tibio, 40- no gustó**. Son los mismos con los que AniList
    pinta su gráfico en verde, amarillo y rojo, así que a quien entre a
    comprobarlo le van a cuadrar.
    """
    if not notas:
        return None
    bien = sum(c for s, c in notas if s >= 70)
    tibio = sum(c for s, c in notas if 50 <= s <= 60)
    mal = sum(c for s, c in notas if s <= 40)
    n = bien + tibio + mal
    if n < MINIMO:
        return None
    return {"pct": _pct((bien, tibio, mal)), "n": n,
            "fuente": "notas de AniList", "url": None, "razones": {}}


def de_steam(appid):
    """Las reseñas de Steam. La tienda da los totales; no hay que estimar nada.

    Steam **no tiene término medio**: o pulgar arriba o pulgar abajo. Así que
    esto devuelve dos trozos y el del medio a cero, y quien lo lea verá que pone
    «reseñas de Steam» y entenderá por qué no hay tibios. Fingir un 2% de
    indiferentes para que salgan tres sería inventarse justo lo que no existe.
    """
    try:
        u = (f"https://store.steampowered.com/appreviews/{appid}"
             "?json=1&language=all&purchase_type=all&num_per_page=0")
        with urllib.request.urlopen(u, timeout=12) as r:
            d = json.load(r).get("query_summary") or {}
    except Exception:                                   # noqa: BLE001
        return None
    bien, mal = d.get("total_positive", 0), d.get("total_negative", 0)
    if bien + mal < MINIMO:
        return None
    return {"pct": _pct((bien, 0, mal)), "n": bien + mal,
            "fuente": "reseñas de Steam", "razones": motivos_steam(appid),
            "url": f"https://store.steampowered.com/app/{appid}/"}


def _resenas(appid, tipo, cuantas=25):
    """Reseñas con texto de un lado, las que la gente marcó como más útiles.

    **En todos los idiomas a propósito.** Se probó pidiendo solo español y lo
    que llega son chistes: recetas de tacos, insultos y notas de 10/10 porque
    un personaje no sale desnudo. Ordenadas por utilidad y sin filtro de idioma
    salen las que explican algo, y el resumen se escribe igual en español.
    """
    try:
        u = (f"https://store.steampowered.com/appreviews/{appid}?json=1"
             f"&filter=all&language=all&purchase_type=all"
             f"&num_per_page={cuantas}&review_type={tipo}")
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
    except Exception:                                   # noqa: BLE001
        return []
    return [x["review"].strip() for x in (d.get("reviews") or [])
            if x.get("review") and len(x["review"].strip()) > 40]


def motivos_steam(appid):
    """Por qué gustó y por qué no, resumido de reseñas de verdad.

    Los porcentajes de Steam vienen de sus totales --cientos de miles de votos--
    pero esos totales no dicen el porqué. El porqué sale de una muestra de las
    reseñas más útiles, y **solo como resumen**: no se cita ninguna literal.
    Entre las mejor valoradas hay bromas privadas y barbaridades, y una cita
    textual de eso en el canal de noticias es un problema, no un adorno.
    """
    import discord_ia as ia
    if not ia.disponible():
        return {}
    fuera = {}
    for tipo, clave in (("positive", "gusto"), ("negative", "no")):
        t = _resenas(appid, tipo)
        if len(t) < 4:
            continue
        x = ia.pedir(_RAZONES, "\n\n---\n\n".join(t)[:5000], tope=60,
                     temperatura=0.3)
        if x and not x.strip().upper().startswith("NADA"):
            fuera[clave] = x.strip().rstrip(".")
    return fuera


_CLASIFICA = """Eres un clasificador. Te doy comentarios sobre una noticia,
numerados. Para CADA UNO responde una sola letra:

  G  si le gusta / lo celebra / lo defiende
  I  si le da igual, no opina, pregunta, o solo aporta un dato
  N  si no le gusta / se queja / lo critica

Responde SOLO las letras separadas por comas, en el mismo orden y la misma
cantidad que los comentarios. Nada mas. Ejemplo: G,N,I,G,N"""

_RAZONES = """Te doy opiniones sobre algo, todas del mismo bando.
Resume EN UNA FRASE CORTA en espanol (maximo 11 palabras) el motivo de fondo que
mas se repite. Sin comillas, sin "los usuarios", directo al motivo.

IGNORA las bromas, las resenas absurdas, los insultos y lo que no hable del
tema. NO cites ni reproduzcas nada literal, ni groserias, ni nada ofensivo:
escribe tu propia frase, neutra y publicable. Si lo unico que hay son chistes o
no ves un motivo claro, responde NADA."""


def de_comentarios(comentarios, ia):
    """Clasifica comentarios de verdad, uno por uno, y luego cuenta.

    Van en un solo viaje y numerados: así el modelo no puede escaquearse
    resumiendo, tiene que devolver tantas letras como comentarios le diste. **Si
    devuelve otra cantidad se tira la respuesta entera** — que devuelva de menos
    significa que se saltó alguno, y entonces ya no sabemos cuál es cuál.
    """
    textos = [c for c in comentarios if c and len(c.strip()) > 12][:60]
    if len(textos) < MINIMO or not ia.disponible():
        return None
    numerado = "\n\n".join(f"[{i+1}] {t[:400]}" for i, t in enumerate(textos))
    r = ia.pedir(_CLASIFICA, numerado, tope=1200, temperatura=0)
    if not r:
        return None
    letras = [x.strip().upper()[:1] for x in re.split(r"[,\s]+", r.strip()) if x.strip()]
    letras = [x for x in letras if x in ("G", "I", "N")]
    if len(letras) != len(textos):
        return None                                     # descuadre: no vale
    grupos = {"G": [], "I": [], "N": []}
    for texto, letra in zip(textos, letras):
        grupos[letra].append(texto)
    # **Un motivo hace falta un grupo, no tres comentarios sueltos.** Con el
    # tope en 3 salio publicado un «12% les gusto -- falta de claridad y
    # complejidad innecesaria»: el motivo de los que SI, redactado con quejas.
    # De tres opiniones no se saca lo que piensa un bando, se saca ruido con
    # forma de frase. Se pide un minimo de cinco y ademas que sean al menos la
    # sexta parte de la muestra, para que el grupo pese algo de verdad.
    razones = {}
    for letra, clave in (("G", "gusto"), ("I", "igual"), ("N", "no")):
        if len(grupos[letra]) >= max(5, len(textos) // 6):
            x = ia.pedir(_RAZONES, "\n\n---\n\n".join(grupos[letra])[:4000],
                         tope=60, temperatura=0.3)
            if x and not x.strip().upper().startswith("NADA"):
                razones[clave] = x.strip().rstrip(".")
    return {"pct": _pct((len(grupos["G"]), len(grupos["I"]), len(grupos["N"]))),
            "n": len(textos), "fuente": "comentarios de Reddit",
            "url": None, "razones": razones}


def reparto(veredicto=None, comentarios=None, appid=None):
    """El mejor reparto que se pueda conseguir, o `None` si no hay ninguno.

    Por orden: las notas de AniList (miles de votos, gratis), las reseñas de
    Steam (totales reales), y por último los comentarios (que cuestan una
    llamada a la IA y traen muchas menos opiniones). El orden es ese porque una
    muestra de cuarenta mil notas describe mejor «cómo se dividió la gente» que
    cuarenta comentarios de un hilo, por buenos que sean los comentarios.
    """
    import discord_ia as ia
    if veredicto and veredicto.get("notas"):
        r = de_anilist(veredicto["notas"])
        if r:
            r["url"] = veredicto.get("url")
            return r
    if appid:
        r = de_steam(appid)
        if r:
            return r
    if comentarios:
        return de_comentarios(comentarios, ia)
    return None


def en_texto(r):
    """El reparto escrito, para el mensaje. Con la muestra siempre a la vista.

    Decir «67%» sin decir de cuántos es la mitad de la información: no es lo
    mismo 67 de cuarenta mil personas que 67 de doce. Va delante, no en letra
    chica.
    """
    if not r:
        return None
    g, i, n = r["pct"]
    razon = r.get("razones") or {}
    filas = []
    for pct, clave, cara, cae in ((g, "gusto", "\U0001F7E9", "les gustó"),
                                  (i, "igual", "\U0001F7E8", "les da igual"),
                                  (n, "no", "\U0001F7E5", "no les gustó")):
        if pct == 0 and clave == "igual":
            continue                                    # Steam no tiene tibios
        linea = f"{cara} **{pct}%** {cae}"
        if razon.get(clave):
            linea += f" — {razon[clave]}"
        filas.append(linea)
    cab = f"De **{r['n']:,}** opiniones ({r['fuente']})".replace(",", ".")
    return cab + "\n" + "\n".join(filas)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("titular")
    ap.add_argument("--tema", default="anime")
    a = ap.parse_args()
    import discord_publico as publico
    ver = publico.veredicto(a.titular, a.tema)
    if isinstance(ver, tuple):
        ver = None
    print(en_texto(reparto(veredicto=ver))
          or "Sin material suficiente: aquí no iría reparto.")


if __name__ == "__main__":
    main()
