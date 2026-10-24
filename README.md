# curia_maxima

curia_maxima es la plataforma de una cámara cívica chilena. Los bots personales de las personas consultan datos oficiales, perfilan candidatos y, más adelante, debaten y votan propuestas. Este repositorio contiene el código de la herramienta y el sitio público. Los datos, las propuestas y la normativa viven en repositorios públicos aparte. El sitio sigue siendo estático: el cuestionario se responde en el navegador.

El costo de operación sigue en cero: GitHub Actions y GitHub Pages. No hay servicios de pago ni secretos.

## Cuatro piezas independientes

| Pieza | Dónde vive | Qué contiene |
| --- | --- | --- |
| Código de la cámara y sitio público | Este repositorio | Esquema, validación, recolectores, la página estática y el cuestionario de ejemplo en `datos/espectro/`. Más adelante, el soporte para que los bots consulten, debaten y voten. Licencia MIT. |
| Propuestas | [nlecarosg/curia_propuestas](https://github.com/nlecarosg/curia_propuestas) | Textos de las propuestas, en CC0. El contenido cívico no queda atado a la licencia del código. |
| Datos y KPI validados | [nlecarosg/curia_datos](https://github.com/nlecarosg/curia_datos) | Series que escriben los recolectores. Este código no versiona esos archivos. |
| Normativa vigente | [nlecarosg/curia_normativas](https://github.com/nlecarosg/curia_normativas) | Normas en JSON. La compilación se ofrece en CC0; los textos oficiales se citan desde Ley Chile. |

Los recolectores escriben en una ruta que se elige al ejecutarlos (`--output` o la variable `CURIA_OUTPUT_DIR`). Esa ruta es una copia del repositorio de datos. El código no asume que los datos están en este repositorio.

```text
bots personales
      |
      v
curia_maxima (este repo, código, MIT)
      |
      +-- escribe series --> repo de datos y KPI (ruta configurable)
      +-- lee, al armar el sitio --> repo de propuestas (CC0)
      +-- lee, al armar el sitio --> repo de normativa
      +-- publica una lectura --> GitHub Pages
```

## Sitio público

La página está en `web/estaticos`. No usa un framework. Quien la abre no consulta GitHub: lee `datos.json`, armado antes y servido en el mismo origen. El cuestionario no sale de ese navegador.

```bash
python -m curia_maxima.sitio --salida _sitio
```

Eso baja las series de `curia_datos`, las propuestas de `curia_propuestas` y las normas de `curia_normativas`, y escribe `_sitio/` con el HTML, el CSS, el JavaScript y `datos.json`. Hace falta PyYAML (`pip install -e ".[sitio]"`; también entra en `.[dev]`).

El flujo [`.github/workflows/paginas.yml`](.github/workflows/paginas.yml) publica esa carpeta en GitHub Pages:

- en cada push a `main`;
- todos los días a las 13:15 UTC, después de la actualización de `curia_datos` (12:00 UTC);
- a mano, con *workflow_dispatch*.

La dirección prevista es <https://nlecarosg.github.io/curia_maxima/>.

### Por qué no se lee desde el navegador

`raw.githubusercontent.com` entrega un archivo, pero no lista carpetas. Las propuestas y las normas cambian de nombre y de ruta, así que hay que pedir el árbol a `api.github.com`. Sin autenticación esa API permite 60 solicitudes por hora y por IP: una visita gasta varias y la página deja de cargar para quien venga después. El workflow usa el `GITHUB_TOKEN` automático del trabajo (no es un secreto guardado en el repositorio) y baja todo una vez. Quien abre la página solo habla con GitHub Pages. No hay analítica ni otros dominios.

Si un repositorio no responde, el armado reintenta y deja en `datos.json` un aviso para esa sección. Las otras se publican igual. Si fallan las tres, el workflow termina con error y Pages conserva la versión anterior. Si `datos.json` no llega al navegador, la página muestra el aviso en vez de quedarse en blanco.

## Espectro, índice de ajuste y rankings

La página deja de ser solo un reporte. Quien la abre puede responder un cuestionario, ver propuestas ordenadas por cercanía y mirar un ranking de actores. Todo eso ocurre en el navegador. No hay backend, ni cuenta, ni analítica.

El contenido político de esta versión es de ejemplo y está marcado así en la página. No hay políticos reales con una posición inventada. Los actores se llaman «Bot ejemplo A», «Figura ejemplo Norte» y similares. Otro equipo definirá el contenido real.

### Ejes

Cada posición es un vector de cuatro números, de −1 a +1. Son cuatro, y no uno, porque una propuesta chilena suele moverse en dimensiones que no se deducen entre sí:

| Eje | −1 | +1 | Por qué va aparte |
| --- | --- | --- | --- |
| Economía | Más redistribución y regulación del mercado | Más mercado y menos intervención | Dice cómo se reparte y se regula la actividad económica. |
| Libertades | Más límites en nombre del orden | Más libertades civiles y autonomía personal | No es el eje económico: se puede preferir el mercado y, a la vez, más control del orden. |
| Rol del Estado | Estado acotado a seguridad y justicia | Estado que provee salud, educación, pensiones y cuidados | No es Economía: se pueden querer servicios públicos amplios y mercados poco intervenidos, o al revés. |
| Territorio | Decisiones en el nivel nacional | Más autonomía de regiones y municipios | La regionalización no sale del eje económico. |

El cuestionario tiene 16 afirmaciones (cuatro por eje), en la escala 1 «muy en desacuerdo» … 5 «muy de acuerdo». Cada afirmación tiene un sentido +1 o −1. La coordenada de un eje es el promedio de `(respuesta − 3) / 2`, multiplicado por ese sentido. Así, «muy de acuerdo» con una afirmación de sentido +1 empuja el eje a +1, y «muy de acuerdo» con una de sentido −1 lo empuja a −1.

### Fórmula del índice

En una frase, la que muestra la interfaz: es el porcentaje de cercanía entre su posición y la de la ficha: 100 si coinciden en todos los ejes y 0 si están en polos opuestos.

```text
ajuste = redondear(100 × (1 − Σ|pᵢ − qᵢ| / (2n)))
```

`p` es la persona, `q` es la propuesta o el actor, `n` es la cantidad de ejes (hoy 4) y cada coordenada está en [−1, +1]. La distancia de un eje es como máximo 2, así que dividir la distancia media por 2 la deja entre 0 y 1. El redondeo es al entero más cercano y el 0,5 sube (no es el redondeo bancario de Python). La misma cuenta está en `curia_maxima.espectro.ajuste` y en `web/estaticos/espectro.js`. Si la persona no respondió, la ficha invita a Mi espectro y no inventa un porcentaje. Las propuestas se pueden ordenar por ese índice.

### Privacidad

Las respuestas se guardan solo en el navegador, en `localStorage`, bajo la clave `curia-maxima-espectro`. No se envían a ningún servidor: no hay `fetch` distinto de `datos.json` en el mismo origen, ni rastreadores, ni analítica. La página lo dice junto al cuestionario y ofrece el botón «Borrar mis respuestas de este navegador», que borra esa clave.

### Dónde viven los datos, y cómo migrarlos

En esta versión los JSON están en este repositorio, en `datos/espectro/`, con el contrato `src/curia_maxima/schemas/espectro.schema.json`. `pytest` los valida. El armado del sitio los copia dentro de `datos.json` y une `posiciones.json` a las propuestas del repositorio por `id`.

Quedan aquí, y no en `curia_propuestas` ni en `curia_datos`, porque son contenido de ejemplo. El esquema de una propuesta rechaza campos extra (`additionalProperties: false`), así que meter `posicion` en el front matter obliga a cambiar ese repositorio. `curia_datos` guarda series oficiales del INE; un actor ficticio no es una serie. Publicar ideología de ejemplo junto a cifras oficiales o junto al texto CC0 mezcla dos cosas que otro equipo va a reemplazar.

Para migrarlos cuando ese equipo tenga el contenido real:

1. **Posiciones de propuestas.** Copiar cada objeto de `datos/espectro/posiciones.json` a `curia_propuestas`, como `posiciones/<PROP-id>.json`, fuera de `propuestas/`. El validador de ese repositorio hoy solo mira los Markdown. En `sitio.py`, al leer una propuesta, si existe ese JSON se llena `posicion` y se deja de usar la entrada local de ese id. Si se prefiere el front matter, hay que ampliar `esquema/propuesta.schema.json` y quitar el `additionalProperties: false` para ese campo.
2. **Actores.** Copiar `datos/espectro/actores.json` a `curia_datos` como `actores/*.json`, fuera de `series/`. El recolector no los escribe. Un lector nuevo en el armado del sitio los baja igual que las series. El esquema puede mudarse a `curia_datos/esquema/`.
3. **Afirmaciones y ejes.** Son el texto del cuestionario, no el corpus cívico. Pueden quedarse en este repositorio. Si el equipo de contenido quiere versionarlos aparte, se mueven a un JSON y el armado los descarga como el resto. Hay que quitar `"ejemplo": { "const": true }` del esquema cuando el contenido deje de ser de muestra.

Las fichas `PROP-2026-901` … `PROP-2026-904` no están en `curia_propuestas`. Existen para poder ordenar varias propuestas por ajuste. Cuando haya propuestas reales con posición, se borran.

### Qué opina la gente

La sección del sitio dice «próximamente». No hay un servidor, y las respuestas de Mi espectro no deben salir del navegador para llenar esa sección. Si más adelante se recogen opiniones, tiene que ser un canal público y separado. Tres alternativas de costo cero:

1. **Pol.is** (el software libre [Polis](https://github.com/compdemocracy/polis)). La gente vota si está de acuerdo con afirmaciones y el sistema agrupa opiniones, sin un hilo de comentarios. Pros: está hecho para mostrar acuerdos y grupos, y se puede usar una instancia comunitaria o auto-hospedarlo. Contras: auto-hospedar ya no es «solo GitHub Pages» (hace falta un proceso, aunque sea un plan gratuito); una instancia de terceros recibe las opiniones; hay que moderar las afirmaciones.
2. **Votos como issues o pull requests en un repositorio público** (por ejemplo `curia_propuestas`). Una opinión es un issue con plantilla, o un JSON en un PR. El siguiente armado del sitio cuenta esos archivos. Pros: costo cero, auditable, y encaja con el snapshot actual; no hace falta otro servicio. Contras: solo opina quien tiene cuenta de GitHub; el voto queda público en el historial de git; hay que moderar spam; no sirve para la posición privada del cuestionario y no hay que mezclarlo con ella.
3. **Un formulario gratuito externo** (por ejemplo Framaforms). Pros: no hace falta cuenta de GitHub y no hay backend propio. Contras: las respuestas salen del navegador hacia ese servicio, así que no puede reutilizar el espectro privado y hay que decirlo; incrustarlo rompe la política de contenido actual (`default-src 'none'`) y mete a un tercero; el plan gratuito puede cambiar o cortarse.

La opción que mejor respeta este sitio, si hace falta elegir una, es la de issues o archivos en un repositorio: el espectro sigue en el navegador y las opiniones públicas quedan en git, con un aviso de que son públicas.

## Ajuste manual de Pages

El `GITHUB_TOKEN` del workflow no puede cambiar la configuración del repositorio. Alguien con permiso de administración tiene que hacer esto una vez:

1. Entrar a **Settings → Pages** de `nlecarosg/curia_maxima`.
2. En **Build and deployment**, dejar **Source** en **GitHub Actions** (no «Deploy from a branch»).

Esa opción aparece cuando el workflow ya está en `main`. Si el primer trabajo «Publicar el sitio» falla porque Pages todavía no está en GitHub Actions, hay que repetirlo después de ese cambio.

## Estructura de este repositorio

```text
.
├── LICENSE
├── README.md
├── pyproject.toml
├── src/curia_maxima/
│   ├── cli.py
│   ├── espectro.py
│   ├── sitio.py
│   ├── hashing.py
│   ├── store.py
│   ├── validation.py
│   ├── collectors/
│   │   └── ine_remuneraciones.py
│   └── schemas/
│       ├── espectro.schema.json
│       ├── observation.schema.json
│       └── series.schema.json
├── datos/espectro/         cuestionario, actores y posiciones de ejemplo
├── tests/
├── web/estaticos/          página estática (HTML, CSS y JS)
└── .github/workflows/
    ├── ci.yml              pruebas, y un armado del sitio contra los repos públicos
    └── paginas.yml         publicación en GitHub Pages
```

`output/`, `data/` y `_sitio/` están en `.gitignore`. No son el lugar de los datos: `_sitio/` es solo la carpeta que arma el comando del sitio.

## Esquema común de la observación

Cada observación publicada tiene estos campos. Los nombres del archivo JSON están en inglés; el significado, en español. El contrato normativo es `src/curia_maxima/schemas/observation.schema.json` (JSON Schema, draft 2020-12). Los tests lo validan en cada ejecución.

| Campo | Significado |
| --- | --- |
| `value` | Valor numérico publicado. |
| `unit` | Unidad del valor. |
| `source.organism` | Organismo que publica el dato. |
| `source.url` | URL HTTPS de la consulta que lo produjo. |
| `data_date` | Fecha del dato (`AAAA-MM-DD`). En una serie mensual es el primer día del mes de referencia. |
| `captured_at` | Fecha y hora UTC de la captura (`AAAA-MM-DDTHH:MM:SSZ`). |
| `raw_hash` | SHA-256 del cuerpo crudo de la respuesta HTTP, con prefijo `sha256:` y hexadecimales en minúscula. |
| `status` | `vigente` o `no actualizado`. |
| `series_id` | Identificador estable de la serie, para que la observación se entienda sola. |

Una captura que falla **no publica un dato nuevo**: no agrega ni modifica observaciones. El resultado queda en el archivo de la serie (`series.schema.json`):

- `status`: `no actualizado`
- `error`: un mensaje que dice qué falló, la URL consultada y, si hubo cuerpo de respuesta, su hash
- `observations`: el historial anterior, intacto. Si nunca hubo una captura vigente, la lista queda vacía.

`vigente` exige al menos una observación y `error` en null. `no actualizado` exige un `error` no vacío.

Ejemplo abreviado:

```json
{
  "schema_version": "1",
  "series_id": "ine.ir2023.nacional.indice",
  "indicator": {
    "code": "IR2023",
    "name": "Índice nominal de remuneraciones (base 2023 = 100)"
  },
  "unit": "índice (base 2023=100)",
  "source": {
    "organism": "Instituto Nacional de Estadísticas (INE)",
    "url": "https://sdmx.ine.gob.cl/rest/data/CL01,DF_IR2023,1.0?startPeriod=2023-01&endPeriod=2026-10"
  },
  "status": "vigente",
  "error": null,
  "captured_at": "2026-10-23T17:00:00Z",
  "observations": [
    {
      "series_id": "ine.ir2023.nacional.indice",
      "value": 124.64,
      "unit": "índice (base 2023=100)",
      "source": {
        "organism": "Instituto Nacional de Estadísticas (INE)",
        "url": "https://sdmx.ine.gob.cl/rest/data/CL01,DF_IR2023,1.0?startPeriod=2023-01&endPeriod=2026-10"
      },
      "data_date": "2026-08-01",
      "captured_at": "2026-10-23T17:00:00Z",
      "raw_hash": "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "status": "vigente"
    }
  ]
}
```

El historial es la lista de observaciones, una por fecha. Una pasada posterior actualiza la misma fecha si el organismo revisa la cifra y conserva los meses que esa pasada no trae.

## Recolector de prueba

El recolector de prueba lee una sola fuente oficial, sin clave:

- **Organismo:** Instituto Nacional de Estadísticas (INE), sistema de información del mercado laboral (SIMEL).
- **Indicador:** índice nominal de remuneraciones, base 2023 = 100, total nacional, frecuencia mensual. Código `IR2023`, unidad `IX` (índice). No se guarda la variación a 12 meses, que viene en la misma respuesta.
- **Consulta:** `https://sdmx.ine.gob.cl/rest/data/CL01,DF_IR2023,1.0`, con `Accept: application/vnd.sdmx.data+json; version=1.0`.
- **Serie escrita:** `ine.ir2023.nacional.indice`, en `{salida}/series/ine.ir2023.nacional.indice.json`.
- **Respuesta cruda:** `{salida}/raw/ine.ir2023.nacional.indice.body`, solo de la última captura vigente. Una captura fallida no reemplaza ese archivo.

El valor se redondea a los decimales que declara la propia respuesta (`DECIMALS`, hoy 2). `raw_hash` es el SHA-256 de ese archivo. El sobre de la API cambia `meta.id` y `meta.prepared` en cada consulta, aunque las cifras sean las mismas: por eso una descarga posterior no repite el hash. El archivo `.body` es el que permite recomputarlo.

Si la fuente no responde, no es JSON, informa errores o cambia la estructura que este recolector entiende (dimensiones, unidad `IX`, periodos, decimales o valores no numéricos), el proceso sale con código 1, deja la serie en `no actualizado` y no publica el dato. La alerta a quienes mantienen el sistema se conectará después; hoy el error verificable es el campo `error` del archivo y el código de salida.

```bash
python -m curia_maxima --output /ruta/del/repo-de-datos
```

También vale `curia-collect --output /ruta/del/repo-de-datos` después de instalar el paquete, o exportar `CURIA_OUTPUT_DIR`.

## Desarrollo y pruebas

Hace falta Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests
pytest
```

`pytest` valida los esquemas, el archivo que escribe el recolector, un cambio de formato simulado, el armado del sitio con datos de prueba y los JSON de `datos/espectro/` (cuestionario, actores, posiciones y la fórmula del índice). Esas pruebas no llaman al INE ni a GitHub. El flujo `.github/workflows/ci.yml` ejecuta lo mismo en cada pull request y, además, arma el sitio una vez contra los tres repositorios públicos. El cron y la publicación están solo en `paginas.yml`. No hay secretos.

## Licencia

El código de este repositorio se publica bajo la licencia MIT. Ver [LICENSE](LICENSE).

MIT es una licencia abierta y simple de cumplir: quien use o modifique la herramienta puede hacerlo, incluida la copia del aviso de licencia. Sirve para este repositorio porque aquí está la herramienta, no el corpus cívico. Las propuestas irán en CC0 en su propio repositorio, y los datos y la normativa tendrán cada uno el suyo. Así los bots personales y esos repositorios pueden reutilizar el esquema y los recolectores sin obligaciones de copyleft.

La otra candidata era AGPL. Conviene volver a mirarla antes de aceptar contribuciones externas si el código futuro de debate y votación debe impedir que alguien opere una cámara modificada sin publicar el código. Mientras este repositorio es el recolector y el esquema, MIT mantiene el costo legal en el mínimo.
