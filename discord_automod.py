#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_automod.py — la moderación automática de Discord, declarada en un sitio.

**Qué es AutoMod y por qué importa aquí.** Es el filtro que trae Discord de
serie: mira cada mensaje **antes** de publicarlo y lo bloquea si encaja con una
regla. Lo interesante para nosotros es que **no necesita ningún bot encendido** —
lo ejecuta Discord en su servidor, así que funciona con el PC apagado y sin
gastar un minuto de GitHub Actions.

**Por qué existe este archivo.** Las reglas ya estaban puestas y funcionando,
pero solo vivían dentro de Discord: nadie sabía cuáles eran sin ir a mirarlas, y
si alguien borra una no hay forma de reponerla igual. Aquí están declaradas —
correr el script deja el servidor como dice esta lista.

    python discord_automod.py            # compara y dice qué cambiaría
    python discord_automod.py --enserio

Lo que Discord permite, y condiciona la lista: **6 reglas de palabras como
máximo**, y **una sola** de spam, una de preajustes y una de menciones.
"""
import argparse
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from discord_servidor import api  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GUILD = os.environ.get("DISCORD_GUILD", "1539896304178823282")
CANAL_AVISOS = "ıı・🧾・log-mod"
STAFF = ["👑 Fundador", "⚙️ Administrador", "🛡️ Moderador"]

# tipos de disparo
PALABRAS, SPAM, PREAJUSTE, MENCIONES = 1, 3, 4, 5
# preajustes de Discord: 1 groserías, 2 contenido sexual, 3 insultos de odio
BLOQUEAR, AVISAR, SILENCIAR = 1, 2, 3

_AVISO = ("Ese mensaje no se ha publicado: lo ha parado el filtro automático "
          "del servidor. Si crees que es un error, dilo en soporte.")


def regla(nombre, disparo, metadatos=None, silenciar=None, exentos=STAFF):
    """Una regla. Todas bloquean y avisan al registro; algunas además silencian.

    **El aviso al registro no es opcional en la práctica.** Una regla que solo
    bloquea deja al staff sin enterarse de nada: el mensaje no aparece y no queda
    rastro, así que un intento de estafa repetido se ve como silencio. Con el
    aviso, el patrón se nota.
    """
    acciones = [{"type": BLOQUEAR, "metadata": {"custom_message": _AVISO}},
                {"type": AVISAR, "metadata": {"channel_id": None}}]  # se rellena
    if silenciar:
        acciones.append({"type": SILENCIAR,
                         "metadata": {"duration_seconds": int(silenciar)}})
    return {"nombre": nombre, "disparo": disparo, "metadatos": metadatos or {},
            "acciones": acciones, "exentos": list(exentos)}


ACORTADORES = ["*bit.ly/*", "*tinyurl.com/*", "*cutt.ly/*", "*is.gd/*",
               "*shorturl*", "*rb.gy/*", "*t.co/*", "*ow.ly/*", "*tiny.cc/*"]
RASTREADORES = ["*grabify*", "*iplogger*", "*ip-logger*", "*blasze*", "*2no.co*",
                "*yip.su*", "*ipgrabber*", "*iplis.ru*", "*ps3cfw.com*"]
ESTAFAS = ["*nitro grati*", "*free nitro*", "*nitro free*", "*regalo de nitro*",
           "*nitro de regalo*", "*discordgift*", "*discord-gift*", "*dlscord*",
           "*steamcommunity.com/gift*", "*disc0rd*"]
INVITACIONES = ["discord.gg/*", "discord.com/invite/*", "dsc.gg/*",
                "discord.io/*", "discordapp.com/invite/*"]
PERSONALES = ["*mi numero es*", "*mi whatsapp es*", "*mi direccion es*",
              "*mi número es*", "*mi dirección es*", "*vivo en la calle*"]

# El estado que debe tener el servidor. Cambiar algo aquí y correr el script.
QUIERO = [
    regla("Anti-spam", SPAM),

    # Los tres preajustes de Discord: groserías, contenido sexual e insultos de
    # odio. **Ojo con el 1**: está pensado para el inglés, así que del castellano
    # pilla poco. El que de verdad aporta es el 3.
    regla("Insultos y contenido sexual", PREAJUSTE, {"presets": [1, 2, 3]}),

    regla("Invitaciones a otros servidores", PALABRAS,
          {"keyword_filter": INVITACIONES}),

    # Sin silenciar: casi siempre es alguien contando su vida sin pensar, no un
    # ataque. Se le para el mensaje y ya.
    regla("Datos personales", PALABRAS, {"keyword_filter": PERSONALES}),

    # Estas dos **sí silencian diez minutos**: no existe la versión legítima de
    # mandar un iplogger o una estafa de Nitro. Quien lo hace, o es una cuenta
    # robada o viene a hacer daño, y en los dos casos lo que hay que hacer es
    # cortarle el turno mientras alguien mira.
    regla("Estafas de Nitro y regalos", PALABRAS, {"keyword_filter": ESTAFAS},
          silenciar=600),
    regla("Rastreadores de IP", PALABRAS, {"keyword_filter": RASTREADORES},
          silenciar=600),

    regla("Enlaces que ocultan su destino", PALABRAS,
          {"keyword_filter": ACORTADORES}),

    # **Estaba en 20, que es el número que trae Discord de fábrica.** Veinte
    # menciones en un mensaje no es spam: es una masacre que ya ocurrió. En un
    # servidor de decenas de personas, seis ya es raro. Y llevaba nombre en
    # inglés y sin aviso, porque nadie la había tocado desde que se creó sola.
    regla("Menciones masivas", MENCIONES,
          {"mention_total_limit": 6, "mention_raid_protection_enabled": True}),
]


def _ids():
    canales = api("GET", f"/guilds/{GUILD}/channels")
    roles = api("GET", f"/guilds/{GUILD}/roles")
    canal = next((c["id"] for c in canales if c["name"] == CANAL_AVISOS), None)
    return canal, {r["name"]: r["id"] for r in roles}


def _cuerpo(r, canal_avisos, rol_id):
    acciones = []
    for a in r["acciones"]:
        a = {"type": a["type"], "metadata": dict(a.get("metadata") or {})}
        if a["type"] == AVISAR:
            if not canal_avisos:
                continue                 # sin canal de registro, no se avisa
            a["metadata"]["channel_id"] = canal_avisos
        acciones.append(a)
    return {
        "name": r["nombre"],
        "event_type": 1,                 # al enviar un mensaje
        "trigger_type": r["disparo"],
        "trigger_metadata": r["metadatos"],
        "actions": acciones,
        "enabled": True,
        "exempt_roles": [rol_id[n] for n in r["exentos"] if n in rol_id],
        "exempt_channels": [],
    }


def _igual(viva, quiero):
    """¿La regla de Discord ya dice lo mismo que el plan?

    Se comparan solo las partes que declaramos. Discord devuelve campos que no
    ponemos (`creator_id`, `guild_id`, metadatos vacíos que rellena solo), y
    compararlo todo daría siempre distinto.
    """
    if not viva.get("enabled"):
        return False
    md_v = {k: v for k, v in (viva.get("trigger_metadata") or {}).items() if v}
    md_q = {k: v for k, v in (quiero["trigger_metadata"] or {}).items() if v}
    if md_v != md_q:
        return False
    if sorted(viva.get("exempt_roles") or []) != sorted(quiero["exempt_roles"]):
        return False
    tipos_v = sorted(a["type"] for a in viva.get("actions") or [])
    tipos_q = sorted(a["type"] for a in quiero["actions"])
    if tipos_v != tipos_q:
        return False
    for a in viva.get("actions") or []:      # que el silencio dure lo que toca
        if a["type"] == SILENCIAR:
            q = next((x for x in quiero["actions"] if x["type"] == SILENCIAR), None)
            if not q or (a.get("metadata") or {}).get("duration_seconds") != \
                    q["metadata"]["duration_seconds"]:
                return False
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--enserio", action="store_true")
    args = p.parse_args()

    canal_avisos, rol_id = _ids()
    if not canal_avisos:
        print(f"  ojo: no existe «{CANAL_AVISOS}», las reglas no avisarán a nadie")
    vivas = {r["name"]: r for r in api("GET",
                                       f"/guilds/{GUILD}/auto-moderation/rules")}
    creadas = tocadas = 0

    for r in QUIERO:
        cuerpo = _cuerpo(r, canal_avisos, rol_id)
        viva = vivas.pop(r["nombre"], None)

        # Una regla del mismo tipo con otro nombre es LA MISMA para Discord: solo
        # deja una de spam, una de preajustes y una de menciones. Si se busca por
        # nombre y no se encuentra, crear da un 400 confuso; hay que reconocerla
        # por su tipo. Así se recupera la «Block Mention Spam» que Discord creó
        # sola con su nombre en inglés.
        if not viva and r["disparo"] in (SPAM, PREAJUSTE, MENCIONES):
            gemela = next((v for v in vivas.values()
                           if v["trigger_type"] == r["disparo"]), None)
            if gemela:
                viva = vivas.pop(gemela["name"])
                print(f"  «{gemela['name']}» es la de este tipo -> "
                      f"la renombro a «{r['nombre']}»")

        if viva and _igual(viva, cuerpo) and viva["name"] == r["nombre"]:
            print(f"  {r['nombre']}   (ya está bien)")
            continue
        if viva:
            print(f"  {r['nombre']}   ACTUALIZAR")
            if args.enserio:
                try:
                    api("PATCH",
                        f"/guilds/{GUILD}/auto-moderation/rules/{viva['id']}",
                        cuerpo)
                except SystemExit as e:
                    # **«Block Mention Spam» no es una regla, es un ajuste
                    # interno de Discord** que aparece en el listado con un id
                    # que no existe como recurso: el PATCH da 404. La única
                    # forma de gobernarla es crear una regla de verdad, que la
                    # sustituye.
                    if "404" not in str(e):
                        raise
                    print("     (no es una regla de verdad, creo una que la "
                          "sustituya)")
                    api("POST", f"/guilds/{GUILD}/auto-moderation/rules", cuerpo)
                time.sleep(0.4)
            tocadas += 1
        else:
            print(f"  {r['nombre']}   <- crear")
            if args.enserio:
                api("POST", f"/guilds/{GUILD}/auto-moderation/rules", cuerpo)
                time.sleep(0.4)
            creadas += 1

    for sobra in vivas.values():
        print(f"  «{sobra['name']}» está en el servidor y no en este archivo. "
              f"No la toco: bórrala a mano si no la quieres.")

    print(f"\n{creadas} creadas · {tocadas} actualizadas"
          if args.enserio else "\n>>> SIMULACRO. Agrega --enserio.")


if __name__ == "__main__":
    main()
