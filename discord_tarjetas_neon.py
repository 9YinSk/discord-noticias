"""Las dos tarjetas que se publican solas, en el lenguaje del logo.

Son las imágenes **más vistas del servidor** y eran las últimas en el diseño
viejo: la de noticia sale cada media hora en cuatro canales, y la de bienvenida
la ve entera cada persona que entra. Dejarlas fuera del rediseño habría sido
dejar fuera justo lo que más se mira.

Las dos comparten la firma del logo con las láminas —los rayos radiales, el
filete de dientes de oro, el neón— pero **no son láminas**: aquí no hay fichas
ni secciones, hay un titular que tiene que leerse de un vistazo y una cara que
tiene que reconocerse. Por eso el layout es propio y no un caso de `lamina()`.

Ambas mantienen la firma de las de `discord_banners`, para que cambiar de
estilo sea cambiar el `import` en `discord_noticias.py` y en
`discord_bienvenida.py`.
"""

import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from discord_banners import (  # noqa: E402
    FUENTE, FUENTE_TIT, SALIDA, sin_emoji, _parrafo, _bajar_imagen, _circular)
from discord_laminas_neon import (  # noqa: E402
    brillar, simbolo, _textura, _envolver, NEGRO, CREMA, GRIS, ORO, MORADO)


def _fondo_neon(w, h, luz, foco, radios=22):
    """Los rayos del logo con el foco donde se le diga. Devuelve la imagen."""
    img = Image.new("RGB", (w, h), NEGRO)
    d = ImageDraw.Draw(img)
    fx, fy = foco
    R = max(w, h) * 1.6
    for k in range(radios):
        a0 = k * (360 / radios)
        if k % 2 == 0:
            d.pieslice([fx-R, fy-R, fx+R, fy+R],
                       start=a0, end=a0 + 360/radios, fill=(26, 13, 40))
    cap = Image.new("L", (w, h), 0)
    ImageDraw.Draw(cap).ellipse([fx-w*.22, fy-h*.34, fx+w*.22, fy+h*.34], fill=125)
    img.paste(Image.new("RGB", (w, h), luz), (0, 0),
              cap.filter(ImageFilter.GaussianBlur(int(h/5))))
    return img


def _dientes(d, w, color, y=0, alto=None):
    """El filete de arriba. Ya SIN dientes, pese al nombre.

    Colgaban veintiséis triángulos de oro de esta banda. Es la cuarta pieza de
    la que se caen —la cabecera de la web, las 41 láminas, el icono del servidor
    y ahora las tarjetas— y siempre por lo mismo: repetido a lo largo de un
    borde deja de ser un remate y pasa a ser un patrón, y encima es lo PRIMERO
    que se ve de la pieza.

    En una tarjeta de bienvenida eso pesa el doble: es la primera imagen que ve
    alguien que acaba de entrar al servidor.

    Se conserva el nombre de la función para no tocar sus llamadas.
    """
    alto = alto or int(w * .0065)
    d.rectangle([0, y, w, y + alto], fill=color)


def tarjeta_noticia(titular, fuente, color, archivo, w=1200, h=630,
                    etiqueta=None, arte_url=None, simb="periodico"):
    """La imagen de una noticia que no trae foto propia.

    Se conserva entero el acierto de la versión vieja: **si se sabe de qué juego
    o anime habla, se usa su ilustración** de fondo, muy oscurecida, porque una
    portada que enseña de qué va vale más que un dibujo genérico bonito. Lo que
    cambia es el marco, que ahora es el del servidor y no el de antes.

    Cuando no hay arte, el hueco lo llena el símbolo en neón — antes quedaba un
    degradado liso con polvo, que era lo más soso de todo el servidor.
    """
    titular = sin_emoji(titular or "")
    fuente_txt = sin_emoji(fuente or "").upper()

    arte = _bajar_imagen(arte_url) if arte_url else None
    if arte:
        base = arte.convert("RGB")
        escala = max(w / base.width, h / base.height)
        base = base.resize((max(w, int(base.width * escala)),
                            max(h, int(base.height * escala))), Image.LANCZOS)
        # se recorta por arriba: en las portadas el personaje suele estar en la
        # mitad de arriba y centrar le corta la cara
        izq = (base.width - w) // 2
        img = base.crop((izq, 0, izq + w, h))
        # Más oscura que antes (0,62 → 0,70) porque encima va un titular a 74 px
        # y el neón del marco: con el arte a media luz competían los tres.
        img = Image.blend(img, Image.new("RGB", (w, h), (10, 8, 18)), 0.70)
        rayos = _fondo_neon(w, h, MORADO, (w*.84, h*.24))
        img = ImageChops.add(img, ImageChops.multiply(
            rayos, Image.new("RGB", (w, h), (70, 70, 70))))
    else:
        img = _fondo_neon(w, h, MORADO, (w*.84, h*.30))
        capa = Image.new("L", (w, h), 0)
        simbolo(simb, ImageDraw.Draw(capa), w*.84, h*.42, h*.20, max(5, int(h/60)))
        img = ImageChops.add(img, brillar(capa, color))

    d = ImageDraw.Draw(img)
    m = int(w * .06)

    # la fuente, arriba a la izquierda, con su subrayado
    f_fuente = ImageFont.truetype(FUENTE, 30)
    d.text((m, 58), fuente_txt, font=f_fuente, fill=color)
    an = d.textlength(fuente_txt, font=f_fuente)
    d.rectangle([m, 100, m + min(int(an), 320), 105], fill=color)

    if etiqueta:
        f_et = ImageFont.truetype(FUENTE, 26)
        texto = sin_emoji(etiqueta).upper()
        ancho_e = int(d.textlength(texto, font=f_et))
        d.rounded_rectangle([w - m - ancho_e - 34, 54, w - m, 102], radius=10,
                            fill=(24, 16, 36),
                            outline=tuple(int(v * .8) for v in color), width=2)
        d.text((w - m - ancho_e - 17, 62), texto, font=f_et, fill=color)

    # El titular manda: ocupa lo que le sobre y solo encoge si no cabe en cuatro
    # líneas. Un titular con puntos suspensivos no sirve de portada.
    ancho_tit = w - m*2 if arte else int(w * .64)
    f_tit, lineas = _parrafo(d, titular, FUENTE_TIT, 74, ancho_tit, 4)
    alto_bloque = len(lineas) * int(f_tit.size * 1.16)
    y = max(150, (h - 130 - alto_bloque) // 2 + 40)

    # halo bajo el titular: sobre una ilustración clara el blanco solo no basta
    cap = Image.new("L", (w, h), 0)
    dc = ImageDraw.Draw(cap)
    yy = y
    for linea in lineas:
        dc.text((m, yy), linea, font=f_tit, fill=255)
        yy += int(f_tit.size * 1.16)
    img = ImageChops.add(img, brillar(cap, color, radios=(6, 20), fuerzas=(.42, .22)))
    d = ImageDraw.Draw(img)
    for linea in lineas:
        d.text((m, y), linea, font=f_tit, fill=CREMA)
        y += int(f_tit.size * 1.16)

    _dientes(d, w, color)
    img = _textura(img, w, h)
    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.save(ruta, "PNG")
    return ruta


def tarjeta_bienvenida(nombre, avatar_url, numero, color, archivo,
                       lema=None, w=1200, h=420):
    """La tarjeta de quien acaba de entrar: su cara, su nombre y qué número hace.

    Se mantiene el motivo de la versión vieja, que sigue siendo bueno: **«eres la
    persona 41» convierte una cifra en un sitio en la fila**, y en un servidor
    pequeño eso juega a favor. Lo que cambia es que ahora entra por la misma
    puerta visual que el resto: rayos, neón y el filete de dientes.
    """
    nombre = sin_emoji(nombre or "")
    img = _fondo_neon(w, h, MORADO, (w*.17, h*.5))

    # el aro del avatar, en neón: es lo que ata la cara al lenguaje del logo
    tam, cx, cy = 210, int(w*.135), h // 2
    aro = Image.new("L", (w, h), 0)
    ImageDraw.Draw(aro).ellipse([cx-tam//2-9, cy-tam//2-9,
                                 cx+tam//2+9, cy+tam//2+9],
                                outline=255, width=7)
    img = ImageChops.add(img, brillar(aro, color, radios=(4, 14), fuerzas=(.8, .4)))

    cara = _bajar_imagen(avatar_url) if avatar_url else None
    if cara:
        mascara = Image.new("L", (tam, tam), 0)
        ImageDraw.Draw(mascara).ellipse([0, 0, tam-1, tam-1], fill=255)
        img.paste(cara.convert("RGB").resize((tam, tam), Image.LANCZOS),
                  (cx - tam//2, cy - tam//2), mascara)
    else:
        # sin avatar, la inicial: nunca un hueco vacío
        d0 = ImageDraw.Draw(img)
        d0.ellipse([cx-tam//2, cy-tam//2, cx+tam//2, cy+tam//2], fill=(24, 16, 36))
        fi = ImageFont.truetype(FUENTE_TIT, 110)
        letra = (nombre or "?")[0].upper()
        bb = d0.textbbox((0, 0), letra, font=fi)
        d0.text((cx-(bb[2]-bb[0])/2-bb[0], cy-(bb[3]-bb[1])/2-bb[1]),
                letra, font=fi, fill=color)

    d = ImageDraw.Draw(img)
    tx = int(w * .265)

    f_hola = ImageFont.truetype(FUENTE, 34)
    d.text((tx, int(h*.16)), "TE ESTÁBAMOS ESPERANDO", font=f_hola, fill=color)

    # el nombre, en neón, que es el motivo de la tarjeta
    f_nom = ImageFont.truetype(FUENTE_TIT, 78)
    while d.textlength(nombre, font=f_nom) > w - tx - int(w*.06) and f_nom.size > 34:
        f_nom = ImageFont.truetype(FUENTE_TIT, f_nom.size - 4)
    cap = Image.new("L", (w, h), 0)
    ImageDraw.Draw(cap).text((tx, int(h*.29)), nombre, font=f_nom, fill=255)
    img = ImageChops.add(img, brillar(cap, color, radios=(4, 16), fuerzas=(.55, .28)))
    d = ImageDraw.Draw(img)
    d.text((tx, int(h*.29)), nombre, font=f_nom, fill=CREMA)

    d.rounded_rectangle([tx, int(h*.585), tx + int(w*.07), int(h*.585)+6],
                        radius=3, fill=ORO)

    f_num = ImageFont.truetype(FUENTE, 34)
    d.text((tx, int(h*.655)), f"Eres la persona nº {numero} de esta casa",
           font=f_num, fill=CREMA)

    f_lema = ImageFont.truetype(FUENTE, 30)
    for k, ln in enumerate(_envolver(
            d, lema or "Pasa por reglas y por tus roles, y el servidor se te abre entero.",
            f_lema, w - tx - int(w*.06))[:2]):
        d.text((tx, int(h*.775) + k*38), ln, font=f_lema, fill=GRIS)

    _dientes(d, w, color)
    img = _textura(img, w, h)
    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, archivo)
    img.save(ruta, "PNG")
    return ruta


# `subir_con_imagen` se reexporta tal cual: los scripts que dibujan también
# suben, y así cambiar de estilo sigue siendo cambiar una sola línea de import
# en vez de dos.
from discord_banners import subir_con_imagen  # noqa: E402,F401
