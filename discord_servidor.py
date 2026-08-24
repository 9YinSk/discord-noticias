#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
discord_servidor.py — arma un servidor de Discord entero desde un plan JSON:
roles con permisos, categorias, canales de texto/voz/anuncios/foro/escenario,
canales privados de staff, solo-lectura, slowmode y etiquetas de foro.

Sin dependencias: solo stdlib (urllib). No usa discord.py.

El token del bot se lee de, en este orden:
  1. variable de entorno  DISCORD_BOT_TOKEN
  2. archivo              herramientas/.discord_token   (una linea, ignorado por git)

Uso:
    python discord_servidor.py invitacion <client_id> [--minimo]
    python discord_servidor.py servidores
    python discord_servidor.py ver <guild_id>
    python discord_servidor.py importar <url-o-codigo> [--a-plan plan.json]
    python discord_servidor.py plantilla > plan.json
    python discord_servidor.py crear <guild_id> --plan plan.json [--fase 1] [--enserio]
    python discord_servidor.py onboarding <guild_id> --plan plan.json [--enserio]

`importar` NO necesita token: el endpoint de plantillas de Discord es publico.
`crear` es simulacro por defecto; hay que pasar --enserio para tocar el servidor.
Nunca borra nada: lo que ya existe con ese nombre, lo salta.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# La consola de Windows es cp1252 y revienta con emoji.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://discord.com/api/v10"
AQUI = os.path.dirname(os.path.abspath(__file__))
ARCHIVO_TOKEN = os.path.join(AQUI, ".discord_token")

TIPOS = {
    "texto": 0,
    "voz": 2,
    "categoria": 4,
    "anuncios": 5,      # requiere Comunidad
    "escenario": 13,    # requiere Comunidad
    "foro": 15,         # requiere Comunidad
    "media": 16,        # requiere Comunidad. Como un foro, pero en galeria
}
NOMBRE_TIPO = {v: k for k, v in TIPOS.items()}
SOLO_COMUNIDAD = {5, 13, 15, 16}

# Bits de permiso que usamos (Discord los maneja como string de un entero)
VER_CANAL = 1 << 10          # 1024
ESCRIBIR = 1 << 11           # 2048
CONECTAR = 1 << 20           # 1048576
HABLAR = 1 << 21             # 2097152
HILOS_PUBLICOS = 1 << 35
HILOS_PRIVADOS = 1 << 36
ESCRIBIR_EN_HILOS = 1 << 38
REACCIONAR = 1 << 6
SILENCIAR_A_OTROS = 1 << 22   # mute members
MOVER_A_OTROS = 1 << 24       # move members
GESTIONAR_CANAL = 1 << 4
PEDIR_LA_PALABRA = 1 << 32
# En un escenario, quien tiene esto es "moderador del escenario": puede subir
# al estrado sin pedir permiso e invitar o bajar a los demas.
MODERA_ESCENARIO = SILENCIAR_A_OTROS | MOVER_A_OTROS | GESTIONAR_CANAL
# Todo lo que se le quita a quien esta silenciado, en cualquier canal
MORDAZA = (ESCRIBIR | HABLAR | REACCIONAR | HILOS_PUBLICOS
           | HILOS_PRIVADOS | ESCRIBIR_EN_HILOS)

# Presets de permisos para roles
PRESETS = {
    "ninguno": 0,
    "admin": 8,  # Administrator: lo incluye todo
    "moderador": (
        (1 << 1)   # kick
        | (1 << 2)   # ban
        | (1 << 13)  # manage messages
        | (1 << 22)  # mute members
        | (1 << 23)  # deafen members
        | (1 << 24)  # move members
        | (1 << 27)  # manage nicknames
        | (1 << 40)  # moderate members (timeout)
        | (1 << 4)   # manage channels
        | VER_CANAL | ESCRIBIR | CONECTAR | HABLAR
    ),
    "staff": (
        (1 << 13)  # manage messages
        | (1 << 33)  # manage events
        | (1 << 24)  # move members
        | (1 << 40)  # moderate members
        | VER_CANAL | ESCRIBIR | CONECTAR | HABLAR
    ),
    # Ordena el CHAT y nada mas: borra, calla un rato y cierra hilos. No toca la voz
    # ni echa a nadie. Es el escalon para quien quiere ayudar sin cargar con todo.
    "mod_chat": (
        (1 << 13)   # manage messages
        | (1 << 40)  # moderate members (timeout)
        | (1 << 34)  # manage threads
        | (1 << 15)  # embed links
        | VER_CANAL | ESCRIBIR | CONECTAR | HABLAR
    ),
    # Ordena la VOZ y nada mas: mueve, silencia y se le oye por encima. No borra
    # mensajes ni sanciona en texto.
    "mod_voz": (
        (1 << 22)   # mute members
        | (1 << 23)  # deafen members
        | (1 << 24)  # move members
        | (1 << 8)   # priority speaker
        | (1 << 4)   # manage channels: hace falta para moderar un escenario
        | VER_CANAL | ESCRIBIR | CONECTAR | HABLAR
    ),
    # Dirige proyectos y castings: cierra hilos y ordena la sala, pero no sanciona.
    "director": (
        (1 << 34)   # manage threads: cerrar y archivar castings
        | (1 << 33)  # manage events
        | (1 << 44)  # create events
        | (1 << 24)  # move members
        | (1 << 22)  # mute members: callar en una grabacion
        | (1 << 8)   # priority speaker: que se le oiga al dirigir
        | (1 << 18)  # usar emojis externos
        | VER_CANAL | ESCRIBIR | CONECTAR | HABLAR
    ),
    # Da clase: manda en el aula y corrige entregas, nada mas.
    "profesor": (
        (1 << 34)   # manage threads: corregir en ejercicios
        | (1 << 33) | (1 << 44)   # eventos
        | (1 << 24) | (1 << 22)   # mover y silenciar en el aula
        | (1 << 8)   # priority speaker
        | (1 << 18)
        | VER_CANAL | ESCRIBIR | CONECTAR | HABLAR
    ),
    # Aporta trabajo, no manda: solo lo que necesita para entregar.
    "colaborador": (
        (1 << 15)   # embed links
        | (1 << 18) | (1 << 37)   # emojis y stickers externos
        | VER_CANAL | ESCRIBIR | CONECTAR | HABLAR
    ),
    # Lleva la radio, el karaoke y los eventos: manda en el estrado, no en la gente.
    "envivo": (
        (1 << 33) | (1 << 44)   # gestionar y crear eventos
        | (1 << 22) | (1 << 24)  # silenciar y mover: ordenar el escenario
        | (1 << 8)   # priority speaker: que se le oiga por encima
        | (1 << 4)   # manage channels: hace falta para moderar un escenario
        | (1 << 18) | (1 << 9)   # emojis externos y video
        | VER_CANAL | ESCRIBIR | CONECTAR | HABLAR
    ),
    # Paga el servidor: detalles cosmeticos.
    "booster": (
        (1 << 26)   # cambiar su apodo
        | (1 << 18) | (1 << 37)
        | (1 << 9)   # priority speaker no; este es 'stream' (video)
        | VER_CANAL | ESCRIBIR | CONECTAR | HABLAR
    ),
}


def token():
    t = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if t:
        return t
    if os.path.exists(ARCHIVO_TOKEN):
        with open(ARCHIVO_TOKEN, encoding="utf-8") as f:
            t = f.read().strip()
        if t:
            return t
    sys.exit(
        "No encuentro el token del bot.\n"
        "  Pon el token en la variable DISCORD_BOT_TOKEN, o guardalo en:\n"
        f"    {ARCHIVO_TOKEN}\n"
        "  (una sola linea, sin comillas y sin la palabra 'Bot')"
    )


def api(metodo, ruta, cuerpo=None, reintentos=5, con_token=True):
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    req = urllib.request.Request(API + ruta, data=datos, method=metodo)
    if con_token:
        req.add_header("Authorization", "Bot " + token())
    req.add_header("User-Agent", "YinX-discord-servidor/1.0")
    if datos:
        req.add_header("Content-Type", "application/json")

    for intento in range(reintentos):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                crudo = r.read().decode("utf-8")
                return json.loads(crudo) if crudo else None
        except urllib.error.HTTPError as e:
            crudo = e.read().decode("utf-8", "replace")
            if e.code == 429:
                try:
                    espera = float(json.loads(crudo).get("retry_after", 1))
                except Exception:
                    espera = 1.0
                time.sleep(espera + 0.25)
                continue
            if e.code in (500, 502, 503, 504) and intento < reintentos - 1:
                time.sleep(1.5 * (intento + 1))
                continue
            raise SystemExit(f"HTTP {e.code} en {metodo} {ruta}\n{crudo}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # Un parpadeo de la conexion no es un error de Discord. Sin esto, un
            # WinError 10054 mataba entero el vigilante de roles a media noche.
            if intento < reintentos - 1:
                time.sleep(2.0 * (intento + 1))
                continue
            raise SystemExit(f"Sin conexion en {metodo} {ruta}\n{e}")
    raise SystemExit(f"Rate limit persistente en {metodo} {ruta}")


def color_a_int(c):
    if c is None:
        return 0
    if isinstance(c, int):
        return c
    return int(str(c).lstrip("#"), 16)


# ---------------------------------------------------------------- comandos

def cmd_inicio(_):
    """Comprueba el token, saca solo el link de invitacion y dice que falta."""
    print("Comprobando el token...\n")
    yo = api("GET", "/users/@me")
    app_id = yo.get("id")
    print(f"  Bot: {yo.get('username')}")
    print(f"  Application ID: {app_id}   (no hace falta que lo busques, sale del token)\n")

    guilds = api("GET", "/users/@me/guilds")
    if guilds:
        print("El bot YA esta dentro de:")
        for g in guilds:
            print(f"   {g['id']}   {g['name']}")
        print("\nListo. Pasale a Claude el numero de la izquierda (el guild id).")
        return

    print("El bot todavia no esta en ningun servidor. Abre este link y autorizalo:\n")
    print(f"https://discord.com/oauth2/authorize"
          f"?client_id={app_id}&scope=bot%20applications.commands&permissions=8")
    print("\nPide Administrador porque tiene que crear roles CON permisos, y Discord no deja")
    print("que un bot otorgue permisos que el mismo no tiene. Al terminar puedes echarlo:")
    print("los canales y los roles se quedan.\n")
    print("Cuando lo autorices, vuelve a correr esto y te dira el guild id.")


def cmd_servidores(_):
    yo = api("GET", "/users/@me")
    print(f"Bot: {yo.get('username')}  (id {yo.get('id')})\n")
    guilds = api("GET", "/users/@me/guilds")
    if not guilds:
        print("El bot no esta en ningun servidor todavia.")
        print(f"Genera el link con:  python discord_servidor.py invitacion {yo.get('id')}")
        return
    for g in guilds:
        print(f"  {g['id']}  {g['name']}")


def cmd_ver(args):
    canales = api("GET", f"/guilds/{args.guild_id}/channels")
    roles = api("GET", f"/guilds/{args.guild_id}/roles")
    # En el orden real del servidor, no alfabetico.
    cats = sorted([c for c in canales if c["type"] == 4],
                  key=lambda c: c.get("position", 0))
    sueltos = [c for c in canales if c["type"] != 4 and not c.get("parent_id")]

    for c in sorted(sueltos, key=lambda x: x.get("position", 0)):
        print(f"  [{NOMBRE_TIPO.get(c['type'], c['type'])}] {c['name']}")
    for cat in cats:
        cid, nombre = cat["id"], cat["name"]
        print(f"\n# {nombre}")
        for c in sorted([x for x in canales if x.get("parent_id") == cid],
                        key=lambda x: x.get("position", 0)):
            print(f"    [{NOMBRE_TIPO.get(c['type'], c['type'])}] {c['name']}")

    print(f"\n{len(canales)} canales, {len(roles)} roles.")
    print("Roles (de arriba a abajo): " +
          ", ".join(r["name"] for r in sorted(roles, key=lambda r: -r["position"])))


def cmd_leer(args):
    """Lee los ultimos mensajes de un canal. El buzon `claude-lee` se lee con esto."""
    canales = api("GET", f"/guilds/{args.guild_id}/channels")
    if args.canal.isdigit():
        objetivo = next((c for c in canales if c["id"] == args.canal), None)
    else:
        aguja = args.canal.lower()
        objetivo = next((c for c in canales if aguja in c["name"].lower()), None)
    if not objetivo:
        sys.exit(f"No encuentro un canal que se parezca a «{args.canal}».")

    print(f"# {objetivo['name']}   (id {objetivo['id']})\n")
    msgs = api("GET", f"/channels/{objetivo['id']}/messages?limit={args.cuantos}") or []
    if not msgs:
        print("  (vacio)")
        return
    for m in reversed(msgs):  # de la API vienen del mas nuevo al mas viejo
        autor = m.get("author", {})
        quien = autor.get("global_name") or autor.get("username", "?")
        if autor.get("bot"):
            quien += " [bot]"
        cuando = m.get("timestamp", "")[:16].replace("T", " ")
        print(f"── {quien}  ·  {cuando}")
        cuerpo = (m.get("content") or "").strip()
        if cuerpo:
            for linea in cuerpo.splitlines():
                print("   " + linea)
        for e in m.get("embeds", []):
            if e.get("title"):
                print(f"   [embed] {e['title']}")
            if e.get("description"):
                for linea in e["description"].splitlines():
                    print("   | " + linea)
        for a in m.get("attachments", []):
            print(f"   [adjunto] {a.get('filename')}  {a.get('url')}")
        print()


def cmd_invitacion(args):
    if args.minimo:
        # Ver canales + escribir + gestionar canales + gestionar roles
        permisos = 1024 | 2048 | 16 | 268435456
        nota = ("Permisos minimos: puede crear canales y roles simples, pero NO podra\n"
                "crear roles con permisos de moderacion. Para el plan completo usa el\n"
                "link de Administrador (sin --minimo).")
    else:
        permisos = 8  # Administrator
        nota = ("Este link pide Administrador porque el bot tiene que crear roles CON\n"
                "permisos (mod, staff). Discord no deja a un bot otorgar permisos que el\n"
                "mismo no tiene. Cuando termines el montaje puedes expulsar el bot: los\n"
                "canales y roles se quedan.")
    print(f"https://discord.com/oauth2/authorize"
          f"?client_id={args.client_id}&scope=bot%20applications.commands&permissions={permisos}")
    print("\n" + nota)


def cmd_importar(args):
    codigo = args.origen.strip().rstrip("/").split("/")[-1]
    req = urllib.request.Request(f"{API}/guilds/templates/{codigo}")
    req.add_header("User-Agent", "YinX-discord-servidor/1.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            t = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")
        if e.code == 404:
            sys.exit(f"No existe la plantilla '{codigo}'. "
                     "Pasa el link completo (discord.new/CODIGO) o solo el codigo.")
        sys.exit(f"HTTP {e.code}: {cuerpo}")

    g = t.get("serialized_source_guild", {})
    canales = g.get("channels", [])
    roles = g.get("roles", [])

    print(f"Plantilla: {t.get('name')}")
    if t.get("description"):
        print(f"  {t['description']}")
    print(f"  Usos: {t.get('usage_count', '?')}   Servidor origen: {g.get('name', '?')}")
    print(f"  {len(canales)} canales, {len(roles)} roles\n")

    cats = {c["id"]: c for c in canales if c.get("type") == 4}
    orden_cat = sorted(cats.values(), key=lambda c: c.get("position", 0))

    def hijos_de(cid):
        return sorted([c for c in canales if c.get("parent_id") == cid],
                      key=lambda c: c.get("position", 0))

    for c in sorted([x for x in canales if x.get("type") != 4 and x.get("parent_id") is None],
                    key=lambda x: x.get("position", 0)):
        print(f"  [{NOMBRE_TIPO.get(c.get('type'), c.get('type'))}] {c.get('name')}")

    for cat in orden_cat:
        print(f"\n# {cat.get('name')}")
        for c in hijos_de(cat["id"]):
            linea = f"    [{NOMBRE_TIPO.get(c.get('type'), c.get('type'))}] {c.get('name')}"
            if c.get("topic"):
                linea += f"   - {c['topic'][:70]}"
            print(linea)

    if roles:
        print("\nRoles: " + ", ".join(r.get("name", "?") for r in roles))

    if args.a_plan:
        plan = {"_origen": f"plantilla {codigo} - {t.get('name')}", "categorias": []}
        for cat in orden_cat:
            entrada = {"nombre": cat.get("name"), "canales": []}
            for c in hijos_de(cat["id"]):
                ch = {"nombre": c.get("name"),
                      "tipo": NOMBRE_TIPO.get(c.get("type"), "texto")}
                if c.get("topic"):
                    ch["tema"] = c["topic"]
                entrada["canales"].append(ch)
            plan["categorias"].append(entrada)
        with open(args.a_plan, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
        print(f"\nGuardado como plan editable en: {args.a_plan}")


def cmd_plantilla(_):
    ruta = os.path.join(AQUI, "discord_plan.json")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            print(f.read())
    else:
        print(json.dumps({"roles": [], "categorias": []}, ensure_ascii=False, indent=2))


def etiquetas_de(lista):
    """Etiquetas de un foro. Un dict con "solo_staff" hace que solo la pueda poner
    quien gestiona hilos: sirve para distinguir lo oficial de lo que no lo es."""
    salida = []
    for t in lista[:20]:
        if isinstance(t, dict):
            salida.append({"name": t["nombre"], "moderated": bool(t.get("solo_staff")),
                           "emoji_name": t.get("emoji"), "emoji_id": None})
        else:
            salida.append({"name": t})
    return salida


def overwrites_de(ch, everyone_id, rol_id, silenciado=None, muro=None):
    """Traduce 'privado' / 'solo_lectura' / 'abierto' del plan a permission_overwrites.

    `muro` es el bloque "muro" del plan: cierra TODOS los canales a quien no
    tenga el rol de verificado, menos los que se declaran "abierto": true.
    """
    ov = []
    es_voz = TIPOS.get(ch.get("tipo", "texto")) in (2, 13)
    solo_ver = "solo_lectura" in ch   # entrar no es escribir: aqui no se reparte ESCRIBIR

    # El rol de silenciado pierde la voz en TODOS los canales, sin excepcion.
    if silenciado and silenciado in rol_id:
        ov.append({"id": rol_id[silenciado], "type": 0,
                   "deny": str(MORDAZA), "allow": "0"})

    privado = ch.get("privado")
    # El muro: lo que no es "abierto" ni ya privado se cierra al rol de verificado.
    if muro and not privado and not ch.get("abierto"):
        privado = [muro["rol"]] + list(muro.get("staff_ve") or [])
        solo_ver = True   # el muro solo abre la puerta; escribir lo decide el canal

    if privado:
        deny = VER_CANAL | (CONECTAR if es_voz else 0)
        ov.append({"id": everyone_id, "type": 0, "deny": str(deny), "allow": "0"})
        for nombre in privado:
            rid = rol_id.get(nombre)
            if not rid:
                print(f"        ojo: el rol '{nombre}' no existe, no puedo darle acceso")
                continue
            # Sin ESCRIBIR explicito cuando el canal es de solo lectura: un allow
            # de rol le gana al deny de @everyone y abriria el canal a todos.
            allow = VER_CANAL | (CONECTAR if es_voz else 0)
            if not solo_ver:
                allow |= (HABLAR if es_voz else ESCRIBIR)
            ov.append({"id": rid, "type": 0, "allow": str(allow), "deny": "0"})

    # Los 3 canales del recorrido de entrada: se ven aunque su categoria este cerrada.
    if ch.get("abierto"):
        ov.append({"id": everyone_id, "type": 0,
                   "allow": str(VER_CANAL | (CONECTAR if es_voz else 0)), "deny": "0"})

    # Solo los 'oradores' hablan; el resto escucha.
    #  · en un ESCENARIO, ademas puede pedir la palabra y subir si le invitan
    #  · en un canal de VOZ es lo mismo pero sin la maquinaria del escenario: es
    #    lo que hace falta cuando el que emite es un bot, porque un bot de musica
    #    entra como publico y un escenario apagado no deja sonar a nadie
    if ch.get("oradores"):
        es_escenario = TIPOS.get(ch.get("tipo", "texto")) == 13
        ov.append({"id": everyone_id, "type": 0,
                   "allow": str(CONECTAR | (PEDIR_LA_PALABRA if es_escenario else 0)),
                   "deny": str(HABLAR)})
        for nombre in ch["oradores"]:
            rid = rol_id.get(nombre)
            if not rid:
                print(f"        ojo: '{nombre}' no existe, no puede ser orador")
                continue
            # VER incluido: un bot de musica que no VE el canal no entra, y aqui
            # solo se salvaba de rebote por tener el rol 🤖 Bots.
            ov.append({"id": rid, "type": 0,
                       "allow": str(VER_CANAL | CONECTAR | HABLAR | MODERA_ESCENARIO),
                       "deny": "0"})

    # Canales donde los bots no pintan nada: que no los ensucien con respuestas.
    if ch.get("sin_bots") and "🤖 Bots" in rol_id:
        ov.append({"id": rol_id["🤖 Bots"], "type": 0,
                   "deny": str(ESCRIBIR | HILOS_PUBLICOS | ESCRIBIR_EN_HILOS),
                   "allow": "0"})
        # ...menos el bot de mantenimiento, que es quien escribe las guias.
        if "YinxClaude" in rol_id:
            ov.append({"id": rol_id["YinxClaude"], "type": 0,
                       "allow": str(ESCRIBIR | HILOS_PUBLICOS), "deny": "0"})

    # Foro donde cada uno pone lo suyo y NADIE comenta debajo: abrir hilo si,
    # responder en el hilo de otro no. Son dos permisos distintos y por eso se puede.
    if ch.get("sin_comentarios"):
        ov.append({"id": everyone_id, "type": 0,
                   "deny": str(ESCRIBIR_EN_HILOS), "allow": "0"})
        pueden = ch["sin_comentarios"]
        for nombre in (pueden if isinstance(pueden, list) else []):
            rid = rol_id.get(nombre)
            if rid:
                ov.append({"id": rid, "type": 0,
                           "allow": str(ESCRIBIR_EN_HILOS), "deny": "0"})

    if "solo_lectura" in ch:
        deny = ESCRIBIR | HILOS_PUBLICOS | HILOS_PRIVADOS
        ov.append({"id": everyone_id, "type": 0, "deny": str(deny), "allow": "0"})
        for nombre in ch.get("solo_lectura") or []:
            rid = rol_id.get(nombre)
            if rid:
                ov.append({"id": rid, "type": 0, "allow": str(ESCRIBIR), "deny": "0"})

    # Discord solo admite UNA entrada por rol: si quedan varias (p.ej. un canal
    # privado que ademas es de solo lectura), la ultima pisa a las anteriores.
    # Hay que sumarlas en una sola.
    fundidos = {}
    for o in ov:
        f = fundidos.setdefault(o["id"], {"id": o["id"], "type": o["type"],
                                          "allow": 0, "deny": 0})
        f["allow"] |= int(o.get("allow", 0))
        f["deny"] |= int(o.get("deny", 0))
    for f in fundidos.values():
        f["deny"] &= ~f["allow"]        # permitir gana sobre denegar
        f["allow"], f["deny"] = str(f["allow"]), str(f["deny"])
    return list(fundidos.values())


def preparar_muro(plan):
    """El rele de entrada: cada canal del recorrido se abre con la llave del anterior.

    En el plan, un canal del recorrido lleva `"paso": "🚪 Paso 1"`. Si el rele esta
    activo, ese canal deja de ser publico y pasa a pedir esa llave. Si se apaga
    (`"rele": {"activo": false}`), los tres canales vuelven a verse de golpe: es el
    interruptor para desarmarlo sin tocar nada mas.
    """
    muro = plan.get("muro")
    if not muro:
        return
    activo = (muro.get("rele") or {}).get("activo")
    for cat in plan.get("categorias", []):
        for ch in cat.get("canales", []):
            paso = ch.get("paso")
            if not paso:
                continue
            if activo:
                ch.pop("abierto", None)
                ch["privado"] = [paso, muro["rol"]] + list(muro.get("staff_ve") or [])
            else:
                ch["abierto"] = True
                ch.pop("privado", None)


def cmd_crear(args):
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    preparar_muro(plan)

    guild = api("GET", f"/guilds/{args.guild_id}")
    es_comunidad = "COMMUNITY" in (guild.get("features") or [])
    everyone_id = args.guild_id  # el rol @everyone tiene el id del servidor

    print(f"Servidor: {guild['name']}")
    print(f"Comunidad activada: {'si' if es_comunidad else 'NO'}")
    if args.fase:
        print(f"Filtro: solo fase {args.fase} (y lo que no declara fase)")
    print(">>> " + ("CREANDO DE VERDAD" if args.enserio
                    else "SIMULACRO. Nada se crea. Agrega --enserio para aplicarlo") + "\n")

    # ---------------------------------------------------------------- roles
    roles_ya = api("GET", f"/guilds/{args.guild_id}/roles")
    rol_id = {r["name"]: r["id"] for r in roles_ya}
    creados_rol = 0

    plan_roles = plan.get("roles", [])
    if plan_roles:
        print("=== ROLES ===")
        actuales = {r["name"]: r for r in roles_ya}
        for r in plan_roles:
            nombre = r["nombre"]

            # 'antes' tambien vale para roles: renombra sin perder a quien lo tiene.
            viejo = r.get("antes")
            if nombre not in rol_id and viejo and viejo in rol_id:
                print(f"  {viejo}  ->  {nombre}   (renombrar)")
                if args.enserio:
                    api("PATCH", f"/guilds/{args.guild_id}/roles/{rol_id[viejo]}",
                        {"name": nombre})
                    time.sleep(0.4)
                rol_id[nombre] = rol_id.pop(viejo)   # sacar el nombre viejo del indice,
                actuales[nombre] = actuales.pop(viejo, {})  # o un rol nuevo con ese nombre
                continue                                    # se confundiria con este

            if nombre in rol_id:
                # Existe: comprobar si el plan cambio sus permisos o su color.
                viejo = actuales.get(nombre, {})
                preset = r.get("permisos", "ninguno")
                bits = PRESETS.get(preset, 0) if isinstance(preset, str) else int(preset)
                quiero_color = color_a_int(r.get("color"))
                cambia = (str(viejo.get("permissions")) != str(bits)
                          or viejo.get("color") != quiero_color
                          or viejo.get("hoist") != bool(r.get("destacado", False)))
                if not cambia:
                    print(f"  {nombre}   (ya existe, sin cambios)")
                    continue
                print(f"  {nombre}   ACTUALIZAR -> permisos {preset}")
                if args.enserio:
                    api("PATCH", f"/guilds/{args.guild_id}/roles/{rol_id[nombre]}", {
                        "permissions": str(bits),
                        "color": quiero_color,
                        "hoist": bool(r.get("destacado", False)),
                        "mentionable": bool(r.get("mencionable", False)),
                    })
                    time.sleep(0.4)
                continue
            preset = r.get("permisos", "ninguno")
            bits = PRESETS.get(preset, 0) if isinstance(preset, str) else int(preset)
            print(f"  {nombre}   color {r.get('color', '-')}  permisos {preset}")
            if args.enserio:
                nuevo = api("POST", f"/guilds/{args.guild_id}/roles", {
                    "name": nombre,
                    "color": color_a_int(r.get("color")),
                    "hoist": bool(r.get("destacado", False)),
                    "mentionable": bool(r.get("mencionable", False)),
                    "permissions": str(bits),
                })
                rol_id[nombre] = nuevo["id"]
                creados_rol += 1
                time.sleep(0.4)

        # Reordenar: el primero del plan queda arriba del todo.
        if args.enserio and creados_rol:
            posiciones = []
            total = len(plan_roles)
            for i, r in enumerate(plan_roles):
                rid = rol_id.get(r["nombre"])
                if rid:
                    posiciones.append({"id": rid, "position": total - i})
            try:
                api("PATCH", f"/guilds/{args.guild_id}/roles", posiciones)
                print("  Orden de roles aplicado.")
            except SystemExit as e:
                print(f"  No pude reordenar los roles ({e}).")
                print("  Normal si el rol del bot no esta lo bastante arriba: "
                      "arrastralo a mano en Ajustes > Roles.")
        print()

    # -------------------------------------------------------------- canales
    existentes = api("GET", f"/guilds/{args.guild_id}/channels")
    cat_id = {c["name"]: c["id"] for c in existentes if c["type"] == 4}
    ya = {(c.get("parent_id"), c["name"].lower()) for c in existentes if c["type"] != 4}

    silenciado = plan.get("silenciar_rol")
    muro = plan.get("muro")
    if silenciado:
        if silenciado in rol_id:
            print(f"Rol de silenciado: {silenciado} — se le quita voz en cada canal creado.\n")
        else:
            print(f"Rol de silenciado '{silenciado}' no existe todavia; se ignora.\n")
            silenciado = None

    por_nombre = {c["name"].lower(): c for c in existentes if c["type"] != 4}
    creados = saltados = degradados = renombrados = 0
    print("=== CANALES ===")

    # 'orden' manda sobre la posicion en el archivo, para no mover bloques enteros.
    cats_plan = sorted(plan.get("categorias", []),
                       key=lambda c: c.get("orden", 999))

    for cat in cats_plan:
        canales = [c for c in cat.get("canales", [])
                   if not args.fase or c.get("fase", 1) <= args.fase]
        if args.fase and cat.get("fase", 1) > args.fase:
            continue
        # Una categoria sin canales puede ser intencionada (p.ej. donde un bot
        # crea los suyos), asi que solo se salta si tampoco hay que crearla.
        if not canales and cat["nombre"] in cat_id:
            continue

        nombre_cat = cat["nombre"]
        padre = cat_id.get(nombre_cat)

        # 'antes' permite cambiar de nombre sin perder los mensajes de dentro.
        if not padre and cat.get("antes") in cat_id:
            viejo = cat["antes"]
            padre = cat_id[viejo]
            print(f"\n# {viejo}  ->  {nombre_cat}   (renombrar)")
            if args.enserio:
                api("PATCH", f"/channels/{padre}", {"name": nombre_cat})
                time.sleep(0.4)
            cat_id[nombre_cat] = padre

        if padre and not cat.get("antes"):
            print(f"\n# {nombre_cat}  (la categoria ya existe)")
        elif padre:
            pass
        else:
            print(f"\n# {nombre_cat}  <- crear")
            if args.enserio:
                cuerpo = {"name": nombre_cat, "type": 4}
                ov = overwrites_de(cat, everyone_id, rol_id, silenciado, muro)
                if ov:
                    cuerpo["permission_overwrites"] = ov
                padre = api("POST", f"/guilds/{args.guild_id}/channels", cuerpo)["id"]
                cat_id[nombre_cat] = padre
                creados += 1
                time.sleep(0.4)

        for ch in canales:
            nombre = ch["nombre"]
            tipo = TIPOS.get(ch.get("tipo", "texto"))
            if tipo is None:
                print(f"    ?? tipo desconocido '{ch.get('tipo')}' en '{nombre}', lo salto")
                continue

            etiqueta = ""
            if tipo in SOLO_COMUNIDAD and not es_comunidad:
                pedido = ch.get("tipo")
                tipo = 2 if tipo == 13 else 0
                degradados += 1
                etiqueta = f"   (pedido: {pedido}, el servidor no es Comunidad)"
            if ch.get("privado"):
                etiqueta += "   [privado: " + ", ".join(ch["privado"]) + "]"
            if "solo_lectura" in ch:
                etiqueta += "   [solo lectura]"

            # Renombrar en vez de recrear: asi no se pierden los mensajes de dentro.
            viejo = ch.get("antes")
            if viejo and (padre, nombre.lower()) not in ya and viejo.lower() in por_nombre:
                c = por_nombre[viejo.lower()]
                print(f"    [{NOMBRE_TIPO[tipo]}] {viejo}  ->  {nombre}   (renombrar){etiqueta}")
                if args.enserio:
                    cambio = {"name": nombre}
                    if padre and c.get("parent_id") != padre:
                        cambio["parent_id"] = padre
                    api("PATCH", f"/channels/{c['id']}", cambio)
                    ya.add((padre, nombre.lower()))
                    renombrados += 1
                    time.sleep(0.4)
                continue

            print(f"    [{NOMBRE_TIPO[tipo]}] {nombre}{etiqueta}")

            if (padre, nombre.lower()) in ya:
                print("        ya existe, salto")
                saltados += 1
                continue
            if not args.enserio:
                continue

            cuerpo = {"name": nombre, "type": tipo}
            if padre:
                cuerpo["parent_id"] = padre
            # Un canal de VOZ rechaza el topic al crearlo — y miente diciendo que
            # "contiene una palabra no permitida", con el texto que sea. Se le pone
            # despues con `permisos`, que hace PATCH y ese si lo acepta.
            if ch.get("tema") and tipo in (0, 5, 13, 15, 16):
                cuerpo["topic"] = ch["tema"]
            if ch.get("lento"):
                cuerpo["rate_limit_per_user"] = int(ch["lento"])
            if tipo in (15, 16) and ch.get("etiquetas"):
                cuerpo["available_tags"] = etiquetas_de(ch["etiquetas"])
            # 1 = lista, 2 = galeria. Los de media ya salen en galeria de fabrica.
            if tipo == 15 and ch.get("vista") == "galeria":
                cuerpo["default_forum_layout"] = 2
            ov = overwrites_de(ch, everyone_id, rol_id, silenciado, muro)
            if ov:
                cuerpo["permission_overwrites"] = ov

            api("POST", f"/guilds/{args.guild_id}/channels", cuerpo)
            creados += 1
            time.sleep(0.4)

    # Dejar categorias Y canales en el mismo orden que el plan.
    if args.enserio:
        ahora = api("GET", f"/guilds/{args.guild_id}/channels")
        cat_ahora = {c["name"]: c["id"] for c in ahora if c["type"] == 4}
        ch_ahora = {c["name"]: c for c in ahora if c["type"] != 4}

        posiciones = [{"id": cat_ahora[c["nombre"]], "position": i}
                      for i, c in enumerate(cats_plan) if c["nombre"] in cat_ahora]
        # Discord ordena texto y voz en dos listas separadas dentro de la categoria,
        # asi que se numeran por separado o se pisan entre ellas.
        for cat in cats_plan:
            n_txt = n_voz = 0
            for ch in cat.get("canales", []):
                real = ch_ahora.get(ch["nombre"])
                if not real:
                    continue
                if real["type"] in (2, 13):
                    posiciones.append({"id": real["id"], "position": n_voz}); n_voz += 1
                else:
                    posiciones.append({"id": real["id"], "position": n_txt}); n_txt += 1
        if posiciones:
            try:
                api("PATCH", f"/guilds/{args.guild_id}/channels", posiciones)
                print(f"\nOrdenados: {len(cats_plan)} categorias y "
                      f"{len(posiciones) - len(cats_plan)} canales.")
            except SystemExit as e:
                print(f"\nNo pude reordenar: {str(e)[:120]}")

    print(f"\nRoles creados: {creados_rol} | Canales creados: {creados} | "
          f"Renombrados: {renombrados} | Ya existian: {saltados} | "
          f"Degradados por falta de Comunidad: {degradados}")
    if not args.enserio:
        print("Repite con --enserio para aplicarlo.")


def cmd_onboarding(args):
    """Aplica el cuestionario de entrada (Community Onboarding) desde el plan."""
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    ob = plan.get("onboarding")
    if not ob:
        sys.exit("El plan no tiene bloque 'onboarding'.")

    guild = api("GET", f"/guilds/{args.guild_id}")
    if "COMMUNITY" not in (guild.get("features") or []):
        sys.exit("Este servidor no tiene Comunidad activada. El onboarding no existe sin ella.\n"
                 "Actívala en Ajustes del servidor > Habilitar Comunidad, y vuelve a correr esto.")

    canales = api("GET", f"/guilds/{args.guild_id}/channels")
    roles = api("GET", f"/guilds/{args.guild_id}/roles")
    canal_id = {c["name"]: c["id"] for c in canales}
    rol_id = {r["name"]: r["id"] for r in roles}

    faltan = []

    def ids_canales(nombres):
        out = []
        for n in nombres or []:
            if n in canal_id:
                out.append(canal_id[n])
            else:
                faltan.append(f"canal '{n}'")
        return out

    def ids_roles(nombres):
        out = []
        for n in nombres or []:
            if n in rol_id:
                out.append(rol_id[n])
            else:
                faltan.append(f"rol '{n}'")
        return out

    prompts = []
    for i, preg in enumerate(ob.get("preguntas", [])):
        print(f"\n{i + 1}. {preg['titulo']}"
              f"   ({'una sola respuesta' if preg.get('una_sola') else 'varias'}"
              f"{', obligatoria' if preg.get('obligatoria') else ''})")
        opciones = []
        for j, op in enumerate(preg.get("opciones", [])):
            cs = ids_canales(op.get("canales"))
            rs = ids_roles(op.get("roles"))
            marca = []
            if op.get("roles"):
                marca.append("roles: " + ", ".join(op["roles"]))
            if op.get("canales"):
                marca.append(f"abre {len(op['canales'])} canales")
            print(f"     {op.get('emoji', '')} {op['titulo']}"
                  + (f"   [{' | '.join(marca)}]" if marca else ""))
            entrada = {
                "id": str(i * 100 + j + 1),
                "title": op["titulo"],
                "description": op.get("descripcion") or None,
                "channel_ids": cs,
                "role_ids": rs,
            }
            if op.get("emoji"):
                entrada["emoji"] = {"name": op["emoji"], "id": None, "animated": False}
            opciones.append(entrada)

        # "donde": "entrada" (el cuestionario), "siempre" (tambien en Canales y roles)
        # o "canales_y_roles" (solo ahi: es el reparto de roles NATIVO, sin bots).
        donde = preg.get("donde", "entrada")
        en_entrada = donde in ("entrada", "siempre")
        prompts.append({
            "id": str(i + 1),
            "type": 0,
            "title": preg["titulo"],
            "options": opciones,
            "single_select": bool(preg.get("una_sola")),
            "required": bool(preg.get("obligatoria")) and en_entrada,
            "in_onboarding": en_entrada,
            "in_channel_settings": donde in ("siempre", "canales_y_roles"),
        })
        if donde != "entrada":
            print(f"     ↳ sale en «Canales y roles»"
                  + (" (y en el cuestionario)" if en_entrada else " — sin bots"))

    por_defecto = ids_canales(ob.get("canales_por_defecto"))
    print(f"\nCanales que ve todo el mundo pase lo que pase: {len(por_defecto)}")

    if faltan:
        print("\nOJO, esto no existe todavia en el servidor (crea los canales primero "
              "con el subcomando 'crear'):")
        for x in sorted(set(faltan)):
            print(f"   - {x}")
        if not args.enserio:
            print("\nSimulacro: no se aplico nada.")
            return
        print("\nSigo igual, pero esas opciones quedaran sin enlazar.")

    if not args.enserio:
        print("\n>>> SIMULACRO. Agrega --enserio para aplicarlo.")
        return

    cuerpo = {
        "prompts": prompts,
        "default_channel_ids": por_defecto,
        "enabled": True,
        "mode": 1,  # ONBOARDING_ADVANCED
    }
    try:
        api("PUT", f"/guilds/{args.guild_id}/onboarding", cuerpo)
        print("\nOnboarding aplicado y activado (modo avanzado).")
    except SystemExit as e:
        print(f"\nDiscord rechazo el onboarding:\n{e}")
        print("\nLo mas comun es que falten canales publicos por defecto, o que el bot no "
              "sea Administrador.\nSi insiste, las 4 preguntas se pueden copiar a mano en "
              "Ajustes del servidor > Onboarding.")


def cmd_limpiar(args):
    """Borra los canales que NO estan en el plan. Simulacro por defecto."""
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    del_plan = {c["nombre"] for cat in plan["categorias"] for c in cat["canales"]}
    del_plan |= {cat["nombre"] for cat in plan["categorias"]}

    canales = api("GET", f"/guilds/{args.guild_id}/channels")
    sobran = [c for c in canales if c["name"] not in del_plan]
    if not sobran:
        print("No sobra nada: todos los canales estan en el plan.")
        return

    cats = {c["id"]: c["name"] for c in canales if c["type"] == 4}
    print(f"{len(sobran)} canales fuera del plan:\n")
    for c in sorted(sobran, key=lambda x: (x["type"] != 4, x.get("position", 0))):
        donde = f"  (dentro de {cats[c['parent_id']]})" if c.get("parent_id") else ""
        print(f"  [{NOMBRE_TIPO.get(c['type'], c['type'])}] {c['name']}{donde}")

    if not args.enserio:
        print("\n>>> SIMULACRO. Nada se borro. Agrega --enserio para borrarlos DE VERDAD.")
        print("    Los mensajes que tengan dentro se pierden y no hay deshacer.")
        return

    # Los hijos primero: borrar una categoria no borra lo que hay dentro.
    hechos = 0
    for c in sorted(sobran, key=lambda x: x["type"] == 4):
        try:
            api("DELETE", f"/channels/{c['id']}")
            print(f"  borrado: {c['name']}")
            hechos += 1
        except SystemExit as e:
            # Discord protege los canales que Comunidad tiene asignados.
            motivo = "lo usa Comunidad" if "50074" in str(e) else str(e).split("\n")[0]
            print(f"  NO se pudo borrar '{c['name']}': {motivo}")
            print("     (corre antes 'ajustes' para apuntar Comunidad a los canales nuevos)")
        time.sleep(0.4)
    print(f"\n{hechos} de {len(sobran)} canales borrados.")

    if args.roles:
        limpiar_roles(args)


def limpiar_roles(args):
    """Borra roles fuera del plan. Nunca toca @everyone ni roles de bots/boost."""
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    del_plan = {r["nombre"] for r in plan.get("roles", [])}

    roles = api("GET", f"/guilds/{args.guild_id}/roles")
    sobran = [r for r in roles
              if r["name"] not in del_plan
              and r["name"] != "@everyone"
              and not r.get("managed")]        # managed = de un bot o de Nitro
    if not sobran:
        print("\nNo sobra ningun rol.")
        return

    print(f"\n{len(sobran)} roles fuera del plan:")
    for r in sobran:
        print(f"  {r['name']}")
    for r in sobran:
        api("DELETE", f"/guilds/{args.guild_id}/roles/{r['id']}")
        print(f"  borrado: {r['name']}")
        time.sleep(0.4)


def cmd_ajustes(args):
    """Deja los canales de sistema del servidor apuntando a los del plan."""
    canales = api("GET", f"/guilds/{args.guild_id}/channels")
    por_nombre = {c["name"]: c for c in canales}

    # que ajuste del servidor -> que canal del plan, y por que
    quiero = [
        ("rules_channel_id",           "📜・reglas",       "canal de reglas"),
        ("system_channel_id",          "👋・bienvenidas",  "avisos de Discord al entrar alguien"),
        ("public_updates_channel_id",  "🧾・log-servidor", "avisos de Discord al staff"),
        ("safety_alerts_channel_id",   "⚖️・moderacion",   "alertas de seguridad"),
        ("afk_channel_id",             "😴 AFK",           "canal AFK"),
    ]

    # En servidores de Comunidad, rules_channel_id y public_updates_channel_id se
    # ignoran EN SILENCIO si no mandas tambien 'features' en la misma peticion.
    guild = api("GET", f"/guilds/{args.guild_id}")
    cuerpo = {"afk_timeout": 300, "premium_progress_bar_enabled": True}
    if "COMMUNITY" in (guild.get("features") or []):
        cuerpo["features"] = guild["features"]
    for campo, nombre, para_que in quiero:
        c = por_nombre.get(nombre)
        if c:
            cuerpo[campo] = c["id"]
            print(f"  {para_que}: {nombre}")
        else:
            print(f"  {para_que}: '{nombre}' no existe, lo dejo como esta")
    print("  barra de progreso de boosts: encendida")
    print("  AFK a los 5 minutos")

    if not args.enserio:
        print("\n>>> SIMULACRO. Agrega --enserio para aplicarlo.")
        return
    api("PATCH", f"/guilds/{args.guild_id}", cuerpo)
    print("\nAjustes aplicados.")


def cmd_publicar(args):
    """Escribe los mensajes iniciales de cada canal (reglas, guia, checklist...)."""
    with open(args.contenido, encoding="utf-8") as f:
        cont = json.load(f)

    canales = api("GET", f"/guilds/{args.guild_id}/channels")
    por_nombre = {c["name"]: c for c in canales}
    puestos = saltados = 0

    for nombre, bloque in cont.get("canales", {}).items():
        c = por_nombre.get(nombre)
        if not c:
            print(f"  '{nombre}' no existe, lo salto")
            continue

        es_foro = c["type"] == 15
        # No duplicar: si el canal ya tiene algo escrito, no se toca.
        if not args.forzar:
            if es_foro:
                hilos = api("GET", f"/guilds/{args.guild_id}/threads/active") or {}
                if any(t.get("parent_id") == c["id"] for t in hilos.get("threads", [])):
                    print(f"  {nombre}: ya tiene hilos, salto")
                    saltados += 1
                    continue
            else:
                previos = api("GET", f"/channels/{c['id']}/messages?limit=1")
                if previos:
                    print(f"  {nombre}: ya tiene mensajes, salto")
                    saltados += 1
                    continue

        cuantos = len(bloque.get("embeds", []))
        print(f"  {nombre}: {'hilo' if es_foro else str(cuantos) + ' bloque(s)'}")
        if not args.enserio:
            continue

        if es_foro:
            api("POST", f"/channels/{c['id']}/threads", {
                "name": bloque.get("titulo", "Empieza aquí"),
                "message": {"content": bloque.get("texto", ""),
                            "embeds": bloque.get("embeds", [])},
            })
        else:
            # Un mensaje por embed: se leen mejor y se pueden editar por separado.
            for i, em in enumerate(bloque.get("embeds", [])):
                cuerpo = {"embeds": [em]}
                if i == 0 and bloque.get("texto"):
                    cuerpo["content"] = bloque["texto"]
                api("POST", f"/channels/{c['id']}/messages", cuerpo)
                time.sleep(0.5)
            if not bloque.get("embeds") and bloque.get("texto"):
                api("POST", f"/channels/{c['id']}/messages", {"content": bloque["texto"]})
        puestos += 1
        time.sleep(0.5)

    print(f"\nCanales escritos: {puestos} | Saltados por tener contenido: {saltados}")
    if not args.enserio:
        print("Repite con --enserio para publicarlo.")


def cmd_jerarquia(args):
    """Ordena los roles de arriba a abajo, metiendo los de los bots donde toca.

    Discord permite que muchos roles compartan la misma posicion, y entonces la
    jerarquia queda indefinida: los bots no pueden repartir roles y no avisan.
    """
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    roles = api("GET", f"/guilds/{args.guild_id}/roles")
    por_nombre = {r["name"]: r for r in roles}
    yo = api("GET", "/users/@me")["id"]

    mi_rol = next((r for r in roles if r.get("tags", {}).get("bot_id") == yo), None)
    de_bots = [r for r in roles
               if r.get("managed") and (not mi_rol or r["id"] != mi_rol["id"])]

    # De arriba a abajo: yo, staff alto, los bots, y el resto del plan.
    orden = []
    if mi_rol:
        orden.append(mi_rol)
    tope = args.bots_bajo
    for r in plan.get("roles", []):
        real = por_nombre.get(r["nombre"])
        if not real:
            continue
        orden.append(real)
        if r["nombre"] == tope:
            orden.extend(de_bots)          # los bots, justo debajo de ese rol
    for r in de_bots:                      # por si el rol tope no existe
        if r not in orden:
            orden.append(r)

    print("Orden que voy a aplicar (de arriba a abajo):\n")
    for i, r in enumerate(orden):
        marca = "  <- BOT" if r.get("managed") else ""
        print(f"  {len(orden) - i:>3}  {r['name']}{marca}")

    if not args.enserio:
        print("\n>>> SIMULACRO. Agrega --enserio para aplicarlo.")
        return

    # Mi propio rol NO se toca: un bot no puede mover el suyo, y si va en la lista
    # Discord rechaza la peticion entera con 'Missing Permissions'.
    # Y todo lo demas tiene que caber POR DEBAJO de el, o pasa lo mismo.
    otros = [r for r in orden if not (mi_rol and r["id"] == mi_rol["id"])]
    techo = (mi_rol["position"] - 1) if mi_rol else len(otros)
    if techo < len(otros):
        print(f"\nOjo: {len(otros)} roles no caben debajo del mio (posicion "
              f"{mi_rol['position']}). Sube el rol del bot mas arriba en Ajustes > Roles.")
    cuerpo = [{"id": r["id"], "position": max(1, techo - i)}
              for i, r in enumerate(otros)]
    try:
        api("PATCH", f"/guilds/{args.guild_id}/roles", cuerpo)
    except SystemExit as e:
        print(f"\nDiscord lo rechazo: {str(e)[:150]}")
        return

    # Comprobar que cuajo de verdad: Discord a veces acepta y no mueve nada.
    ahora = api("GET", f"/guilds/{args.guild_id}/roles")
    empatados = {}
    for r in ahora:
        empatados.setdefault(r["position"], []).append(r["name"])
    peor = max((len(v) for k, v in empatados.items() if k > 0), default=0)
    if peor > 1:
        print(f"\nNO cuajo: siguen {peor} roles compartiendo posicion.")
        print("Causa: un bot no puede mover roles por encima del suyo, y el suyo esta")
        print("empatado con los demas. Arrastra el rol del bot al TOPE de la lista en")
        print("Ajustes del servidor > Roles, y vuelve a correr esto.")
    else:
        print("\nJerarquia aplicada: cada rol en su propia posicion.")


def cmd_automod(args):
    """Crea las reglas de AutoMod. Es nativo: bloquea ANTES de publicar el mensaje."""
    canales = {c["name"]: c["id"] for c in api("GET", f"/guilds/{args.guild_id}/channels")}
    roles = {r["name"]: r["id"] for r in api("GET", f"/guilds/{args.guild_id}/roles")}
    ya = {r["name"] for r in api("GET", f"/guilds/{args.guild_id}/auto-moderation/rules")}

    alerta = next((canales[n] for n in ("ıı・🧾・log-mod", "🧾・log-mod") if n in canales), None)
    exentos = [roles[n] for n in ("👑 Fundador", "⚙️ Administrador", "🛡️ Moderador")
               if n in roles]

    def acciones(texto):
        a = [{"type": 1, "metadata": {"custom_message": texto}}]
        if alerta:
            a.append({"type": 2, "metadata": {"channel_id": alerta}})
        return a

    reglas = [
        {
            "name": "Anti-spam",
            "event_type": 1,
            "trigger_type": 3,          # SPAM
            "trigger_metadata": {},
            "actions": acciones("Eso parece spam. Si te has equivocado, escríbelo distinto."),
        },
        {
            "name": "Insultos y contenido sexual",
            "event_type": 1,
            "trigger_type": 4,          # KEYWORD_PRESET
            "trigger_metadata": {"presets": [1, 2, 3], "allow_list": []},
            "actions": acciones("Aquí no. Lee las reglas en el canal de reglas."),
        },
        {
            "name": "Invitaciones a otros servidores",
            "event_type": 1,
            "trigger_type": 1,          # KEYWORD
            "trigger_metadata": {"keyword_filter": ["discord.gg/*", "discord.com/invite/*",
                                                    "dsc.gg/*", "discord.io/*"]},
            "actions": acciones("No se reparten invitaciones a otros servidores. "
                                "Si es una colaboración, habla con el staff."),
        },
        {
            "name": "Datos personales",
            "event_type": 1,
            "trigger_type": 1,
            "trigger_metadata": {"keyword_filter": ["*mi numero es*", "*mi whatsapp es*",
                                                    "*mi direccion es*"]},
            "actions": acciones("Mejor no publiques datos personales en un canal abierto. "
                                "Usa un mensaje privado."),
        },
    ]

    puestas = 0
    for r in reglas:
        if r["name"] in ya:
            print(f"  {r['name']}: ya existe, salto")
            continue
        print(f"  {r['name']}: crear" + ("  (avisa en log-mod)" if alerta else ""))
        if not args.enserio:
            continue
        cuerpo = dict(r, enabled=True, exempt_roles=exentos, exempt_channels=[])
        try:
            api("POST", f"/guilds/{args.guild_id}/auto-moderation/rules", cuerpo)
            puestas += 1
            time.sleep(0.5)
        except SystemExit as e:
            print(f"     rechazada: {str(e).splitlines()[-1][:110]}")

    print(f"\nReglas creadas: {puestas}. Exentos: " +
          (", ".join(n for n in ("👑 Fundador", "⚙️ Administrador", "🛡️ Moderador")
                     if n in roles) or "nadie"))
    if not args.enserio:
        print("Repite con --enserio para aplicarlo.")


def cmd_permisos(args):
    """Reaplica a los canales YA EXISTENTES los permisos que dice el plan.

    'crear' solo pone permisos al crear el canal. Si despues cambias 'privado',
    'solo_lectura', 'oradores' o 'sin_bots' en el plan, hace falta esto.
    """
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    preparar_muro(plan)

    everyone = args.guild_id
    rol_id = {r["name"]: r["id"] for r in api("GET", f"/guilds/{args.guild_id}/roles")}
    ch_ahora = {c["name"]: c for c in api("GET", f"/guilds/{args.guild_id}/channels")}
    silenciado = plan.get("silenciar_rol")
    muro = plan.get("muro")
    tocados = 0

    for cat in plan.get("categorias", []):
        for ch in [cat] + list(cat.get("canales", [])):
            real = ch_ahora.get(ch["nombre"])
            if not real:
                continue
            # A las categorias hay que darles su tipo para calcular bien voz/texto.
            entrada = dict(ch)
            if ch is cat:
                entrada.setdefault("tipo", "categoria")
            # El tema y el slowmode tambien se quedaban solo en la creacion.
            retoque = {}
            # Tipo 2 (voz) fuera: no admite descripcion por API, ni al crear ni al
            # modificar. Su "tema" en el plan queda como documentacion nuestra.
            if ch.get("tema") and real["type"] in (0, 5, 13, 15, 16) \
                    and (real.get("topic") or "") != ch["tema"]:
                retoque["topic"] = ch["tema"]
            if ch.get("lento") and real.get("rate_limit_per_user") != int(ch["lento"]):
                retoque["rate_limit_per_user"] = int(ch["lento"])
            if retoque:
                print(f"  {ch['nombre']}  [{'descripcion' if 'topic' in retoque else 'slowmode'}]")
                if args.enserio:
                    api("PATCH", f"/channels/{real['id']}", retoque)
                    tocados += 1
                    time.sleep(0.4)

            ov = overwrites_de(entrada, everyone, rol_id, silenciado, muro)
            if not ov:
                continue

            marcas = []
            if ch.get("abierto"):      marcas.append("ABIERTO a todos")
            elif muro and not ch.get("privado"):
                marcas.append("muro")
            if ch.get("privado"):      marcas.append("privado")
            if "solo_lectura" in ch:   marcas.append("solo lectura")
            if ch.get("oradores"):     marcas.append("oradores")
            if ch.get("sin_bots"):     marcas.append("sin bots")
            print(f"  {ch['nombre']}  [{', '.join(marcas) or 'mordaza'}]")

            if args.enserio:
                api("PATCH", f"/channels/{real['id']}", {"permission_overwrites": ov})
                tocados += 1
                time.sleep(0.4)

    print(f"\nCanales con permisos reaplicados: {tocados}")
    if not args.enserio:
        print("Repite con --enserio para aplicarlo.")


def cmd_verificar(args):
    """Da ✅ Verificado a todo el que ya tenga su hilo en presentaciones.

    Red de respaldo: lo normal es que lo de Arcane al subir de nivel, porque
    presentarse ya da experiencia. Esto es para barrer a los que se quedaron
    colgados si el bot fallo.
    """
    roles = {r["name"]: r["id"] for r in api("GET", f"/guilds/{args.guild_id}/roles")}
    verif = roles.get("✅ Verificado")
    if not verif:
        sys.exit("no existe el rol ✅ Verificado")

    canales = api("GET", f"/guilds/{args.guild_id}/channels")
    foro = next((c for c in canales if "presentaciones" in c["name"]), None)
    if not foro:
        sys.exit("no encuentro el foro de presentaciones")

    activos = (api("GET", f"/guilds/{args.guild_id}/threads/active") or {}).get("threads", [])
    hilos = [t for t in activos if t.get("parent_id") == foro["id"]]

    # quien abrio cada hilo: el id del hilo es el del mensaje que lo creo
    autores = set()
    for t in hilos:
        if t.get("owner_id"):
            autores.add(t["owner_id"])
    print(f"{len(hilos)} hilos en presentaciones, de {len(autores)} personas distintas")

    try:
        miembros = api("GET", f"/guilds/{args.guild_id}/members?limit=1000")
    except SystemExit:
        sys.exit("hace falta el intent 'Server Members' en el portal de desarrolladores")

    dados = 0
    for m in miembros:
        if m["user"].get("bot"):
            continue
        uid = m["user"]["id"]
        if uid not in autores or verif in m["roles"]:
            continue
        print(f"  {m['user']['username']}: se presento y no estaba verificado")
        if args.enserio:
            api("PUT", f"/guilds/{args.guild_id}/members/{uid}/roles/{verif}")
            dados += 1
            time.sleep(0.4)

    print(f"\nVerificados: {dados}")
    if not args.enserio:
        print("Repite con --enserio para aplicarlo.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("inicio", help="comprueba el token y da el link de invitacion").set_defaults(f=cmd_inicio)

    sub.add_parser("servidores", help="lista los servidores donde esta el bot").set_defaults(f=cmd_servidores)

    v = sub.add_parser("ver", help="muestra canales y roles actuales de un servidor")
    v.add_argument("guild_id")
    v.set_defaults(f=cmd_ver)

    le = sub.add_parser("leer", help="lee los ultimos mensajes de un canal (buzon claude-lee)")
    le.add_argument("guild_id")
    le.add_argument("canal", help="nombre (o parte) del canal, o su id")
    le.add_argument("--cuantos", type=int, default=50, help="cuantos mensajes (max 100)")
    le.set_defaults(f=cmd_leer)

    sub.add_parser("plantilla", help="imprime el plan JSON de este repo").set_defaults(f=cmd_plantilla)

    im = sub.add_parser("importar", help="lee una plantilla publica (discord.new/CODIGO). Sin token")
    im.add_argument("origen", help="url de la plantilla o solo el codigo")
    im.add_argument("--a-plan", dest="a_plan", metavar="ARCHIVO.json",
                    help="ademas de mostrarla, la guarda como plan editable")
    im.set_defaults(f=cmd_importar)

    c = sub.add_parser("crear", help="crea roles, categorias y canales desde un plan JSON")
    c.add_argument("guild_id")
    c.add_argument("--plan", required=True)
    c.add_argument("--fase", type=int, default=0,
                   help="crea solo los canales de esta fase o menor (1 = arranque)")
    c.add_argument("--enserio", action="store_true",
                   help="sin esto es simulacro: no toca el servidor")
    c.set_defaults(f=cmd_crear)

    l = sub.add_parser("limpiar", help="borra los canales que NO estan en el plan")
    l.add_argument("guild_id")
    l.add_argument("--plan", required=True)
    l.add_argument("--roles", action="store_true",
                   help="borra tambien los roles sobrantes (nunca los de bots ni @everyone)")
    l.add_argument("--enserio", action="store_true")
    l.set_defaults(f=cmd_limpiar)

    pu = sub.add_parser("publicar", help="escribe los mensajes iniciales de los canales")
    pu.add_argument("guild_id")
    pu.add_argument("--contenido", required=True)
    pu.add_argument("--forzar", action="store_true",
                    help="escribe aunque el canal ya tenga mensajes (duplica)")
    pu.add_argument("--enserio", action="store_true")
    pu.set_defaults(f=cmd_publicar)

    pe = sub.add_parser("permisos",
                        help="reaplica los permisos del plan a los canales ya existentes")
    pe.add_argument("guild_id")
    pe.add_argument("--plan", required=True)
    pe.add_argument("--enserio", action="store_true")
    pe.set_defaults(f=cmd_permisos)

    am = sub.add_parser("automod", help="crea las reglas de AutoMod (nativo de Discord)")
    am.add_argument("guild_id")
    am.add_argument("--enserio", action="store_true")
    am.set_defaults(f=cmd_automod)

    je = sub.add_parser("jerarquia", help="ordena los roles y coloca los de los bots")
    je.add_argument("guild_id")
    je.add_argument("--plan", required=True)
    je.add_argument("--bots-bajo", dest="bots_bajo", default="⚙️ Administrador",
                    help="los roles de bots van justo debajo de este rol")
    je.add_argument("--enserio", action="store_true")
    je.set_defaults(f=cmd_jerarquia)

    vf = sub.add_parser("verificar",
                        help="da Verificado a quien ya se presento (red de respaldo)")
    vf.add_argument("guild_id")
    vf.add_argument("--enserio", action="store_true")
    vf.set_defaults(f=cmd_verificar)

    aj = sub.add_parser("ajustes", help="apunta los canales de sistema a los del plan")
    aj.add_argument("guild_id")
    aj.add_argument("--enserio", action="store_true")
    aj.set_defaults(f=cmd_ajustes)

    o = sub.add_parser("onboarding",
                       help="aplica el cuestionario de entrada. Correr DESPUES de 'crear'")
    o.add_argument("guild_id")
    o.add_argument("--plan", required=True)
    o.add_argument("--enserio", action="store_true")
    o.set_defaults(f=cmd_onboarding)

    i = sub.add_parser("invitacion", help="genera el link para meter el bot a tu servidor")
    i.add_argument("client_id")
    i.add_argument("--minimo", action="store_true",
                   help="permisos reducidos en vez de Administrador")
    i.set_defaults(f=cmd_invitacion)

    args = p.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
