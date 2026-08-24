# Noticias del servidor, en automatico

Esto publica las noticias en Discord **sin que ningun PC este encendido**. Lo
ejecuta GitHub cada 30 minutos, gratis.

## Que hay aqui

## Los tres trabajos

| Cuando | Que hace |
|---|---|
| **cada 10 min** | Reparte los **roles por reaccion**: colores, paises, zonas |
| **cada 30 min** | Publica las **noticias** nuevas de los 8 feeds |
| **los lunes** | Lo mejor valorado de la **temporada de anime** |

El de los roles es el mas importante de los tres. Discord no deja que un bot
escuche reacciones sin estar conectado las 24 h, asi que este pregunta quien ha
reaccionado y reparte. Sin el, elegir tu color o abrir una zona **no hace nada**
mientras el PC de casa este apagado.

| Archivo | Que hace |
|---|---|
| `discord_reacciones.py` + `.json` | El reparto de roles y sus paneles |
| `discord_noticias.py` + `discord_feeds.py` | Los feeds y donde va cada uno |
| `discord_opiniones.py` | El veredicto de la gente sobre un anime o un juego |
| `discord_temporada.py` | El repaso semanal de la temporada |
| `discord_servidor.py` | Hablar con la API de Discord |

## Los pasos, una sola vez

1. **Crea el repositorio.** En github.com, boton `+` arriba a la derecha »
   *New repository*. Nombre: `discord-noticias`. **Ponlo en Private.**
   No marques nada mas. *Create repository*.

2. **Sube esta carpeta.** Ya viene con el repo de git hecho y el remoto puesto,
   asi que es un solo comando desde aqui:

   ```bash
   git push -u origin main
   ```

   La primera vez se abre una ventana del navegador para entrar en GitHub. Se
   hace una sola vez: despues quedan guardadas las credenciales.

   *(Si prefieres arrastrar archivos: en la pagina del repo, «uploading an
   existing file». Ojo, tiene que subir tambien la carpeta oculta `.github`, y
   por eso el comando es mas fiable.)*

3. **Guarda el token del bot.** En el repo: *Settings* » *Secrets and variables*
   » *Actions* » **New repository secret**.
   - Name: `DISCORD_BOT_TOKEN`
   - Secret: el token, tal cual, sin comillas y sin la palabra `Bot`
   Esta en `herramientas/.discord_token`, en tu PC.

4. **Enciendelo.** Pestana *Actions* » si sale un aviso, *I understand my
   workflows, go ahead and enable them* » elige **Noticias** » *Run workflow*.
   En un minuto deberian aparecer noticias en Discord.

Y ya esta. A partir de ahi va solo cada 30 minutos.

## Opcional: que la IA traduzca y resuma

Anime News Network publica **en ingles**. Con esto, los titulares salen en
espanol y con una linea de contexto.

1. Entra en **aistudio.google.com/apikey** (con tu cuenta de Google).
2. *Create API key*. Es gratis y no pide tarjeta.
3. Guardala como otro secret, igual que antes, con el nombre `GEMINI_API_KEY`.

Si no lo haces, no pasa nada: publica igual, en el idioma original.

## Opcional: el canal de musica

MusicButler avisa **solo cuando un artista saca algo** — nada de vida personal.

1. Cuenta gratis en **musicbutler.io** y sigue a unos cuantos artistas.
   El enlace RSS **solo aparece cuando ya sigues a alguien**.
2. Settings » copia tu **RSS feed**.
3. Guardalo como secret con el nombre `MUSICBUTLER_RSS`.

**Ese enlace es privado.** Su politica dice que compartirlo publicamente puede
costar la cuenta, y por eso va como secret y no dentro del codigo.

## Cuidado con dos cosas

- **El token es la llave del bot.** Quien lo tenga puede hacer lo que quiera en
  el servidor. Por eso el repo va en **Private** y el token va como *secret*,
  nunca dentro de un archivo.
- **GitHub apaga el cron de un repo sin actividad tras 60 dias.** Si un dia dejan
  de llegar noticias, entra en *Actions* y dale a *Run workflow*: se reactiva.

## Ojo con una cosa

`discord_reacciones.json` guarda **los ids de los mensajes** de cada panel. Si se
vuelven a publicar los paneles de `autoroles` o de `reglas`, esos ids cambian y
hay que volver a subir el archivo, o el reparto de roles apuntara a mensajes que
ya no existen. Se hace con `python herramientas/discord_nube.py` y un push.

## Para actualizarlo cuando cambien los scripts

En tu PC:

```bash
python herramientas/discord_nube.py
```

Vuelve a copiar los scripts aqui. Luego `git add . && git commit && git push`.
