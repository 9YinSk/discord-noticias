# Noticias del servidor, en automatico

Esto publica las noticias en Discord **sin que ningun PC este encendido**. Lo
ejecuta GitHub cada 30 minutos, gratis.

## Que hay aqui

| Archivo | Que hace |
|---|---|
| `discord_noticias.py` | Lee los feeds y publica lo nuevo |
| `discord_feeds.py` | La lista de feeds y su canal |
| `discord_opiniones.py` | El veredicto de la gente sobre un anime o un juego |
| `discord_servidor.py` | Hablar con la API de Discord |
| `.github/workflows/noticias.yml` | El cron que lo lanza |

## Los pasos, una sola vez

1. **Crea el repositorio.** En github.com, boton `+` arriba a la derecha »
   *New repository*. Nombre: `discord-noticias`. **Ponlo en Private.**
   No marques nada mas. *Create repository*.

2. **Sube esta carpeta.** En la pagina que sale, *uploading an existing file*, y
   arrastra **todo lo que hay dentro de `discord-nube`**. Ojo: tiene que subir
   tambien la carpeta oculta `.github`. Si al arrastrar no aparece, usa los
   comandos que estan al final.

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

## Cuidado con dos cosas

- **El token es la llave del bot.** Quien lo tenga puede hacer lo que quiera en
  el servidor. Por eso el repo va en **Private** y el token va como *secret*,
  nunca dentro de un archivo.
- **GitHub apaga el cron de un repo sin actividad tras 60 dias.** Si un dia dejan
  de llegar noticias, entra en *Actions* y dale a *Run workflow*: se reactiva.

## Si prefieres subirlo por comandos

```bash
cd discord-nube
git init
git add .
git commit -m "noticias en automatico"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/discord-noticias.git
git push -u origin main
```

## Para actualizarlo cuando cambien los scripts

En tu PC:

```bash
python herramientas/discord_nube.py
```

Vuelve a copiar los scripts aqui. Luego `git add . && git commit && git push`.
