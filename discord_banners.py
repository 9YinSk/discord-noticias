#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_banners.py — genera las imagenes del servidor y las sube por API.

Hace tres cosas:
  icono       el icono del servidor (PATCH /guilds/{id}, en base64)
  banners     una cabecera por seccion, que se sube como primer mensaje
  mapa        el mapa visual de las zonas
  navegacion  panel de botones que llevan a cada canal de un clic

Sin dependencias raras: pillow + urllib.

Uso:
    python discord_banners.py generar            # solo crea los PNG en banners/
    python discord_banners.py icono <guild_id> --enserio
    python discord_banners.py subir <guild_id> --enserio
"""

import argparse
import base64
import io
import json
import math
import random
import os
import sys
import time
import urllib.error
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discord_servidor as ds   # reutiliza api() y el token

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "banners")
# Tipografia. Barlow —una grotesca ligeramente condensada— en vez de Segoe UI:
# condensa mas letra en el mismo ancho, que es justo lo que hace falta cuando la
# lamina tiene que explicar como se usa un canal, y pega con la onda de audio. Es
# fuente de usuario, ya instalada en esta PC (18 pesos).
#
# **Primero se mira dentro del repositorio.** Barlow estaba instalada solo en el
# PC de casa y la reserva apuntaba a `C:/Windows/Fonts/`, que en el Linux de
# GitHub Actions no existe: dibujar alli reventaba al abrir la fuente. Con los
# `.ttf` versionados en `tipografia/`, el mismo codigo dibuja igual aqui y en la
# nube — y las dos licencias (OFL y DejaVu) permiten redistribuirlos.
_PROPIA = os.path.join(AQUI, "tipografia")
_USUARIO = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Microsoft", "Windows", "Fonts")


def _fuente(nombre, *reservas):
    """La primera que exista: la del repo, la instalada, y luego las reservas."""
    for ruta in (os.path.join(_PROPIA, nombre), os.path.join(_USUARIO, nombre),
                 *reservas):
        if ruta and os.path.exists(ruta):
            return ruta
    return reservas[-1] if reservas else os.path.join(_PROPIA, nombre)


FUENTE_TIT = _fuente("Barlow-Black.ttf", "C:/Windows/Fonts/segoeuib.ttf")
FUENTE = _fuente("Barlow-Bold.ttf", "C:/Windows/Fonts/segoeuib.ttf")
FUENTE_FINA = _fuente("Barlow-Regular.ttf", "C:/Windows/Fonts/segoeui.ttf")
FUENTE_CURSIVA = _fuente("Barlow-MediumItalic.ttf", "C:/Windows/Fonts/segoeuii.ttf")

# La paleta del servidor: morado del rol Director sobre el gris de Discord.
MORADO = (155, 89, 182)
ROSA = (255, 123, 172)
AZUL = (114, 137, 218)
ORO = (241, 196, 15)
FONDO = (30, 31, 34)


def degradado(w, h, a, b):
    """Degradado en diagonal suave, calculado por filas y columnas a la vez."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(0, w, 2):
            t = ((x / w) * 0.78 + (y / h) * 0.22) ** 0.9
            c = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))
            px[x, y] = c
            if x + 1 < w:
                px[x + 1, y] = c
    return img


def brillo(img, centro, radio, color, fuerza=90):
    """Un halo suave, para que el fondo no quede plano."""
    capa = Image.new("RGB", img.size, (0, 0, 0))
    d = ImageDraw.Draw(capa)
    d.ellipse([centro[0] - radio, centro[1] - radio,
               centro[0] + radio, centro[1] + radio], fill=color)
    capa = capa.filter(ImageFilter.GaussianBlur(radio // 2))
    return Image.blend(img, Image.blend(img, capa, 0.5), fuerza / 255)


def onda(d, x0, x1, cy, alto, color, semilla=0, ancho=3, hueco=5):
    """La onda de audio de la derecha: barras de alto variable, con reflejo.

    Se dibuja con una suma de senos en vez de al azar, para que tenga forma de
    voz —crece, revienta y baja— en vez de parecer ruido.
    """
    rnd = random.Random(semilla)
    n = (x1 - x0) // (ancho + hueco)
    for i in range(n):
        t = i / max(1, n - 1)
        sobre = math.exp(-((t - 0.5) ** 2) / 0.055)          # el bulto del centro
        forma = (math.sin(t * 22) * 0.45 + math.sin(t * 7.3) * 0.35
                 + math.sin(t * 41) * 0.2)
        alt = max(2, int(alto * sobre * (0.35 + abs(forma) * 0.75)
                         * rnd.uniform(0.75, 1.15)))
        x = x0 + i * (ancho + hueco)
        c = tuple(min(255, int(v * (0.55 + sobre * 0.6))) for v in color)
        d.rectangle([x, cy - alt, x + ancho, cy + alt], fill=c)
    # Una linea fina cruzando por el centro: ata las barras entre si y hace que
    # se lea como una onda y no como barras sueltas. El reflejo de debajo se
    # quito — parecia que la onda goteaba.
    d.rectangle([x0 - 20, cy - 1, x1 + 20, cy + 1],
                fill=tuple(int(v * 0.45) for v in color))


def polvo(d, w, h, color, n=90, semilla=1):
    """Puntitos de estrella, muy tenues. Sin esto el fondo se ve muerto."""
    rnd = random.Random(semilla)
    for _ in range(n):
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        r = rnd.choice([0, 0, 1, 1, 2])
        op = rnd.uniform(0.15, 0.55)
        d.ellipse([x - r, y - r, x + r, y + r],
                  fill=tuple(int(v * op) for v in color))


def detalles(d, w, h, color):
    """Las cosillas que hacen que no parezca una plantilla vacia.

    Nada llamativo: una esquina marcada, una rejilla de puntos muy tenue y una
    raya diagonal de luz. Lo justo para que el fondo tenga algo que mirar sin
    quitarle protagonismo al titulo.
    """
    tenue = tuple(int(v * 0.30) for v in color)

    # esquina superior derecha: dos lineas en angulo, como un marco de encuadre
    d.line([(w - 96, 30), (w - 30, 30)], fill=tenue, width=3)
    d.line([(w - 30, 30), (w - 30, 96)], fill=tenue, width=3)
    # y la opuesta abajo a la izquierda, para equilibrar
    d.line([(36, h - 30), (102, h - 30)], fill=tenue, width=3)
    d.line([(36, h - 96), (36, h - 30)], fill=tenue, width=3)

    # rejilla de puntitos en la esquina inferior derecha
    for fila in range(4):
        for col in range(9):
            x = w - 250 + col * 22
            y = h - 92 + fila * 20
            d.ellipse([x, y, x + 3, y + 3], fill=tenue)

    # Aquí había tres rayas diagonales cruzando el fondo. Se quitaron: con una
    # textura de zona detrás sumaban un segundo patrón de franjas y la lámina
    # acababa pareciendo un mantel. El fondo ya tiene algo que mirar; esto solo
    # competía con el título.


def banner(titulo, subtitulo, emoji_txt, color, archivo, w=1200, h=444):
    """Cabecera de canal.

    **Las medidas importan mas que el dibujo**: Discord reduce las imagenes del
    chat a unos 520 px de ancho. A 4:1 el titulo queda ilegible; a 2.7:1 se lee.
    Y el titulo tiene que ocupar buena parte del alto, no flotar en un mar de
    fondo vacio.
    """
    # El fondo es SIEMPRE el mismo morado noche. Antes se teñia con el color de
    # acento y los banners calidos salian de un amarillo turbio que no pegaba con
    # nada. El acento se queda donde se ve bien: la onda, la franja y el halo.
    oscuro, noche = (26, 18, 46), (14, 16, 34)
    img = degradado(w, h, oscuro, noche)
    img = brillo(img, (int(w * 0.78), h // 2), int(h * 0.9), color, 60)
    img = brillo(img, (int(w * 0.05), int(h * 0.2)), int(h * 0.5), color, 28)
    d = ImageDraw.Draw(img)
    polvo(d, w, h, (255, 255, 255), 110, semilla=len(titulo))
    onda(d, int(w * 0.60), int(w * 0.95), int(h * 0.5), int(h * 0.30), color,
         semilla=len(titulo) * 7)

    # franja de acento a la izquierda
    d.rectangle([0, 0, 8, h], fill=color)
    detalles(d, w, h, color)

    f_tit = ImageFont.truetype(FUENTE_TIT, 92)
    f_sub = ImageFont.truetype(FUENTE_FINA, 34)
    lineas = titulo.upper().split("\n")
    y = h // 2 - (len(lineas) * 100 + 96) // 2
    for ln in lineas:
        d.text((58, y), ln, font=f_tit, fill=(255, 255, 255))
        y += 100
    # Subrayado corto DEBAJO del titulo, no encima: a `y` ya se le sumo el alto
    # de la ultima linea, pero la fuente deja cola por debajo y la raya cruzaba
    # las letras. Con +14 queda limpia.
    ancho1 = int(d.textlength(lineas[0].split(" ")[0], font=f_tit))
    d.rectangle([60, y + 14, 60 + min(ancho1, 220), y + 20], fill=color)
    d.text((62, y + 38), subtitulo, font=f_sub, fill=(198, 200, 214))

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.save(ruta, "PNG")
    return ruta


def lamina_info(titulo, lineas, color, archivo, w=1200, h=None):
    """Lamina con el titulo y las lineas clave DIBUJADAS dentro.

    Discord la reduce a ~520 px de ancho, asi que el texto se dibuja **grande**:
    52 px en el archivo son unos 22 px en pantalla, que se leen. Menos de eso no.

    Va lo esencial —las cinco zonas, los tres pasos—, no la explicacion entera:
    lo que hay que poder copiar, buscar o leer con un lector de pantalla se
    queda en el texto del mensaje.
    """
    alto_linea = 78
    h = h or (210 + alto_linea * len(lineas) + 60)
    oscuro, noche = (26, 18, 46), (14, 16, 34)
    img = degradado(w, h, oscuro, noche)
    img = brillo(img, (int(w * 0.86), int(h * 0.25)), int(h * 0.55), color, 45)
    d = ImageDraw.Draw(img)
    polvo(d, w, h, (255, 255, 255), 90, semilla=len(titulo))
    d.rectangle([0, 0, 8, h], fill=color)

    f_tit = ImageFont.truetype(FUENTE_TIT, 76)
    f_lin = ImageFont.truetype(FUENTE, 52)
    d.text((58, 62), titulo.upper(), font=f_tit, fill=(255, 255, 255))
    d.rectangle([60, 168, 60 + 190, 174], fill=color)      # subrayado corto

    y = 214
    for texto in lineas:
        # un punto de color delante hace de vineta y ordena la lectura
        d.ellipse([62, y + 22, 62 + 15, y + 37], fill=color)
        d.text((96, y), texto, font=f_lin, fill=(232, 234, 244))
        y += alto_linea

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.save(ruta, "PNG")
    return ruta


def _fondo_de_archivo(ruta, w, h, color):
    """Usa una imagen generada (Firefly, Canva, Nano Banana) como fondo.

    Se recorta al tamaño que toca, se oscurece **mucho** y se le tiñe un halo del
    color del canal. Sin ese oscurecido el titulo blanco no se lee sobre un fondo
    con detalle, que es justo lo que devuelven los generadores.
    """
    base = Image.open(ruta).convert("RGB")
    # encaje tipo "cover": se escala por el lado que falta y se recorta el sobrante
    escala = max(w / base.width, h / base.height)
    base = base.resize((max(w, int(base.width * escala)),
                        max(h, int(base.height * escala))), Image.LANCZOS)
    base = base.crop(((base.width - w) // 2, (base.height - h) // 2,
                      (base.width - w) // 2 + w, (base.height - h) // 2 + h))
    velo = Image.new("RGB", (w, h), (12, 10, 26))
    img = Image.blend(base, velo, 0.72)
    return brillo(img, (int(w * 0.80), int(h * 0.3)), int(h * 0.7), color, 40)


_SIN_GLIFO = {}


def _falta_glifo(ch):
    """¿La fuente NO sabe dibujar este caracter?

    Nada de listas de rangos a ojo: **se pregunta a la fuente**. Se compara el
    dibujo del caracter con el de uno del area privada de Unicode, que seguro no
    existe; si salen iguales, los dos son el mismo cuadrito vacio.

    La primera version iba por rangos y se llevaba por delante las flechas `→`,
    que Segoe UI si tiene. Esto no se equivoca.
    """
    if ch in _SIN_GLIFO:
        return _SIN_GLIFO[ch]
    if ch.isascii() or ch.isspace():
        _SIN_GLIFO[ch] = False
        return False
    f = ImageFont.truetype(FUENTE, 40)

    def pinta(t):
        m = f.getmask(t)
        return (m.size, bytes(bytearray(m)))

    _SIN_GLIFO[ch] = pinta(ch) == pinta("")
    return _SIN_GLIFO[ch]


def sin_emoji(texto):
    """Quita del texto DIBUJADO lo que la fuente no sabe dibujar, y avisa.

    Segoe UI Bold no tiene glifos de emoji: cada uno sale como un cuadrito vacio,
    y en la lamina no se distingue de un fallo de fuente. Dibujarlos de verdad
    pediria Segoe UI Emoji, que en Pillow solo compone a un tamaño fijo. No vale
    la pena: en el texto dibujado se escriben con palabras, y el emoji se queda
    donde si se ve —el nombre del canal, la etiqueta del boton, la reaccion.
    """
    fuera = [c for c in texto if _falta_glifo(c)]
    if not fuera:
        return texto
    print(f"     ojo: quito {''.join(fuera)!r} de «{texto}» — la fuente no los "
          f"dibuja", file=sys.stderr)
    limpio = "".join(" " if c in fuera else c for c in texto)
    return " ".join(limpio.split())


def _encoge(d, textos, ruta_fuente, tam, ancho_max, minimo=30):
    """Baja el cuerpo de letra hasta que la linea mas larga entre en la lamina.

    Con 46 px fijos, una linea larga se salia por la derecha y quedaba cortada.
    Mejor una lamina con letra un punto menor que una frase a medias.
    """
    while tam > minimo:
        f = ImageFont.truetype(ruta_fuente, tam)
        if max((d.textlength(t, font=f) for t in textos), default=0) <= ancho_max:
            return f
        tam -= 2
    return ImageFont.truetype(ruta_fuente, tam)


def lamina_completa(titulo, subtitulo, lineas, color, archivo, w=1200, fondo=None):
    """La cabecera Y el texto en UNA sola imagen.

    Arriba la cabecera de siempre —titulo, subtitulo, onda y detalles— y debajo
    las lineas clave dibujadas. Asi el mensaje del canal es solo la imagen y los
    botones: nada de texto encima repitiendo lo mismo.

    `fondo` es opcional: la ruta de un PNG generado fuera (Firefly, Canva Pro,
    Nano Banana). El dibujo es el mismo; solo cambia lo que hay detras.
    """
    titulo, subtitulo = sin_emoji(titulo), sin_emoji(subtitulo)
    lineas = [sin_emoji(t) for t in lineas]
    alto_cab, alto_linea = 300, 74
    h = alto_cab + alto_linea * len(lineas) + 54
    if fondo and os.path.exists(fondo):
        img = _fondo_de_archivo(fondo, w, h, color)
    else:
        oscuro, noche = (26, 18, 46), (14, 16, 34)
        img = degradado(w, h, oscuro, noche)
        img = brillo(img, (int(w * 0.80), int(alto_cab * 0.5)), 260, color, 60)
    d = ImageDraw.Draw(img)
    polvo(d, w, h, (255, 255, 255), 120, semilla=len(titulo))
    onda(d, int(w * 0.62), int(w * 0.95), int(alto_cab * 0.46), 78, color,
         semilla=len(titulo) * 7)
    d.rectangle([0, 0, 8, h], fill=color)
    detalles(d, w, h, color)

    # El titulo se encoge tambien: uno largo —«¿QUE JUGAMOS?»— llegaba a tocar la
    # onda de la derecha. El limite es donde empieza la onda, no el borde.
    f_tit = _encoge(d, [titulo.upper()], FUENTE_TIT, 82, int(w * 0.60) - 58, minimo=52)
    f_sub = ImageFont.truetype(FUENTE_FINA, 32)
    f_lin = _encoge(d, lineas, FUENTE, 46, w - 94 - 58)
    d.text((58, 74), titulo.upper(), font=f_tit, fill=(255, 255, 255))
    ancho1 = int(d.textlength(titulo.upper().split(" ")[0], font=f_tit))
    d.rectangle([60, 172, 60 + min(ancho1, 220), 178], fill=color)
    d.text((62, 196), subtitulo, font=f_sub, fill=(198, 200, 214))

    # una raya de separacion entre la cabecera y las lineas
    d.rectangle([58, alto_cab - 22, w - 58, alto_cab - 21],
                fill=tuple(int(v * 0.25) for v in color))
    y = alto_cab
    for texto in lineas:
        d.ellipse([62, y + 19, 62 + 13, y + 32], fill=color)
        d.text((94, y), texto, font=f_lin, fill=(228, 230, 242))
        y += alto_linea

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.save(ruta, "PNG")
    return ruta


# Consolas es de Microsoft y no se puede meter en el repositorio. DejaVu Mono si,
# y en la nube es la que se usa: los comandos siguen saliendo en su cajita.
FUENTE_MONO = _fuente("DejaVuSansMono-Bold.ttf", "C:/Windows/Fonts/consolab.ttf",
                      FUENTE)


def _trozos(texto):
    """Parte una linea en trozos con su tipo: normal, `comando` o **fuerte**."""
    partes, resto = [], texto
    while True:
        pos_c, pos_f = resto.find("`"), resto.find("**")
        if pos_c < 0 and pos_f < 0:
            break
        # gana el que aparezca antes en la linea
        if pos_c >= 0 and (pos_f < 0 or pos_c < pos_f):
            antes, _, resto = resto.partition("`")
            dentro, _, resto = resto.partition("`")
            tipo = "cmd"
        else:
            antes, _, resto = resto.partition("**")
            dentro, _, resto = resto.partition("**")
            tipo = "fuerte"
        if antes:
            partes.append((antes, ""))
        if dentro:
            partes.append((dentro, tipo))
    if resto:
        partes.append((resto, ""))
    return partes or [(texto, "")]


def _ancho_rico(d, texto, f_txt, f_cmd, f_fuerte):
    """Cuánto ocupa de verdad una línea con cajitas y realces.

    No vale medir el texto pelado: una cajita de comando suma su borde y su aire
    a los lados. Sin esto, una línea larga se salía por el borde derecho y se
    cortaba — pasó en la guía, con la lista de roles por antigüedad.
    """
    ancho = 0
    for trozo, tipo in _trozos(texto):
        if tipo == "cmd":
            ancho += d.textlength(trozo, font=f_cmd) + 28
        elif tipo == "fuerte":
            ancho += d.textlength(trozo, font=f_fuerte or f_txt)
        else:
            ancho += d.textlength(trozo, font=f_txt)
    return ancho


def _linea_rica(d, x, y, texto, f_txt, f_cmd, color, claro=(228, 230, 242),
                f_fuerte=None):
    """Dibuja una linea con dos realces: `comando` y **lo importante**.

    Un comando escrito igual que el resto de la frase no se ve; metido en una
    cajita con letra monoespaciada, se lee como algo que hay que escribir. Y lo
    marcado con dobles asteriscos sale en el color del canal — que es como se
    subraya una idea sin poder usar negrita de verdad, porque la fuente de las
    lineas **ya es negrita**.
    """
    for trozo, tipo in _trozos(texto):
        if tipo == "fuerte":
            f = f_fuerte or f_txt
            d.text((x, y), trozo, font=f, fill=color)
            x += d.textlength(trozo, font=f)
            continue
        if tipo != "cmd":
            d.text((x, y), trozo, font=f_txt, fill=claro)
            x += d.textlength(trozo, font=f_txt)
            continue
        ancho = d.textlength(trozo, font=f_cmd)
        alto = f_cmd.size
        d.rounded_rectangle([x, y - 4, x + ancho + 20, y + alto + 12], radius=7,
                            fill=(38, 33, 62),
                            outline=tuple(int(v * 0.65) for v in color), width=2)
        d.text((x + 10, y + 2), trozo, font=f_cmd, fill=color)
        x += ancho + 28
    return x


def _bloque_voz(d, x, y, w, personaje, frase, color):
    """La linea de guion del final: un personaje diciendo algo.

    Es un servidor de doblaje, asi que la firma de la lamina tiene la forma de lo
    que se hace aqui: **una linea de guion con su personaje delante**, como en un
    reparto. Da personalidad sin hacerse el gracioso, y cambia por zona — el
    Director no habla igual que el Gremlin.
    """
    f_nom = ImageFont.truetype(FUENTE, 26)
    f_dic = ImageFont.truetype(FUENTE_CURSIVA, 34)
    alto = 104
    d.rounded_rectangle([x, y, w - 58, y + alto], radius=10,
                        fill=(22, 19, 40),
                        outline=tuple(int(v * 0.35) for v in color), width=2)
    d.rectangle([x, y + 2, x + 5, y + alto - 2], fill=color)
    # el nombre va espaciado, como el pie de un personaje en un guion
    d.text((x + 24, y + 14), " ".join(personaje.upper()), font=f_nom, fill=color)
    d.text((x + 24, y + 50), f"«{frase}»", font=f_dic, fill=(214, 216, 230))
    return alto


def lamina(titulo, subtitulo, secciones, color, archivo, w=1200, fondo=None,
           pie=None, voz=None):
    """La lámina explicada: cabecera + secciones con encabezado propio.

    `lamina_completa()` sirve para un canal que se entiende con tres frases. Esta
    es para los que **hay que saber usar**: lleva secciones («QUE ES», «COMO SE
    USA», «OJO CON»), letra mas pequeña para que quepa lo que hace falta, y los
    comandos dibujados como comandos.

        secciones = [("Cómo se usa", ["Escribe `/set` y te pregunta el día",
                                      "Solo día y mes: el año no se pide"])]
    """
    titulo, subtitulo = sin_emoji(titulo), sin_emoji(subtitulo)
    secciones = [(sin_emoji(t), [sin_emoji(x) for x in ls]) for t, ls in secciones]

    alto_cab, alto_lin, alto_enc = 300, 58, 60
    h = alto_cab + sum(alto_enc + alto_lin * len(ls) + 18
                       for _, ls in secciones) + 66
    if pie:
        h += 62
    if voz:
        h += 126
    if fondo and os.path.exists(fondo):
        img = _fondo_de_archivo(fondo, w, h, color)
    else:
        oscuro, noche = (26, 18, 46), (14, 16, 34)
        img = degradado(w, h, oscuro, noche)
        img = brillo(img, (int(w * 0.80), int(alto_cab * 0.5)), 280, color, 60)
    d = ImageDraw.Draw(img)
    polvo(d, w, h, (255, 255, 255), 130, semilla=len(titulo))
    onda(d, int(w * 0.62), int(w * 0.95), int(alto_cab * 0.46), 78, color,
         semilla=len(titulo) * 7)
    d.rectangle([0, 0, 8, h], fill=color)
    detalles(d, w, h, color)

    f_tit = _encoge(d, [titulo.upper()], FUENTE_TIT, 82, int(w * 0.60) - 58, minimo=48)
    f_sub = ImageFont.truetype(FUENTE_FINA, 32)
    f_enc = ImageFont.truetype(FUENTE, 30)
    f_lin = ImageFont.truetype(FUENTE, 40)
    f_cmd = ImageFont.truetype(FUENTE_MONO, 36)
    f_fuerte = ImageFont.truetype(FUENTE_TIT, 40)
    f_pie = ImageFont.truetype(FUENTE_FINA, 28)

    # Y si aun así la línea más larga no entra, se baja el cuerpo de las tres
    # fuentes a la vez —texto, comando y realce— para que sigan cuadrando entre
    # sí. Mejor una lámina con letra un punto menor que una frase cortada.
    tope = w - 74 - 58
    todas = [t for _, ls in secciones for t in ls]
    tam = 40
    while tam > 30 and max((_ancho_rico(d, t, f_lin, f_cmd, f_fuerte)
                            for t in todas), default=0) > tope:
        tam -= 2
        f_lin = ImageFont.truetype(FUENTE, tam)
        f_cmd = ImageFont.truetype(FUENTE_MONO, tam - 4)
        f_fuerte = ImageFont.truetype(FUENTE_TIT, tam)

    d.text((58, 74), titulo.upper(), font=f_tit, fill=(255, 255, 255))
    ancho1 = int(d.textlength(titulo.upper().split(" ")[0], font=f_tit))
    d.rectangle([60, 172, 60 + min(ancho1, 220), 178], fill=color)
    d.text((62, 196), subtitulo, font=f_sub, fill=(198, 200, 214))

    # la raya que separa la cabecera del contenido, igual que en lamina_completa
    d.rectangle([58, alto_cab - 26, w - 58, alto_cab - 25],
                fill=tuple(int(v * 0.25) for v in color))
    y = alto_cab + 6
    for encabezado, lineas in secciones:
        d.text((60, y), encabezado.upper(), font=f_enc, fill=color)
        ancho = d.textlength(encabezado.upper(), font=f_enc)
        # la raya sale del encabezado y cruza hasta el borde: ata la seccion
        d.rectangle([70 + ancho, y + 18, w - 58, y + 19],
                    fill=tuple(int(v * 0.28) for v in color))
        y += alto_enc
        for texto in lineas:
            _linea_rica(d, 74, y, texto, f_lin, f_cmd, color, f_fuerte=f_fuerte)
            y += alto_lin
        y += 18

    if pie:
        d.text((62, y + 6), sin_emoji(pie), font=f_pie, fill=(150, 152, 170))
        y += 62
    if voz:
        _bloque_voz(d, 58, y + 10, w, sin_emoji(voz[0]), sin_emoji(voz[1]), color)

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.save(ruta, "PNG")
    return ruta


RATIO_DISCORD = 550 / 350      # la caja donde Discord mete una imagen del chat


def lamina_ancha(titulo, subtitulo, secciones, color, archivo, w=1200, fondo=None,
                 pie=None, voz=None, ratio=1.78):
    """La lámina **apaisada**. La misma información, legible sin abrirla.

    **Por qué existe.** Discord no enseña la imagen a tamaño real: la encoge
    hasta que quepa en una caja que es mucho más ancha que alta —del orden de
    550×350—. Una lámina vertical choca contra el alto, así que se encoge por
    ahí y **deja media anchura sin usar**: una de 1200×1500 acaba dibujada a
    279×350, y su letra de 40 px se lee a 9. Por eso hay que hacer zoom para
    leerlas, y por eso nadie las lee.

    Apaisada, el que manda es el ancho, que es el lado bueno: la misma letra de
    40 px se lee a **18**. El doble, sin cambiar ni la fuente ni el diseño.

    Lo que **no** funciona, y está medido: hacer el lienzo más grande (1600,
    1800…) no gana nada, porque Discord lo encoge más. Y partir en dos columnas
    tampoco — la columna es la mitad de ancha, así que la letra tiene que ser la
    mitad, y se anula. **Lo único que sube el tamaño real es que quepa menos
    texto por línea, y menos líneas.**

    De ahí el `ratio`: si el contenido no cabe, la lámina se hace más alta igual
    —nunca se recorta una frase— pero devuelve el alto de más en `sobra`, para
    que quien la genere sepa cuánto hay que quitar.
    """
    titulo, subtitulo = sin_emoji(titulo), sin_emoji(subtitulo)
    secciones = [(sin_emoji(t), [sin_emoji(x) for x in ls]) for t, ls in secciones]

    # La cabecera vertical gastaba 300 px en título y subtítulo. Aquí el título y
    # la onda comparten franja: 196 es lo justo para que el subtítulo no se meta
    # dentro del primer encabezado — pasó a 168 y se pisaban.
    alto_cab, alto_lin, alto_enc = 196, 54, 52
    alto_cuerpo = sum(alto_enc + alto_lin * len(ls) + 16 for _, ls in secciones)
    h = alto_cab + alto_cuerpo + 46
    if pie:
        h += 54
    if voz:
        h += 118
    objetivo = int(w / ratio)
    sobra = max(0, h - objetivo)
    h = max(h, objetivo)                       # nunca más estrecha que el objetivo

    if fondo and os.path.exists(fondo):
        img = _fondo_de_archivo(fondo, w, h, color)
    else:
        img = degradado(w, h, (26, 18, 46), (14, 16, 34))
        img = brillo(img, (int(w * 0.84), int(alto_cab * 0.52)), 300, color, 60)
    d = ImageDraw.Draw(img)
    polvo(d, w, h, (255, 255, 255), 110, semilla=len(titulo))
    onda(d, int(w * 0.66), int(w * 0.96), int(alto_cab * 0.44), 62, color,
         semilla=len(titulo) * 7)
    d.rectangle([0, 0, 8, h], fill=color)
    detalles(d, w, h, color)

    f_tit = _encoge(d, [titulo.upper()], FUENTE_TIT, 74, int(w * 0.58) - 58,
                    minimo=44)
    f_sub = ImageFont.truetype(FUENTE_FINA, 29)
    f_enc = ImageFont.truetype(FUENTE, 28)
    f_lin = ImageFont.truetype(FUENTE, 40)
    f_cmd = ImageFont.truetype(FUENTE_MONO, 36)
    f_fuerte = ImageFont.truetype(FUENTE_TIT, 40)
    f_pie = ImageFont.truetype(FUENTE_FINA, 27)

    tope = w - 74 - 58
    todas = [t for _, ls in secciones for t in ls]
    tam = 40
    while tam > 30 and max((_ancho_rico(d, t, f_lin, f_cmd, f_fuerte)
                            for t in todas), default=0) > tope:
        tam -= 2
        f_lin = ImageFont.truetype(FUENTE, tam)
        f_cmd = ImageFont.truetype(FUENTE_MONO, tam - 4)
        f_fuerte = ImageFont.truetype(FUENTE_TIT, tam)

    d.text((58, 34), titulo.upper(), font=f_tit, fill=(255, 255, 255))
    ancho1 = int(d.textlength(titulo.upper().split(" ")[0], font=f_tit))
    d.rectangle([60, 34 + f_tit.size + 10, 60 + min(ancho1, 220),
                 34 + f_tit.size + 15], fill=color)
    d.text((62, 34 + f_tit.size + 26), subtitulo, font=f_sub, fill=(198, 200, 214))
    d.rectangle([58, alto_cab - 20, w - 58, alto_cab - 19],
                fill=tuple(int(v * 0.25) for v in color))

    # El hueco que sobra cuando el lienzo crecio hasta el objetivo se reparte
    # arriba y abajo del cuerpo. Todo abajo dejaba un claro raro entre la ultima
    # linea y la firma, como si la lamina se hubiera quedado a medias.
    fijo = alto_cab + alto_cuerpo + 46 + (54 if pie else 0) + (118 if voz else 0)
    y = alto_cab + 4 + max(0, (h - fijo)) // 2
    for encabezado, lineas in secciones:
        d.text((60, y), encabezado.upper(), font=f_enc, fill=color)
        ancho = d.textlength(encabezado.upper(), font=f_enc)
        d.rectangle([70 + ancho, y + 17, w - 58, y + 18],
                    fill=tuple(int(v * 0.28) for v in color))
        y += alto_enc
        for texto in lineas:
            _linea_rica(d, 74, y, texto, f_lin, f_cmd, color, f_fuerte=f_fuerte)
            y += alto_lin
        y += 16

    if pie:
        d.text((62, y + 4), sin_emoji(pie), font=f_pie, fill=(150, 152, 170))
        y += 54
    if voz:
        # pegado abajo, no flotando: si el lienzo crecio hasta el objetivo, el
        # hueco de mas tiene que quedar ENTRE el texto y la firma, no debajo
        _bloque_voz(d, 58, h - 112, w, sin_emoji(voz[0]), sin_emoji(voz[1]), color)

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.save(ruta, "PNG")
    return ruta, sobra


def faja(titulo, subtitulo, color, archivo, w=1200, h=250):
    """Una cabecera BAJA, para separar bloques dentro de un mismo canal.

    La lamina completa es una portada: si se pone una por bloque, el canal se
    convierte en un desfile de portadas. Esta es la mitad de alta y no lleva
    lineas dibujadas — solo pone cara al bloque. Debajo va el texto de verdad,
    que en un canal de comandos **hay que poder copiar**: son nombres de bots.
    """
    titulo, subtitulo = sin_emoji(titulo), sin_emoji(subtitulo)
    oscuro, noche = (26, 18, 46), (14, 16, 34)
    img = degradado(w, h, oscuro, noche)
    img = brillo(img, (int(w * 0.82), h // 2), int(h * 0.9), color, 55)
    d = ImageDraw.Draw(img)
    polvo(d, w, h, (255, 255, 255), 60, semilla=len(titulo))
    onda(d, int(w * 0.66), int(w * 0.95), h // 2, int(h * 0.26), color,
         semilla=len(titulo) * 7)
    d.rectangle([0, 0, 8, h], fill=color)

    # los mismos detalles que la lamina, pero solo la esquina de encuadre: a esta
    # altura, la rejilla y la diagonal ensucian en vez de adornar
    tenue = tuple(int(v * 0.30) for v in color)
    d.line([(w - 84, 26), (w - 26, 26)], fill=tenue, width=3)
    d.line([(w - 26, 26), (w - 26, 84)], fill=tenue, width=3)

    f_tit = _encoge(d, [titulo.upper()], FUENTE_TIT, 62, int(w * 0.62) - 58, minimo=40)
    f_sub = ImageFont.truetype(FUENTE_FINA, 28)
    d.text((58, 62), titulo.upper(), font=f_tit, fill=(255, 255, 255))
    ancho1 = int(d.textlength(titulo.upper().split(" ")[0], font=f_tit))
    d.rectangle([60, 136, 60 + min(ancho1, 180), 141], fill=color)
    d.text((62, 158), subtitulo, font=f_sub, fill=(198, 200, 214))

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.save(ruta, "PNG")
    return ruta


def icono_servidor(archivo="icono.png", tam=512):
    """El icono del servidor: la onda, que es la marca de la casa.

    El anterior era un microfono dibujado a mano, del primer dia, y no se parecia
    a nada de lo demas. Este usa **lo mismo que llevan las 54 laminas**: el
    degradado morado noche, el polvo de estrellas y la onda de audio. Asi el icono
    de la lista de servidores y la portada de cualquier canal son la misma cosa.

    A 32 px —que es como se ve de verdad en la lista— un microfono con su arco y
    su pie se convierte en un borron. Una onda gruesa y centrada se sigue leyendo.
    """
    oscuro, noche = (32, 22, 58), (14, 16, 34)
    img = degradado(tam, tam, oscuro, noche)
    img = brillo(img, (tam // 2, tam // 2), int(tam * 0.55), MORADO, 70)
    d = ImageDraw.Draw(img)
    polvo(d, tam, tam, (255, 255, 255), 70, semilla=7)

    # la onda, gorda y centrada: es lo unico que tiene que leerse a 32 px
    onda(d, int(tam * 0.15), int(tam * 0.85), tam // 2, int(tam * 0.32), ROSA,
         semilla=3, ancho=tam // 40, hueco=tam // 64)

    # un anillo por dentro del borde, que da el aire de insignia
    m = int(tam * 0.045)
    d.ellipse([m, m, tam - m, tam - m], outline=tuple(int(v * 0.55) for v in ROSA),
              width=max(3, tam // 90))

    # Discord recorta el icono en circulo: lo de fuera del circulo se pierde, asi
    # que se pinta negro para que no asome un pico de degradado en las esquinas
    mascara = Image.new("L", (tam, tam), 0)
    ImageDraw.Draw(mascara).ellipse([0, 0, tam, tam], fill=255)
    fondo = Image.new("RGB", (tam, tam), (10, 10, 20))
    fondo.paste(img, (0, 0), mascara)

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    fondo.save(ruta, "PNG")
    return ruta


def _icono_viejo(archivo="icono_viejo.png", tam=512):
    """El microfono del primer dia. Se guarda por si hay que volver."""
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # disco de fondo con degradado radial fingido por circulos
    for i in range(tam // 2, 0, -1):
        t = 1 - i / (tam / 2)
        c = (int(45 + 110 * t), int(30 + 59 * t), int(70 + 112 * t))
        d.ellipse([tam // 2 - i, tam // 2 - i, tam // 2 + i, tam // 2 + i], fill=c)

    cx = tam // 2
    # capsula del microfono
    d.rounded_rectangle([cx - 62, 118, cx + 62, 300], radius=62, fill=(255, 255, 255))
    # arco
    d.arc([cx - 112, 168, cx + 112, 372], start=0, end=180,
          fill=(255, 255, 255), width=22)
    # pie
    d.rectangle([cx - 11, 360, cx + 11, 418], fill=(255, 255, 255))
    d.rounded_rectangle([cx - 78, 412, cx + 78, 436], radius=12, fill=(255, 255, 255))
    # rejilla de la capsula
    for y in range(150, 290, 26):
        d.line([cx - 40, y, cx + 40, y], fill=(150, 110, 190), width=7)

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.convert("RGB").save(ruta, "PNG")
    return ruta


# ------------------------------------------------------------------ subida

def _parrafo(d, texto, fuente_ruta, tam, ancho, lineas_max):
    """Parte un texto en líneas que quepan, encogiendo la letra si hacen falta
    más de las permitidas. Devuelve `(fuente, lineas)`."""
    while tam > 22:
        f = ImageFont.truetype(fuente_ruta, tam)
        lineas, actual = [], ""
        for palabra in texto.split():
            prueba = (actual + " " + palabra).strip()
            if d.textlength(prueba, font=f) <= ancho:
                actual = prueba
            else:
                if actual:
                    lineas.append(actual)
                actual = palabra
        if actual:
            lineas.append(actual)
        if len(lineas) <= lineas_max:
            return f, lineas
        tam -= 4
    return ImageFont.truetype(fuente_ruta, tam), lineas[:lineas_max]


def tarjeta_noticia(titular, fuente, color, archivo, w=1200, h=630, etiqueta=None):
    """La imagen de una noticia **que no trae imagen**.

    Media docena de feeds publican sin foto, y esas noticias salían como lo que
    son: un renglón de texto y un enlace azul. Al lado de una con portada se ven
    huérfanas, y el canal queda descosido — unas con cara y otras sin.

    Antes de esto se intentaba sacar la `og:image` de la propia página, que
    resuelve muchas; las que quedan es porque **la página tampoco tiene**, o
    porque la que tiene es el logo del sitio, y poner el logo es peor que no
    poner nada: es la imagen que «no tiene nada que ver».

    Así que se dibuja una. No inventa contenido —solo pone el titular grande, la
    fuente y, si la hay, la etiqueta— y viene con la cara del servidor, así que
    el canal se lee como una sola cosa en vez de como un revoltijo de webs.

    1200x630 es la proporción de las portadas de toda la vida (1,91:1), y en
    Discord manda el ancho, que es el lado bueno: se ve entera sin abrirla.
    """
    titular = sin_emoji(titular or "")
    img = degradado(w, h, (26, 18, 46), (14, 16, 34))
    img = brillo(img, (int(w * 0.82), int(h * 0.22)), 340, color, 55)
    d = ImageDraw.Draw(img)
    polvo(d, w, h, (255, 255, 255), 120, semilla=len(titular))
    onda(d, int(w * 0.06), int(w * 0.94), int(h * 0.86), 54, color,
         semilla=len(titular) * 5)
    d.rectangle([0, 0, 10, h], fill=color)
    detalles(d, w, h, color)

    margen = 72
    f_fuente = ImageFont.truetype(FUENTE, 30)
    d.text((margen, 56), sin_emoji(fuente).upper(), font=f_fuente, fill=color)
    ancho_f = d.textlength(sin_emoji(fuente).upper(), font=f_fuente)
    d.rectangle([margen, 98, margen + min(int(ancho_f), 320), 103], fill=color)

    if etiqueta:
        f_et = ImageFont.truetype(FUENTE, 26)
        texto = sin_emoji(etiqueta).upper()
        ancho_e = int(d.textlength(texto, font=f_et))
        d.rounded_rectangle([w - margen - ancho_e - 34, 52,
                             w - margen, 100], radius=10,
                            fill=(38, 33, 62),
                            outline=tuple(int(v * 0.7) for v in color), width=2)
        d.text((w - margen - ancho_e - 17, 60), texto, font=f_et, fill=color)

    # El titular manda: ocupa lo que le sobre y encoge solo si no cabe en cuatro
    # lineas. Un titular cortado con puntos suspensivos no sirve de portada.
    f_tit, lineas = _parrafo(d, titular, FUENTE_TIT, 74, w - margen * 2, 4)
    alto_bloque = len(lineas) * int(f_tit.size * 1.16)
    y = max(150, (h - 120 - alto_bloque) // 2 + 40)
    for linea in lineas:
        d.text((margen, y), linea, font=f_tit, fill=(255, 255, 255))
        y += int(f_tit.size * 1.16)

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.save(ruta, "PNG")
    return ruta


def _circular(img, tam):
    """Recorta una imagen a un círculo, con borde suave. Para el avatar."""
    img = img.convert("RGB").resize((tam, tam), Image.LANCZOS)
    # la máscara se dibuja al cuádruple y se reduce: así el borde sale liso en
    # vez de con los dientes de sierra que deja un círculo dibujado a pelo
    mascara = Image.new("L", (tam * 4, tam * 4), 0)
    ImageDraw.Draw(mascara).ellipse([0, 0, tam * 4, tam * 4], fill=255)
    mascara = mascara.resize((tam, tam), Image.LANCZOS)
    salida = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    salida.paste(img, (0, 0), mascara)
    return salida


def _bajar_imagen(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "YinX/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return Image.open(io.BytesIO(r.read()))
    except Exception:                                   # noqa: BLE001
        return None


def tarjeta_bienvenida(nombre, avatar_url, numero, color, archivo,
                       lema=None, w=1200, h=420):
    """La tarjeta de quien acaba de entrar: su cara, su nombre y qué número hace.

    Un «bienvenido @fulano» de texto se pierde entre los mensajes en diez
    minutos. Una tarjeta con **su propia cara dentro** se queda, y al que entra
    le dice que alguien preparó el sitio antes de que llegara — que es justo la
    diferencia entre un servidor y una sala vacía.

    El número no es decoración: **«eres la persona 41» convierte una cifra en un
    sitio en la fila**. En un servidor pequeño eso juega a favor, no en contra.
    """
    img = degradado(w, h, (26, 18, 46), (14, 16, 34))
    img = brillo(img, (int(w * 0.18), h // 2), 300, color, 70)
    d = ImageDraw.Draw(img)
    polvo(d, w, h, (255, 255, 255), 90, semilla=len(nombre or "x"))
    onda(d, int(w * 0.34), int(w * 0.97), int(h * 0.86), 46, color,
         semilla=len(nombre or "x") * 3)
    d.rectangle([0, 0, 10, h], fill=color)
    detalles(d, w, h, color)

    # el avatar, con un aro del color del servidor
    tam, cx, cy = 210, 150, h // 2
    d.ellipse([cx - tam // 2 - 7, cy - tam // 2 - 7,
               cx + tam // 2 + 7, cy + tam // 2 + 7], outline=color, width=5)
    cara = _bajar_imagen(avatar_url) if avatar_url else None
    if cara:
        img.paste(_circular(cara, tam), (cx - tam // 2, cy - tam // 2),
                  _circular(cara, tam))
    else:
        # sin avatar no se deja el hueco: se pone la inicial
        d.ellipse([cx - tam // 2, cy - tam // 2, cx + tam // 2, cy + tam // 2],
                  fill=(38, 33, 62))
        f = ImageFont.truetype(FUENTE_TIT, 110)
        letra = (sin_emoji(nombre or "?").strip() or "?")[0].upper()
        ancho = d.textlength(letra, font=f)
        d.text((cx - ancho / 2, cy - 76), letra, font=f, fill=color)

    x = cx + tam // 2 + 54
    f_arriba = ImageFont.truetype(FUENTE, 30)
    d.text((x, 92), "TE ESTÁBAMOS ESPERANDO", font=f_arriba, fill=color)

    f_nom = _encoge(d, [sin_emoji(nombre or "")], FUENTE_TIT, 76, w - x - 60,
                    minimo=40)
    d.text((x, 136), sin_emoji(nombre or ""), font=f_nom, fill=(255, 255, 255))
    d.rectangle([x + 2, 232, x + 90, 238], fill=color)

    f_pie = ImageFont.truetype(FUENTE_FINA, 32)
    d.text((x, 258), f"Eres la persona número {numero}", font=f_pie,
           fill=(198, 200, 214))
    if lema:
        f_lema = ImageFont.truetype(FUENTE_CURSIVA, 28)
        d.text((x, 306), f"«{sin_emoji(lema)}»", font=f_lema, fill=(150, 152, 170))

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.convert("RGB").save(ruta, "PNG")
    return ruta


def subir_con_imagen(canal_id, ruta, payload, endpoint="messages", metodo="POST"):
    """Multipart: Discord necesita esto para adjuntar un archivo.

    `endpoint` es "messages" para un canal normal y "threads" para abrir un hilo
    con la imagen dentro — que es la unica forma de poner una portada en un foro,
    porque un foro no acepta mensajes sueltos. Tambien vale "messages/<id>" con
    metodo PATCH, para **añadirle una imagen a un mensaje que ya existe** sin
    tocar su texto.
    """
    limite = "----yinx" + str(int(time.time() * 1000))
    nombre = os.path.basename(ruta)
    with open(ruta, "rb") as f:
        binario = f.read()

    partes = []
    partes.append(f"--{limite}\r\n".encode())
    partes.append(b'Content-Disposition: form-data; name="payload_json"\r\n')
    partes.append(b"Content-Type: application/json\r\n\r\n")
    partes.append(json.dumps(payload).encode("utf-8") + b"\r\n")
    partes.append(f"--{limite}\r\n".encode())
    partes.append(f'Content-Disposition: form-data; name="files[0]"; filename="{nombre}"\r\n'
                  .encode())
    partes.append(b"Content-Type: image/png\r\n\r\n")
    partes.append(binario + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    cuerpo = b"".join(partes)

    req = urllib.request.Request(f"{ds.API}/channels/{canal_id}/{endpoint}",
                                 data=cuerpo, method=metodo)
    req.add_header("Authorization", "Bot " + ds.token())
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    req.add_header("User-Agent", "YinX-discord-servidor/1.0")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code} subiendo {nombre}:\n"
                         f"{e.read().decode('utf-8', 'replace')[:400]}")


BANNERS = [
    ("ıı・📜・reglas",       "Reglas",     "Ocho normas y sentido comun",              MORADO, "reglas.png"),
    ("ıı・🗺️・guia",         "El mapa",    "Ocho zonas, y que hay en cada una",        AZUL,   "guia.png"),
    ("ıı・⭐・autoroles",    "Tus roles",  "Elige color, avisos y por donde empiezas", ROSA,   "roles.png"),
    ("ıı・👋・bienvenidas",  "Bienvenido", "Aqui saludamos a cada persona nueva",      (46, 204, 113), "bienvenida.png"),
    ("ıı・🎧・demos",        "Demos",      "Tu ficha de voz: un hilo, el tuyo",        ORO,    "demos.png"),
    ("ıı・🎬・castings",     "Castings",   "Cada convocatoria, un hilo",               (231, 76, 60),  "castings.png"),
    ("ıı・📂・proyectos",    "Proyectos",  "De buscando gente a estrenado",            (26, 188, 156), "proyectos.png"),
    ("ıı・📣・avisos-clases","Clases",     "Doblaje, locucion y canto",                (26, 188, 156), "clases.png"),
    ("ıı・🎟️・eventos",      "En vivo",    "Radio, karaoke, escenario y eventos",      (230, 126, 34), "envivo.png"),
    ("ıı・🎫・soporte",      "Soporte",    "Abre un ticket: solo lo vemos tu y el staff", (149, 165, 166), "soporte.png"),
    ("ıı・🎚️・edicion",      "Edicion",    "Audio, video, miniaturas y diseno",        (142, 154, 175), "edicion.png"),
    ("ıı・🧰・recursos",    "Recursos",   "Lo que le sirve a los demas",              (241, 196, 15), "recursos.png"),
    ("ıı・🎬・estrenos",     "Estrenos",   "Lo que se termina, con sus creditos",      (241, 196, 15), "estrenos.png"),
    ("ıı・🤝・colaboraciones","Colaborar",  "El que sabe con el que empieza",           (26, 188, 156), "colaboraciones.png"),
    ("ıı・😹・fandub-de-memes","Memes",     "Doblar tonterias, y que de risa",          (255, 123, 172), "fandubmemes.png"),
    ("ıı・🌐・traduccion",    "Traduccion", "Guiones y letras, de un idioma a otro",    (114, 137, 218), "traduccion.png"),
    ("ıı・🎛️・hardware",     "Hardware",   "Micros y camaras, con el precio delante",  (149, 165, 166), "hardware.png"),
    ("ıı・💭・ideas-de-proyecto","Ideas",   "Trae la tuya, aunque acabes de llegar",    (155, 89, 182), "ideas.png"),
    ("ıı・🗳️・votaciones",   "Votaciones", "Cuando decide todo el mundo",              (52, 152, 219), "votaciones.png"),
    ("ıı・📰・noticias",      "Noticias",   "Anime, juegos y doblaje, segun sale",      (230, 126, 34), "noticias.png"),
    ("ıı・📚・material-de-clase","Clases",  "Cada clase, con su numero y su resumen",   (26, 188, 156), "material.png"),
    ("ıı・🔴・en-directo",    "En directo", "Alguien esta haciendo algo ahora mismo",   (231, 76, 60),  "endirecto.png"),
    ("ıı・🧭・sugerido",      "Sugerido",   "Lo que vale la pena y casi nadie vio",     (241, 196, 15), "sugerido.png"),
    ("ıı・🙋・si-te-atascas", "Atascado",   "Escribe aqui y te sacamos",                (46, 204, 113), "atascas.png"),
    ("ıı・🔓・tus-zonas",     "Tus zonas",  "Abre y cierra lo que quieras ver",         (155, 89, 182), "zonas.png"),
    ("ıı・🤝・alianzas",      "Alianzas",   "Servidores amigos",                        (114, 137, 218), "alianzas.png"),
    ("ıı・🎂・cumples",       "Cumples",    "Solo dia y mes: el año no se pregunta",    (255, 123, 172), "cumples.png"),
    ("ıı・🎵・canto",         "Canto",      "Hablar de cantar, sin que juzgue nadie",   (0, 184, 212),  "canto.png"),
    ("ıı・🎼・demos-canto",   "Demos de canto", "Un hilo por cover",              (0, 184, 212),  "demoscanto.png"),
    ("ıı・🧰・recursos",      "Recursos",   "Lo que le sirve a los demas",              (241, 196, 15), "recursos.png"),
    ("ıı・🤖・comandos",     "Ocio",       "Bots, mudae y sorteos",                    ROSA,   "ocio.png"),
]


def cmd_generar(_):
    print("icono:", icono_servidor())
    for _canal, tit, sub, color, arch in BANNERS:
        print("banner:", banner(tit, sub, "", color, arch))


def cmd_icono(args):
    ruta = icono_servidor()
    with open(ruta, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    print(f"icono generado ({os.path.getsize(ruta) // 1024} KB)")
    if not args.enserio:
        print(">>> SIMULACRO. Agrega --enserio para ponerlo en el servidor.")
        return
    g = ds.api("GET", f"/guilds/{args.guild_id}")
    ds.api("PATCH", f"/guilds/{args.guild_id}",
           {"features": g.get("features"), "icon": "data:image/png;base64," + b64})
    print("icono aplicado al servidor")


def cmd_subir(args):
    todos = ds.api("GET", f"/guilds/{args.guild_id}/channels")
    canales = {c["name"]: c for c in todos}
    activos = (ds.api("GET", f"/guilds/{args.guild_id}/threads/active") or {}).get("threads", [])
    ya = {c["id"] for c in todos
          if c["type"] in (0, 5) and any(
              m.get("attachments") for m in
              ds.api("GET", f"/channels/{c['id']}/messages?limit=10") or [])}

    puestos = 0
    for canal, tit, sub, color, arch in BANNERS:
        c = canales.get(canal)
        if not c:
            print(f"  no existe {canal}")
            continue
        # Un foro no acepta mensajes: hay que escribir dentro de un hilo suyo.
        if c["type"] == 15:
            hilo = next((t for t in activos if t.get("parent_id") == c["id"]), None)
            if not hilo:
                print(f"  {canal}: es un foro y no tiene hilos, lo salto")
                continue
            cid = hilo["id"]
        else:
            cid = c["id"]
            # Con --rehacer se borra la cabecera vieja del bot y se pone la nueva.
            # Sin esto, al cambiar el diseño los canales se quedaban con la de antes
            # y el servidor acababa con dos estilos mezclados.
            if cid in ya and getattr(args, "rehacer", False):
                for m in ds.api("GET", f"/channels/{cid}/messages?limit=20") or []:
                    if m.get("attachments") and (m.get("author") or {}).get("bot") \
                            and not (m.get("content") or "").strip():
                        ds.api("DELETE", f"/channels/{cid}/messages/{m['id']}")
                        time.sleep(0.35)
                ya.discard(cid)
            if cid in ya:
                print(f"  {canal}: ya tiene una imagen, lo salto")
                continue
        ruta = banner(tit, sub, "", color, arch)
        print(f"  {canal}  <- {arch}")
        if not args.enserio:
            continue
        # 'content' vacio tiene que ir SI o SI: sin el, Discord devuelve 400.
        # El banner va solo, como primer mensaje: hace de portada de la seccion.
        subir_con_imagen(cid, ruta, {"content": "",
                                     "attachments": [{"id": 0, "filename": arch}]})
        puestos += 1
        time.sleep(0.8)
    print(f"\nbanners subidos: {puestos}")
    if not args.enserio:
        print("Repite con --enserio.")


def cmd_navegacion(args):
    """Panel de botones que llevan a cada canal de un clic.

    Son botones de estilo 5 (LINK): solo abren una URL, asi que NO hacen falta
    interacciones ni que el bot este corriendo. Funcionan siempre, aunque el
    bot se vaya del servidor.
    """
    G = args.guild_id
    ch = {c["name"]: c["id"] for c in ds.api("GET", f"/guilds/{G}/channels")}

    def url(frag):
        for n, i in ch.items():
            if frag in n:
                return f"https://discord.com/channels/{G}/{i}"

    def boton(lab, emo, frag):
        u = url(frag)
        return {"type": 2, "style": 5, "label": lab,
                "emoji": {"name": emo}, "url": u} if u else None

    filas = [
        [("Reglas", "📜", "reglas"), ("Tus roles", "⭐", "autoroles"),
         ("Preséntate", "🪪", "presentaciones"), ("General", "🌐", "general")],
        [("Tus demos", "🎧", "demos"), ("Castings", "🎬", "castings"),
         ("Proyectos", "📂", "proyectos"), ("Clases", "📣", "avisos-clases")],
        [("Radio", "📻", "Radio 24/7"), ("Karaoke", "🎶", "Karaoke"),
         ("Cine", "🍿", "Cine"), ("Crear sala", "➕", "CREAR SALA")],
        [("Edición", "🎚️", "edicion"), ("Galería", "🖼️", "galeria"),
         ("Soporte", "🎫", "soporte"), ("Sugerencias", "💡", "sugerencias")],
    ]
    componentes = []
    for fila in filas:
        botones = [b for b in (boton(*x) for x in fila) if b]
        if botones:
            componentes.append({"type": 1, "components": botones[:5]})

    total = sum(len(f["components"]) for f in componentes)
    print(f"{total} botones en {len(componentes)} filas")
    if not args.enserio:
        print(">>> SIMULACRO. Agrega --enserio.")
        return

    cid = ch.get("ıı・🗺️・guia")
    r = ds.api("POST", f"/channels/{cid}/messages", {
        "content": ("## 🧭 Ir directo a...\nUn clic y te lleva. Si un botón no te abre "
                    "nada, es que esa zona no la tienes activada todavía: se cambia en "
                    "**Canales y roles**."),
        "components": componentes,
    })
    ds.api("PUT", f"/channels/{cid}/pins/{r['id']}")
    print("panel publicado y fijado")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("generar").set_defaults(f=cmd_generar)
    i = s.add_parser("icono"); i.add_argument("guild_id")
    i.add_argument("--enserio", action="store_true"); i.set_defaults(f=cmd_icono)
    u = s.add_parser("subir"); u.add_argument("guild_id")
    u.add_argument("--enserio", action="store_true")
    u.add_argument("--rehacer", action="store_true",
                   help="borra la cabecera vieja del bot y pone la nueva")
    u.set_defaults(f=cmd_subir)
    nv = s.add_parser("navegacion"); nv.add_argument("guild_id")
    nv.add_argument("--enserio", action="store_true"); nv.set_defaults(f=cmd_navegacion)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
