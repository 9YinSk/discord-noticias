"""Las láminas del servidor, en el estilo del logo nuevo.

El logo del servidor (29-ago-2026) es una fusión de tres cosas: el **neón** del
cyberpunk, los **rayos radiales** art déco al modo de Hazbin Hotel, y la
**textura pintada** de Arcane. Este módulo lleva ese mismo lenguaje a las
láminas de cada canal, para que el servidor entero se vea de la misma casa.

Qué hace distinto al generador antiguo (`discord_banners.lamina`):

· Cada canal tiene **su propio símbolo en neón**, no el mismo micrófono para
  todos. El símbolo se dibuja de trazo, porque el neón necesita contorno: una
  forma maciza no brilla, se empasta.
· Cada canal tiene **su color de acento**, heredado de su categoría. Así el
  estudio es magenta, la academia dorada y el ocio naranja, pero todos comparten
  los rayos, el halo y el filete de dientes.
· El pie ya no es una frase suelta: es una **tarjeta de personaje**, con avatar,
  nombre, oficio y punto de «en línea». Tiene aire de mensaje de soporte.
· **No lleva botones dibujados.** Los botones de Discord son componentes reales
  y van fuera de la imagen; pintarlos dentro solo crea dibujos que nadie puede
  pulsar. De eso se sigue encargando `discord_botones.py`.

El texto sigue viniendo de `discord_contenido_canales.CANALES` y las voces de
`VOCES`, así que cambiar una frase sigue siendo cambiar una línea y volver a
generar. El PNG nunca es la fuente de verdad.
"""

import colorsys
import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from discord_banners import FUENTE, FUENTE_TIT, SALIDA

# ── la paleta del logo ───────────────────────────────────────────────────
NEGRO   = (11, 8, 16)
CREMA   = (246, 240, 232)
GRIS    = (170, 158, 180)
ORO     = (232, 182, 92)      # el filete y los dientes, siempre
MAGENTA = (240, 62, 150)
CIAN    = (74, 226, 232)
VERDE   = (110, 226, 140)
NARANJA = (246, 138, 72)
ROJO    = (232, 46, 66)
MORADO  = (108, 44, 168)


def brillar(capa, color, radios=(3, 10, 22), fuerzas=(1.0, .5, .28)):
    """Convierte una máscara de trazo en neón.

    Tres halos de radio creciente y un núcleo casi blanco encima. Sin el núcleo
    el tubo parece apagado; sin los halos parece una línea de color y no luz.
    """
    w, h = capa.size
    out = Image.new("RGB", (w, h), (0, 0, 0))
    for r, f in zip(radios, fuerzas):
        halo = capa.filter(ImageFilter.GaussianBlur(r))
        cap = Image.new("RGB", (w, h), tuple(int(c * f) for c in color))
        out = ImageChops.add(out, ImageChops.multiply(cap, Image.merge("RGB", (halo, halo, halo))))
    out.paste(Image.new("RGB", (w, h), (255, 250, 252)), (0, 0),
              capa.filter(ImageFilter.GaussianBlur(.6)))
    return out


def _textura(img, w, h, fuerza=18):
    """El grano de Arcane. Discreto: a más de 20 ensucia en vez de dar cuerpo."""
    rnd = random.Random(7)
    g = Image.new("L", (w, h), 0)
    px = g.load()
    for _ in range(w * h // 6):
        px[rnd.randrange(w), rnd.randrange(h)] = rnd.randrange(0, fuerza)
    return ImageChops.add(img, Image.merge("RGB", (g, g, g)).filter(ImageFilter.GaussianBlur(.5)))


# ── los símbolos, todos de trazo ─────────────────────────────────────────
def simbolo(nombre, d, cx, cy, s, g):
    """Dibuja el símbolo del canal en un cuadrado de lado 2s centrado en (cx, cy).

    `d` tiene que ser un ImageDraw sobre una máscara en modo "L": aquí solo se
    pinta con 255 (traza) y 0 (borra), y el color lo pone `brillar` después.
    """
    if nombre == "micro":
        d.rounded_rectangle([cx-s*.30, cy-s*.85, cx+s*.30, cy-s*.05], radius=s*.30, outline=255, width=g)
        d.arc([cx-s*.56, cy-s*.52, cx+s*.56, cy+s*.42], start=0, end=180, fill=255, width=g)
        d.line([cx, cy+s*.42, cx, cy+s*.80], fill=255, width=g)
        d.line([cx-s*.34, cy+s*.80, cx+s*.34, cy+s*.80], fill=255, width=g)

    elif nombre == "claqueta":
        d.rounded_rectangle([cx-s*.78, cy-s*.20, cx+s*.78, cy+s*.72], radius=s*.10, outline=255, width=g)
        d.line([cx-s*.78, cy-s*.62, cx+s*.78, cy-s*.62], fill=255, width=g)
        d.line([cx-s*.78, cy-s*.62, cx-s*.78, cy-s*.20], fill=255, width=g)
        d.line([cx+s*.78, cy-s*.62, cx+s*.78, cy-s*.20], fill=255, width=g)
        for k in range(4):
            x = cx-s*.78 + k*s*.39
            d.line([x+s*.10, cy-s*.62, x+s*.30, cy-s*.20], fill=255, width=g)

    elif nombre == "nota":
        d.ellipse([cx-s*.62, cy+s*.10, cx-s*.02, cy+s*.66], outline=255, width=g)
        d.line([cx-s*.05, cy+s*.40, cx-s*.05, cy-s*.72], fill=255, width=g)
        d.line([cx-s*.05, cy-s*.72, cx+s*.62, cy-s*.48], fill=255, width=g)
        d.line([cx-s*.05, cy-s*.40, cx+s*.62, cy-s*.16], fill=255, width=g)

    elif nombre == "faders":
        for k, alt in enumerate([-.18, .22, -.02]):
            x = cx-s*.55 + k*s*.55
            d.line([x, cy-s*.72, x, cy+s*.72], fill=255, width=max(2, g-2))
            d.rounded_rectangle([x-s*.20, cy+alt*s-s*.12, x+s*.20, cy+alt*s+s*.12],
                                radius=s*.07, outline=255, width=g)

    elif nombre == "arte":
        # Paleta de pintor. Van ya tres intentos: un pincel suelto que se leía
        # como una flecha, y una paleta con los pegotes DIBUJADOS DE CONTORNO
        # que salía como una bola de bolos -- cuatro circulitos huecos del mismo
        # grosor que el borde, y nada dice que sean pintura.
        #
        # Lo que lo arregla es que los pegotes vayan MACIZOS. En un dibujo de
        # trazo, lo relleno se lee como materia; el neón aguanta perfectamente
        # una mancha pequeña, lo que no aguanta es una forma grande maciza.
        # Y el agujero del pulgar tiene que ser el único hueco, o compite.
        d.ellipse([cx-s*.86, cy-s*.72, cx+s*.86, cy+s*.62], outline=255, width=g)
        # el mordisco de abajo a la derecha, que es lo que hace que sea paleta
        # y no un plato: el hueco por donde entra la mano
        d.arc([cx+s*.10, cy-s*.02, cx+s*.98, cy+s*.86], start=170, end=350, fill=255, width=g)
        d.ellipse([cx+s*.26, cy-s*.02, cx+s*.54, cy+s*.26], outline=255, width=max(2, g-1))
        for px_, py, rr in [(-.46, -.18, .15), (-.14, -.42, .13),
                            (.22, -.34, .11), (-.34, .20, .12)]:
            d.ellipse([cx+s*px_-s*rr, cy+s*py-s*rr, cx+s*px_+s*rr, cy+s*py+s*rr],
                      fill=255)

    elif nombre == "birrete":
        d.polygon([(cx, cy-s*.62), (cx+s*.85, cy-s*.18), (cx, cy+s*.26), (cx-s*.85, cy-s*.18)],
                  outline=255, width=g)
        d.line([cx+s*.55, cy-s*.02, cx+s*.55, cy+s*.56], fill=255, width=g)
        d.arc([cx-s*.45, cy+s*.06, cx+s*.45, cy+s*.52], start=0, end=180, fill=255, width=g)

    elif nombre == "megafono":
        d.polygon([(cx-s*.72, cy-s*.22), (cx+s*.20, cy-s*.68), (cx+s*.20, cy+s*.62),
                   (cx-s*.72, cy+s*.20)], outline=255, width=g)
        for k, r in enumerate([.30, .48, .66]):
            d.arc([cx+s*.20-s*r, cy-s*r, cx+s*.20+s*r, cy+s*r], start=-58, end=58,
                  fill=255, width=max(2, g-1))

    elif nombre == "bocadillo":
        d.rounded_rectangle([cx-s*.78, cy-s*.62, cx+s*.78, cy+s*.30], radius=s*.26, outline=255, width=g)
        d.line([cx-s*.36, cy+s*.30, cx-s*.50, cy+s*.74], fill=255, width=g)
        d.line([cx-s*.50, cy+s*.74, cx-s*.08, cy+s*.30], fill=255, width=g)

    elif nombre == "pergamino":
        d.rounded_rectangle([cx-s*.58, cy-s*.72, cx+s*.58, cy+s*.72], radius=s*.10, outline=255, width=g)
        for k in range(4):
            y = cy-s*.42 + k*s*.28
            d.line([cx-s*.34, y, cx+s*.34, y], fill=255, width=max(2, g-2))

    elif nombre == "mando":
        d.rounded_rectangle([cx-s*.82, cy-s*.34, cx+s*.82, cy+s*.38], radius=s*.34, outline=255, width=g)
        d.line([cx-s*.48, cy, cx-s*.18, cy], fill=255, width=max(2, g-1))
        d.line([cx-s*.33, cy-s*.15, cx-s*.33, cy+s*.15], fill=255, width=max(2, g-1))
        d.ellipse([cx+s*.20, cy-s*.16, cx+s*.44, cy+s*.08], outline=255, width=max(2, g-1))

    elif nombre == "camara":
        d.rounded_rectangle([cx-s*.80, cy-s*.42, cx+s*.80, cy+s*.58], radius=s*.14, outline=255, width=g)
        d.ellipse([cx-s*.30, cy-s*.18, cx+s*.30, cy+s*.42], outline=255, width=g)
        d.rounded_rectangle([cx-s*.34, cy-s*.62, cx+s*.02, cy-s*.42], radius=s*.05, outline=255, width=g)

    elif nombre == "mapa":
        # Mapa plegado. Antes era una brújula y parecía un diamante en un círculo.
        d.polygon([(cx-s*.82, cy-s*.44), (cx-s*.27, cy-s*.66), (cx+s*.27, cy-s*.40),
                   (cx+s*.82, cy-s*.62), (cx+s*.82, cy+s*.50), (cx+s*.27, cy+s*.72),
                   (cx-s*.27, cy+s*.46), (cx-s*.82, cy+s*.68)], outline=255, width=g)
        d.line([cx-s*.27, cy-s*.66, cx-s*.27, cy+s*.46], fill=255, width=max(2, g-2))
        d.line([cx+s*.27, cy-s*.40, cx+s*.27, cy+s*.72], fill=255, width=max(2, g-2))
        d.ellipse([cx-s*.10, cy-s*.16, cx+s*.10, cy+s*.04], outline=255, width=max(2, g-1))

    elif nombre == "calendario":
        d.rounded_rectangle([cx-s*.74, cy-s*.52, cx+s*.74, cy+s*.70], radius=s*.10, outline=255, width=g)
        d.line([cx-s*.74, cy-s*.18, cx+s*.74, cy-s*.18], fill=255, width=max(2, g-1))
        d.line([cx-s*.40, cy-s*.74, cx-s*.40, cy-s*.34], fill=255, width=g)
        d.line([cx+s*.40, cy-s*.74, cx+s*.40, cy-s*.34], fill=255, width=g)

    elif nombre == "salvavidas":
        # Para soporte. El ticket con muesca no se entendía a tamaño pequeño.
        d.ellipse([cx-s*.80, cy-s*.80, cx+s*.80, cy+s*.80], outline=255, width=g)
        d.ellipse([cx-s*.34, cy-s*.34, cx+s*.34, cy+s*.34], outline=255, width=g)
        for a in (45, 135, 225, 315):
            ar = math.radians(a)
            d.line([cx+s*.34*math.cos(ar), cy+s*.34*math.sin(ar),
                    cx+s*.80*math.cos(ar), cy+s*.80*math.sin(ar)], fill=255, width=g)

    elif nombre == "libro":
        d.line([cx, cy-s*.42, cx, cy+s*.60], fill=255, width=g)
        d.polygon([(cx-s*.02, cy-s*.42), (cx-s*.82, cy-s*.22), (cx-s*.82, cy+s*.56),
                   (cx-s*.02, cy+s*.60)], outline=255, width=g)
        d.polygon([(cx+s*.02, cy-s*.42), (cx+s*.82, cy-s*.22), (cx+s*.82, cy+s*.56),
                   (cx+s*.02, cy+s*.60)], outline=255, width=g)

    elif nombre == "periodico":
        d.rounded_rectangle([cx-s*.78, cy-s*.58, cx+s*.62, cy+s*.62], radius=s*.06, outline=255, width=g)
        d.rounded_rectangle([cx+s*.62, cy-s*.30, cx+s*.82, cy+s*.62], radius=s*.06,
                            outline=255, width=max(2, g-1))
        d.rounded_rectangle([cx-s*.60, cy-s*.40, cx-s*.06, cy-s*.02], radius=s*.04,
                            outline=255, width=max(2, g-1))
        for k in range(3):
            y = cy+s*.12 + k*s*.18
            d.line([cx-s*.60, y, cx+s*.44, y], fill=255, width=max(2, g-2))

    elif nombre == "auriculares":
        d.arc([cx-s*.78, cy-s*.72, cx+s*.78, cy+s*.48], start=180, end=360, fill=255, width=g)
        d.rounded_rectangle([cx-s*.80, cy-s*.14, cx-s*.36, cy+s*.56], radius=s*.16, outline=255, width=g)
        d.rounded_rectangle([cx+s*.36, cy-s*.14, cx+s*.80, cy+s*.56], radius=s*.16, outline=255, width=g)

    elif nombre == "onda":
        for k, a in enumerate([.28, .58, .88, .58, .28]):
            x = cx - s*.72 + k*s*.36
            d.line([x, cy-s*a, x, cy+s*a], fill=255, width=g)

    elif nombre == "estrella":
        pts = []
        for k in range(10):
            ang = math.radians(-90 + k*36)
            rr = s*.80 if k % 2 == 0 else s*.34
            pts.append((cx + rr*math.cos(ang), cy + rr*math.sin(ang)))
        d.polygon(pts, outline=255, width=g)

    elif nombre == "diana":
        for r in (.80, .52, .24):
            d.ellipse([cx-s*r, cy-s*r, cx+s*r, cy+s*r], outline=255, width=g)

    elif nombre == "carpeta":
        d.polygon([(cx-s*.80, cy+s*.60), (cx-s*.80, cy-s*.46), (cx-s*.18, cy-s*.46),
                   (cx-s*.02, cy-s*.24), (cx+s*.80, cy-s*.24), (cx+s*.80, cy+s*.60)],
                  outline=255, width=g)

    elif nombre == "llave":
        d.ellipse([cx-s*.78, cy-s*.34, cx-s*.10, cy+s*.34], outline=255, width=g)
        d.line([cx-s*.16, cy, cx+s*.78, cy], fill=255, width=g)
        d.line([cx+s*.44, cy, cx+s*.44, cy+s*.34], fill=255, width=g)
        d.line([cx+s*.70, cy, cx+s*.70, cy+s*.26], fill=255, width=g)

    elif nombre == "etiqueta":
        d.polygon([(cx-s*.72, cy-s*.52), (cx+s*.28, cy-s*.52), (cx+s*.80, cy),
                   (cx+s*.28, cy+s*.52), (cx-s*.72, cy+s*.52)], outline=255, width=g)
        d.ellipse([cx+s*.28, cy-s*.12, cx+s*.52, cy+s*.12], outline=255, width=max(2, g-1))

    elif nombre == "enlace":
        # Eran dos arcos muy achatados pegados por una raya, y juntos se leían
        # como UN óvalo con un palo dentro. Un eslabón se reconoce por ser
        # cerrado y alargado, y una cadena por ser DOS con un hueco entre medias.
        #
        # Así que van dos cápsulas cerradas, separadas de verdad, y la barra que
        # las une sale por el hueco. El hueco es la pieza que hace el dibujo: sin
        # él vuelven a fundirse en una sola forma.
        # Segunda pasada: con .88 de ancho y .68 de alto cada cápsula salía
        # casi redonda, y dos círculos unidos por una barra son unas gafas.
        # Un eslabón es LARGO -- esa es su proporción, y es lo que lo distingue
        # de un aro. Se estrechan a la mitad de alto y se solapan más.
        d.rounded_rectangle([cx-s*.96, cy-s*.26, cx-s*.08, cy+s*.26],
                            radius=s*.26, outline=255, width=g)
        d.rounded_rectangle([cx+s*.08, cy-s*.26, cx+s*.96, cy+s*.26],
                            radius=s*.26, outline=255, width=g)
        d.line([cx-s*.36, cy, cx+s*.36, cy], fill=255, width=g)

    elif nombre == "escudo":
        # Era un hexágono, y se leía como un hexágono. La culpa la tenía el
        # remate de ARRIBA: subía a una punta, y un polígono con punta arriba y
        # punta abajo es simétrico, o sea una tuerca.
        #
        # Un escudo tiene el borde de arriba RECTO --es donde se agarra-- y solo
        # la parte de abajo baja a punta. Con esa asimetría se reconoce al
        # instante, y encima gana un arriba y un abajo, que un hexágono no tiene.
        d.polygon([(cx-s*.66, cy-s*.72), (cx+s*.66, cy-s*.72),
                   (cx+s*.66, cy+s*.06), (cx, cy+s*.82), (cx-s*.66, cy+s*.06)],
                  outline=255, width=g)

    elif nombre == "tarjeta":
        d.rounded_rectangle([cx-s*.80, cy-s*.54, cx+s*.80, cy+s*.54], radius=s*.12, outline=255, width=g)
        d.ellipse([cx-s*.58, cy-s*.30, cx-s*.14, cy+s*.14], outline=255, width=max(2, g-1))
        for k in range(3):
            y = cy-s*.24 + k*s*.24
            d.line([cx+s*.06, y, cx+s*.58, y], fill=255, width=max(2, g-2))

    # ── los quince del 30-ago ────────────────────────────────────────────
    # Se dibujaron porque doce símbolos estaban repartidos entre veintisiete
    # canales: el bocadillo salía en cuatro y la nota en tres. Distinguirlos
    # solo por el color no es diseñar cada uno, es pintar el mismo dos veces.

    elif nombre == "puerta":                      # bienvenidas
        # Era un rectángulo con una raya y un punto: podía ser una puerta, una
        # nevera o un armario. Y este canal es el de BIENVENIDAS, así que la
        # puerta tiene que estar ABIERTA -- una puerta cerrada dice lo contrario
        # de lo que dice el canal.
        #
        # Se abre con perspectiva: el marco es un rectángulo y la hoja un
        # trapecio que se estrecha hacia dentro. Ese estrechamiento es todo el
        # truco; con la hoja rectangular vuelve a ser un armario.
        d.rectangle([cx-s*.74, cy-s*.82, cx+s*.30, cy+s*.82], outline=255, width=g)
        d.polygon([(cx-s*.06, cy-s*.82), (cx+s*.74, cy-s*.56),
                   (cx+s*.74, cy+s*.56), (cx-s*.06, cy+s*.82)],
                  outline=255, width=g)
        d.ellipse([cx+s*.44, cy-s*.08, cx+s*.60, cy+s*.08], fill=255)
        # el suelo, que asienta la escena y remata la perspectiva
        d.line([cx-s*.74, cy+s*.82, cx+s*.74, cy+s*.82], fill=255, width=max(2, g-1))

    elif nombre == "mano":                        # dudas — la mano levantada
        # Eran tres barras sueltas sobre un arco, y se leía como tres palos
        # encima de una sonrisa. Faltaba lo que hace que una mano sea una mano:
        # la PALMA. Los dedos tienen que nacer de algo, y ese algo tiene que
        # tener anchura.
        #
        # Van cuatro dedos de alturas distintas --iguales parecen un peine--
        # saliendo de una palma con cuerpo, y un pulgar a un lado, que es el
        # detalle que descarta cualquier otra lectura.
        # Segunda pasada. La palma estaba, pero los dedos BAJABAN DENTRO de
        # ella y su contorno cruzaba el de la palma: salía una rejilla de rayas
        # y no una mano. En un dibujo de trazo dos contornos que se cruzan se
        # leen como una tercera forma, la de las celdas que crean.
        #
        # Así que los dedos se quedan FUERA, con un hueco de por medio. El ojo
        # une lo que está alineado y separado por poco -- no hace falta que se
        # toquen, y si se tocan es peor.
        d.rounded_rectangle([cx-s*.50, cy+s*.12, cx+s*.50, cy+s*.86],
                            radius=s*.24, outline=255, width=g)
        for x0, alto in [(-.42, .60), (-.16, .82), (.10, .72), (.34, .50)]:
            d.rounded_rectangle([cx+s*x0, cy-s*alto, cx+s*(x0+.17), cy+s*.02],
                                radius=s*.085, outline=255, width=g)
        # El pulgar SÍ toca la palma, al revés que los dedos.
        #
        # Separado quedaba como una pastilla flotando al lado, sin relación con
        # nada. Y no es incoherente con lo de los dedos: aquéllos están
        # alineados y repetidos, así que el ojo los agrupa solo aunque haya
        # hueco; el pulgar está solo y en otro ángulo, y a una pieza única no la
        # agrupa nadie -- tiene que tocar para pertenecer.
        d.rounded_rectangle([cx-s*.94, cy+s*.24, cx-s*.42, cy+s*.46],
                            radius=s*.11, outline=255, width=g)

    elif nombre == "bombilla":                    # sugerencias
        d.arc([cx-s*.52, cy-s*.80, cx+s*.52, cy+s*.24], start=180, end=360, fill=255, width=g)
        d.line([cx-s*.52, cy-s*.28, cx-s*.24, cy+s*.34], fill=255, width=g)
        d.line([cx+s*.52, cy-s*.28, cx+s*.24, cy+s*.34], fill=255, width=g)
        d.line([cx-s*.24, cy+s*.34, cx+s*.24, cy+s*.34], fill=255, width=g)
        d.line([cx-s*.18, cy+s*.58, cx+s*.18, cy+s*.58], fill=255, width=g)
        d.line([cx-s*.10, cy+s*.80, cx+s*.10, cy+s*.80], fill=255, width=g)

    elif nombre == "diapason":                    # demos-canto
        # Se leía como una U a secas: las púas eran cortas, el mango también, y
        # los tres trozos medían casi lo mismo, así que nada decía cuál era la
        # pieza principal.
        #
        # Un diapasón es sobre todo DOS PÚAS LARGAS. Se alargan, se separan más,
        # y el mango se estrecha y baja hasta una base -- el canto que se apoya
        # para que suene. Con esa jerarquía --largo arriba, corto abajo-- ya no
        # se puede confundir con una herradura.
        d.line([cx-s*.42, cy-s*.86, cx-s*.42, cy+s*.06], fill=255, width=g)
        d.line([cx+s*.42, cy-s*.86, cx+s*.42, cy+s*.06], fill=255, width=g)
        # Las bolitas de las puntas, fuera. Se pusieron para marcar dónde se
        # golpea, y lo que hicieron fue convertirlo en un fonendoscopio: dos
        # bolas al final de dos tubos que bajan a una pieza central es
        # exactamente ese dibujo. Un diapasón acaba en punta lisa.
        d.arc([cx-s*.42, cy-s*.24, cx+s*.42, cy+s*.40], start=0, end=180, fill=255, width=g)
        d.line([cx, cy+s*.40, cx, cy+s*.78], fill=255, width=g)
        d.rounded_rectangle([cx-s*.22, cy+s*.78, cx+s*.22, cy+s*.94],
                            radius=s*.07, fill=255)

    elif nombre == "vinilo":                      # musica-nueva
        d.ellipse([cx-s*.82, cy-s*.82, cx+s*.82, cy+s*.82], outline=255, width=g)
        d.ellipse([cx-s*.46, cy-s*.46, cx+s*.46, cy+s*.46], outline=255, width=max(2, g-1))
        d.ellipse([cx-s*.10, cy-s*.10, cx+s*.10, cy+s*.10], outline=255, width=max(2, g-1))

    elif nombre == "engranaje":                   # staff
        # Salía un sol, no un engranaje. Y por dos motivos a la vez: los dientes
        # eran RAYAS FINAS del mismo grosor que el aro, y arrancaban SEPARADAS
        # de él --de .52 cuando el aro está en .46--. Una raya fina que sale de
        # un círculo y no lo toca es exactamente como se dibuja un sol.
        #
        # Un diente es macizo, ancho y pegado a la rueda. Se dibuja como un
        # polígono de cuatro puntas que nace DENTRO del aro y sale, para que se
        # vea que es la misma pieza.
        d.ellipse([cx-s*.52, cy-s*.52, cx+s*.52, cy+s*.52], outline=255, width=g)
        d.ellipse([cx-s*.19, cy-s*.19, cx+s*.19, cy+s*.19], outline=255, width=max(2, g-1))
        for k in range(8):
            a = math.radians(k * 45)
            # ancho del diente en radianes: estrecha un poco al salir, como los
            # de verdad, que van en cuña para poder engranar
            for (r0, r1, an) in [(.44, .84, .17)]:
                p1 = (cx + s*r0*math.cos(a-an), cy + s*r0*math.sin(a-an))
                p2 = (cx + s*r1*math.cos(a-an*.70), cy + s*r1*math.sin(a-an*.70))
                p3 = (cx + s*r1*math.cos(a+an*.70), cy + s*r1*math.sin(a+an*.70))
                p4 = (cx + s*r0*math.cos(a+an), cy + s*r0*math.sin(a+an))
                d.polygon([p1, p2, p3, p4], fill=255)
        # el aro se repasa por encima: los dientes macizos le comen el trazo al
        # cruzarlo, y sin esto la rueda queda descosida
        d.ellipse([cx-s*.52, cy-s*.52, cx+s*.52, cy+s*.52], outline=255, width=g)

    elif nombre == "regalo":                      # ofertas-y-gratis
        d.rounded_rectangle([cx-s*.74, cy-s*.20, cx+s*.74, cy+s*.72], radius=s*.08,
                            outline=255, width=g)
        d.rounded_rectangle([cx-s*.82, cy-s*.48, cx+s*.82, cy-s*.14], radius=s*.08,
                            outline=255, width=g)
        d.line([cx, cy-s*.14, cx, cy+s*.72], fill=255, width=g)
        d.arc([cx-s*.44, cy-s*.76, cx+s*.02, cy-s*.38], start=90, end=290, fill=255, width=g)
        d.arc([cx-s*.02, cy-s*.76, cx+s*.44, cy-s*.38], start=250, end=90, fill=255, width=g)

    elif nombre == "campana":                     # avisos-clases
        d.arc([cx-s*.60, cy-s*.72, cx+s*.60, cy+s*.36], start=180, end=360, fill=255, width=g)
        d.line([cx-s*.60, cy-s*.18, cx-s*.60, cy+s*.34], fill=255, width=g)
        d.line([cx+s*.60, cy-s*.18, cx+s*.60, cy+s*.34], fill=255, width=g)
        d.line([cx-s*.78, cy+s*.34, cx+s*.78, cy+s*.34], fill=255, width=g)
        d.arc([cx-s*.18, cy+s*.40, cx+s*.18, cy+s*.76], start=0, end=180, fill=255, width=g)
        d.line([cx, cy-s*.72, cx, cy-s*.86], fill=255, width=g)

    elif nombre == "sobre":                       # postulaciones
        d.rounded_rectangle([cx-s*.82, cy-s*.54, cx+s*.82, cy+s*.54], radius=s*.08,
                            outline=255, width=g)
        d.line([cx-s*.82, cy-s*.54, cx, cy+s*.08], fill=255, width=g)
        d.line([cx+s*.82, cy-s*.54, cx, cy+s*.08], fill=255, width=g)

    elif nombre == "cinta":                       # general-doblaje
        d.rounded_rectangle([cx-s*.84, cy-s*.50, cx+s*.84, cy+s*.50], radius=s*.10,
                            outline=255, width=g)
        d.ellipse([cx-s*.56, cy-s*.28, cx-s*.08, cy+s*.20], outline=255, width=max(2, g-1))
        d.ellipse([cx+s*.08, cy-s*.28, cx+s*.56, cy+s*.20], outline=255, width=max(2, g-1))
        d.line([cx-s*.40, cy+s*.34, cx+s*.40, cy+s*.34], fill=255, width=max(2, g-2))

    elif nombre == "pluma":                       # poemas
        # Era una raya diagonal con un arco encima y salía un gancho. Le
        # faltaba la parte que se reconoce de una pluma: la BARBA, esa hoja
        # ancha con forma de lágrima, y las nervaduras que la cruzan.
        #
        # Se dibuja como dos arcos que se juntan en las dos puntas --arriba a la
        # derecha y abajo a la izquierda-- y el raquis por dentro. Con eso ya es
        # una hoja; con las tres nervaduras cortas, una pluma.
        # Segunda pasada, y la lección es sobre `arc`.
        #
        # La barba se hizo con dos arcos, y `arc` en PIL solo dibuja elipses
        # ALINEADAS CON LOS EJES: no se puede inclinar una. Los dos arcos
        # acababan formando un círculo, y con el raquis cruzándolo en diagonal
        # el resultado era una señal de prohibido.
        #
        # Una forma inclinada hay que dibujarla con un polígono, punto a punto.
        # No es tan bonito de escribir, pero es lo único que permite que la hoja
        # siga la diagonal de la pluma, que es lo que la hace pluma.
        hoja = [(.70, -.80), (.28, -.74), (-.10, -.44), (-.36, -.02),
                (-.46, .30), (-.16, .12), (.16, -.18), (.46, -.50)]
        d.polygon([(cx + s*a, cy + s*b) for a, b in hoja], outline=255, width=g)
        # el raquis: de la punta de arriba a la de abajo, por dentro de la hoja
        d.line([cx+s*.70, cy-s*.80, cx-s*.46, cy+s*.30], fill=255, width=max(2, g-1))
        # las barbas, cortas y perpendiculares al raquis
        for k in range(3):
            f = .22 + k * .24
            ax, ay = .70 - 1.16*f, -.80 + 1.10*f
            d.line([cx+s*ax, cy+s*ay, cx+s*(ax+.26), cy+s*(ay+.06)],
                   fill=255, width=max(2, g-2))
        # y el cañón, hasta la punta que escribe
        d.line([cx-s*.46, cy+s*.30, cx-s*.86, cy+s*.86], fill=255, width=g)

    elif nombre == "risa":                        # memes
        d.ellipse([cx-s*.80, cy-s*.80, cx+s*.80, cy+s*.80], outline=255, width=g)
        d.arc([cx-s*.48, cy-s*.20, cx+s*.48, cy+s*.52], start=0, end=180, fill=255, width=g)
        d.line([cx-s*.48, cy+s*.16, cx+s*.48, cy+s*.16], fill=255, width=g)
        d.line([cx-s*.46, cy-s*.34, cx-s*.16, cy-s*.34], fill=255, width=g)
        d.line([cx+s*.16, cy-s*.34, cx+s*.46, cy-s*.34], fill=255, width=g)

    elif nombre == "dado":                        # comandos-y-sorteos
        d.rounded_rectangle([cx-s*.70, cy-s*.70, cx+s*.70, cy+s*.70], radius=s*.18,
                            outline=255, width=g)
        for px, py in ((-.34, -.34), (.34, -.34), (0, 0), (-.34, .34), (.34, .34)):
            d.ellipse([cx+s*px-s*.10, cy+s*py-s*.10, cx+s*px+s*.10, cy+s*py+s*.10],
                      outline=255, width=max(2, g-1))

    elif nombre == "tele":                        # noticias-series
        d.rounded_rectangle([cx-s*.82, cy-s*.36, cx+s*.82, cy+s*.62], radius=s*.10,
                            outline=255, width=g)
        d.line([cx-s*.40, cy-s*.82, cx-s*.06, cy-s*.40], fill=255, width=g)
        d.line([cx+s*.40, cy-s*.82, cx+s*.06, cy-s*.40], fill=255, width=g)
        d.line([cx+s*.44, cy-s*.14, cx+s*.44, cy+s*.40], fill=255, width=max(2, g-2))

    elif nombre == "chip":                        # config-bots
        d.rounded_rectangle([cx-s*.50, cy-s*.50, cx+s*.50, cy+s*.50], radius=s*.08,
                            outline=255, width=g)
        d.rounded_rectangle([cx-s*.20, cy-s*.20, cx+s*.20, cy+s*.20], radius=s*.05,
                            outline=255, width=max(2, g-1))
        for k in (-.28, 0, .28):
            d.line([cx+s*k, cy-s*.50, cx+s*k, cy-s*.80], fill=255, width=max(2, g-2))
            d.line([cx+s*k, cy+s*.50, cx+s*k, cy+s*.80], fill=255, width=max(2, g-2))
            d.line([cx-s*.50, cy+s*k, cx-s*.80, cy+s*k], fill=255, width=max(2, g-2))
            d.line([cx+s*.50, cy+s*k, cx+s*.80, cy+s*k], fill=255, width=max(2, g-2))

    # ── los dos de las reacciones ────────────────────────────────────────
    # No son símbolos de canal: son el ✅ que abre el servidor y la ➡️ que
    # pasa al siguiente paso, dibujados en el estilo de la casa para que la
    # puerta no sea lo único con los emojis de Discord de serie.

    elif nombre == "visto":                       # el ✅ de reglas
        d.line([cx-s*.62, cy+s*.04, cx-s*.16, cy+s*.50], fill=255, width=int(g*1.4))
        d.line([cx-s*.16, cy+s*.50, cx+s*.66, cy-s*.46], fill=255, width=int(g*1.4))

    elif nombre == "flecha":                      # la ➡️ de autoroles
        d.line([cx-s*.68, cy, cx+s*.44, cy], fill=255, width=int(g*1.3))
        d.line([cx+s*.10, cy-s*.36, cx+s*.62, cy], fill=255, width=int(g*1.3))
        d.line([cx+s*.10, cy+s*.36, cx+s*.62, cy], fill=255, width=int(g*1.3))

    else:
        raise ValueError(f"No conozco el símbolo «{nombre}»")


# ═══════════════════════════════════════════════════════════════════════════
#  EL COLOR DE CADA CANAL, Y EL FONDO DE CADA ZONA
#
#  Antes había **seis colores para cuarenta canales** —el de su categoría— y
#  **un solo fondo**: los rayos radiales del logo, iguales en todas las láminas
#  salvo por el número de rayos. El servidor se leía por zonas, que era la
#  intención, pero dentro de una zona las once láminas eran la misma lámina con
#  otro texto.
#
#  Lo que cambia:
#
#  · **Cada canal tiene su color.** No uno al azar: el tono se mueve dentro de
#    la banda de su categoría. Así `demos` y `castings` siguen siendo los dos
#    del estudio y se reconocen como tales, pero ya no son idénticos. Tirar los
#    colores de zona y dar cuarenta tonos sueltos habría roto lo único que hoy
#    permite orientarse en el servidor sin leer.
#
#  · **Cada zona tiene su fondo, y dice para qué es.** Ocho familias, elegidas
#    por lo que se hace en esa zona: quien entra ve una rejilla que se va al
#    horizonte, el estudio tiene forma de onda, la academia papel de plano, las
#    noticias líneas de televisión mal sintonizada. Y dentro de cada familia,
#    cada canal tiene su propia semilla, así que no hay dos iguales.
#
#  Todo en el mismo lenguaje de siempre: base oscura teñida, trazo de neón fino,
#  y la textura pintada por encima. Cyberpunk de fondo, art déco en la forma,
#  Arcane en el grano.
# ═══════════════════════════════════════════════════════════════════════════

# Qué fondo le toca a cada zona. Se busca por el color de LUZ, que es lo único
# que identifica a una categoría sin ambigüedad: dos zonas comparten acento
# —las noticias y la entrada son las dos cian— pero ninguna comparte luz.
FAMILIAS = {
    (38, 70, 150):  "rejilla",    # EMPIEZA AQUÍ · se entra a un sitio
    (28, 92, 78):   "circuito",   # RECURSOS y TICKETS · herramienta
    (128, 30, 56):  "pulso",      # EN VIVO · algo está pasando ahora
    MORADO:         "onda",       # EL ESTUDIO · aquí se graba
    (96, 66, 24):   "plano",      # LA ACADEMIA · aquí se enseña
    (120, 62, 30):  "bruma",      # COMUNIDAD y OCIO · la plaza
    (30, 60, 120):  "scan",       # NOTICIAS · viene de fuera, por la tele
    (70, 30, 90):   "humo",       # PRIVADOS · solo lo ve el staff
}


# Las doce familias, en orden. Doce y no ocho por una razón de cuentas: la
# zona más grande --el estudio-- tiene doce canales, y para que ninguno repita
# fondo con otro de su misma zona hacen falta al menos tantas familias como
# canales tenga la zona mayor.
FAMILIA_LISTA = ["rejilla", "onda", "plano", "bruma", "scan", "circuito",
                 "pulso", "humo", "panal", "lluvia", "estrellas", "aspas"]


def familia_de(clave):
    """Qué fondo le toca a ESTE canal.

    Antes lo elegía la zona, y era defendible: la entrada tenía rejilla, el
    estudio forma de onda, la academia papel de plano. Pero el estudio tiene
    DOCE canales, así que doce láminas salían con el mismo fondo, y mirándolas
    de una en una --que es como se miran-- eso es «todas iguales».

    Ahora se reparten: a cada zona se le da la baraja empezando por SU familia
    --la que le tocaba antes por temática-- y se va repartiendo una distinta a
    cada canal. Así el primer canal de cada zona conserva el fondo que la
    describe, ningún canal repite con otro de su zona, y entre zonas las
    coincidencias caen en familias distintas porque cada baraja empieza en otro
    sitio.
    """
    i, _n = _sitio_en_su_zona(clave)
    valor = ESTILO.get(clave)
    suya = (FAMILIAS.get(tuple(valor[2]), "bruma") if valor
            else FAMILIA_LISTA[_semilla(clave + "fam").randrange(len(FAMILIA_LISTA))])
    inicio = FAMILIA_LISTA.index(suya) if suya in FAMILIA_LISTA else 0
    return FAMILIA_LISTA[(inicio + i) % len(FAMILIA_LISTA)]


def acento_de_zona(clave):
    """El color de la categoría, sin mover. Se usa sólo para el filete de
    arriba: es lo único que sigue diciendo de qué zona es la lámina ahora que
    el color principal es propio de cada canal."""
    valor = ESTILO.get(clave)
    return valor[1] if valor else MAGENTA


def _semilla(texto):
    """Un azar estable. La misma lámina sale siempre igual, y dos distintas
    salen distintas: si fuera `random` a secas, cada regeneración movería los
    cuarenta fondos y no se podría comparar un cambio con el anterior."""
    return random.Random(sum(ord(c) * (i * 31 + 7) for i, c in enumerate(texto)))


def _rgb_a_hls(c):
    return colorsys.rgb_to_hls(c[0] / 255, c[1] / 255, c[2] / 255)


def _hls_a_rgb(h, l, s):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, max(0, min(1, l)), max(0, min(1, s)))
    return (int(r * 255), int(g * 255), int(b * 255))


def color_de_canal(nombre, acento):
    """El acento de la categoría, movido lo justo para que este canal sea suyo.

    El tono se desplaza dentro de ±26 grados. Ese número no es caprichoso: por
    debajo de unos 15 los canales de una misma zona no se distinguen entre sí, y
    por encima de unos 35 el magenta del estudio empieza a caer en naranja y la
    zona deja de leerse como una zona. Se toca además un poco la claridad, que
    es lo que separa dos tonos vecinos cuando el ojo ya no distingue el giro.
    """
    i, n = _sitio_global(nombre)
    r = _semilla(nombre + "color")

    h, l, sa = _rgb_a_hls(acento)
    # Repartido, no al azar. Con un desplazamiento aleatorio salian colisiones:
    # `castings` daba rgb(242,34,143) y `canto` rgb(242,35,143) -- dos canales
    # de la misma zona con el mismo color, que es justo lo que habia que
    # arreglar. Repartiendo la banda entre los canales que hay, la distancia
    # entre dos vecinos es siempre la maxima posible.
    # ── EL COLOR SALE DE TODA LA RUEDA, NO DE LA BANDA DE SU ZONA ──────────
    #
    # Antes el tono se movía sólo +-20 grados alrededor del color de su
    # categoría. Sobre el papel estaba bien --el servidor se leía por zonas sin
    # tener que leer los nombres-- y en la pantalla no: entre el magenta del
    # estudio y el naranja de la comunidad, DIECINUEVE de las cuarenta y una
    # caían en tonos cálidos parecidos, y de un vistazo eran «todas naranjas».
    #
    # Ahora cada canal ocupa su sitio en el círculo entero: cuarenta canales,
    # nueve grados entre vecinos. Lo que se pierde --saber la zona por el
    # color-- se recupera en el filete de arriba, que sí conserva el de su
    # categoría. El tono manda sobre la lámina; la zona, sobre su borde.
    #
    # Se reparte y no se sortea: cuarenta tonos al azar dejan huecos en una
    # parte de la rueda y amontonamientos en otra, que es exactamente el
    # problema del que veníamos.
    h = (i / max(1, n)) + 0.02
    # Y una pizca de claridad, que es lo que separa dos tonos vecinos cuando el
    # ojo ya no distingue el giro. Esta si va por semilla: no hace falta que sea
    # exacta, solo que no sea igual.
    l = min(.78, max(.52, l + r.uniform(-.045, .055)))
    sa = min(1.0, max(.62, sa + r.uniform(-.05, .035)))
    return _hls_a_rgb(h, l, sa)


_SITIOS = {}
_GLOBAL = {}


def _sitio_global(nombre):
    """Qué puesto ocupa este canal entre TODOS, y cuántos hay.

    Ordenados por nombre para que el reparto sea estable: mientras no se añadan
    ni quiten canales, cada uno conserva su color entre ejecuciones.
    """
    if not _GLOBAL:
        for k, clave in enumerate(sorted(ESTILO)):
            _GLOBAL[clave] = (k, len(ESTILO))
    if nombre in _GLOBAL:
        return _GLOBAL[nombre]
    # Una lámina que no está en la tabla --`claude-lee`, `radio-en-vivo`,
    # `roles`-- caía toda en (0, 1), o sea que las tres salían del mismo color
    # exacto y con el mismo fondo. Un valor por defecto CONSTANTE es una fábrica
    # de repetidos. Se le da un sitio propio derivado de su nombre.
    # Un sitio FRACCIONARIO, no un hueco entero. Sorteando un hueco de los
    # cuarenta, dos nombres desconocidos chocan con una probabilidad nada
    # despreciable -- y chocaron: `claude-lee` y `radio-en-vivo` salieron del
    # mismo color exacto. Con un sitio continuo caen entre dos huecos y no
    # encima de ninguno.
    return (_semilla(nombre + "sitio").uniform(0, len(ESTILO) or 1), len(ESTILO) or 1)


def _sitio_en_su_zona(nombre):
    """Que puesto ocupa este canal entre los de su misma zona, y cuantos son.

    Se calcula una vez y se guarda. No puede calcularse al importar porque
    `ESTILO` se define mas abajo en este mismo archivo, y esto se necesita
    desde `estilo_de`, que se llama siempre despues.
    """
    if not _SITIOS:
        zonas = {}
        for clave, (_s, _a, luz) in ESTILO.items():
            zonas.setdefault(tuple(luz), []).append(clave)
        for claves in zonas.values():
            # Ordenadas por nombre: asi el reparto es estable entre ejecuciones
            # y un canal no cambia de color porque se anada otro a la tabla...
            # salvo los de su propia zona, que es inevitable y correcto.
            claves.sort()
            for i, c in enumerate(claves):
                _SITIOS[c] = (i, len(claves))
    if nombre in _SITIOS:
        return _SITIOS[nombre]
    return (_semilla(nombre + "zona").randrange(12), 12)


def _base(w, h, luz):
    """El suelo de la lámina: un degradado de la luz de la zona al negro.

    Se dibuja en pequeño y se estira. Un degradado pintado línea a línea a 1200
    de ancho son 1200 rectángulos por lámina y cuarenta y una láminas; en 2x600
    son dos píxeles y se ve exactamente igual, porque estirar un degradado es
    justo lo que hace el remuestreo bicúbico.
    """
    tira = Image.new("RGB", (2, 600))
    dt = ImageDraw.Draw(tira)
    for y in range(600):
        k = y / 599
        # Arriba tiñe la luz de la zona; abajo se va al negro de la casa. La
        # curva es exponencial y no recta: con una recta el medio queda lechoso.
        #
        # La fuerza estaba en .55 y era demasiado: el titulo, que va justo
        # arriba, quedaba nadando en color en vez de destacar sobre el negro, y
        # con la luz dorada de la academia el fondo entero se volvia marron.
        # Un fondo tiene que decir de que zona es, no competir con lo que lleva
        # encima -- y lo que lleva encima es para lo que existe la lamina.
        f = (1 - k) ** 2.4 * .30
        dt.line([(0, y), (1, y)], fill=(
            int(NEGRO[0] + (luz[0] - NEGRO[0]) * f),
            int(NEGRO[1] + (luz[1] - NEGRO[1]) * f),
            int(NEGRO[2] + (luz[2] - NEGRO[2]) * f)))
    return tira.resize((w, h), Image.BICUBIC)


def _trazos(familia, w, h, cx, cy, r, v):
    """La máscara del fondo: dónde va el neón. Solo blanco sobre negro; el color
    y el halo los pone `brillar` después, igual que con los símbolos."""
    cap = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(cap)

    if familia == "rejilla":
        # Una cuadrícula que se va al horizonte. Es la imagen de «entrar»: hay
        # un fondo al que se avanza. El punto de fuga va alto y a la derecha,
        # detrás del símbolo, para que las líneas lo señalen sin tocarlo.
        # el punto de fuga se mueve por canal: con uno fijo, seis láminas de
        # entrada tenían la rejilla exactamente igual
        fx, fy = w * (.62 + v["origen"][0] * .30), h * (.18 + v["origen"][1] * .26)
        for k in range(-9, 10):
            d.line([(fx + k * w * .16, h * 1.25), (fx, fy)], fill=42, width=3)
        # Las horizontales se juntan al alejarse: eso es la perspectiva. Se
        # colocan con una curva y un numero FIJO de lineas, no subiendo con un
        # paso que se encoge.
        #
        # Escrito de esa segunda forma era un bucle infinito, y de los que no se
        # ven leyendo: con `paso *= .80` la distancia recorrida converge a cinco
        # veces el paso inicial --0,26 del alto-- asi que arrancando en 1,02 no
        # llega nunca al horizonte, que esta en 0,35. El generador se comio once
        # minutos para sacar UNA lamina antes de que se notara.
        base, tope = h * 1.10, fy + h * .04
        for k in range(1, 23):
            y = base - (base - tope) * (k / 22) ** 2.1
            d.line([(0, y), (w, y)], fill=34, width=3)

    elif familia == "onda":
        # La forma de onda de una voz. Es el estudio: aquí se graba.
        eje = h * .62
        x, k = 0, 0
        while x < w:
            alto = (abs(math.sin(k * .7)) * .55 + abs(math.sin(k * .23)) * .45)
            alto = alto * h * .30 * (.35 + r.random())
            d.rounded_rectangle([x, eje - alto, x + w * .0075, eje + alto],
                                radius=w * .004, fill=40)
            x += w * .0155 / v["densidad"]
            k += 1
        d.line([(0, eje), (w, eje)], fill=26, width=2)

    elif familia == "plano":
        # Papel de plano: cuadrícula fina, y cada cinco una línea más marcada.
        paso = w * .028 / v["densidad"]
        n = 0
        x = 0
        while x < w:
            d.line([(x, 0), (x, h)], fill=44 if n % 5 == 0 else 20, width=2)
            x += paso
            n += 1
        n, y = 0, 0
        while y < h:
            d.line([(0, y), (w, y)], fill=44 if n % 5 == 0 else 20, width=2)
            y += paso
            n += 1
        # dos cotas, como en un plano de verdad
        for _ in range(2):
            yy = r.uniform(h * .2, h * .8)
            x0, x1 = r.uniform(0, w * .3), r.uniform(w * .55, w * .9)
            d.line([(x0, yy), (x1, yy)], fill=70, width=3)
            for xx in (x0, x1):
                d.line([(xx, yy - h * .012), (xx, yy + h * .012)], fill=70, width=3)

    elif familia == "bruma":
        # Manchas grandes y blandas: la plaza, donde hay gente y ruido.
        for _ in range(int(9 * v["densidad"])):
            rr = r.uniform(w * .08, w * .22)
            xx, yy = r.uniform(0, w), r.uniform(0, h)
            d.ellipse([xx - rr, yy - rr, xx + rr, yy + rr], outline=52,
                      width=int(r.uniform(3, 7)))
        cap = cap.filter(ImageFilter.GaussianBlur(w * .006))

    elif familia == "scan":
        # Líneas de televisión mal sintonizada, con dos bandas desplazadas.
        y = 0
        while y < h:
            d.line([(0, y), (w, y)], fill=26, width=2)
            y += max(4, int(7 / v["densidad"]))
        # Las bandas desplazadas, la parte que hace que parezca mal sintonizada.
        # A 64 de brillo cruzaban el texto del cuerpo y se lo comian: quedaban
        # renglones legibles sobre una barra clara y otros no. A 26 se leen como
        # interferencia --que es lo que son-- y el texto sigue mandando.
        for _ in range(3):
            yy = r.uniform(0, h - h * .05)
            alto = r.uniform(h * .012, h * .04)
            dx = r.uniform(w * .02, w * .07) * r.choice((-1, 1))
            d.rectangle([dx, yy, w + dx, yy + alto], fill=26)

    elif familia == "circuito":
        # Pistas de circuito impreso: la zona de las herramientas.
        for _ in range(int(16 * v["densidad"])):
            x, y = r.uniform(0, w), r.uniform(0, h)
            for _ in range(r.randint(2, 4)):
                largo = r.uniform(w * .05, w * .17)
                if r.random() < .5:
                    x2, y2 = x + largo * r.choice((-1, 1)), y
                else:
                    x2, y2 = x, y + largo * r.choice((-1, 1))
                d.line([(x, y), (x2, y2)], fill=46, width=3)
                x, y = x2, y2
            d.ellipse([x - 7, y - 7, x + 7, y + 7], outline=64, width=3)

    elif familia == "pulso":
        # Anillos que salen del símbolo: algo está pasando y se está emitiendo.
        rr = r.uniform(w * .05, w * .09)
        while rr < w * 1.1:
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=34, width=3)
            rr *= 1.26

    elif familia == "panal":
        # Panal: hexágonos. Es la textura de "esto está hecho de piezas".
        r0 = w * .050 * v["densidad"]
        alto = r0 * 1.732
        fila = 0
        y = -alto
        while y < h + alto:
            desfase = 0 if fila % 2 == 0 else r0 * 1.5
            x = -r0
            while x < w + r0 * 2:
                pts = [(x + desfase + r0 * math.cos(math.radians(60 * k)),
                        y + r0 * math.sin(math.radians(60 * k))) for k in range(6)]
                d.polygon(pts, outline=30, width=2)
                x += r0 * 3
            y += alto / 2
            fila += 1

    elif familia == "lluvia":
        # Trazos verticales de largos distintos, cayendo. Cyberpunk de manual, y
        # lo único de las doce que tiene dirección clara.
        x = 0
        while x < w:
            largo = h * (.10 + r.random() * .38)
            arriba = r.uniform(-h * .1, h - largo)
            d.line([(x, arriba), (x, arriba + largo)], fill=34, width=2)
            x += w * .017 / v["densidad"]

    elif familia == "estrellas":
        # Puntos de tamaños distintos y unas cuantas líneas uniéndolos: un cielo
        # con constelaciones. Es lo más cerca que está el servidor del altiplano.
        puntos = []
        for _ in range(int(90 * v["densidad"])):
            xx, yy = r.uniform(0, w), r.uniform(0, h)
            rr = r.uniform(1, 3.4)
            d.ellipse([xx - rr, yy - rr, xx + rr, yy + rr], fill=int(30 + rr * 22))
            puntos.append((xx, yy))
        for _ in range(6):
            a1 = r.choice(puntos)
            cerca = sorted(puntos, key=lambda q: (q[0]-a1[0])**2 + (q[1]-a1[1])**2)[1:4]
            for a2 in cerca:
                d.line([a1, a2], fill=18, width=2)

    elif familia == "aspas":
        # Bandas diagonales anchas. El ángulo sale de la semilla, así que dos
        # canales con esta familia no se ven nunca igual.
        ang = math.radians(v["giro"])
        paso = w * .14 / v["densidad"]
        largo = (w + h) * 1.5
        k = -14
        while k < 26:
            x0 = k * paso
            dx, dy = math.cos(ang) * largo, math.sin(ang) * largo
            d.line([(x0 - dx, -dy), (x0 + dx, dy)], fill=26, width=int(w * .012))
            k += 2

    elif familia == "humo":
        # Bandas diagonales muy tenues. Es la zona privada: tiene que verse
        # apagada a propósito, para que se note que no es de todos.
        for _ in range(7):
            yy = r.uniform(-h * .2, h)
            d.polygon([(0, yy), (w, yy - h * .18), (w, yy - h * .10), (0, yy + h * .08)],
                      fill=18)
        cap = cap.filter(ImageFilter.GaussianBlur(w * .012))

    return cap


def fondo(familia, w, h, cx, cy, acento, luz, semilla):
    """El fondo entero de una lámina: base teñida + trazos de neón + halo."""
    img = _base(w, h, luz)
    r = _semilla(semilla)
    # Las palancas que hacen que dos láminas de la MISMA familia no se vean
    # calcadas: cuánta densidad, con qué ángulo, y desde dónde. Salen de la
    # semilla del canal, así que son suyas y siempre las mismas.
    v = {"densidad": .72 + r.random() * .70,
         "giro": r.uniform(-58, 58),
         "origen": (r.uniform(.15, .85), r.uniform(.15, .85))}
    cap = _trazos(familia, w, h, cx, cy, r, v)
    # Flojo a propósito: es fondo. Con la fuerza de los símbolos competiría con
    # el texto, y el texto es para lo que existe la lámina.
    img = ImageChops.add(img, brillar(cap, acento, radios=(2, 9), fuerzas=(.30, .16)))

    # El halo detrás del símbolo se queda: es lo que lo despega del fondo.
    velo = Image.new("L", (w, h), 0)
    ImageDraw.Draw(velo).ellipse(
        [cx - w * .20, cy - h * .17, cx + w * .20, cy + h * .17], fill=118)
    img.paste(Image.new("RGB", (w, h), luz), (0, 0),
              velo.filter(ImageFilter.GaussianBlur(int(h / 5))))
    return img


def _envolver(d, texto, fuente, ancho):
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if d.textlength(prueba, font=fuente) <= ancho:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def _lineas_de(contenido):
    """Normaliza el contenido a una lista de (cabecera_o_None, [líneas]).

    Se acepta tanto una lista suelta de frases como la estructura de secciones
    de `discord_contenido_canales` —(título, [líneas])—, porque las láminas de
    canal traen lo primero y los paneles de roles lo segundo, y no tiene sentido
    obligar a quien llama a convertir.
    """
    bloques = []
    for item in contenido:
        if isinstance(item, (tuple, list)) and len(item) == 2 \
                and isinstance(item[1], (list, tuple)):
            bloques.append((str(item[0]), [str(x) for x in item[1]]))
        else:
            if bloques and bloques[-1][0] is None:
                bloques[-1][1].append(str(item))
            else:
                bloques.append((None, [str(item)]))
    return bloques


def _referencias(texto):
    """Parte una línea en trozos, marcando los nombres de canal citados.

    Devuelve una lista de `(trozo, canal_o_None)`. Lo que venga marcado con
    `**dobles asteriscos**` y coincida con un canal conocido se dibuja como
    **pastilla**: el símbolo de ese canal en su color, y el nombre al lado. Así
    «Las **reglas** — son ocho» deja de ser texto en negrita y pasa a enseñar el
    mismo escudo que lleva el botón de abajo y la lámina de destino, que es lo
    que hace que se entienda sin explicarlo.

    Lo que va en negrita y **no** es un canal se devuelve como texto normal: no
    se inventa una pastilla para cualquier palabra resaltada.
    """
    fuera, resto = [], texto
    while "**" in resto:
        antes, _, cola = resto.partition("**")
        dentro, _, resto = cola.partition("**")
        if antes:
            fuera.append((antes, None))
        clave = _canal_citado(dentro)
        fuera.append((dentro, clave))
    if resto:
        fuera.append((resto, None))
    return fuera or [(texto, None)]


def _canal_citado(texto):
    """El canal al que se refiere un texto resaltado, o None.

    Se busca por el nombre corto y por unos pocos alias que la gente escribe de
    otra forma («la guía» por `guia`, «canales y roles» por `autoroles`). Sin los
    alias, media docena de referencias reales se quedaban sin pastilla.
    """
    t = texto.lower().strip(" .,:;—-«»¿?¡!")
    t = t.replace("á", "a").replace("é", "e").replace("í", "i") \
         .replace("ó", "o").replace("ú", "u")
    for prefijo in ("la ", "el ", "los ", "las ", "tu ", "en ", "tu hilo en "):
        if t.startswith(prefijo):
            t = t[len(prefijo):]
    t = t.strip()
    if t in ALIAS:
        return ALIAS[t]
    return t if t in ESTILO else None


def lamina(simb, titulo, sub, contenido, personaje, oficio, frase,
           acento=MAGENTA, luz=MORADO, archivo="lamina.png", w=1200, h=None,
           variante=None):
    """Una lámina completa. Devuelve la ruta del PNG.

    Es la composición de la primera versión —título a la izquierda, el símbolo
    grande a la derecha, la tarjeta de personaje abajo— con cuatro arreglos, y
    solo cuatro. La versión intermedia, la de dos columnas con el símbolo subido
    a la cabecera, se descartó: partía la lectura en dos y el símbolo dejaba de
    ser lo primero que se ve, que es justo lo que hace que un canal se reconozca.

    Lo que cambia respecto de aquella primera:

    · **No se recorta el texto.** Antes cabían tres líneas y las de más de 68
      caracteres desaparecían sin dejar rastro. Ahora entran todas: se envuelven
      si son largas y la lámina crece solo lo que necesite.
    · **Fuera las viñetas de triángulo**, que eran de diapositiva. En su sitio va
      un guion corto en neón del color del canal: marca la línea sin gritar.
    · **Las referencias a otros canales salen con su símbolo.** Lo que la ficha
      escribe en `**negrita**` y coincide con un canal se dibuja como pastilla —
      el mismo icono que llevará el botón de abajo y la lámina de destino.
    · **Cada lámina tiene su composición.** El foco de los rayos, el número de
      rayos y la altura del símbolo salen del nombre del archivo, así que dos
      canales seguidos no se ven calcados y cada uno sale siempre igual.

    `h` sigue aceptándose para las llamadas viejas, pero manda el contenido.
    """
    if variante is None:
        variante = sum(ord(c) for c in os.path.basename(archivo)) % 3

    B = 600                    # base tipográfica: el alto ya no la decide
    m = w * .06
    ancho_txt = w * .64        # hasta donde llega el texto sin pisar el símbolo

    ft = ImageFont.truetype(FUENTE_TIT, int(B*.145))
    fs = ImageFont.truetype(FUENTE, int(B*.053))
    fl = ImageFont.truetype(FUENTE, int(B*.049))
    fn = ImageFont.truetype(FUENTE, int(B*.046))
    fo = ImageFont.truetype(FUENTE, int(B*.036))
    ff = ImageFont.truetype(FUENTE, int(B*.047))

    CAB = int(B*.40)
    SALTO = int(B*.072)
    TARJETA = int(B*.225)

    # ── medir el texto antes de decidir el alto ──────────────────────────
    medidor = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    # Cada fila es (texto, clase). La clase decide cómo se pinta:
    #   "cab"  cabecera de sección, en oro
    #   "uno"  primera línea de una frase: lleva el guion en neón
    #   "sig"  continuación de una frase envuelta: sin guion, sangrada
    filas = []
    for cabecera, lineas in _lineas_de(contenido):
        # Las cabeceras de sección se pintaban antes y luego se dejaron de
        # pintar; volver a tirarlas es volver a recortar texto. Van, pero como
        # un renglón corto en oro y no como un bloque numerado, que era lo que
        # daba aire de diapositiva.
        if cabecera and cabecera.strip():
            filas.append((cabecera.strip(), "cab"))
        for linea in lineas:
            limpia = linea.strip()
            if not limpia:
                continue
            trozos = _envolver_rico(medidor, limpia, fl, ancho_txt - w*.022)
            filas.extend((t, "uno" if k == 0 else "sig")
                         for k, t in enumerate(trozos))

    alto_cuerpo = sum(int(SALTO * .82) if c == "cab" else SALTO
                      for _t, c in filas)
    h = max(int(B), int(CAB + B*.045 + alto_cuerpo + B*.045 + TARJETA + B*.055))

    # ── el fondo del logo ────────────────────────────────────────────────
    # el símbolo se centra en el cuerpo, no en la lámina: cuando hay mucho texto
    # y la lámina crece, un símbolo centrado por alto se iba al fondo, lejos del
    # título, y dejaba la cabecera desnuda
    cx = w * (.845, .850, .840)[variante]
    cy = CAB + alto_cuerpo * .46
    # acotado por arriba: sin tope, en una lámina con mucho texto el
    # símbolo crecía hasta meterse dentro de las frases
    s = max(B*.185, min(B*.255, alto_cuerpo*.42))

    # ── el fondo de la zona ──────────────────────────────────────────────
    #
    # Aquí iban los rayos radiales del logo, los mismos en las cuarenta y una
    # láminas salvo por cuántos eran. Dos problemas: se repetían, y no decían
    # nada del canal -- el mismo abanico detrás de las reglas que detrás de un
    # canal de memes.
    #
    # Ahora el fondo lo elige la ZONA y lo varía el canal: la entrada tiene una
    # rejilla que se va al horizonte, el estudio una forma de onda, la academia
    # papel de plano. Ver `FAMILIAS` arriba.
    clave = os.path.splitext(os.path.basename(archivo))[0]
    img = fondo(familia_de(clave), w, h, cx, cy,
                acento, luz, os.path.basename(archivo))
    d = ImageDraw.Draw(img)

    capa = Image.new("L", (w, h), 0)
    simbolo(simb, ImageDraw.Draw(capa), cx, cy, s, max(5, int(s/13)))
    img = ImageChops.add(img, brillar(capa, acento))

    d = ImageDraw.Draw(img)

    # ── la cabecera ──────────────────────────────────────────────────────
    cap2 = Image.new("L", (w, h), 0)
    ImageDraw.Draw(cap2).text((m, B*.10), titulo.upper(), font=ft, fill=255)
    img = ImageChops.add(img, brillar(cap2, acento, radios=(4, 15), fuerzas=(.5, .26)))
    d = ImageDraw.Draw(img)
    d.text((m, B*.10), titulo.upper(), font=ft, fill=CREMA)
    d.rounded_rectangle([m, B*.285, m + w*.085, B*.285 + B*.012],
                        radius=B*.006, fill=ORO)
    for k, trozo in enumerate(_envolver(d, sub, fs, ancho_txt)[:2]):
        d.text((m, B*.325 + k*B*.060), trozo, font=fs, fill=GRIS)

    # ── el cuerpo ────────────────────────────────────────────────────────
    y = CAB + B*.045
    fcab = ImageFont.truetype(FUENTE_TIT, int(B*.040))
    for fila, clase in filas:
        if clase == "cab":
            d.text((m, y + B*.012), fila.upper(), font=fcab, fill=ORO)
            y += int(SALTO * .82)
            continue
        # **Sin marca a la izquierda de la línea.** Primero fueron triángulos y
        # luego un guion en neón; las dos versiones se descartaron por lo mismo,
        # que parecen viñetas de diapositiva. La estructura la lleva entera la
        # cabecera dorada de cada sección, y el texto empieza en el margen.
        sangria = w*.022 if clase == "sig" else 0
        _pintar_rico(d, m + sangria, y, fila, fl, CREMA, img)
        d = ImageDraw.Draw(img)
        y += SALTO

    # ── la tarjeta del personaje ─────────────────────────────────────────
    ty = h - TARJETA - B*.055
    d.rounded_rectangle([m, ty, w*.72, ty + TARJETA], radius=B*.030, fill=(21, 15, 32))
    d.rounded_rectangle([m, ty, w*.72, ty + TARJETA], radius=B*.030,
                        outline=(62, 44, 84), width=2)
    d.rounded_rectangle([m, ty + B*.030, m + w*.0035, ty + TARJETA - B*.030],
                        radius=3, fill=acento)

    ax, ay, ar = m + w*.042, ty + TARJETA*.42, B*.052
    d.ellipse([ax-ar, ay-ar, ax+ar, ay+ar], fill=acento)
    ini = ImageFont.truetype(FUENTE_TIT, int(B*.058))
    letra = personaje.split()[-1][0]
    bb = d.textbbox((0, 0), letra, font=ini)
    d.text((ax-(bb[2]-bb[0])/2-bb[0], ay-(bb[3]-bb[1])/2-bb[1]), letra,
           font=ini, fill=NEGRO)

    tx = m + w*.078
    d.text((tx, ty + B*.028), personaje, font=fn, fill=acento)
    an = d.textlength(personaje, font=fn)
    d.ellipse([tx+an+w*.010, ty+B*.045, tx+an+w*.054/4, ty+B*.054], fill=(88, 216, 120))
    d.text((tx+an+w*.026, ty+B*.036), oficio, font=fo, fill=(122, 112, 136))
    for k, ln in enumerate(_envolver(d, frase, ff, w*.72 - tx - w*.02)[:2]):
        d.text((tx, ty + B*.095 + k*B*.058), ln, font=ff, fill=(212, 205, 220))

    # ── el filete de arriba, ya sin dientes ──────────────────────────────
    #
    # Colgaban 26 triángulos de oro de esta banda: era la firma del logo, y en
    # el logo funciona. Repetida a lo ancho de una lámina de 1200 px y encima
    # de todo, no: queda de banderillas de verbena y es lo primero que se ve
    # de cada canal, antes incluso que su título.
    #
    # Es exactamente el mismo problema que ya se resolvió en la cabecera de la
    # web, y con la misma salida: se quitan los dientes y la banda se queda en
    # una línea fina, que basta para rematar el borde sin gritar.
    #
    # El oro NO desaparece del diseño: sigue en el subrayado del título y en el
    # aro de la tarjeta de personaje, que es donde remata sin competir.
    # El filete lleva el color de la ZONA, no el del canal.
    #
    # Es lo único que queda diciendo a qué parte del servidor pertenece esta
    # lámina, ahora que el color principal es propio de cada canal. Una línea de
    # seis milésimas del alto no compite con nada, y puestas dos láminas juntas
    # se ve al momento si son de la misma casa.
    d.rectangle([0, 0, w, B*.006], fill=acento_de_zona(clave))

    img = _textura(img, w, h)
    ruta = os.path.join(SALIDA, archivo)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    img.save(ruta, "PNG")
    return ruta


def _alto_de(columna, salto, alto_cab, B):
    alto = 0
    for clase, _, _ in columna:
        alto += alto_cab if clase == "cab" else salto
    return alto + int(B*.018)


def _envolver_rico(d, texto, fuente, ancho):
    """Envuelve conservando las marcas `**` de las referencias a canales.

    No se puede envolver el texto ya limpio y pintar las pastillas después: al
    quitar los asteriscos cambian las anchuras y las pastillas caían medio
    renglón desplazadas. Así que se envuelve **con** las marcas puestas,
    midiendo cada palabra por lo que va a ocupar de verdad.
    """
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if _ancho_rico_medida(d, prueba, fuente) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas or [""]


def _ancho_rico_medida(d, texto, fuente):
    """Lo que ocupa una línea contando las pastillas, que llevan símbolo."""
    ancho = 0
    for trozo, canal in _referencias(texto):
        ancho += d.textlength(trozo, font=fuente)
        if canal:
            ancho += fuente.size * 1.35      # el símbolo y su aire
    return ancho


def _pintar_rico(d, x, y, texto, fuente, color, img):
    """Pinta una línea, dibujando una pastilla donde se cita a un canal.

    El símbolo de la pastilla se dibuja en un azulejo pequeño y se pega con
    máscara. Se probó antes a rellenarlo con el neón completo y no compensa: a
    catorce píxeles el halo solo emborrona: el trazo limpio del color del canal
    se reconoce mucho mejor.
    """
    for trozo, canal in _referencias(texto):
        if canal:
            simb_c, acento_c, _luz = ESTILO[canal]
            lado = int(fuente.size * 1.55)
            tile = Image.new("L", (lado, lado), 0)
            simbolo(simb_c, ImageDraw.Draw(tile), lado/2, lado/2, lado*.42,
                    max(3, int(lado/7)))
            img.paste(Image.new("RGB", (lado, lado), acento_c),
                      (int(x), int(y - fuente.size*.22)), tile)
            x += lado + fuente.size * .10
            d.text((x, y), trozo, font=fuente, fill=acento_c)
            x += d.textlength(trozo, font=fuente)
        else:
            d.text((x, y), trozo, font=fuente, fill=color)
            x += d.textlength(trozo, font=fuente)
# ── qué símbolo y qué color le toca a cada canal ─────────────────────────
# El color lo hereda de la categoría: así el servidor se lee por zonas sin
# necesidad de leer el nombre. El símbolo es propio de cada canal.
ESTILO = {
    # EMPIEZA AQUÍ · cian, la zona de entrada
    "reglas":              ("escudo",      CIAN,    (38, 70, 150)),
    "guia":                ("mapa",        CIAN,    (38, 70, 150)),
    "bienvenidas":        ("puerta",   CIAN,    (38, 70, 150)),
    "autoroles":           ("etiqueta",    CIAN,    (38, 70, 150)),
    "anuncios":            ("megafono",    CIAN,    (38, 70, 150)),
    "presentaciones":      ("tarjeta",     CIAN,    (38, 70, 150)),

    # TICKETS · verde, lo que te saca de un apuro
    "soporte":             ("salvavidas",  VERDE,   (28, 92, 78)),

    # EN VIVO · rojo, lo que está pasando ahora
    "en-directo":          ("onda",        ROJO,    (128, 30, 56)),
    "eventos":             ("calendario",  ROJO,    (128, 30, 56)),

    # EL ESTUDIO · magenta, el oficio
    "general-doblaje":    ("cinta",       MAGENTA, MORADO),
    "demos":               ("micro",       MAGENTA, MORADO),
    "castings":            ("claqueta",    MAGENTA, MORADO),
    "canto":               ("nota",        MAGENTA, MORADO),
    "demos-canto":        ("diapason",        MAGENTA, MORADO),
    "proyectos":           ("carpeta",     MAGENTA, MORADO),
    "reto-de-la-semana":   ("diana",       MAGENTA, MORADO),
    "textos":              ("libro",       MAGENTA, MORADO),
    "edicion":             ("faders",      MAGENTA, MORADO),

    # LA ACADEMIA · oro, donde se enseña
    "avisos-clases":      ("campana",    ORO,     (96, 66, 24)),
    "material-de-clase":   ("birrete",     ORO,     (96, 66, 24)),
    "dudas":              ("mano",   ORO,     (96, 66, 24)),

    # COMUNIDAD · naranja, la plaza
    "general":             ("bocadillo",   NARANJA, (120, 62, 30)),
    "memes":              ("risa",    NARANJA, (120, 62, 30)),
    "arte":                ("arte",        NARANJA, (120, 62, 30)),
    "fotos":               ("camara",      NARANJA, (120, 62, 30)),
    "poemas":             ("pluma",       NARANJA, (120, 62, 30)),
    "destacados":          ("estrella",    NARANJA, (120, 62, 30)),

    # OCIO · naranja también, es la misma zona de ambiente
    "comandos-y-sorteos": ("dado",       NARANJA, (120, 62, 30)),

    # NOTICIAS · cian frío, viene de fuera
    "noticias-anime":      ("periodico",   CIAN,    (30, 60, 120)),
    "noticias-series":    ("tele",   CIAN,    (30, 60, 120)),
    "noticias-gaming":     ("mando",       CIAN,    (30, 60, 120)),
    "musica-nueva":       ("vinilo",        CIAN,    (30, 60, 120)),
    "ofertas-y-gratis":   ("regalo",    CIAN,    (30, 60, 120)),

    # RECURSOS · verde, lo que te sirve
    "recursos":            ("llave",       VERDE,   (28, 92, 78)),
    "hardware":            ("auriculares", VERDE,   (28, 92, 78)),
    "sugerencias":        ("bombilla",   VERDE,   (28, 92, 78)),
    "redes-y-novedades":   ("enlace",      VERDE,   (28, 92, 78)),

    # PRIVADOS · magenta apagado, solo lo ve el staff
    "staff":              ("engranaje",      MAGENTA, (70, 30, 90)),
    "postulaciones":      ("sobre",     MAGENTA, (70, 30, 90)),
    "config-bots":        ("chip",       MAGENTA, (70, 30, 90)),
}


# Cada bloque de la guía con su símbolo. El color y el fondo salen igual que
# los demás --de su nombre-- así que trece bloques dan trece láminas distintas.
GUIA = {
    "guia":    ("mapa",       CIAN,    (38, 70, 150)),   # de un vistazo
    "guia_1":  ("puerta",     CIAN,    (38, 70, 150)),   # cómo se entra
    "guia_2a": ("libro",      CIAN,    (38, 70, 150)),   # lo que hay que leer
    "guia_2b": ("micro",      MAGENTA, MORADO),          # dónde se trabaja
    "guia_2c": ("onda",       ROJO,    (128, 30, 56)),   # lo que pasa en vivo
    "guia_3":  ("etiqueta",   NARANJA, (120, 62, 30)),   # los roles que te pones
    "guia_4":  ("diana",      ORO,     (96, 66, 24)),    # los roles que se ganan
    "guia_4b": ("llave",      ORO,     (96, 66, 24)),    # de dónde sale un rol
    "guia_4c": ("estrella",   ORO,     (96, 66, 24)),    # los talentos
    "guia_5":  ("escudo",     MAGENTA, (70, 30, 90)),    # el staff
    "guia_6":  ("calendario", ROJO,    (128, 30, 56)),   # reuniones y eventos
    "guia_7":  ("salvavidas", VERDE,   (28, 92, 78)),    # cómo pedir algo
    "zonas":   ("carpeta",    NARANJA, (120, 62, 30)),   # tus zonas
}


def estilo_de(nombre_canal):
    """Encuentra el estilo por el trozo legible del nombre del canal.

    Los canales del servidor llevan adornos («ıı・🎧・demos»), así que se busca
    por coincidencia del final, que es la parte que importa.
    """
    limpio = nombre_canal.split("・")[-1].strip().lower()

    def suyo(clave, valor):
        """El estilo de la categoria, con el acento movido a ESTE canal.

        La luz NO se toca: es la que identifica la zona, y de ella cuelgan tanto
        el degradado del fondo como que familia de fondo le toca ().
        Si se moviera tambien, cada canal seria su propia zona y se perderia lo
        unico que hoy permite orientarse en el servidor sin leer.
        """
        simb, acento, luz = valor
        return (simb, color_de_canal(clave, acento), luz)

    # ── LOS HILOS DE LA GUÍA, PRIMERO Y POR IGUALDAD EXACTA ────────────────
    #
    # La guía no es un canal: es un foro con trece hilos, y cada uno se dibuja
    # con su propio PNG (`guia_1.png`, `guia_4b.png`, `zonas.png`...). Al buscar
    # abajo por coincidencia, «guia» está dentro de «guia_1», de «guia_2a» y de
    # los diez restantes, así que **los doce salían con el mismo símbolo de
    # mapa**. Doce láminas seguidas con el mismo icono, que es justo lo que se
    # veía en el foro.
    #
    # Se consultan antes y por igualdad exacta. Y viven en su propia tabla, no
    # metidos en `ESTILO`: esa tabla es la que reparte los colores entre los
    # cuarenta canales, y meterle trece entradas más movería el color de todas
    # las láminas del servidor para arreglar el icono de trece.
    if limpio in GUIA:
        return suyo(limpio, GUIA[limpio])

    if limpio in ESTILO:
        return suyo(limpio, ESTILO[limpio])
    for clave, valor in ESTILO.items():
        if clave in limpio:
            return suyo(clave, valor)
    # El último recurso TAMBIÉN pasa por `suyo`.
    #
    # Devolvía el magenta crudo, sin tocar, así que todas las láminas que no
    # encajaban en la tabla salían exactamente del mismo color -- que es
    # justamente lo que hay que evitar. `claude-lee` y `radio-en-vivo` daban el
    # mismo rgb hasta el último dígito.
    return suyo(limpio, ("bocadillo", MAGENTA, MORADO))


# Cómo se escriben en las fichas los canales que no se llaman igual que su
# nombre corto. Sin esto, «la guía» o «Canales y roles» quedaban como texto en
# negrita en vez de enseñar su símbolo.
ALIAS = {
    "guia": "guia",
    "canales y roles": "autoroles",
    "tus roles": "autoroles",
    "avisos": "autoroles",
    "hilo en demos": "demos",
    "demos": "demos",
    "soporte": "soporte",
    "tickets": "soporte",
    "si te atascas": "soporte",
    "presentate": "presentaciones",
    "preséntate": "presentaciones",
    "reto de la semana": "reto-de-la-semana",
    "material de clase": "material-de-clase",
    "ofertas": "ofertas-y-gratis",
    "comandos": "comandos-y-sorteos",
    "redes": "redes-y-novedades",
}
