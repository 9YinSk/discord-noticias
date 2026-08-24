#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_opiniones.py — qué opina la gente de un anime o de un juego.

Un canal de noticias es un muro de titulares: dice qué ha salido, no si vale la
pena. Esto es lo otro — **el veredicto de la gente**, con la nota, cuántos han
votado y **citas reales** de reseñas, cada una con su autor.

No se inventa nada ni se resume con IA: se cita a quien lo escribió y se enlaza
su reseña. Si alguien dice que un juego es una porquería, sale tal cual.

De dónde salen los datos, y las dos son **gratis y sin clave**:

  anime  » **AniList** (GraphQL). Nota media sobre 100, popularidad y reseñas
  juego  » **Steam** (`appreviews`). El veredicto oficial —«Muy positivas»—,
           el recuento y reseñas de usuario **en español**

    python discord_opiniones.py anime "Frieren"
    python discord_opiniones.py juego "Hollow Knight" --enserio
    python discord_opiniones.py juego "Hades" --canal sugerido --enserio

Jikan (la API de MyAnimeList) se probó primero y devolvía **504 sin parar**, así
que el anime va por AniList, que responde a la primera.
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from discord_servidor import api  # noqa: E402
from discord_botones import boton, buscar_en_youtube, publicar  # noqa: E402
import discord_ia as ia  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GUILD = "1539896304178823282"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126"}
_TAG = re.compile(r"<[^>]+>")


def limpio(t, tope=None):
    t = " ".join(html.unescape(_TAG.sub(" ", t or "")).split())
    if tope and len(t) > tope:
        t = t[:tope].rsplit(" ", 1)[0] + "…"
    return t


def pedir(url, cuerpo=None, cabeceras=None):
    req = urllib.request.Request(url, data=cuerpo, headers={**UA, **(cabeceras or {})})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def barra(pct, ancho=14):
    """Una barra de bloques. En Discord es texto, así que se ve en todas partes."""
    llenos = round(pct / 100 * ancho)
    return "█" * llenos + "░" * (ancho - llenos)


# ------------------------------------------------------------------- ANIME
CONSULTA = """
query($s:String){ Media(search:$s, type:ANIME){
  title{romaji english} averageScore meanScore popularity episodes status
  coverImage{large} siteUrl genres
  reviews(perPage:3, sort:RATING_DESC){ nodes{ summary score user{name} siteUrl } }
}}"""


def opinion_anime(nombre):
    d = pedir("https://graphql.anilist.co",
              json.dumps({"query": CONSULTA, "variables": {"s": nombre}}).encode(),
              {"Content-Type": "application/json"})
    m = (d.get("data") or {}).get("Media")
    if not m:
        return None
    titulo = m["title"].get("english") or m["title"]["romaji"]
    nota = m.get("averageScore") or 0
    campos = []
    for r in m["reviews"]["nodes"]:
        campos.append({
            "name": f"{r['user']['name']}  —  {r['score']}/100",
            "value": f"[{limpio(r['summary'], 170)}]({r['siteUrl']})",
            "inline": False,
        })
    resumen = ia.resumir_opiniones([r["summary"] for r in m["reviews"]["nodes"]])
    if resumen:
        campos.insert(0, {"name": "En resumen", "value": resumen, "inline": False})
    return {
        "author": {"name": "Lo que opina la gente  ·  AniList"},
        "title": titulo,
        "url": m["siteUrl"],
        "color": 0x02A9FF,
        "description": (f"**{nota}/100**   `{barra(nota)}`\n"
                        f"-# {m.get('popularity', 0):,} personas lo tienen en su lista"
                        .replace(",", ".")),
        "thumbnail": {"url": m["coverImage"]["large"]},
        "fields": campos,
        "footer": {"text": limpio(" · ".join(
            [x for x in [" · ".join(m.get("genres") or []),
                         ia.AVISO if resumen else ""] if x])[:100])},
    }


# ------------------------------------------------------------------- JUEGO
VEREDICTO = {
    "Overwhelmingly Positive": "Abrumadoramente positivas",
    "Very Positive": "Muy positivas", "Positive": "Positivas",
    "Mostly Positive": "Mayormente positivas", "Mixed": "Variadas",
    "Mostly Negative": "Mayormente negativas", "Negative": "Negativas",
    "Very Negative": "Muy negativas",
    "Overwhelmingly Negative": "Abrumadoramente negativas",
}


def opinion_juego(nombre):
    # la búsqueda de la tienda, en soles y en español
    q = urllib.parse.quote(nombre)
    b = pedir(f"https://store.steampowered.com/api/storesearch/?term={q}"
              f"&cc=pe&l=spanish")
    if not b.get("items"):
        return None
    j = b["items"][0]
    d = pedir(f"https://store.steampowered.com/appreviews/{j['id']}?json=1"
              f"&language=spanish&num_per_page=3&purchase_type=all"
              f"&review_type=all&filter=all")
    s = d.get("query_summary") or {}
    total, pos = s.get("total_reviews", 0), s.get("total_positive", 0)
    pct = round(pos / total * 100) if total else 0
    campos = []
    for r in (d.get("reviews") or [])[:3]:
        horas = round((r.get("author") or {}).get("playtime_forever", 0) / 60)
        campos.append({
            "name": f"{'👍 Recomendado' if r['voted_up'] else '👎 No lo recomienda'}"
                    f"  —  {horas} h jugadas",
            "value": limpio(r["review"], 200) or "*(sin texto)*",
            "inline": False,
        })
    resumen = ia.resumir_opiniones([r["review"] for r in (d.get("reviews") or [])])
    if resumen:
        campos.insert(0, {"name": "En resumen", "value": resumen, "inline": False})
    precio = (j.get("price") or {}).get("final")
    pie = [VEREDICTO.get(s.get("review_score_desc", ""), s.get("review_score_desc", ""))]
    if precio is not None:
        pie.append("Gratis" if precio == 0 else f"S/ {precio / 100:.2f}")
    if resumen:
        pie.append(ia.AVISO)
    return {
        "author": {"name": "Lo que opina la gente  ·  Steam"},
        "title": j["name"],
        "url": f"https://store.steampowered.com/app/{j['id']}/",
        "color": 0x66C0F4,
        "description": (f"**{pct}% positivas**   `{barra(pct)}`\n"
                        f"-# {pos:,} de {total:,} reseñas".replace(",", ".")),
        "thumbnail": {"url": j.get("tiny_image")},
        "fields": campos,
        "footer": {"text": " · ".join(x for x in pie if x)},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("que", choices=["anime", "juego"])
    p.add_argument("nombre")
    p.add_argument("--canal", default=None,
                   help="un trozo del nombre del canal; por defecto, el que toca")
    p.add_argument("--enserio", action="store_true")
    args = p.parse_args()

    e = (opinion_anime if args.que == "anime" else opinion_juego)(args.nombre)
    if not e:
        sys.exit(f"No encuentro «{args.nombre}» como {args.que}.")

    # El botón de la ficha **sale solo** del `url` del embed (lo pone `publicar`).
    # Aquí van los de al lado: las reseñas enteras y el tráiler, que es lo que
    # más se busca después de leer una nota.
    if args.que == "anime":
        extra = [boton(e["url"] + "/reviews", "Leer las reseñas", "💬"),
                 boton(buscar_en_youtube(f"{e['title']} anime trailer"),
                       "Ver el tráiler", "▶️")]
    else:
        extra = [boton(e["url"] + "#app_reviews_hash", "Todas las reseñas", "💬"),
                 boton(buscar_en_youtube(f"{e['title']} gameplay"),
                       "Ver cómo se juega", "▶️")]

    print(f"  {e['title']}")
    print(f"  {limpio(e['description'])}")
    for c in e["fields"]:
        print(f"    · {c['name']}\n      {limpio(c['value'], 90)}")
    if not args.enserio:
        print("\n>>> SIMULACRO. Agrega --enserio para publicarlo.")
        return

    trozo = args.canal or ("noticias-anime" if args.que == "anime"
                           else "noticias-gaming")
    cid = next((c["id"] for c in api("GET", f"/guilds/{GUILD}/channels")
                if trozo in c["name"]), None)
    if not cid:
        sys.exit(f"No encuentro un canal con «{trozo}» en el nombre.")
    publicar(cid, e, extra)
    print(f"\npublicado en el canal de «{trozo}»")


if __name__ == "__main__":
    main()
