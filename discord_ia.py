#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_ia.py — lo que escribe la IA, en un solo sitio.

Usa **Gemini con la capa gratis** de Google AI Studio: la clave se saca en
`aistudio.google.com/apikey`, es gratis y no pide tarjeta. Se lee de la variable
`GEMINI_API_KEY`.

Tres reglas que valen para todo lo de aquí, y no son adorno:

1. **Es opcional siempre.** Sin clave, cada función devuelve el texto original o
   nada, y el script sigue como si este archivo no existiera. Una noticia en
   inglés es mejor que ninguna noticia.
2. **Se marca lo que escribe la IA.** Un resumen automático lleva su aviso al
   pie. Mezclar una frase inventada con datos reales sin decirlo es la forma más
   rápida de que nadie se fíe del canal.
3. **No opina de lo que no sabe.** Los prompts piden resumir o traducir **lo que
   se le da**, y prohíben añadir datos. Si la IA no tiene material, calla.

    python discord_ia.py            # prueba que la clave funciona
"""
import json
import os
import sys
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# **El modelo NO se escribe a mano.** La primera versión fijaba `gemini-2.0-flash`
# y no traducía nada: ese modelo **se apagó el 1 de junio de 2026** y la API
# devolvía 404 en silencio. Google jubila modelos cada pocos meses, así que
# escribir uno concreto es garantizarse que esto se rompa solo con el tiempo.
#
# Ahora se le **pregunta a Google** qué hay vivo y se coge un Flash — el rápido y
# el que más cuota gratis tiene. Si algún día no hay ninguno, vale cualquiera que
# sepa generar texto.
_ELEGIDO = None


def modelos():
    """Los modelos a probar, en orden. Se pregunta una vez por ejecución.

    Devuelve **varios** a propósito: el alias `-latest` apunta al modelo de moda
    y por eso es justo el que se satura. Cuando devuelve 503 —«high demand»— hay
    que tener a dónde caer, o la IA se apaga cada vez que hay pico.
    """
    global _ELEGIDO
    if _ELEGIDO:
        return _ELEGIDO
    try:
        req = urllib.request.Request(f"{BASE}?key={clave()}&pageSize=100")
        with urllib.request.urlopen(req, timeout=20) as r:
            todos = json.loads(r.read().decode("utf-8")).get("models", [])
    except Exception as e:                       # noqa: BLE001
        print(f"      (no puedo listar modelos: {type(e).__name__})", file=sys.stderr)
        return None

    sirven = [m["name"].split("/")[-1] for m in todos
              if "generateContent" in (m.get("supportedGenerationMethods") or [])]

    # **`gemini-flash-latest` es la respuesta buena**: Google mantiene ese alias
    # apuntando siempre al Flash más nuevo, así que no caduca nunca. Es lo que
    # había que usar desde el principio.
    orden = [a for a in ("gemini-flash-latest", "gemini-flash-lite-latest")
             if a in sirven]

    # Y si algún día no existiera el alias: el Flash **estable** de número más
    # alto. Se filtran los `preview` —la primera versión eligió uno y devolvía
    # error 400 en cada llamada— y los que no son de texto: image, tts, robotics.
    def version(nombre):
        num = "".join(c for c in nombre if c.isdigit() or c == ".")
        try:
            return float(num.strip(".").split(".")[0] + "." +
                         (num.strip(".").split(".") + ["0"])[1])
        except (ValueError, IndexError):
            return 0.0

    estables = [m for m in sirven
                if "flash" in m
                and not any(x in m for x in ("preview", "exp", "image", "tts",
                                             "thinking", "robotics", "computer"))]
    estables.sort(key=version, reverse=True)
    _ELEGIDO = (orden + estables + sirven)[:4]
    if _ELEGIDO:
        print(f"      (IA: probaré {', '.join(_ELEGIDO)})", file=sys.stderr)
    return _ELEGIDO

AVISO = "Resumen automático · puede equivocarse"


def clave():
    return os.environ.get("GEMINI_API_KEY", "").strip()


def disponible():
    return bool(clave())


def pedir(instruccion, texto, tope=300, temperatura=0.3):
    """Una llamada a Gemini. Si algo falla, devuelve None y el script sigue.

    **Nunca lanza.** Un canal de noticias que se cae porque una API de terceros
    tuvo un mal minuto es peor que un canal sin traducir.
    """
    k = clave()
    if not k or not texto:
        return None
    lista = modelos()
    if not lista:
        return None

    # El tope va **holgado**: los modelos nuevos gastan tokens pensando antes de
    # contestar, y con el tope justo la respuesta sale cortada a media frase.
    cuerpo = json.dumps({
        "contents": [{"parts": [{"text": instruccion + "\n\n" + texto}]}],
        "generationConfig": {"temperature": temperatura,
                             "maxOutputTokens": max(tope, 800)},
    }).encode("utf-8")

    for m in lista:
        try:
            req = urllib.request.Request(f"{BASE}/{m}:generateContent?key={k}",
                                         data=cuerpo,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            salida = d["candidates"][0]["content"]["parts"][0]["text"].strip()
            # a veces devuelve el texto entre comillas aunque se le diga que no
            return salida.strip('"').strip() or None
        except urllib.error.HTTPError as e:
            # 503 es «high demand» y 429 es cuota: los dos se arreglan probando
            # otro modelo, y justo el alias `-latest` es el que más se satura
            # porque apunta al de moda. El resto de errores no se arreglan
            # insistiendo, así que se corta.
            if e.code in (429, 503) and m != lista[-1]:
                print(f"      ({m} saturado, pruebo el siguiente)", file=sys.stderr)
                continue
            print(f"      (IA: HTTP {e.code} en {m})", file=sys.stderr)
            return None
        except (urllib.error.URLError, KeyError, IndexError, TimeoutError,
                json.JSONDecodeError) as e:
            print(f"      (IA no disponible: {type(e).__name__})", file=sys.stderr)
            return None
    return None


# ─────────────────────────────────────────────────────────────── titulares
_TRADUCIR = (
    "Traduce este titular de noticias al español de España neutro, como lo "
    "escribiría un medio hispanohablante. Devuelve SOLO el titular traducido: "
    "sin comillas, sin explicaciones, sin añadir nada que no esté. Si ya está en "
    "español, devuélvelo igual.")


def traducir(titular):
    return pedir(_TRADUCIR, titular, tope=200, temperatura=0.2) or titular


# ─────────────────────────────────────────────────────── por qué importa
_CONTEXTO = (
    "Eres el bot de un servidor de doblaje y fandub en español. Lee esta noticia "
    "y escribe UNA sola frase de menos de 140 caracteres diciendo por qué le "
    "puede interesar a alguien que dobla, canta o edita.\n"
    "Reglas estrictas:\n"
    "- Usa SOLO lo que dice la noticia. No inventes fechas, nombres ni datos.\n"
    "- Si la noticia no tiene nada que ver con doblaje, voz, música o edición, "
    "responde exactamente: NADA\n"
    "- Sin comillas, sin emojis, sin «esta noticia». Directo.")


def por_que_importa(titular, extracto=""):
    """Una línea de contexto, o None si la noticia no da para nada.

    El `NADA` del prompt es importante: **la IA tiene que poder callarse**. Sin
    esa salida, rellena con frases vacías del tipo «interesante para el mundo del
    doblaje» en cada noticia, y eso ensucia más de lo que aporta.
    """
    r = pedir(_CONTEXTO, f"{titular}\n{extracto}"[:1200], tope=120)
    if not r or r.strip().upper().startswith("NADA"):
        return None
    return r


# ──────────────────────────────────────────────────────── opiniones
_OPINIONES = (
    "Te doy reseñas reales de usuarios sobre una obra. Resúmelas en dos o tres "
    "frases: en qué coinciden y en qué no.\n"
    "Reglas estrictas:\n"
    "- Resume SOLO lo que dicen estas reseñas. No añadas nada de tu conocimiento.\n"
    "- Si hay críticas, dilas. No suavices ni hagas publicidad.\n"
    "- Escribe en español, en tercera persona: «coinciden en…», «varios señalan…»\n"
    "- Menos de 350 caracteres. Sin comillas ni listas.")


def resumir_opiniones(textos):
    """«La gente coincide en X, aunque varios señalan Y». De reseñas reales."""
    junto = "\n\n---\n\n".join(t for t in textos if t)[:6000]
    return pedir(_OPINIONES, junto, tope=300, temperatura=0.4)


# ──────────────────────────────────────────────────────── temporada
_TEMPORADA = (
    "Te doy la lista de los animes mejor valorados de la temporada, con su nota. "
    "Escribe dos frases sobre qué está pasando esta temporada.\n"
    "Reglas estrictas:\n"
    "- Usa SOLO los títulos, notas y géneros que te doy. No añadas otros.\n"
    "- Nada de superlativos vacíos. Si algo destaca por su nota, dilo con la nota.\n"
    "- Español, menos de 300 caracteres, sin listas ni emojis.")


def resumen_temporada(lineas):
    return pedir(_TEMPORADA, "\n".join(lineas)[:2000], tope=250, temperatura=0.4)


# ──────────────────────────────────────────────── en qué se dividió la gente
#
# Lo que hace interesante una noticia no es la noticia: es la bronca de después.
# Esto lee los comentarios de verdad de un hilo y cuenta **en qué bandos se
# partió**, con lo que dice cada uno.
#
# Las dos reglas duras son las que evitan el desastre típico de estos resúmenes:
# **nada de porcentajes** (no hay forma de contarlos con 40 comentarios y quedan
# como un dato falso pero convincente), y **decirlo cuando NO hubo división** —
# fingir polémica donde todos estaban de acuerdo es la manera más rápida de que
# nadie se vuelva a fiar de esta sección.
_DIVIDIO = (
    "Te doy comentarios reales de un hilo de Reddit sobre una noticia, del más "
    "votado al menos. Cuenta en qué se dividió la gente.\n"
    "Reglas estrictas:\n"
    "- Máximo DOS o TRES posturas, cada una en una línea que empieza por «— ».\n"
    "- Cada línea: la postura y el porqué, con lo que de verdad dicen.\n"
    "- **Nada de porcentajes ni de «la mayoría»**: no se pueden contar y suenan "
    "a dato inventado. Vale «varios», «unos cuantos», «los que más votos tienen».\n"
    "- **Si no hubo división, dilo en una sola línea** y no te inventes un bando "
    "que no existe. Es un resultado perfectamente bueno.\n"
    "- Si los comentarios no hablan de la noticia sino de otra cosa, responde "
    "exactamente NADA.\n"
    "- Español neutro, menos de 480 caracteres en total, sin emojis.")


def como_se_dividio(titular, comentarios):
    """«— Unos dicen X porque… / — Otros que Y». De comentarios de verdad."""
    junto = "\n\n---\n\n".join(c for c in comentarios if c)[:7000]
    if not junto:
        return None
    r = pedir(_DIVIDIO, f"NOTICIA: {titular}\n\nCOMENTARIOS:\n{junto}",
              tope=420, temperatura=0.4)
    if not r or r.strip().upper().startswith("NADA"):
        return None
    return r


if __name__ == "__main__":
    if not disponible():
        sys.exit("No hay GEMINI_API_KEY. Sácala gratis en aistudio.google.com/apikey\n"
                 "y ponla así:   $env:GEMINI_API_KEY = \"tu-clave\"")
    print("clave encontrada, probando...\n")
    print("  traducir:", traducir("K Manga Adds Daiki Yamazaki's Golden Phantom"))
    print("  contexto:", por_que_importa(
        "Castlevania: Belmont's Curse desvela su reparto de actores de voz"))
    print("  callarse:", por_que_importa("Nueva actualización del parche 2.3 de un RTS"))
