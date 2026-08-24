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

# Flash es el modelo rápido y barato: para traducir un titular sobra, y es el que
# más cuota gratis tiene.
MODELO = "gemini-2.0-flash"
URL = (f"https://generativelanguage.googleapis.com/v1beta/models/"
       f"{MODELO}:generateContent?key=")

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
    cuerpo = json.dumps({
        "contents": [{"parts": [{"text": instruccion + "\n\n" + texto}]}],
        "generationConfig": {"temperature": temperatura, "maxOutputTokens": tope},
    }).encode("utf-8")
    try:
        req = urllib.request.Request(URL + k, data=cuerpo,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        salida = d["candidates"][0]["content"]["parts"][0]["text"].strip()
        # a veces devuelve el texto entre comillas aunque se le diga que no
        return salida.strip('"').strip() or None
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, IndexError,
            TimeoutError, json.JSONDecodeError) as e:
        print(f"      (IA no disponible: {type(e).__name__})", file=sys.stderr)
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


if __name__ == "__main__":
    if not disponible():
        sys.exit("No hay GEMINI_API_KEY. Sácala gratis en aistudio.google.com/apikey\n"
                 "y ponla así:   $env:GEMINI_API_KEY = \"tu-clave\"")
    print("clave encontrada, probando...\n")
    print("  traducir:", traducir("K Manga Adds Daiki Yamazaki's Golden Phantom"))
    print("  contexto:", por_que_importa(
        "Castlevania: Belmont's Curse desvela su reparto de actores de voz"))
    print("  callarse:", por_que_importa("Nueva actualización del parche 2.3 de un RTS"))
