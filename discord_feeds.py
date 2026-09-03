#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_feeds.py — deja en config-bots la lista de feeds lista para pegar.

Los canales de noticias los llenan **bots, no nosotros**. Pero un bot de RSS se
configura desde **su panel web, con login**, y eso no lo puede hacer nuestro bot
por API: los feeds viven en la base de datos del bot de turno, no en Discord.

Así que esto hace la parte que sí se puede: dejar en el canal privado de
configuración **la lista exacta**, con la URL y el canal de cada feed, para
pegarla una vez. Después funciona solo, y sin que nadie tenga el PC encendido.

**Se usa Readybot, no MonitoRSS**, y por dos motivos medidos el 24-ago-2026:

  · **MonitoRSS gratis solo admite 3 feeds** — y aquí hacen falta nueve
  · **sus comandos están desactivados** en el bot público, así que tampoco se
    podía configurar desde Discord

Readybot da **20 feeds gratis** y comprueba cada 10 minutos. MonitoRSS puede
quedarse igualmente: no estorba, y su límite de 3 da para el canal de anime.

**Todas las URLs están comprobadas una por una.** Cuatro que parecían obvias se
cayeron y no están: Crunchyroll (404 en su RSS de noticias), Eurogamer.es (403),
3DJuegos (404 en la ruta de siempre) y Misión Tokyo, cuyo dominio **redirige a
una tienda que no es suya** — está secuestrado.

    python discord_feeds.py            # simulacro
    python discord_feeds.py --enserio
"""
import argparse
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from discord_servidor import api  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GUILD = "1539896304178823282"
CANAL = "ıı・🔧・config-bots"

# (bot, canal de destino, [(qué es, url)])
FEEDS = [
    ("Readybot", "ıı・📰・noticias-anime", [
        ("Anime News Network · sala de prensa — solo noticias, **sin reseñas de "
         "episodios**. Es el que hay que poner",
         "https://www.animenewsnetwork.com/newsroom/rss.xml"),
        # El feed de «todo» de ANN estaba puesto aquí al lado del de sala de
        # prensa, y **contiene a la sala de prensa entera**: cada noticia salía
        # dos veces en el canal, una por cada feed, y como cada uno lleva su
        # propia memoria de enlaces ninguno sabía lo que había publicado el
        # otro. Encima llegaban en idiomas distintos —uno traducido, el otro
        # no— así que ni pareciendo iguales se notaba de dónde venía el
        # duplicado. Fuera; con la sala de prensa sobra.
    ]),
    ("Readybot", "ıı・🎮・noticias-gaming", [
        ("Vandal — videojuegos en español",
         "https://vandal.elespanol.com/xml.cgi"),
        ("Nintenderos — todo lo de Nintendo, en español",
         "https://www.nintenderos.com/feed/"),
    ]),
    ("Readybot", "ıı・🍿・noticias-series", [
        ("Espinof — cine y series en español",
         "https://www.espinof.com/feedburner.xml"),
        ("SensaCine — estrenos y cartelera, en español",
         "https://www.sensacine.com/rss/noticias.xml"),
    ]),
    ("Readybot", "ıı・🏷️・ofertas-y-gratis", [
        ("IsThereAnyDeal · regalos — ya en región Perú",
         "https://isthereanydeal.com/feeds/PE/giveaways.rss"),
        ("IsThereAnyDeal · ofertas — región Perú, precios en USD",
         "https://isthereanydeal.com/feeds/PE/USD/deals.rss"),
    ]),
    # **El RSS de MusicButler es privado y NO va en el código.** Su política dice
    # que compartir ese enlace puede costar la cuenta: quien lo tenga ve tu feed.
    # Por eso sale de la variable de entorno `MUSICBUTLER_RSS`, que en la nube es
    # un secret de GitHub. Sin ella, el canal de música se salta y ya está.
    ("Readybot", "ıı・🎵・musica-nueva", [
        ("MusicButler — tu RSS personal, desde la variable MUSICBUTLER_RSS",
         os.environ.get("MUSICBUTLER_RSS", "").strip()
         or "https://www.musicbutler.io/users/rss-feed/"),
    ]),
]

CABECERA = (
    "## 📡 Feeds de noticias — pegar una vez y olvidarse\n"
    "Con **Readybot**, no con MonitoRSS: el gratis de MonitoRSS solo admite **3 "
    "feeds** y aquí hacen falta nueve, y además tiene los comandos desactivados.\n"
    "Readybot da **20 gratis** y mira cada 10 minutos.\n")

EXTRA = """### Cómo se ponen, y dos cosas más

**Readybot se configura en su panel, no con comandos:**
1. Entra en **readybot.io** y pulsa *Add server* — login con Discord
2. *Add bot*, y le pones un nombre. Por ejemplo `Noticias`
3. *Add feed*, pegas la URL de arriba y eliges su canal

Solo manda entradas **nuevas**: no vuelca el historial al empezar. Y funciona sin \
que nadie tenga el PC encendido.

**FreeStuff** ya está en el servidor y hace lo de los regalos mejor que un RSS: se \
configura con `/setup` y se le dice el canal. Ponlo en `🏷️・ofertas-y-gratis` y \
deja el feed de IsThereAnyDeal solo para las rebajas.

**Para un artista suelto, sin MusicButler**, vale el RSS de su canal de YouTube:
```
https://www.youtube.com/feeds/videos.xml?channel_id=EL_ID_DEL_CANAL
```
El `channel_id` sale del código fuente de su página, buscando `channelId`. Avisa \
de **cada subida**, así que solo compensa con artistas que suben poco.

-# Comprobado el 24-ago-2026, uno por uno. Fuera de la lista por no funcionar: \
Crunchyroll (404), Eurogamer.es (403), 3DJuegos (404) y Misión Tokyo, cuyo \
dominio redirige a una tienda que no es suya."""


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--enserio", action="store_true")
    args = p.parse_args()

    ch = {c["name"]: c["id"] for c in api("GET", f"/guilds/{GUILD}/channels")}
    canal = ch.get(CANAL)
    if not canal:
        sys.exit(f"No encuentro {CANAL}")

    total = sum(len(f[2]) for f in FEEDS)
    print(f"  {total} feeds, en {len(FEEDS)} canales")
    if not args.enserio:
        for bot, destino, lista in FEEDS:
            print(f"\n  {destino}   ({bot})")
            for que, url in lista:
                print(f"    · {que[:60]}\n      {url}")
        print("\n>>> SIMULACRO. Agrega --enserio.")
        return

    # se borra lo que dejó este script antes, para no apilar listas viejas
    for m in api("GET", f"/channels/{canal}/messages?limit=50") or []:
        if (m.get("content") or "").startswith("## 📡 Feeds"):
            api("DELETE", f"/channels/{canal}/messages/{m['id']}")
            time.sleep(0.35)

    partes = [CABECERA]
    for bot, destino, lista in FEEDS:
        cid = ch.get(destino)
        ref = f"<#{cid}>" if cid else f"`{destino}`"
        partes.append(f"\n**{ref}**")
        for que, url in lista:
            partes.append(f"· {que}\n{url}")

    api("POST", f"/channels/{canal}/messages", {"content": "\n".join(partes)[:1990]})
    time.sleep(0.6)
    api("POST", f"/channels/{canal}/messages", {"content": EXTRA})
    print("  lista publicada en config-bots")


if __name__ == "__main__":
    main()
