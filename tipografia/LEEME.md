# Las tipografías, aquí dentro a propósito

Estos `.ttf` están en el repositorio **porque el dibujo también corre en la
nube**. Barlow estaba instalada solo en el PC de casa, y la reserva que había
apuntaba a `C:/Windows/Fonts/` — que en el Linux de GitHub Actions no existe.
Sin esto, generar una imagen allí revienta al abrir la fuente.

| Archivo | Para qué | Licencia |
|---|---|---|
| `Barlow-Black.ttf` | Títulos y realces | SIL Open Font License 1.1 |
| `Barlow-Bold.ttf` | Líneas y encabezados | SIL Open Font License 1.1 |
| `Barlow-Regular.ttf` | Subtítulos y pies | SIL Open Font License 1.1 |
| `Barlow-MediumItalic.ttf` | La línea de guion del personaje | SIL Open Font License 1.1 |
| `DejaVuSansMono-Bold.ttf` | Los comandos, en su cajita | Bitstream Vera / DejaVu |

Las dos licencias **permiten redistribuir el archivo**, que es justo lo que se
hace aquí. Barlow es de Jeremy Tribby; DejaVu, del proyecto DejaVu.

Ojo: **Barlow no dibuja la flecha `→`** — en su lugar se usa `»`. El detector de
glifos de `discord_banners.py` lo averigua preguntando a la fuente, no mirando
rangos de caracteres.
