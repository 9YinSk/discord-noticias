#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_contadores.py — los números del servidor, escritos en el nombre de un canal.

Es el truco que usan los servidores grandes: arriba del todo, unos canales que
nadie puede abrir y que en vez de contenido tienen el dato en el propio nombre —
`👥 Miembros • 74`, `🟢 En línea • 12`. Se leen sin pulsar nada y le dan al
servidor un aire de sitio cuidado.

Suele venderse como función de bot de pago (Statistics, Server Stats…). No hace
falta: **es renombrar un canal**, y eso ya lo sabemos hacer. Va con el trabajo de
los roles, que corre cada 10 minutos en la nube.

**El límite que manda sobre todo el diseño:** Discord solo deja **2 cambios de
nombre cada 10 minutos por canal**, y cuando te pasas no da error — deja la
petición esperando. Por eso aquí **solo se renombra si el número cambió**. En un
servidor tranquilo la mayoría de las vueltas no tocan nada, que es justo lo que
hay que conseguir.

Son canales de **voz** a propósito: un canal de texto invita a escribir y estos
no son para eso. Con `CONECTAR` denegado a todos, quedan como etiquetas.

    python discord_contadores.py              # dice qué pondría
    python discord_contadores.py --crear --enserio   # crea la categoría
    python discord_contadores.py --enserio    # pone los números al día
"""
import argparse
import datetime
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from discord_servidor import api  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GUILD = os.environ.get("DISCORD_GUILD", "1539896304178823282")
CATEGORIA = "─── 📊 EL SERVIDOR ───"

VER_CANAL = 1 << 10
CONECTAR = 1 << 20

# clave -> (emoji, etiqueta). El orden es el que tendrán en la lista.
CONTADORES = [
    ("miembros", "👥", "Miembros"),
    ("enlinea",  "🟢", "En línea"),
    ("bots",     "🤖", "Bots"),
    ("mejoras",  "💎", "Mejoras"),
    ("desde",    "📅", "Desde"),
]


def nombre_de(clave, emoji, etiqueta, valor):
    """`👥 Miembros • 74`. El mismo molde para todos, que es lo que los hace serie."""
    return f"{emoji} {etiqueta} • {valor}"


def datos():
    """Los números de ahora mismo.

    `with_counts` es lo que trae el total y **cuántos hay conectados**; sin ese
    parámetro Discord devuelve el servidor sin esos dos campos y la cuenta sale
    a cero sin decir por qué.
    """
    g = api("GET", f"/guilds/{GUILD}?with_counts=true")
    miembros = api("GET", f"/guilds/{GUILD}/members?limit=1000") or []
    bots = sum(1 for m in miembros if (m.get("user") or {}).get("bot"))
    # `approximate_member_count` incluye a los bots; se restan para que el número
    # de personas sea el número de personas.
    total = g.get("approximate_member_count") or len(miembros)
    creado = datetime.datetime.fromtimestamp(
        ((int(GUILD) >> 22) + 1420070400000) / 1000, datetime.timezone.utc)
    # **Los bots se descuentan también de los conectados.** Este servidor tiene
    # 36 bots y todos figuran en línea las 24 h, así que el número crudo decía
    # «En línea • 36» con cuatro personas dentro: un dato que parece contar gente
    # y cuenta software. Restarlos da una estimación honrada — puede quedarse
    # corta si algún bot está caído, y eso es preferible a inflarla.
    presencia = g.get("approximate_presence_count") or 0
    return {
        "miembros": max(0, total - bots),
        "enlinea": max(0, presencia - bots),
        "bots": bots,
        "mejoras": g.get("premium_subscription_count") or 0,
        "desde": creado.strftime("%d/%m/%Y"),
    }


def categoria(canales):
    return next((c for c in canales if c["type"] == 4 and c["name"] == CATEGORIA), None)


def crear(enserio):
    """Crea la categoría y sus canales, arriba del todo y cerrados a la voz."""
    canales = api("GET", f"/guilds/{GUILD}/channels")
    cat = categoria(canales)
    if not cat:
        print(f"  crear categoría {CATEGORIA}")
        if enserio:
            cat = api("POST", f"/guilds/{GUILD}/channels",
                      {"name": CATEGORIA, "type": 4, "position": 0})
            time.sleep(0.4)
    if not enserio:
        return
    d = datos()
    ya = {c["name"] for c in canales}
    for clave, emoji, etiqueta in CONTADORES:
        nombre = nombre_de(clave, emoji, etiqueta, d[clave])
        if any(n.startswith(f"{emoji} {etiqueta} •") for n in ya):
            print(f"  {nombre}   (ya existe)")
            continue
        print(f"  {nombre}   <- crear")
        api("POST", f"/guilds/{GUILD}/channels", {
            "name": nombre, "type": 2, "parent_id": cat["id"],
            # se ve, pero no se entra: es una etiqueta, no una sala
            "permission_overwrites": [
                {"id": GUILD, "type": 0, "allow": str(VER_CANAL),
                 "deny": str(CONECTAR)}],
        })
        time.sleep(0.5)


def toca_ahora():
    """Si esta vuelta le toca a los contadores.

    **Discord solo deja 2 cambios de nombre cada 10 minutos por canal**, y
    cuando te pasas no da error: deja la petición esperando. Mientras el cron
    iba cada 10 minutos esto encajaba solo. Al bajarlo a 5 —cosa que se hizo
    por la bienvenida, no por esto— «En línea» cambia casi cada vuelta y se
    comería el cupo.

    Así que el trabajo corre cada 5 y **los contadores se saltan las vueltas
    impares**: siguen a su ritmo de 10 sin frenar a los demás.
    """
    return datetime.datetime.now(datetime.timezone.utc).minute % 10 < 5


def poner_al_dia(enserio):
    """Renombra **solo lo que cambió**. Ver el límite de 2 cada 10 minutos."""
    canales = api("GET", f"/guilds/{GUILD}/channels")
    cat = categoria(canales)
    if not cat:
        print("  no existe la categoría de contadores; créala con --crear")
        return 0
    dentro = [c for c in canales if c.get("parent_id") == cat["id"]]
    d = datos()
    cambios = 0
    for clave, emoji, etiqueta in CONTADORES:
        actual = next((c for c in dentro
                       if c["name"].startswith(f"{emoji} {etiqueta} •")), None)
        if not actual:
            print(f"  falta el canal de «{etiqueta}»")
            continue
        quiero = nombre_de(clave, emoji, etiqueta, d[clave])
        if actual["name"] == quiero:
            print(f"  {quiero}   (sin cambio)")
            continue
        print(f"  {actual['name']}  ->  {quiero}")
        if enserio:
            api("PATCH", f"/channels/{actual['id']}", {"name": quiero})
            time.sleep(0.5)
        cambios += 1
    return cambios


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--crear", action="store_true",
                   help="crea la categoría y los canales (solo la primera vez)")
    p.add_argument("--enserio", action="store_true")
    args = p.parse_args()

    if args.crear:
        crear(args.enserio)
    elif args.enserio and not toca_ahora():
        print("  esta vuelta no toca (el nombre de un canal solo se puede "
              "cambiar 2 veces cada 10 min)")
        return
    n = poner_al_dia(args.enserio)
    if not args.enserio:
        print("\n>>> SIMULACRO. Agrega --enserio.")
    else:
        print(f"\n{n} contadores actualizados" if n else "\nsin novedad")


if __name__ == "__main__":
    main()
