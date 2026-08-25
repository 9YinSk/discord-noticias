"""Lee Reddit sin credenciales, a través del archivo público Arctic Shift.

Por qué existe:
    Reddit cerró el autoservicio de apps OAuth (hace falta aprobación manual),
    y tanto WebFetch como el navegador integrado tienen reddit.com bloqueado.
    El MCP `reddit` solo navega feeds por RSS: no busca, no lee comentarios, y
    devuelve score/num_comments en null porque el RSS no los trae.

    Arctic Shift (arctic-shift.photon-reddit.com) es un archivo público de
    Reddit mantenido por la comunidad, el sucesor de Pushshift. No es
    reddit.com, así que no está bloqueado, y no pide credenciales.

Cómo se arregló la búsqueda (16-ago-2026):

    El archivo tiene DOS clases de consulta, y se comportan al revés de lo que
    uno esperaría:

      · Consulta por ÍNDICE (subreddit + rango de fechas, sin texto)
            -> HTTP 200 en ~2-6 s, 100 items por página. Siempre responde.

      · Consulta por TEXTO (query=/body=, o sea la búsqueda de verdad)
            -> HTTP 422 «Timeout. Maybe slow down a bit». SIEMPRE.
               Medido: falla igual con ventana de 6 meses y con ventana de
               7 días. No es que vaya lenta ni que haya que reintentar: el
               escaneo de texto del archivo está caído para nosotros.

    Así que la búsqueda de texto del servidor NO SE USA. En su lugar se baja
    el listado del subreddit por índice (que sí responde) y se filtra el texto
    aquí, en local. Es la misma respuesta, y encima llega con score y
    num_comments de verdad — que es justo lo que el MCP no puede dar.

    Límites medidos del archivo: limit máximo 100; `fields` funciona pero
    `permalink` no es un campo válido (la URL se reconstruye desde el id);
    `query` sin subreddit da 400 (no hay búsqueda global, nunca la hubo).

Uso:
    # buscar texto dentro de uno o varios subreddits
    python leer_reddit.py buscar --sub korea --q meeff
    python leer_reddit.py buscar --sub korea,Living_in_Korea --q "meeff,scam"
    python leer_reddit.py buscar --sub korea --q meeff --en comentarios
    python leer_reddit.py buscar --sub korea --q meeff --desde 2026-01-01

    # comentarios de un hilo concreto (lo más fiable que hay)
    python leer_reddit.py hilo --url https://www.reddit.com/r/korea/comments/1fyudcf/...
    python leer_reddit.py hilo --id 1fyudcf
"""

import argparse
import datetime as dt
import json
import re
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://arctic-shift.photon-reddit.com/api"
UA = "yinx-lector-reddit/2.0 (uso personal, lectura de archivo publico)"

TOPE_LIMITE = 100  # el archivo rechaza limit>100 con un 400 explícito

CAMPOS_POST = "id,title,selftext,created_utc,score,num_comments,author,subreddit"
CAMPOS_COMENTARIO = "id,body,author,created_utc,score,link_id,subreddit"

# La consola de Windows es cp1252 y revienta con japonés, coreano o emoji —
# que es justo lo que vamos a leer. Se fuerza UTF-8 en la salida.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def pedir(ruta, params, intentos=4):
    """Una llamada al archivo, con reintento y espera creciente.

    Solo se usa para consultas por índice, que responden bien. Si aquí
    aparece un 422 repetido es que el archivo está saturado de verdad, no que
    la consulta sea pesada."""
    url = BASE + ruta + "?" + urllib.parse.urlencode(
        {k: v for k, v in params.items() if v not in (None, "")})
    espera = 3
    for intento in range(1, intentos + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                cuerpo = json.loads(r.read().decode("utf-8", "replace"))
                return cuerpo.get("data") or []
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:200]
            if e.code == 400:  # error de parámetros: reintentar no arregla nada
                print("  [400] {}".format(detalle))
                return []
            if intento < intentos:
                print("  (el archivo pide calma; reintento {}/{} en {}s)".format(
                    intento, intentos - 1, espera))
                time.sleep(espera)
                espera *= 2
                continue
            print("  [{}] {}".format(e.code, detalle or e.reason))
            return []
        except Exception as e:
            if intento < intentos:
                time.sleep(espera)
                espera *= 2
                continue
            print("  error de red: {}".format(e))
            return []
    return []


def bajar_listado(ruta, campos, sub, desde, hasta, paginas):
    """Baja el listado de un subreddit hacia atrás en el tiempo, página a
    página. Va de lo más nuevo a lo más viejo: si se corta a medias, lo que
    ya se tiene es lo más reciente.

    El cursor es el created_utc del último item, reusado como `before`."""
    acumulado = []
    cursor = hasta
    for pagina in range(paginas):
        params = {"subreddit": sub, "limit": TOPE_LIMITE, "sort": "desc",
                  "fields": campos, "after": desde, "before": cursor}
        lote = pedir(ruta, params)
        if not lote:
            break
        acumulado.extend(lote)
        cursor = lote[-1].get("created_utc")
        print("    pagina {}/{}: {} items (van {})".format(
            pagina + 1, paginas, len(lote), len(acumulado)))
        if len(lote) < TOPE_LIMITE or not cursor:
            break  # se acabó el material antes de agotar las páginas
        time.sleep(1.0)  # cortesía con un archivo comunitario y gratuito;
        #                  con 0.5 s saltaba un 422 de cada dos páginas
    return acumulado


def fecha(ts):
    if not ts:
        return "?"
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime("%d-%b-%Y")


def limpiar(t, ancho=100, lineas=8):
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t).strip()
    return "\n      ".join(textwrap.wrap(t, ancho)[:lineas])


def id_de_url(u):
    m = re.search(r"/comments/([a-z0-9]+)", u)
    return m.group(1) if m else None


def coincide(texto, terminos):
    t = (texto or "").lower()
    return any(term in t for term in terminos)


def buscar(subs, terminos, donde, desde, hasta, paginas):
    total = 0
    for sub in subs:
        print("\n{}\n=== r/{} · busco {} ===".format("=" * 78, sub, terminos))

        if donde in ("posts", "ambos"):
            print("  bajando posts...")
            posts = bajar_listado("/posts/search", CAMPOS_POST,
                                  sub, desde, hasta, paginas)
            cubierto(posts)
            hits = [p for p in posts
                    if coincide(p.get("title", "") + " " + (p.get("selftext") or ""),
                                terminos)]
            print("\n  --> {} posts coinciden (de {} revisados)".format(
                len(hits), len(posts)))
            total += len(hits)
            for p in hits:
                print("\n  [{} · {} pts · {} coment.] {}".format(
                    fecha(p.get("created_utc")), p.get("score", "?"),
                    p.get("num_comments", "?"), p.get("title", "")))
                print("      https://reddit.com/comments/{}".format(p.get("id")))
                cuerpo = p.get("selftext") or ""
                if cuerpo and cuerpo not in ("[removed]", "[deleted]"):
                    print("      " + limpiar(cuerpo))
                elif cuerpo:
                    print("      (texto borrado — los comentarios pueden seguir ahí)")

        if donde in ("comentarios", "ambos"):
            print("\n  bajando comentarios...")
            coments = bajar_listado("/comments/search", CAMPOS_COMENTARIO,
                                    sub, desde, hasta, paginas)
            cubierto(coments)
            hits = [c for c in coments if coincide(c.get("body"), terminos)]
            print("\n  --> {} comentarios coinciden (de {} revisados)".format(
                len(hits), len(coments)))
            total += len(hits)
            for c in hits:
                hilo = (c.get("link_id") or "").replace("t3_", "")
                print("\n  [{} · {} pts] u/{}".format(
                    fecha(c.get("created_utc")), c.get("score", "?"),
                    c.get("author", "?")))
                print("      https://reddit.com/comments/{}".format(hilo))
                print("      " + limpiar(c.get("body")))

    print("\n{}\nTotal: {} coincidencias.".format("=" * 78, total))
    if not total:
        print("Ojo: 0 coincidencias puede significar que no hay nada, o que el\n"
              "tramo de fechas revisado no llega hasta donde está. Mira el rango\n"
              "que se imprimió arriba y amplíalo con --desde o --paginas.")


def cubierto(items):
    """Dice qué tramo de tiempo se llegó a revisar de verdad. Sin esto, un
    '0 resultados' es indistinguible de 'no bajé hasta ahí'."""
    if not items:
        print("    (nada bajado)")
        return
    ts = [i.get("created_utc") for i in items if i.get("created_utc")]
    print("    revisado del {} al {}".format(fecha(min(ts)), fecha(max(ts))))


def ver_hilo(pid, limite):
    print("\n=== comentarios del post {} ===".format(pid))
    datos = pedir("/comments/search",
                  {"link_id": pid, "limit": min(limite, TOPE_LIMITE), "sort": "desc"})
    if not datos:
        print("  (sin comentarios archivados)")
        return
    humanos = [c for c in datos if c.get("author") != "AutoModerator"]
    if not humanos:
        # Sin esto la pantalla queda en blanco y parece un fallo del script.
        # Que el único comentario sea el bot ES el dato: nadie respondió.
        print("  (los {} comentarios son de AutoModerator — nadie humano "
              "respondió a este hilo)".format(len(datos)))
        return
    for c in humanos:
        print("\n  u/{} · {} pts:".format(c.get("author", "?"), c.get("score", "?")))
        print("      " + limpiar(c.get("body", "")))


def main():
    ap = argparse.ArgumentParser(
        description="Lee Reddit vía el archivo Arctic Shift, sin credenciales.")
    ap.add_argument("modo", choices=["buscar", "hilo", "posts", "comentarios"],
                    help="'posts' y 'comentarios' son alias viejos de 'buscar'")
    ap.add_argument("--sub", help="subreddit(s), separados por coma")
    ap.add_argument("--q", help="texto a buscar; varios términos con coma = O")
    ap.add_argument("--en", choices=["posts", "comentarios", "ambos"],
                    default="ambos", help="dónde buscar (por defecto: ambos)")
    ap.add_argument("--desde", help="fecha mínima, YYYY-MM-DD")
    ap.add_argument("--hasta", help="fecha máxima, YYYY-MM-DD")
    ap.add_argument("--paginas", type=int, default=15,
                    help="tope de páginas de 100 por subreddit (por defecto 15 = 1500)")
    ap.add_argument("--id", help="id del post (modo hilo)")
    ap.add_argument("--url", help="URL del post (modo hilo)")
    ap.add_argument("--limite", type=int, default=100)
    a = ap.parse_args()

    if a.modo == "hilo":
        pid = a.id or (id_de_url(a.url) if a.url else None)
        if not pid:
            sys.exit("Para 'hilo' hace falta --id o --url de un post.")
        ver_hilo(pid, a.limite)
        return

    if not a.sub or not a.q:
        sys.exit("Hace falta --sub y --q.\n"
                 "El archivo no tiene búsqueda global: siempre hay que acotar a\n"
                 "un subreddit. Ej: --sub korea,Living_in_Korea --q meeff")

    donde = a.en
    if a.modo == "posts":            # alias viejos, se respetan
        donde = "posts"
    elif a.modo == "comentarios":
        donde = "comentarios"

    subs = [s.strip() for s in a.sub.split(",") if s.strip()]
    terminos = [t.strip().lower() for t in a.q.split(",") if t.strip()]
    buscar(subs, terminos, donde, a.desde, a.hasta, a.paginas)


if __name__ == "__main__":
    main()
