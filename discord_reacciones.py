#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_reacciones.py — reparte roles por reaccion, sin bot de terceros.

Discord no deja que un bot "escuche" reacciones sin un proceso conectado a su
gateway las 24 h. Esto hace lo mismo por el camino corto: **pregunta** quien ha
reaccionado a unos mensajes concretos y reparte (o quita) los roles.

  · una pasada:   python discord_reacciones.py            → pone al dia a todos
  · vigilando:    python discord_reacciones.py --vigilar 20

Con `--vigilar` se comporta como un bot de reaction roles de verdad, mientras la
ventana este abierta. Sin el, es un "ponte al dia" que se corre cuando sea: quien
reacciono mientras no habia nadie mirando, recibe su rol en la siguiente pasada.

Los paneles se declaran en `discord_reacciones.json`:

    { "guild": "123...",
      "paneles": [
        { "que_es": "Paso 1 del recorrido de entrada",
          "mensaje": "154097...",
          "quitar": false,            // una vez dado, no se quita
          "reacciones": { "➡️": "🚪 Paso 1" } },
        { "que_es": "Colores",
          "mensaje": "154093...",
          "exclusivo": true,          // solo un color a la vez
          "quitar": true,             // quitar la reaccion quita el rol
          "reacciones": { "🔴": "🔴 Rojo", ... } } ] }

El token sale de donde siempre: DISCORD_BOT_TOKEN o herramientas/.discord_token.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from discord_servidor import api  # noqa: E402  (reusa token, reintentos y 429)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CONFIG = os.path.join(AQUI, "discord_reacciones.json")


def quienes_reaccionaron(mensaje_id, canal_id, emoji):
    """Los que han puesto ESE emoji en ESE mensaje. Sin contar bots."""
    e = urllib.parse.quote(emoji)
    gente, despues = [], None
    while True:
        ruta = f"/channels/{canal_id}/messages/{mensaje_id}/reactions/{e}?limit=100"
        if despues:
            ruta += f"&after={despues}"
        lote = api("GET", ruta) or []
        gente += [u for u in lote if not u.get("bot")]
        if len(lote) < 100:
            return gente
        despues = lote[-1]["id"]


def hilos_de(canal_id, guild):
    """Todos los hilos de un foro: los vivos y los archivados."""
    activos = api("GET", f"/guilds/{guild}/threads/active") or {}
    hilos = [t for t in activos.get("threads", []) if t.get("parent_id") == canal_id]
    viejos = api("GET", f"/channels/{canal_id}/threads/archived/public?limit=100") or {}
    return hilos + list(viejos.get("threads", []))


def al_publicar(cfg, rol_id, tiene, nombre, enserio, bots=frozenset()):
    """Quien abre su hilo en un canal se lleva un rol. Es el ultimo paso del
    recorrido de entrada: presentarse abre el servidor, sin que nadie este mirando.

    El mensaje que abre un hilo tiene el MISMO id que el hilo: por ahi se mira
    que la presentacion no sea un "hola" de tres letras.
    """
    guild = cfg["guild"]
    cambios = 0
    for regla in cfg.get("al_publicar", []):
        rol = regla["rol"]
        if rol not in rol_id:
            print(f"  ojo: el rol «{rol}» no existe")
            continue
        minimo = int(regla.get("minimo_caracteres", 0))
        for hilo in hilos_de(regla["canal_id"], guild):
            dueno = hilo.get("owner_id")
            # Los hilos de plantilla los abre el propio bot: no se verifica solo.
            if not dueno or dueno in bots or dueno not in tiene \
                    or rol_id[rol] in tiene[dueno]:
                continue
            if minimo:
                try:
                    primero = api("GET", f"/channels/{hilo['id']}/messages/{hilo['id']}")
                    largo = len((primero.get("content") or "").strip())
                except SystemExit:
                    largo = 0
                if largo < minimo:
                    print(f"  {nombre.get(dueno, dueno)}: su presentacion son {largo} "
                          f"caracteres, hacen falta {minimo}. Lo dejo para la proxima.")
                    continue
            print(f"  + {rol}  a {nombre.get(dueno, dueno)}  (se presento: «{hilo['name'][:40]}»)")
            if enserio:
                api("PUT", f"/guilds/{guild}/members/{dueno}/roles/{rol_id[rol]}")
                time.sleep(0.3)
                if regla.get("avisar_en"):
                    api("POST", f"/channels/{regla['avisar_en']}/messages", {
                        "content": f"✅ <@{dueno}> se presentó y se le abrió el servidor "
                                   f"— hilo: **{hilo['name'][:60]}**"})
                    time.sleep(0.3)
            tiene[dueno].add(rol_id[rol])
            cambios += 1
    return cambios


def zonas(cfg, rol_id, tiene, nombre, enserio):
    """La Y que Discord no sabe hacer: **verificado + interés = acceso**.

    Entre roles, un `allow` siempre le gana a un `deny`, asi que no se puede pedir
    dos roles a la vez para ver un canal. La vuelta: el cuestionario reparte
    roles que NO abren nada (los intereses), y esto los traduce en las llaves de
    verdad solo cuando la persona ya paso el recorrido. Funciona en los dos
    sentidos — si se quita el interes, se le cierra la zona.
    """
    z = cfg.get("zonas")
    if not z:
        return 0
    requiere = rol_id.get(z.get("requiere", ""))
    cambios = 0
    for uid, suyos in tiene.items():
        verificado = requiere in suyos if requiere else True
        for regla in z["reglas"]:
            llave = rol_id.get(regla["llave"])
            if not llave:
                continue
            quiere = any(rol_id.get(i) in suyos for i in regla["intereses"])
            deberia = verificado and quiere
            if deberia and llave not in suyos:
                print(f"  + {regla['llave']}  a {nombre.get(uid, uid)}")
                if enserio:
                    api("PUT", f"/guilds/{cfg['guild']}/members/{uid}/roles/{llave}")
                    time.sleep(0.3)
                suyos.add(llave)
                cambios += 1
            # Con `nunca_quitar` el script solo AÑADE. Desde que el cuestionario
            # reparte las llaves el solo —para que la entrada funcione con el PC
            # apagado—, quitarlas seria deshacer lo que hizo Discord.
            elif not z.get("nunca_quitar") and not verificado and llave in suyos:
                print(f"  - {regla['llave']}  a {nombre.get(uid, uid)}  "
                      f"(aun no se ha verificado)")
                if enserio:
                    api("DELETE", f"/guilds/{cfg['guild']}/members/{uid}/roles/{llave}")
                    time.sleep(0.3)
                suyos.discard(llave)
                cambios += 1
    return cambios


def limpiar(cfg, enserio):
    """Borra lo viejo de los canales que no deben acumular conversacion.

    Da tiempo a que alguien conteste y luego lo quita, para que el canal no se
    convierta en un chat. **Nunca toca los mensajes fijados**: ahi va lo que
    explica para que es el canal.
    """
    from datetime import datetime, timezone
    cambios = 0
    for regla in cfg.get("limpiar", []):
        minutos = int(regla.get("minutos", 60))
        ahora = datetime.now(timezone.utc)
        for m in api("GET", f"/channels/{regla['canal_id']}/messages?limit=100") or []:
            if m.get("pinned"):
                continue
            cuando = datetime.fromisoformat(m["timestamp"])
            edad = (ahora - cuando).total_seconds() / 60
            if edad < minutos:
                continue
            quien = (m.get("author") or {}).get("username", "?")
            print(f"  🧹 borro un mensaje de {quien} ({int(edad)} min) en "
                  f"{regla.get('que_es', regla['canal_id'])}")
            if enserio:
                api("DELETE", f"/channels/{regla['canal_id']}/messages/{m['id']}")
                time.sleep(0.35)
            cambios += 1
    return cambios


def antiguedad(cfg, rol_id, miembros, tiene, nombre, enserio, bots=frozenset()):
    """Roles por tiempo dentro. No hace falta ningún bot: la fecha de entrada
    viene en cada miembro (`joined_at`).

    Es una escalera: solo se lleva el escalón más alto alcanzado, y los de abajo
    se quitan. Si no, alguien con un año acabaría con los cinco puestos.
    """
    from datetime import datetime, timezone
    z = cfg.get("antiguedad")
    if not z:
        return 0
    escalones = sorted(z["escalones"], key=lambda e: e["dias"])
    ahora = datetime.now(timezone.utc)
    cambios = 0
    for m in miembros:
        uid = m["user"]["id"]
        if uid in bots or not m.get("joined_at"):
            continue
        dias = (ahora - datetime.fromisoformat(m["joined_at"])).days
        gana = None
        for e in escalones:
            if dias >= e["dias"] and e["rol"] in rol_id:
                gana = e["rol"]
        suyos = tiene.get(uid, set())
        for e in escalones:
            rid = rol_id.get(e["rol"])
            if not rid:
                continue
            deberia = (e["rol"] == gana)
            if deberia and rid not in suyos:
                print(f"  + {e['rol']}  a {nombre.get(uid, uid)}  ({dias} días dentro)")
                if enserio:
                    api("PUT", f"/guilds/{cfg['guild']}/members/{uid}/roles/{rid}")
                    time.sleep(0.3)
                suyos.add(rid)
                cambios += 1
            elif not deberia and rid in suyos:
                print(f"  - {e['rol']}  a {nombre.get(uid, uid)}  (ya subió de escalón)")
                if enserio:
                    api("DELETE", f"/guilds/{cfg['guild']}/members/{uid}/roles/{rid}")
                    time.sleep(0.3)
                suyos.discard(rid)
                cambios += 1
    return cambios


def una_pasada(cfg, enserio=True, callado=False):
    guild = cfg["guild"]
    rol_id = {r["name"]: r["id"] for r in api("GET", f"/guilds/{guild}/roles")}
    miembros = api("GET", f"/guilds/{guild}/members?limit=1000")
    tiene = {m["user"]["id"]: set(m["roles"]) for m in miembros}
    nombre = {m["user"]["id"]: (m["user"].get("global_name") or m["user"]["username"])
              for m in miembros}
    cambios = 0

    for panel in cfg["paneles"]:
        # El canal se deduce del propio mensaje si no viene puesto.
        canal = panel.get("canal_id")
        if not canal:
            sys.exit(f"al panel «{panel.get('que_es', '?')}» le falta canal_id")

        grupo = {rol_id[n] for n in panel["reacciones"].values() if n in rol_id}
        marcados = {}          # usuario -> roles que le tocan por este panel
        muerto = False
        for emoji, rol in panel["reacciones"].items():
            if rol not in rol_id:
                print(f"  ojo: el rol «{rol}» no existe")
                continue
            try:
                gente = quienes_reaccionaron(panel["mensaje"], canal, emoji)
            except SystemExit as e:
                # Un panel borrado no puede tumbar la pasada entera: si no, deja
                # de repartirse TODO —zonas, verificacion, limpieza— por un
                # mensaje que ya no existe.
                if "404" in str(e):
                    print(f"  ojo: el panel «{panel.get('que_es', '?')}» apunta a un "
                          f"mensaje que ya no existe ({panel['mensaje']}). Lo salto.")
                    muerto = True
                    break
                raise
            for u in gente:
                marcados.setdefault(u["id"], set()).add(rol_id[rol])
        if muerto:
            continue

        for uid, tocan in marcados.items():
            if uid not in tiene:
                continue                      # reacciono y se fue del servidor
            if panel.get("exclusivo") and len(tocan) > 1:
                print(f"  {nombre.get(uid, uid)} reacciono a varios en un panel de uno "
                      f"solo: lo dejo como esta")
                continue
            for r in tocan - tiene[uid]:
                print(f"  + {[k for k, v in rol_id.items() if v == r][0]}  a "
                      f"{nombre.get(uid, uid)}")
                if enserio:
                    api("PUT", f"/guilds/{guild}/members/{uid}/roles/{r}")
                    time.sleep(0.3)
                tiene[uid].add(r)
                cambios += 1
            if panel.get("exclusivo"):        # fuera los demas del grupo
                for r in (tiene[uid] & grupo) - tocan:
                    print(f"  - {[k for k, v in rol_id.items() if v == r][0]}  a "
                          f"{nombre.get(uid, uid)}  (eligio otro)")
                    if enserio:
                        api("DELETE", f"/guilds/{guild}/members/{uid}/roles/{r}")
                        time.sleep(0.3)
                    tiene[uid].discard(r)
                    cambios += 1

        if panel.get("quitar"):               # quito la reaccion -> pierde el rol
            for uid, suyos in tiene.items():
                sobran = (suyos & grupo) - marcados.get(uid, set())
                for r in sobran:
                    print(f"  - {[k for k, v in rol_id.items() if v == r][0]}  a "
                          f"{nombre.get(uid, uid)}  (quito la reaccion)")
                    if enserio:
                        api("DELETE", f"/guilds/{guild}/members/{uid}/roles/{r}")
                        time.sleep(0.3)
                    suyos.discard(r)
                    cambios += 1

    bots = {m["user"]["id"] for m in miembros if m["user"].get("bot")}
    cambios += al_publicar(cfg, rol_id, tiene, nombre, enserio, bots)
    for uid in bots:                     # a los bots no se les reparten zonas
        tiene.pop(uid, None)
    cambios += zonas(cfg, rol_id, tiene, nombre, enserio)
    cambios += antiguedad(cfg, rol_id, miembros, tiene, nombre, enserio, bots)
    cambios += limpiar(cfg, enserio)

    # Un bot recien invitado solo trae su propio rol, y con el muro puesto eso
    # significa que NO VE NI UN CANAL: entra y no puede hacer nada. Paso tres veces
    # (Wick, Xenon, MonitoRSS) antes de automatizarlo.
    rol_bots = rol_id.get("🤖 Bots")
    if rol_bots:
        for m in miembros:
            uid = m["user"]["id"]
            if uid not in bots or rol_bots in m["roles"]:
                continue
            print(f"  + 🤖 Bots  a {m['user']['username']}  (bot recién invitado)")
            if enserio:
                api("PUT", f"/guilds/{guild}/members/{uid}/roles/{rol_bots}")
                time.sleep(0.3)
            cambios += 1

    # que ninguna persona se quede sin rol destacado: si no, acaba en «En linea»,
    # que es el grupo donde caen los bots
    base = (cfg.get("todos_llevan") or {}).get("rol")
    if base and base in rol_id:
        for uid, suyos in tiene.items():
            if uid in bots or rol_id[base] in suyos:
                continue
            print(f"  + {base}  a {nombre.get(uid, uid)}")
            if enserio:
                api("PUT", f"/guilds/{guild}/members/{uid}/roles/{rol_id[base]}")
                time.sleep(0.3)
            suyos.add(rol_id[base])
            cambios += 1

    if cambios or not callado:
        print(f"  {cambios} cambios" if cambios else "  sin novedad")
    return cambios


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=CONFIG)
    p.add_argument("--vigilar", type=int, metavar="SEGUNDOS",
                   help="se queda mirando y reparte segun la gente reacciona")
    p.add_argument("--simulacro", action="store_true", help="dice que haria, sin hacerlo")
    args = p.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    if not args.vigilar:
        print("Poniendo al dia los roles por reaccion...")
        una_pasada(cfg, enserio=not args.simulacro)
        return

    print(f"Vigilando cada {args.vigilar} s. Ctrl+C para parar.\n")
    fallos = 0
    try:
        while True:
            try:
                # Se relee en cada vuelta: si se republica un panel y cambia su id,
                # el vigilante se entera solo en vez de quedarse apuntando al viejo.
                with open(args.config, encoding="utf-8") as f:
                    cfg = json.load(f)
                una_pasada(cfg, enserio=not args.simulacro, callado=True)
                fallos = 0
            except SystemExit as e:
                # Que un corte de internet no mate la vigilancia: se apunta y sigue.
                fallos += 1
                print(f"  (pasada fallida {fallos}: {str(e).splitlines()[0][:80]})")
                if fallos >= 20:
                    print("20 pasadas seguidas fallando. Algo va mal de verdad: paro.")
                    return
            time.sleep(args.vigilar)
    except KeyboardInterrupt:
        print("\nParado.")


if __name__ == "__main__":
    main()
