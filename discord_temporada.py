#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_temporada.py — lo mejor valorado de la temporada de anime, cada lunes.

Un canal de noticias cuenta lo que ha salido. Esto cuenta **qué está gustando**,
que es otra cosa: la nota que le pone la gente, en orden, con su portada.

Los datos son de **AniList**, gratis y sin clave. Se pide la temporada en curso
ordenada por puntuación, y se publica el podio con lo que la gente está viendo de
verdad — no lo que más ruido hace.

Va con `discord_opiniones.py` pero al revés: aquel responde «qué opinan de esto»
cuando preguntas por algo; este dice «esto es lo que está gustando» sin que
nadie pregunte.

    python discord_temporada.py                 # simulacro
    python discord_temporada.py --enserio
    python discord_temporada.py --enserio --cuantos 8
"""
import argparse
import datetime
import json
import os
import sys
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from discord_servidor import api  # noqa: E402
import discord_ia as ia  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GUILD = "1539896304178823282"
CANAL = "noticias-anime"

CONSULTA = """
query($temporada:MediaSeason, $anio:Int, $n:Int){
  Page(perPage:$n){
    media(season:$temporada, seasonYear:$anio, type:ANIME, format:TV,
          sort:SCORE_DESC, isAdult:false){
      title{romaji english} averageScore popularity episodes siteUrl
      coverImage{large} genres studios(isMain:true){nodes{name}}
    }
  }
}"""

ESTACION = {12: "WINTER", 1: "WINTER", 2: "WINTER",
            3: "SPRING", 4: "SPRING", 5: "SPRING",
            6: "SUMMER", 7: "SUMMER", 8: "SUMMER",
            9: "FALL", 10: "FALL", 11: "FALL"}
EN_CASTELLANO = {"WINTER": "invierno", "SPRING": "primavera",
                 "SUMMER": "verano", "FALL": "otoño"}
MEDALLA = ["🥇", "🥈", "🥉"]


def temporada_actual():
    """La estación de hoy. En diciembre ya cuenta como el invierno del año que viene."""
    hoy = datetime.date.today()
    est = ESTACION[hoy.month]
    anio = hoy.year + 1 if hoy.month == 12 else hoy.year
    return est, anio


def barra(pct, ancho=12):
    llenos = round(pct / 100 * ancho)
    return "█" * llenos + "░" * (ancho - llenos)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--enserio", action="store_true")
    p.add_argument("--cuantos", type=int, default=5)
    args = p.parse_args()

    est, anio = temporada_actual()
    cuerpo = json.dumps({"query": CONSULTA,
                         "variables": {"temporada": est, "anio": anio,
                                       "n": args.cuantos}}).encode()
    req = urllib.request.Request("https://graphql.anilist.co", data=cuerpo,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        medios = json.loads(r.read())["data"]["Page"]["media"]

    # los que aún no tienen nota no dicen nada: se caen
    medios = [m for m in medios if m.get("averageScore")]
    if not medios:
        sys.exit("AniList no da notas todavía para esta temporada.")

    campos = []
    for i, m in enumerate(medios):
        titulo = m["title"].get("english") or m["title"]["romaji"]
        estudio = (m["studios"]["nodes"] or [{}])[0].get("name", "")
        nota = m["averageScore"]
        detalle = " · ".join(x for x in (estudio, ", ".join(m["genres"][:2])) if x)
        campos.append({
            "name": f"{MEDALLA[i] if i < 3 else f'{i + 1}.'}  {titulo}",
            "value": f"**{nota}/100**  `{barra(nota)}`\n-# {detalle}"
                     f"\n[Ver en AniList]({m['siteUrl']})",
            "inline": False,
        })

    resumen = ia.resumen_temporada(
        [f"{(m['title'].get('english') or m['title']['romaji'])} — "
         f"{m['averageScore']}/100 — {', '.join(m['genres'][:3])}" for m in medios])
    descripcion = "-# La nota la pone la gente, no la crítica. Sale sola cada lunes."
    if resumen:
        descripcion = f"{resumen}\n\n-# {ia.AVISO} · la nota la pone la gente"
    e = {
        "author": {"name": "Lo que está gustando  ·  AniList"},
        "title": f"Temporada de {EN_CASTELLANO[est]} {anio}",
        "color": 0x02A9FF,
        "description": descripcion,
        "fields": campos,
        "thumbnail": {"url": medios[0]["coverImage"]["large"]},
        "footer": {"text": "Si te apetece doblar algo de aquí, dilo en ideas de "
                           "proyecto"},
    }

    print(f"  {e['title']}")
    for c in campos:
        print(f"    {c['name']}")
    if not args.enserio:
        print("\n>>> SIMULACRO. Agrega --enserio.")
        return

    cid = next((c["id"] for c in api("GET", f"/guilds/{GUILD}/channels")
                if CANAL in c["name"]), None)
    if not cid:
        sys.exit(f"No encuentro el canal «{CANAL}»")
    api("POST", f"/channels/{cid}/messages", {"embeds": [e]})
    print(f"\npublicado en {CANAL}")


if __name__ == "__main__":
    main()
