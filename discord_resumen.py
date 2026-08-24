#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_resumen.py — el domingo, lo que pasó en el servidor esta semana.

En un servidor pequeño lo que más se pierde es **darse cuenta de que sí pasan
cosas**. Alguien abre su primera demo un martes y el jueves ya nadie lo ve. Este
resumen lo saca a flote: quién entró, qué hilos se abrieron, qué se estrenó.

No inventa nada: cuenta lo que hay. Y si la semana ha estado muerta, **lo dice**
en vez de rellenar — un resumen que finge movimiento se nota enseguida y deja de
leerse.

    python discord_resumen.py                # simulacro
    python discord_resumen.py --enserio
    python discord_resumen.py --dias 30 --enserio
"""
import argparse
import datetime
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from discord_servidor import api  # noqa: E402
import discord_ia as ia  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GUILD = "1539896304178823282"
CANAL = "ıı・🌐・general"
EPOCA = 1420070400000        # Discord cuenta el tiempo desde 2015


def cuando(id_discord):
    """La fecha de cualquier cosa de Discord, sacada de su propio id."""
    ms = (int(id_discord) >> 22) + EPOCA
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--enserio", action="store_true")
    p.add_argument("--dias", type=int, default=7)
    args = p.parse_args()

    corte = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=args.dias)
    canales = api("GET", f"/guilds/{GUILD}/channels")
    nombre = {c["id"]: c["name"] for c in canales}
    activos = (api("GET", f"/guilds/{GUILD}/threads/active") or {}).get("threads", [])

    # ── hilos nuevos, sin contar los del bot
    hilos = [t for t in activos
             if cuando(t["id"]) > corte
             and not t.get("name", "").startswith(("📌", "EJEMPLO ·"))]

    # ── gente que entró
    miembros = api("GET", f"/guilds/{GUILD}/members?limit=200") or []
    nuevos = [m for m in miembros
              if not (m.get("user") or {}).get("bot")
              and m.get("joined_at", "") > corte.isoformat()]

    # ── lo que más gustó: se mira en los canales donde se habla
    mejor = []
    for c in canales:
        if c["type"] != 0 or not any(k in c["name"] for k in
                                     ("general", "memes", "clips", "destacados")):
            continue
        for m in api("GET", f"/channels/{c['id']}/messages?limit=50") or []:
            if cuando(m["id"]) < corte or (m.get("author") or {}).get("bot"):
                continue
            n = sum(r["count"] for r in m.get("reactions") or [])
            if n:
                mejor.append((n, m, c["name"]))
        time.sleep(0.15)
    mejor.sort(key=lambda x: -x[0])

    print(f"  {len(hilos)} hilos · {len(nuevos)} personas nuevas · "
          f"{len(mejor)} mensajes con reacciones")

    # **Si no ha pasado nada, se dice.** Un resumen que rellena para parecer vivo
    # se nota a la segunda semana, y entonces ya no lo lee nadie.
    if not (hilos or nuevos or mejor):
        campos = [{"name": "Semana tranquila",
                   "value": "No se abrió ningún hilo nuevo. No pasa nada: hay "
                            "semanas así.\nSi tenías algo a medias, esta es la "
                            "excusa para terminarlo.", "inline": False}]
    else:
        campos = []
        if nuevos:
            campos.append({
                "name": f"Entraron {len(nuevos)}",
                "value": " · ".join(f"<@{m['user']['id']}>" for m in nuevos[:10])
                         + "\n-# Si no les habéis dicho nada todavía, ahora es "
                           "buen momento",
                "inline": False})
        if hilos:
            por_canal = {}
            for t in hilos:
                por_canal.setdefault(t.get("parent_id"), []).append(t)
            lineas = []
            for cid, lista in sorted(por_canal.items(),
                                     key=lambda x: -len(x[1]))[:6]:
                corto = nombre.get(cid, "?").split("・")[-1]
                lineas.append(f"**{corto}** — " + " · ".join(
                    t["name"][:38] for t in lista[:3]))
            campos.append({"name": f"{len(hilos)} hilos nuevos",
                           "value": "\n".join(lineas)[:1020], "inline": False})
        if mejor:
            n, m, canal = mejor[0]
            texto = (m.get("content") or "").strip() or "*(una imagen)*"
            campos.append({
                "name": f"Lo más reaccionado · {n} reacciones",
                "value": f"En **{canal.split('・')[-1]}**, de <@{m['author']['id']}>\n"
                         f"> {texto[:160]}", "inline": False})

    # la frase de arriba la escribe la IA si hay clave; si no, una fija
    resumen = None
    if hilos or nuevos:
        resumen = ia.pedir(
            "Eres el bot de un servidor de doblaje. Con estos datos de la semana, "
            "escribe UNA frase de menos de 160 caracteres, en español, animando "
            "sin exagerar. Nada de superlativos ni emojis. Si los números son "
            "bajos, no finjas que son altos.",
            f"Hilos nuevos: {len(hilos)}. Personas nuevas: {len(nuevos)}. "
            f"Canales con movimiento: "
            f"{', '.join({nombre.get(t.get('parent_id'), '') for t in hilos})}",
            tope=120)

    e = {
        "author": {"name": f"La semana en el servidor"},
        "title": f"Del {corte.strftime('%d/%m')} al "
                 f"{datetime.datetime.now().strftime('%d/%m')}",
        "color": 0x2ECC71,
        "description": (resumen + f"\n\n-# {ia.AVISO}") if resumen else
                       "-# Sale solo cada domingo.",
        "fields": campos,
        "footer": {"text": "Lo que no aparece aquí es porque no pasó, no porque "
                           "no se mire"},
    }

    for c in campos:
        print(f"    · {c['name']}")
    if not args.enserio:
        print("\n>>> SIMULACRO. Agrega --enserio.")
        return

    cid = next((c["id"] for c in canales if c["name"] == CANAL), None)
    if not cid:
        sys.exit(f"No encuentro {CANAL}")
    api("POST", f"/channels/{cid}/messages", {"embeds": [e]})
    print("\npublicado en general")


if __name__ == "__main__":
    main()
