# curia_maxima

curia_maxima es la plataforma de una cámara cívica chilena. Los bots personales de las personas consultan datos oficiales, perfilan candidatos y, más adelante, debaten y votan propuestas. Este repositorio contiene **solo el código de la herramienta**. Los datos, las propuestas y la normativa viven en repositorios públicos aparte, que todavía no están creados.

El costo de operación tiene que seguir en cero: planes gratuitos y GitHub Actions. Este repositorio no despliega servicios ni programa recolecciones.

## Cuatro piezas independientes

| Pieza | Dónde vive | Qué contiene |
| --- | --- | --- |
| Código de la cámara | Este repositorio | Esquema, validación y recolectores. Más adelante, el soporte para que los bots consulten, debatan y voten. Licencia MIT. |
| Propuestas | Repositorio propio, aún no creado | Textos de las propuestas, en CC0. El contenido cívico no queda atado a la licencia del código. |
| Datos y KPI validados | Repositorio propio, aún no creado | Series que escriben los recolectores. Este código no versiona esos archivos. |
| Normativa vigente | Repositorio propio, aún no creado | Textos normativos de referencia, separados de las propuestas y de los datos. |

Los recolectores escriben en una ruta que se elige al ejecutarlos (`--output` o la variable `CURIA_OUTPUT_DIR`). Esa ruta será, cuando exista, una copia del repositorio de datos. El código no asume que los datos están en este repositorio.

```text
bots personales
      |
      v
curia_maxima (este repo, código, MIT)
      |
      +-- escribe series --> repo de datos y KPI (ruta configurable)
      +-- leerá --> repo de propuestas (CC0)
      +-- leerá --> repo de normativa vigente
```

## Estructura de este repositorio

```text
.
├── LICENSE
├── README.md
├── pyproject.toml
├── src/curia_maxima/
│   ├── cli.py
│   ├── hashing.py
│   ├── store.py
│   ├── validation.py
│   ├── collectors/
│   │   └── ine_remuneraciones.py
│   └── schemas/
│       ├── observation.schema.json
│       └── series.schema.json
├── tests/
└── .github/workflows/ci.yml
```

`output/` y `data/` están en `.gitignore` por si alguien escribe dentro del clon. No son el lugar de los datos.

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

`pytest` valida los esquemas, el archivo que escribe el recolector y un cambio de formato simulado. Esas pruebas no llaman al INE. El flujo de GitHub Actions (`.github/workflows/ci.yml`) ejecuta lo mismo en cada pull request. No hay despliegue, cron ni secretos.

## Licencia

El código de este repositorio se publica bajo la licencia MIT. Ver [LICENSE](LICENSE).

MIT es una licencia abierta y simple de cumplir: quien use o modifique la herramienta puede hacerlo, incluida la copia del aviso de licencia. Sirve para este repositorio porque aquí está la herramienta, no el corpus cívico. Las propuestas irán en CC0 en su propio repositorio, y los datos y la normativa tendrán cada uno el suyo. Así los bots personales y esos repositorios pueden reutilizar el esquema y los recolectores sin obligaciones de copyleft.

La otra candidata era AGPL. Conviene volver a mirarla antes de aceptar contribuciones externas si el código futuro de debate y votación debe impedir que alguien opere una cámara modificada sin publicar el código. Mientras este repositorio es el recolector y el esquema, MIT mantiene el costo legal en el mínimo.
