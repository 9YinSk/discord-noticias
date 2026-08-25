#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_publico.py — qué está diciendo la gente de una noticia, de verdad.

Una noticia es un titular y un enlace. Eso está bien para enterarse y **es
aburrido**: no dice si la cosa gustó, si hubo bronca, ni por qué. Lo que engancha
de una noticia es lo de después — que medio internet la celebró y la otra mitad
la puso a parir, y cuál era el argumento de cada lado.

Esto va a buscar eso. Baja lo que se ha escrito estos días en los subreddits que
tocan, **cruza cada noticia con ese material** y deja los comentarios de verdad,
con su puntuación, para que la IA cuente en qué se dividió la gente.

**Por qué así y no buscando cada titular.** El archivo (Arctic Shift, el sucesor
público de Pushshift) tiene dos formas de consultar y se portan al revés de lo
que uno espera: **por índice** —dame lo último de r/anime— responde en segundos,
y **por texto** —busca «Frieren»— devuelve `422` siempre, esté saturado o no.
Así que no se busca: se baja el listado una sola vez por subreddit y se filtra
**aquí**, en local. Encima sale gratis el `score` de cada comentario, que es lo
que separa una opinión que la gente comparte de un señor gritando solo.

Y se baja **una vez por pasada, no una vez por noticia**. Con 8 feeds y 3
noticias cada uno serían 24 rastreos; así son 6, y las 24 noticias se cruzan
contra el mismo material sin tocar la red.

    python discord_publico.py "Frieren temporada 2"
    python discord_publico.py "Hollow Knight Silksong" --horas 168
"""
import argparse
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from leer_reddit import (bajar_listado, pedir, TOPE_LIMITE,  # noqa: E402
                         CAMPOS_POST, CAMPOS_COMENTARIO)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Dónde se habla de lo que publicamos. Uno por tema, no más: cada uno cuesta una
# bajada, y los grandes ya traen de sobra.
SUBS = {
    "anime": ["anime", "Animedubs"],
    "juegos": ["Games", "gaming"],
    "cine": ["movies", "television"],
    "ofertas": ["GameDeals"],
}

# Palabras que aparecen en todos los titulares y no distinguen nada. Sin esta
# lista, «la» y «de» casan con cualquier comentario y el cruce da basura.
VACIAS = set("""
a al algo ahora ante antes aqui asi aun cada como con contra cual cuando de del
desde donde dos el ella ellos en entre era eres es esa ese eso esta este esto
fue ha han hasta hay la las le les lo los mas me mi mientras muy no nos nueva
nuevo o os para pero por porque que quien se ser si sin sobre solo son su sus
tambien te tiene todo tras tu un una uno unos y ya
about after all also and are as at be been but by can for from has have his how
in into is it its just like more new not now of on one or out over new season
that the their there they this to trailer up was were what when which who will
with you your
""".split())

_LIMPIA = re.compile(r"[^\w\sáéíóúüñÁÉÍÓÚÜÑ']", re.U)


def claves(titular, minimo=4):
    """Las palabras del titular que sirven para reconocerlo en otro texto.

    Se quedan las **largas y raras**: los nombres propios, que son los que de
    verdad identifican de qué va la noticia. Un titular sin ninguna palabra así
    —«Ya está aquí lo nuevo de la semana»— devuelve lista vacía, y entonces no se
    cruza nada: mejor no decir nada que inventarse una relación.
    """
    palabras = _LIMPIA.sub(" ", titular or "").split()
    return [p for p in palabras
            if len(p) >= minimo and p.lower() not in VACIAS and not p.isdigit()]


def pozo(tema, horas=72, paginas=2, callado=False):
    """Todo lo escrito últimamente en los subreddits de un tema.

    Es el material contra el que se cruzan **todas** las noticias de esa pasada.
    Los comentarios son mucho más densos que los posts —100 posts cubren semanas,
    100 comentarios apenas unas horas—, así que se bajan las dos cosas: los posts
    dan cobertura y los comentarios dan opinión.
    """
    ahora = int(time.time())
    desde = ahora - horas * 3600
    material = []
    for sub in SUBS.get(tema, []):
        if not callado:
            print(f"  bajando r/{sub}...")
        for ruta, campos, clase in (("/posts/search", CAMPOS_POST, "post"),
                                    ("/comments/search", CAMPOS_COMENTARIO, "com")):
            for x in bajar_listado(ruta, campos, sub, desde, ahora, paginas):
                texto = (x.get("title", "") + " " + (x.get("selftext") or "")
                         if clase == "post" else (x.get("body") or ""))
                if texto.strip() in ("", "[removed]", "[deleted]"):
                    continue
                hilo = (x.get("link_id") or "").replace("t3_", "") or x.get("id")
                material.append({
                    "texto": texto.strip(),
                    "score": x.get("score") or 0,
                    "sub": sub,
                    "url": f"https://reddit.com/comments/{hilo}",
                })
    return material


def cruzar(titular, material, minimo_claves=2, cuantos=14):
    """Lo que se ha dicho sobre **esta** noticia, de todo lo que se bajó.

    Se exige que casen **dos** palabras clave, no una. Con una sola, «Nintendo»
    ata cualquier comentario del sub a cualquier noticia de Nintendo, y el
    resumen sale hablando de otra cosa con mucha seguridad — que es la peor
    manera de equivocarse.
    """
    ks = [k.lower() for k in claves(titular)]
    if len(ks) < minimo_claves:
        return []
    hits = []
    for m in material:
        t = m["texto"].lower()
        n = sum(1 for k in ks if k in t)
        if n >= minimo_claves:
            hits.append((n, m))
    # primero lo que más coincide, y a igualdad lo que más gente respaldó
    hits.sort(key=lambda x: (-x[0], -x[1]["score"]))
    return [m for _, m in hits[:cuantos]]


def comentarios_del_hilo(post_id, cuantos=60):
    """Los comentarios de UN hilo concreto, sin el bot de turno.

    Aquí está la señal buena. Rastrear el subreddit entero y quedarse con lo que
    mencione la noticia da dos o tres frases sueltas —medido: 2 de 374—, porque
    la gente no repite el titular, **responde debajo de él**. En cambio el hilo
    de esa noticia trae la discusión entera y ordenada por votos, que es
    exactamente «en qué se dividió la gente».
    """
    datos = pedir("/comments/search",
                  {"link_id": post_id, "limit": min(cuantos, TOPE_LIMITE),
                   "sort": "desc"}) or []
    fuera = ("AutoModerator", "[deleted]")
    vivos = [c for c in datos
             if c.get("author") not in fuera
             and (c.get("body") or "").strip() not in ("", "[removed]", "[deleted]")]
    vivos.sort(key=lambda c: -(c.get("score") or 0))
    return [{"texto": c["body"].strip(), "score": c.get("score") or 0,
             "autor": c.get("author", "?")} for c in vivos]


_CACHE_POSTS = {}

# **Presupuesto de tiempo para toda la pasada.** Esto no es lo importante de
# publicar una noticia: es el adorno. El archivo es comunitario y gratuito, y
# cuando va lento sus reintentos con espera creciente pueden tardar minutos por
# consulta. Sin un tope, un mal día del archivo deja colgada la publicación
# entera — y las noticias sí importan. Pasado el tope, se deja de buscar debate
# y las noticias siguen saliendo, solo que sin esa sección.
PRESUPUESTO = 150.0
_ARRANQUE = [None]


def queda_tiempo():
    if _ARRANQUE[0] is None:
        _ARRANQUE[0] = time.time()
    return time.time() - _ARRANQUE[0] < PRESUPUESTO


def posts_de(tema, horas=72, paginas=2, callado=True):
    """Lo publicado últimamente en los subreddits de un tema. **Se cachea.**

    Aquí está el ahorro que hace esto viable: con 8 feeds y 3 noticias cada uno
    hay 24 titulares por pasada, y bajar el listado para cada uno serían 24
    rastreos de dos páginas. Se baja **una vez por tema** y los 24 titulares se
    cruzan contra el mismo material sin volver a tocar la red.
    """
    clave_c = (tema, horas, paginas)
    if clave_c in _CACHE_POSTS:
        return _CACHE_POSTS[clave_c]
    ahora = int(time.time())
    posts = []
    for sub in SUBS.get(tema, []):
        if not callado:
            print(f"  bajando r/{sub}...")
        posts += bajar_listado("/posts/search", CAMPOS_POST, sub,
                               ahora - horas * 3600, ahora, paginas)
    _CACHE_POSTS[clave_c] = posts
    return posts


def debate(titular, tema="anime", horas=72, paginas=2, callado=True):
    """El hilo que habla de esta noticia y lo que se dijo dentro.

    Devuelve `(hilo, comentarios)`. Sin hilo no hay debate: se devuelve
    `(None, [])` y quien llame **no escribe nada**, que es lo correcto. Una
    noticia sin repercusión es una noticia sin repercusión; rellenarla con una
    frase de relleno se nota a la tercera y hace que dejen de leerse todas.
    """
    if not queda_tiempo():
        return None, []
    posts = posts_de(tema, horas, paginas, callado)
    ks = [k.lower() for k in claves(titular)]
    if len(ks) < 2:
        return None, []
    mejores = []
    for p in posts:
        titulo = p.get("title") or ""
        if "Removed by moderator" in titulo:
            continue
        n = sum(1 for k in ks if k in titulo.lower())
        if n >= 2:
            mejores.append((n, p))
    if not mejores:
        return None, []

    # **No se puede ordenar por `num_comments`.** El archivo guarda el post tal
    # como nació, así que ese campo vale 0 o 2 en todos: los comentarios llegan
    # después y se guardan aparte. Medido: hilos con 60 comentarios de verdad
    # figuraban con 2. La única forma de saber cuál se habló es **preguntar por
    # los comentarios de cada candidato**, y por eso solo se miran los 3 que
    # mejor casan — no los 40.
    mejores.sort(key=lambda x: -x[0])
    mejor, suyos = None, []
    for _, p in mejores[:3]:
        if not queda_tiempo():
            break
        cs = comentarios_del_hilo(p["id"])
        if not callado:
            print(f"  candidato: «{p.get('title', '')[:62]}» — {len(cs)} coment.")
        if len(cs) > len(suyos):
            mejor, suyos = p, cs
        time.sleep(0.6)
    if len(suyos) < 4:
        return None, []          # cuatro frases no son «en qué se dividió la gente»
    return mejor, suyos


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("titular")
    p.add_argument("--tema", default="anime", choices=sorted(SUBS))
    p.add_argument("--horas", type=int, default=72)
    p.add_argument("--paginas", type=int, default=2)
    args = p.parse_args()

    print(f"claves: {claves(args.titular)}\n")
    hilo, coments = debate(args.titular, args.tema, args.horas, args.paginas,
                           callado=False)
    if not hilo:
        print("  no encuentro ningún hilo que hable de esto. No se escribe nada.")
        return
    print(f"\n{len(coments)} comentarios vivos\n")
    for c in coments[:10]:
        print(f"  [{c['score']:>5} pts] {c['texto'][:150]}")


if __name__ == "__main__":
    main()
