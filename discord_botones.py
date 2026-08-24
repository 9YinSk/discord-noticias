#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_botones.py — el enlace, siempre como botón. Y siempre enviado.

**Por qué existe esto.** Un enlace suelto dentro de un embed es texto azul largo:
se lee mal y no dice a dónde va hasta que lo pulsas. Un botón sí lo dice. Pero el
botón hay que acordarse de mandarlo, y ahí estaba el fallo — `discord_opiniones.py`
los construía enteros y luego publicaba `{"embeds": [e]}` a secas, así que **nunca
salieron**. El botón existía en el código y no en Discord.

La cura no es acordarse mejor: es que el sitio por donde se publica **ponga el
botón solo**. `publicar()` mira el `url` del embed y le cuelga su botón sin que
nadie se lo pida; los demás botones se añaden encima.

    from discord_botones import publicar, boton
    publicar(cid, e)                                   # el botón sale solo
    publicar(cid, e, [boton(j["url"]), boton(yt, "Ver el tráiler", "▶️")])

Reglas de Discord que condicionan el diseño (medidas, no supuestas):

  · los botones de **enlace** son `style: 5` y **no necesitan bot escuchando** —
    por eso valen en la nube, donde no hay nadie conectado
  · un botón de enlace **no lleva `custom_id`**; si se le pone, la API lo rechaza
  · **5 botones por fila, 5 filas** — 25 como mucho por mensaje
  · la etiqueta son **80 caracteres** como tope
"""
import os
import sys
import urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from discord_servidor import api  # noqa: E402

# Cada sitio con su nombre y su icono. Sin esto todos los botones dirían «Abrir
# el enlace», que es justo lo que un botón viene a evitar: el botón bueno dice a
# dónde lleva **antes** de pulsarlo.
SITIOS = {
    "anilist.co": ("Ver en AniList", "📺"),
    "myanimelist.net": ("Ver en MyAnimeList", "📺"),
    "store.steampowered.com": ("Ver en Steam", "🎮"),
    "isthereanydeal.com": ("Ver la oferta", "🏷️"),
    "www.youtube.com": ("Ver en YouTube", "▶️"),
    "youtu.be": ("Ver en YouTube", "▶️"),
    "www.animenewsnetwork.com": ("Leer la noticia", "📄"),
    "vandal.elespanol.com": ("Leer la noticia", "📄"),
    "www.nintenderos.com": ("Leer la noticia", "📄"),
    "www.espinof.com": ("Leer la noticia", "📄"),
    "www.sensacine.com": ("Leer la noticia", "📄"),
    "www.musicbutler.io": ("Escuchar", "🎧"),
    "discord.com": ("Ir al mensaje", "💬"),
}
POR_DEFECTO = ("Abrir el enlace", "🔗")


def de_donde_es(url):
    """El nombre y el icono que le tocan a un enlace, por su dominio."""
    try:
        dominio = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return POR_DEFECTO
    if dominio in SITIOS:
        return SITIOS[dominio]
    # `store.steampowered.com` y `steamcommunity.com` son el mismo sitio para
    # quien mira; se busca por trozo antes de rendirse.
    for clave, valor in SITIOS.items():
        raiz = clave.split(".")[-2] if clave.count(".") > 1 else clave
        if raiz in dominio:
            return valor
    return POR_DEFECTO


def boton(url, etiqueta=None, emoji=None):
    """Un botón de enlace. Sin `url` devuelve `None`, para poder colarlo en listas.

    Que devuelva `None` en vez de reventar es a propósito: media docena de sitios
    de llamada tienen enlaces que a veces existen y a veces no (el tráiler, la
    ficha de Steam), y así se escriben en una línea sin un `if` alrededor.
    """
    if not url:
        return None
    nombre, icono = de_donde_es(url)
    b = {"type": 2, "style": 5, "label": (etiqueta or nombre)[:80], "url": url}
    icono = emoji or icono
    if icono:
        b["emoji"] = {"name": icono}
    return b


def filas(botones):
    """Los botones repartidos en filas de 5. Discord admite 5 filas: 25 en total."""
    limpios = [b for b in botones if b]
    if not limpios:
        return None
    return [{"type": 1, "components": limpios[i:i + 5]}
            for i in range(0, min(len(limpios), 25), 5)]


def enlace_mensaje(guild, canal, mensaje):
    """El enlace a un mensaje concreto del servidor, para poder saltar a él."""
    return f"https://discord.com/channels/{guild}/{canal}/{mensaje}"


def enlace_canal(guild, canal):
    return f"https://discord.com/channels/{guild}/{canal}"


def buscar_en_youtube(texto):
    """Una búsqueda de YouTube. Para tráilers: enlazar a un video concreto pide
    clave de la API de YouTube, y la búsqueda no pide nada y acierta igual."""
    return ("https://www.youtube.com/results?search_query="
            + urllib.parse.quote(texto))


def componentes(embed, extra=None):
    """Los botones que le tocan a un embed: **el suyo primero**, luego los demás.

    El primero sale del propio `embed["url"]`, que es el enlace del que va la
    cosa. Esa es toda la gracia del módulo: nadie tiene que acordarse de ponerlo.
    """
    ya = set()
    fila = []
    for b in [boton((embed or {}).get("url"))] + list(extra or []):
        if b and b["url"] not in ya:
            ya.add(b["url"])
            fila.append(b)
    return filas(fila)


def publicar(canal_id, embed, extra=None, **resto):
    """Publica el embed **con sus botones**. Es la única puerta que hay que usar.

    `resto` pasa tal cual al cuerpo del mensaje (`content`, `thread_name`…).
    """
    cuerpo = {"embeds": [embed], **resto}
    comp = componentes(embed, extra)
    if comp:
        cuerpo["components"] = comp
    return api("POST", f"/channels/{canal_id}/messages", cuerpo)
