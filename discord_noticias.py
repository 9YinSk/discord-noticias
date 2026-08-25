#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_noticias.py — lee los feeds y los publica. Sin bots de terceros.

**Por qué existe esto.** Los bots de RSS (MonitoRSS, Readybot) se configuran desde
su panel web, con login de Discord: eso no lo puede hacer nuestro bot por API. Y
MonitoRSS además solo admite 3 feeds gratis.

Así que esto hace lo mismo por el camino corto: **lee los RSS y publica lo nuevo**
con nuestro propio bot, que ya tiene permisos en esos canales. Solo stdlib —
`urllib` para bajar y `xml` para parsear; nada de `feedparser`.

Lo que ya se ha publicado se guarda en `.noticias_vistas.json`, así que correrlo
dos veces no repite nada. La primera vez publica **solo las 3 últimas de cada
feed**, para no vaciar el historial entero de golpe en el canal.

    python discord_noticias.py                 # simulacro: dice qué publicaría
    python discord_noticias.py --enserio
    python discord_noticias.py --enserio --max 5

Si existe la variable `GEMINI_API_KEY`, los titulares se **traducen al español**
antes de publicarlos — Anime News Network publica en inglés. Sin esa clave, salen
en su idioma y no pasa nada: es opcional.

**Corre sin el PC encendido.** `discord_nube.py` arma la carpeta `discord-nube/`
para subirla a GitHub, donde **GitHub Actions lo ejecuta cada 30 minutos gratis**.
Los pasos están en el README que genera. Aquí en local sigue funcionando igual,
que es lo cómodo para probar.
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from discord_servidor import api  # noqa: E402
from discord_feeds import FEEDS  # noqa: E402  — la misma lista, un solo sitio
from discord_botones import boton, publicar  # noqa: E402  — el enlace, como botón

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GUILD = "1539896304178823282"
VISTAS = os.path.join(AQUI, ".noticias_vistas.json")

# Sin esto, varios servidores devuelven 403: un User-Agent de Python huele a bot
# de scraping. Con uno normal, responden.
CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
}


def bajar(url, timeout=25):
    """Baja el feed, **descomprimiéndolo si hace falta**.

    Vandal devuelve gzip aunque no se pida (su cabecera empieza por `1f 8b`), y
    pasarle eso al parser da un `ParseError` en la columna 1 que despista mucho:
    parece XML roto y es XML comprimido.
    """
    req = urllib.request.Request(url, headers=CABECERAS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        crudo = r.read()
        codif = (r.headers.get("Content-Encoding") or "").lower()
    if crudo[:2] == b"\x1f\x8b" or codif == "gzip":
        import gzip
        crudo = gzip.decompress(crudo)
    elif codif == "deflate":
        import zlib
        crudo = zlib.decompress(crudo, -zlib.MAX_WBITS)
    return crudo


def _texto(elem, *nombres):
    """El primer hijo que exista, sea RSS o Atom (que usan nombres distintos)."""
    for n in nombres:
        hijo = elem.find(n)
        if hijo is not None:
            if hijo.text:
                return hijo.text.strip()
            if hijo.get("href"):            # Atom pone el enlace en un atributo
                return hijo.get("href")
    return ""


_CONTROL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_IMG = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
_TAG = re.compile(r"<[^>]+>")


_OG = re.compile(rb'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', re.I)
_OG2 = re.compile(rb'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', re.I)

# lo que ya se ha mirado, para no pedir la misma página dos veces en una corrida
_PORTADAS = {}


def portada(enlace):
    """La imagen de la noticia, sacada de **la propia página**.

    La mitad de los feeds no manda imagen: Anime News Network, Nintenderos y las
    ofertas venían a cero, y el canal quedaba descompensado — unas noticias con
    foto y otras sin. Pero todas esas páginas tienen `og:image`, que es la
    etiqueta que usan WhatsApp y Twitter para la vista previa.

    Solo se pide la página **cuando el feed no trae nada**, y como mucho tres
    veces por feed. No es un rastreo: es completar lo que falta.
    """
    if enlace in _PORTADAS:
        return _PORTADAS[enlace]
    img = None
    try:
        req = urllib.request.Request(enlace, headers=CABECERAS)
        with urllib.request.urlopen(req, timeout=15) as r:
            crudo = r.read(80000)      # con el <head> basta, no hace falta la página
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                import gzip
                import io as _io
                crudo = gzip.GzipFile(fileobj=_io.BytesIO(crudo)).read()
        m = _OG.search(crudo) or _OG2.search(crudo)
        if m:
            img = html.unescape(m.group(1).decode("utf-8", "replace"))
    except Exception:                                   # noqa: BLE001
        pass                                            # sin imagen se vive
    _PORTADAS[enlace] = img
    return img


def _imagen(it, descripcion):
    """La imagen del artículo, de donde la haya puesto cada feed.

    No hay un sitio único: unos usan `media:thumbnail`, otros `enclosure`, y
    Espinof la mete **dentro del HTML de la descripción**. Se miran los tres.
    """
    M = "{http://search.yahoo.com/mrss/}"
    for tag in (f"{M}thumbnail", f"{M}content", "enclosure"):
        h = it.find(tag)
        if h is not None and h.get("url"):
            return h.get("url")
    m = _IMG.search(descripcion or "")
    return m.group(1) if m else None


def entradas(xml_bytes):
    """Una lista de dicts con lo que se puede sacar de cada item.

    Antes de parsear se quitan los **bytes de control**: Vandal cuela alguno en
    sus descripciones y `ElementTree` revienta con `ParseError` por un carácter
    que ni se ve. Un feed no se descarta por eso.
    """
    xml_bytes = _CONTROL.sub(b" ", xml_bytes)
    raiz = ET.fromstring(xml_bytes)
    A = "{http://www.w3.org/2005/Atom}"
    D = "{http://purl.org/dc/elements/1.1/}"
    items = raiz.findall(".//item") or raiz.findall(f".//{A}entry")
    out = []
    for it in items:
        titulo = _texto(it, "title", f"{A}title")
        enlace = _texto(it, "link", f"{A}link")
        if not (titulo and enlace):
            continue
        desc = _texto(it, "description", "summary", f"{A}summary", f"{A}content")
        out.append({
            "titulo": html.unescape(titulo),
            "enlace": enlace.strip(),
            "desc": desc,
            "imagen": _imagen(it, desc),
            "autor": _texto(it, f"{D}creator", "author", f"{A}author"),
            "categoria": _texto(it, "category"),
            "fecha": _texto(it, "pubDate", "published", f"{A}published", f"{A}updated"),
        })
    return out


def limpio(t, tope=None):
    """Sin etiquetas ni espacios de más: casi todos los feeds meten HTML dentro.

    Vandal además abre sus descripciones con un `<!--cache-->` que hay que tirar.
    """
    t = html.unescape(_TAG.sub(" ", t or "").replace("<!--cache-->", ""))
    t = " ".join(t.split())
    if tope and len(t) > tope:
        t = t[:tope].rsplit(" ", 1)[0] + "…"
    return t


# Cada fuente con su color y su nombre bonito. Sin esto, cuatro canales de
# noticias son cuatro muros de enlaces iguales: es lo que les da cara.
FUENTES = {
    "www.animenewsnetwork.com": ("Anime News Network", 0xE67E22),
    "vandal.elespanol.com": ("Vandal", 0x1F8FE5),
    "www.nintenderos.com": ("Nintenderos", 0xE60012),
    "www.espinof.com": ("Espinof", 0xE91E63),
    "www.sensacine.com": ("SensaCine", 0xF5C518),
    "isthereanydeal.com": ("IsThereAnyDeal", 0x2ECC71),
    "www.musicbutler.io": ("MusicButler", 0x00B8D4),
}


import discord_ia as ia  # noqa: E402  — todo lo que escribe la IA, en un sitio
import discord_publico as publico  # noqa: E402  — lo que dice la gente

# De qué se habla en cada canal, para saber en qué subreddits mirar. Los que no
# están aquí —la música— no llevan sección de debate: nadie discute en Reddit el
# single nuevo de un artista que sigues tú.
TEMA_DEL_CANAL = {
    "noticias-anime": "anime",
    "noticias-gaming": "juegos",
    "noticias-series": "cine",
    "ofertas-y-gratis": "ofertas",
}


# Trozos que delatan una imagen **genérica del sitio**, no de la noticia: el
# logo, la portada por defecto, la tarjeta de compartir de la sección. Ponerla es
# peor que no poner ninguna — es la que «no tiene nada que ver».
_GENERICA = ("/socials/", "/og/og_", "default", "placeholder", "/logo",
             "share-image", "twitter-card")


def util(url_imagen):
    return bool(url_imagen) and not any(x in url_imagen.lower() for x in _GENERICA)


def _steam(titulo):
    """La ficha de Steam de un juego, por su nombre. Para las ofertas.

    Los feeds de ofertas no traen ni imagen ni precio: solo «Nombre free on
    Steam». Buscando el nombre en la tienda salen **la portada y el precio en
    soles**, que es lo que convierte una línea de texto en algo que apetece
    mirar.
    """
    nombre = re.split(r"\s+(?:free on|on)\s+", titulo)[0].strip()
    if not nombre:
        return None
    try:
        req = urllib.request.Request(
            "https://store.steampowered.com/api/storesearch/?term="
            + urllib.parse.quote(nombre) + "&cc=pe&l=spanish", headers=CABECERAS)
        with urllib.request.urlopen(req, timeout=15) as r:
            items = json.loads(r.read().decode("utf-8")).get("items") or []
    except Exception:                                   # noqa: BLE001
        return None
    if not items:
        return None
    j = items[0]
    # la cabecera grande de la tienda, que es la buena; `tiny_image` es diminuta
    return {
        "nombre": j["name"],
        "imagen": f"https://cdn.cloudflare.steamstatic.com/steam/apps/"
                  f"{j['id']}/header.jpg",
        "url": f"https://store.steampowered.com/app/{j['id']}/",
        "precio": (j.get("price") or {}).get("final"),
    }


# El `.*` glotón de delante es lo que hace que enganche el ÚLTIMO «on», no el
# primero: sin él, en «… on Epic Games on Epic Game Store» la coletilla capturada
# era «Epic Games on Epic Game Store» entera y no coincidía con nada.
# `en` va también, que el feed de itch.io publica en español.
_TIENDA = re.compile(r"^(.*)\s+(?:on|en)\s+([\w'.\- ]+?)\s*$", re.I)


def sin_repetir_tienda(titulo):
    """Quita el «on Epic Game Store» que el feed de ofertas pega al final.

    Ese feed compone el título como «Juego - FREE on Epic Games» y luego le añade
    la tienda otra vez: queda **«… on Epic Games on Epic Game Store»**, que se lee
    como un error de programa. Solo se corta cuando la coletilla repite algo que
    ya estaba en el título — si la tienda se nombra una sola vez, se respeta.
    """
    m = _TIENDA.match(titulo or "")
    if not m:
        return titulo
    delante, cola = m.group(1).strip(), m.group(2).strip()
    # basta con que compartan la primera palabra: «Epic Games» vs «Epic Game Store»
    raiz = cola.split()[0].lower() if cola.split() else ""
    if raiz and raiz in delante.lower():
        return delante.strip()
    return titulo


def tarjeta(titular, fuente, color_int, etiqueta=None, arte_url=None):
    """Dibuja la portada de una noticia sin imagen. `None` si no se puede.

    El dibujo se importa **aquí dentro y no arriba**: `discord_banners` trae
    Pillow detrás, y las noticias tienen que poder publicarse aunque Pillow no
    esté instalado. Sin imagen se vive; sin noticias, no.
    """
    try:
        import discord_banners as db
    except ImportError:
        return None
    rgb = ((color_int >> 16) & 255, (color_int >> 8) & 255, color_int & 255)
    try:
        return db.tarjeta_noticia(titular, fuente, rgb, "_noticia.png",
                                  etiqueta=limpio(etiqueta or "", 22) or None,
                                  arte_url=arte_url)
    except Exception:                                   # noqa: BLE001
        return None


def tema_de(canal):
    """El tema de un canal. Por trozo, que el nombre real lleva `ıı・📰・` delante."""
    return next((t for k, t in TEMA_DEL_CANAL.items() if k in (canal or "")), None)


def con_la_gente(e, titulo, tema, extra, ver=None):
    """Le añade a la noticia **en qué se dividió la gente**, si se dividió.

    Es lo que separa un tablón de titulares de algo que apetece leer: la noticia
    dice qué pasó, esto dice qué le pareció al mundo.

    **Se juntan todas las fuentes antes de resumir**, no una sola. Los
    comentarios del hilo de Reddit, las reseñas de Steam a favor y en contra, y
    las de AniList con su nota. Cada fuente por su cuenta da una foto parcial —
    Reddit solo cubre 2 de cada 14 noticias, y las reseñas de una tienda tiran a
    favorables; juntas se parecen bastante a «qué opina internet».

    Y **si no hay nada, no se escribe nada**: el hueco vacío es información, el
    relleno no.
    """
    if not tema:
        return
    voces = []

    if ia.disponible():
        try:
            _hilo, coments = publico.debate(titulo, tema)
            voces += [c["texto"] for c in coments[:25]]
        except Exception:                               # noqa: BLE001
            pass                        # el archivo es gratis: puede no estar

    if ver and ver.get("voces"):
        voces += ver["voces"]

    # **El enlace a la tienda es el único botón que se añade aquí.** Nada de
    # botones a Reddit ni a la ficha: la discusión se lee dentro de Discord, y
    # los botones son para lo que se hace fuera — leer la noticia o ir a
    # comprar. Un botón que saca a la gente del servidor a leer lo mismo que ya
    # tiene delante es tirarse piedras al tejado.
    if ver and ver.get("tienda"):
        extra.append(boton(ver["tienda"]))

    if voces and ia.disponible():
        dividio = ia.como_se_dividio(titulo, voces[:40])
        if dividio:
            hubo_bandos = dividio.lstrip().startswith("—")
            e.setdefault("fields", []).append({
                "name": ("En qué se dividió la gente" if hubo_bandos
                         else "Lo que dice la gente") + f"  ·  {len(voces)} opiniones",
                "value": dividio[:1020], "inline": False})
            return

    # Sin material para resumir, queda la nota pelada: mejor eso que nada.
    if ver and ver.get("nota"):
        e.setdefault("fields", []).append({
            "name": "La nota que le pone la gente",
            "value": ver["nota"][:1020], "inline": False})


def embed(item, url_feed, canal=""):
    """La noticia con cara: fuente, titular, extracto, imagen y fecha.

    `canal` solo sirve para saber en qué subreddits buscar el debate: el tema
    lo marca el canal de destino, no el dominio del feed.
    """
    dominio = url_feed.split("/")[2]
    nombre, color = FUENTES.get(dominio, (dominio, 0x9B59B6))
    e = {
        "author": {"name": nombre,
                   "icon_url": f"https://icons.duckduckgo.com/ip3/{dominio}.ico"},
        "title": ia.traducir(limpio(item["titulo"], 250)),
        "url": item["enlace"],
        "color": color,
    }
    desc = limpio(item["desc"], 300)
    if desc and desc.lower() != e["title"].lower():
        e["description"] = desc
    extra = []
    imagen = item["imagen"] if util(item["imagen"]) else None

    # **La ficha se busca aquí, antes de dibujar nada.** De ella salen dos cosas
    # que se necesitan en momentos distintos: la nota que opina la gente (va
    # abajo, en un campo) y **la ilustración del juego o del anime**, que va de
    # fondo de la portada. Buscándola una sola vez sirve para las dos.
    tema = tema_de(canal)
    ver = publico.veredicto(e["title"], tema) if tema else None

    # Las ofertas son un caso aparte: su feed no trae ni imagen ni precio, y la
    # `og:image` del sitio es una tarjeta generica. La ficha de Steam si tiene
    # portada de verdad y el precio en soles.
    if "isthereanydeal" in dominio:
        e["title"] = sin_repetir_tienda(e["title"])
        j = _steam(item["titulo"])
        if j:
            imagen = j["imagen"]
            extra.append(boton(j["url"]))            # «Ver en Steam», por dominio
            if j["precio"] == 0:
                e["title"] = f"{j['nombre']} — GRATIS"
            elif j["precio"]:
                e["title"] = f"{j['nombre']} — S/ {j['precio'] / 100:.2f}"

    if not imagen:
        de_la_pagina = portada(item["enlace"])
        imagen = de_la_pagina if util(de_la_pagina) else None
    if imagen:
        e["image"] = {"url": imagen}
    else:
        # Ni el feed ni la página tienen foto. En vez de dejar la noticia como un
        # renglón de texto con un enlace azul —que al lado de una con portada se
        # ve huérfana—, se le dibuja una con la cara del servidor.
        ruta = tarjeta(e["title"], nombre, color, item.get("categoria"),
                       arte_url=(ver or {}).get("arte"))
        if ruta:
            e["image"] = {"url": "attachment://" + os.path.basename(ruta)}
            e["_tarjeta"] = ruta
    e["_extra"] = extra
    pie = [x for x in (item["categoria"], item["autor"]) if x]

    # La línea de «por qué te importa esto a ti, que doblas». La IA puede
    # **callarse** si la noticia no da para nada, y se calla a menudo: es lo que
    # evita que cada noticia lleve una frase de relleno pegada.
    porque = ia.por_que_importa(e["title"], desc) if ia.disponible() else None
    if porque:
        e["fields"] = [{"name": "Por qué te puede interesar", "value": porque}]
        pie.append(ia.AVISO)
    con_la_gente(e, e["title"], tema, extra, ver)
    if any(c["name"].startswith(("En qué se dividió", "Lo que dijo")) for c in e.get("fields", [])) \
            and ia.AVISO not in pie:
        pie.append(ia.AVISO)
    if pie:
        e["footer"] = {"text": limpio(" · ".join(pie), 100)}
    return e


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--enserio", action="store_true")
    p.add_argument("--max", type=int, default=3,
                   help="cuántas publicar por feed como mucho (por defecto 3)")
    args = p.parse_args()

    vistas = {}
    if os.path.exists(VISTAS):
        vistas = json.load(open(VISTAS, encoding="utf-8"))

    ch = {c["name"]: c["id"] for c in api("GET", f"/guilds/{GUILD}/channels")}
    publicados = 0

    for _bot, canal, lista in FEEDS:
        cid = ch.get(canal)
        if not cid:
            print(f"  no existe {canal}")
            continue
        for que, url in lista:
            if url.rstrip("/").endswith("musicbutler.io/users/rss-feed"):
                # esa es la PAGINA DE AYUDA de MusicButler, no un feed. El RSS de
                # verdad es personal: sale de la cuenta de cada uno y lleva un
                # identificador dentro. Mientras siga puesta la de ayuda, se salta.
                print(f"  {canal}: falta tu RSS personal de MusicButler, lo salto")
                continue
            try:
                items = entradas(bajar(url))
            except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError,
                    TimeoutError) as e:
                print(f"  {canal}: falla {url.split('/')[2]} — {type(e).__name__}")
                continue

            ya = set(vistas.get(url, []))
            nuevos = [x for x in items if x["enlace"] not in ya][:args.max]
            print(f"  {canal[:26]:26} {url.split('/')[2][:24]:24} "
                  f"{len(items):3} items, {len(nuevos)} nuevos")
            if not args.enserio:
                for x in nuevos[:2]:
                    marca = "🖼" if x["imagen"] else " "
                    print(f"      {marca} {limpio(x['titulo'])[:76]}")
                continue

            for item in reversed(nuevos):               # de vieja a nueva
                e = embed(item, url, canal)
                extra = e.pop("_extra", None)
                ruta = e.pop("_tarjeta", None)
                if ruta:
                    # Con adjunto no vale el POST de siempre: la imagen y el
                    # embed tienen que ir en la MISMA peticion multipart, o el
                    # `attachment://` del embed apunta a un archivo que no existe
                    # y Discord deja el hueco en blanco.
                    import discord_banners as db
                    from discord_botones import componentes
                    cuerpo = {"embeds": [e]}
                    comp = componentes(e, extra)
                    if comp:
                        cuerpo["components"] = comp
                    db.subir_con_imagen(cid, ruta, cuerpo)
                else:
                    publicar(cid, e, extra)
                publicados += 1
                time.sleep(1.2)
            # se guardan TODOS los enlaces del feed, no solo los publicados: si no,
            # la próxima corrida trataría como nuevo lo que hoy se dejó fuera del
            # tope y acabaría publicando el historial entero a trozos
            vistas[url] = [x["enlace"] for x in items][:200]

    if args.enserio:
        t = json.dumps(vistas, ensure_ascii=False, indent=1)
        json.loads(t)
        with open(VISTAS, "w", encoding="utf-8") as f:
            f.write(t + "\n")
        print(f"\n{publicados} noticias publicadas. Memoria en "
              f"{os.path.basename(VISTAS)}")
    else:
        print("\n>>> SIMULACRO. Agrega --enserio.")


if __name__ == "__main__":
    main()
