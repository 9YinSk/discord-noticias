#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_bienvenida.py — saluda a quien entra, con una tarjeta dibujada.

Discord avisa de que ha entrado alguien con una línea gris que se pierde en diez
minutos. Esto pone en su lugar **una tarjeta con su propia cara**, su nombre y
qué número hace en el servidor, más un par de botones para que lo primero que
haga tenga un sitio al que ir.

**Cómo sabe quién es nuevo, sin estar conectado.** No hay bot escuchando: esto
corre cada 10 minutos con el resto. Podría guardar en un archivo a quién ya
saludó, pero hay algo mejor y que no se puede desincronizar — **mirar el propio
canal de bienvenidas**. Quien ya tiene su tarjeta publicada, ya fue saludado. Si
alguien borra un mensaje, se vuelve a saludar; si el archivo de estado se
perdiera, no habría forma de saberlo. El canal *es* el estado.

    python discord_bienvenida.py                  # dice a quién saludaría
    python discord_bienvenida.py --enserio
    python discord_bienvenida.py --prueba TU_ID   # una de mentira, para verla
"""
import argparse
import datetime
import os
import re
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from discord_servidor import api  # noqa: E402
import discord_tarjetas_neon as db  # noqa: E402
from discord_botones import boton, componentes  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GUILD = os.environ.get("DISCORD_GUILD", "1539896304178823282")
CANAL = "ıı・👋・bienvenidas"
COLOR = (46, 204, 113)

# A dónde mandarle. Son los tres del recorrido de entrada: sin esto, la tarjeta
# es bonita y deja a la persona sin saber qué hacer.
DESTINOS = [("ıı・⭐・autoroles", "Empieza por aquí", "⭐"),
            ("ıı・🗺️・guia", "El mapa del servidor", "🗺️"),
            ("ıı・🪪・presentaciones", "Preséntate", "🪪")]

LEMAS = [
    "Aquí no juzga nadie. El que lleva veinte años empezó sin saber respirar.",
    "Todos los que están dentro grabaron una primera vez que daba vergüenza.",
    "El micro del móvil también vale para empezar. Lo demás ya vendrá.",
]

_MENCION = re.compile(r"<@!?(\d+)>")


def ya_saludados(canal_id, cuantos=100):
    """Los ids que ya aparecen mencionados en el canal. **El canal es el estado.**"""
    vistos = set()
    for m in api("GET", f"/channels/{canal_id}/messages?limit={cuantos}") or []:
        vistos.update(_MENCION.findall(m.get("content") or ""))
        for e in m.get("embeds") or []:
            vistos.update(_MENCION.findall(e.get("description") or ""))
    return vistos


def avatar_de(user):
    """La URL de su foto. Si no tiene, la que Discord le asigna por defecto."""
    if user.get("avatar"):
        ext = "gif" if str(user["avatar"]).startswith("a_") else "png"
        return (f"https://cdn.discordapp.com/avatars/{user['id']}/"
                f"{user['avatar']}.{ext}?size=256")
    # Los usuarios nuevos usan el id; los viejos, el discriminador. Con el id
    # funciona para ambos desde que Discord retiró los `#0000`.
    return f"https://cdn.discordapp.com/embed/avatars/{(int(user['id']) >> 22) % 6}.png"


def saludar(canal_id, miembro, numero, ids_canales, enserio):
    user = miembro["user"]
    nombre = miembro.get("nick") or user.get("global_name") or user["username"]
    lema = LEMAS[int(user["id"]) % len(LEMAS)]
    print(f"  {nombre}  (nº {numero})")
    if not enserio:
        return False

    ruta = db.tarjeta_bienvenida(nombre, avatar_de(user), numero, COLOR,
                                 "_bienvenida.png", lema=lema)
    e = {
        "description": f"**Bienvenido, <@{user['id']}>.**\n"
                       f"Ya sois {numero} por aquí.",
        "color": (COLOR[0] << 16) + (COLOR[1] << 8) + COLOR[2],
        "image": {"url": "attachment://" + os.path.basename(ruta)},
    }
    extra = [boton(f"https://discord.com/channels/{GUILD}/{ids_canales[n]}", t, em)
             for n, t, em in DESTINOS if n in ids_canales]
    cuerpo = {"embeds": [e]}
    comp = componentes(e, extra)
    if comp:
        cuerpo["components"] = comp
    db.subir_con_imagen(canal_id, ruta, cuerpo)
    return True


# La pantalla que Discord enseña **dentro del propio Discord** al entrar y en la
# vista previa de la invitación. Es gratis y es de las pocas cosas que ve alguien
# **antes de decidir si se queda**. Estaba sin configurar.
PANTALLA = {
    "texto": ("Un sitio para doblar, cantar y aprender a hacerlo. "
              "Se empieza sin saber: aquí no juzga nadie."),
    # **Solo canales que vea @everyone.** Discord rechaza el resto con
    # `WELCOME_CHANNEL_PERMISSIONS_REQUIRED`, y tiene sentido: esta pantalla se
    # enseña a quien todavía no ha entrado. `presentaciones` no vale desde que
    # se cerró tras el 🚪 Paso 1.
    "canales": [
        ("ıı・⭐・autoroles", "⭐", "Elige qué te interesa y se te abre"),
        ("ıı・🗺️・guia", "🗺️", "El mapa: qué hay en cada zona"),
        ("ıı・🙋・si-te-atascas", "🙋", "Si algo no se entiende, aquí"),
        ("ıı・👋・bienvenidas", "👋", "Aquí saludamos a cada persona nueva"),
    ],
}


def pantalla(ids, enserio):
    """Configura la pantalla de bienvenida de Discord. Solo servidores Comunidad.

    **No confundir con el fondo decorado** que se ve en las capturas de otros
    servidores: eso es el *splash* de invitación y **pide nivel 1 de mejoras**
    (2 boosts). Esto es la parte de texto, que sí es gratis.
    """
    cuerpo = {
        "enabled": True,
        "description": PANTALLA["texto"],
        "welcome_channels": [
            {"channel_id": ids[n], "description": d, "emoji_name": e}
            for n, e, d in PANTALLA["canales"] if n in ids
        ][:5],                       # Discord admite 5 como mucho
    }
    print(f"  «{PANTALLA['texto'][:60]}...»")
    for c in cuerpo["welcome_channels"]:
        print(f"    {c['emoji_name']}  {c['description']}")
    if enserio:
        api("PATCH", f"/guilds/{GUILD}/welcome-screen", cuerpo)
        print("\n  pantalla de bienvenida activada")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--enserio", action="store_true")
    p.add_argument("--pantalla", action="store_true",
                   help="configura la pantalla de bienvenida de Discord y sale")
    p.add_argument("--dias", type=int, default=7,
                   help="hasta cuándo mirar hacia atrás (por defecto 7 días)")
    p.add_argument("--max", type=int, default=4,
                   help="cuántos saludar como mucho por vuelta")
    p.add_argument("--prueba", metavar="ID",
                   help="dibuja la tarjeta de ese usuario y la publica, para verla")
    args = p.parse_args()

    canales = api("GET", f"/guilds/{GUILD}/channels")
    ids = {c["name"]: c["id"] for c in canales}
    canal_id = ids.get(CANAL)
    if not canal_id:
        sys.exit(f"No encuentro {CANAL}")

    miembros = api("GET", f"/guilds/{GUILD}/members?limit=1000") or []
    personas = [m for m in miembros if not (m.get("user") or {}).get("bot")]
    # el número que hace cada uno: por orden de llegada, que es lo que significa
    personas.sort(key=lambda m: m.get("joined_at") or "")
    puesto = {m["user"]["id"]: i + 1 for i, m in enumerate(personas)}

    if args.pantalla:
        pantalla(ids, args.enserio)
        if not args.enserio:
            print("\n>>> SIMULACRO. Agrega --enserio.")
        return

    if args.prueba:
        m = next((x for x in miembros if x["user"]["id"] == args.prueba), None)
        if not m:
            sys.exit("Ese id no está en el servidor.")
        saludar(canal_id, m, puesto.get(args.prueba, 1), ids, True)
        print("\npublicada la de prueba")
        return

    corte = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=args.dias)).isoformat()
    vistos = ya_saludados(canal_id)
    nuevos = [m for m in personas
              if (m.get("joined_at") or "") > corte
              and m["user"]["id"] not in vistos]

    print(f"{len(personas)} personas · {len(vistos)} ya saludadas · "
          f"{len(nuevos)} por saludar")
    hechos = 0
    for m in nuevos[:args.max]:
        if saludar(canal_id, m, puesto[m["user"]["id"]], ids, args.enserio):
            hechos += 1
            time.sleep(1.2)

    if not args.enserio:
        print("\n>>> SIMULACRO. Agrega --enserio.")
    else:
        print(f"\n{hechos} bienvenidas publicadas" if hechos else "\nsin novedad")


if __name__ == "__main__":
    main()
