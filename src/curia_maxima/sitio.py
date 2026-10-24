"""Build the read-only public site from the other public repositories.

The browser never calls GitHub. A workflow downloads the series, the proposals
and the norms, writes ``datos.json`` next to the static files, and Pages
serves that snapshot. Listing those repos from the browser would spend the
unauthenticated API quota (60 requests per hour per IP) and the page would
fail for visitors. See the README.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlparse

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only when the extra is missing
    yaml = None

REPO_DATOS = "nlecarosg/curia_datos"
REPO_PROPUESTAS = "nlecarosg/curia_propuestas"
REPO_NORMATIVAS = "nlecarosg/curia_normativas"
RAMA = "main"
MAX_BYTES = 1_500_000
USER_AGENT = "curia-maxima-sitio"
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HTTPS = re.compile(r"^https://[^\s\"'<>]+$")
_ORDEN_NORMA = {"vigente": 0, "modificada": 1, "derogada": 2}


class ErrorDeFuente(Exception):
    """A public repository could not be read. ``aviso`` is safe to publish."""

    def __init__(self, aviso: str, *, reintentar: bool = False) -> None:
        super().__init__(aviso)
        self.aviso = aviso
        self.reintentar = reintentar


class ErrorDeSitio(Exception):
    """The local site files could not be written. Not a data-source failure."""


class Lector(Protocol):
    def texto(self, url: str) -> str: ...

    def json(self, url: str) -> Any: ...


class _SinRedireccion(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so an API token cannot be forwarded to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code, "redirección no seguida", headers, fp
        )


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def token_desde_entorno() -> str | None:
    """Read the automatic Actions token. Never taken from the command line."""
    for clave in ("GITHUB_TOKEN", "GH_TOKEN"):
        valor = os.environ.get(clave, "").strip()
        if valor:
            return valor
    return None


def url_arbol(repo: str) -> str:
    return f"https://api.github.com/repos/{repo}/git/trees/{RAMA}?recursive=1"


def url_crudo(repo: str, ruta: str) -> str:
    camino = "/".join(quote(parte) for parte in ruta.split("/"))
    return f"https://raw.githubusercontent.com/{repo}/{RAMA}/{camino}"


def url_blob(repo: str, ruta: str) -> str:
    camino = "/".join(quote(parte) for parte in ruta.split("/"))
    return f"https://github.com/{repo}/blob/{RAMA}/{camino}"


def url_repo(repo: str) -> str:
    return f"https://github.com/{repo}"


def https_url(valor: object) -> str | None:
    if isinstance(valor, str) and _HTTPS.fullmatch(valor):
        return valor
    return None


def como_texto(valor: object) -> str | None:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, str):
        limpio = valor.strip()
        return limpio or None
    if isinstance(valor, int) and not isinstance(valor, bool):
        return str(valor)
    return None


class ClienteHTTP:
    """GET https URLs. Retries timeouts and 429/5xx. Does not follow redirects."""

    def __init__(
        self,
        token: str | None = None,
        timeout: float = 20.0,
        reintentos: int = 3,
        espera: float = 1.0,
    ) -> None:
        self.token = token.strip() if token else None
        self.timeout = timeout
        self.reintentos = max(1, reintentos)
        self.espera = espera

    def texto(self, url: str) -> str:
        datos = self._bytes(url)
        try:
            return datos.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ErrorDeFuente("La respuesta no es texto UTF-8.") from exc

    def json(self, url: str) -> Any:
        crudo = self.texto(url)
        try:
            return json.loads(crudo)
        except json.JSONDecodeError as exc:
            raise ErrorDeFuente("La respuesta no es JSON válido.") from exc

    def _bytes(self, url: str) -> bytes:
        ultimo: ErrorDeFuente | None = None
        for intento in range(self.reintentos):
            try:
                return self._una_vez(url)
            except ErrorDeFuente as exc:
                ultimo = exc
                if not exc.reintentar or intento + 1 >= self.reintentos:
                    break
                time.sleep(self.espera * (2**intento))
        if ultimo is None:  # pragma: no cover - the loop always assigns on failure
            raise ErrorDeFuente("No se pudo leer la dirección.")
        raise ultimo

    def _una_vez(self, url: str) -> bytes:
        partes = urlparse(url)
        if partes.scheme != "https":
            raise ErrorDeFuente("Solo se consultan direcciones https.")
        solicitud = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json, application/json, text/plain;q=0.9",
            },
        )
        if self.token and partes.netloc == "api.github.com":
            solicitud.add_header("Authorization", f"Bearer {self.token}")
        opener = urllib.request.build_opener(_SinRedireccion())
        try:
            with opener.open(solicitud, timeout=self.timeout) as respuesta:
                return _leer_limitado(respuesta)
        except TimeoutError as exc:
            raise ErrorDeFuente(
                "El repositorio no respondió a tiempo.", reintentar=True
            ) from exc
        except urllib.error.HTTPError as exc:
            codigo = exc.code
            exc.close()
            if 300 <= codigo < 400:
                raise ErrorDeFuente(
                    "La dirección respondió con una redirección y no se siguió."
                ) from exc
            raise ErrorDeFuente(
                _mensaje_http(codigo),
                reintentar=codigo == 429 or codigo >= 500,
            ) from exc
        except urllib.error.URLError as exc:
            raise ErrorDeFuente(
                "No se pudo conectar con el repositorio.", reintentar=True
            ) from exc


def _leer_limitado(respuesta: Any, limite: int = MAX_BYTES) -> bytes:
    partes: list[bytes] = []
    leido = 0
    while True:
        bloque = respuesta.read(65536)
        if not bloque:
            break
        leido += len(bloque)
        if leido > limite:
            raise ErrorDeFuente("El archivo publicado es demasiado grande para mostrarlo.")
        partes.append(bloque)
    return b"".join(partes)


def _mensaje_http(codigo: int) -> str:
    if codigo == 404:
        return "No se encontró lo publicado (HTTP 404)."
    if codigo in (403, 429):
        return f"GitHub limitó la consulta (HTTP {codigo})."
    return f"GitHub respondió con HTTP {codigo}."


def _aviso_repo(cual: str, exc: ErrorDeFuente) -> str:
    return f"No se pudo leer el repositorio {cual}. {exc.aviso}"


def _fallo(repo: str, aviso: str, *, series: bool = False) -> dict[str, Any]:
    seccion: dict[str, Any] = {
        "ok": False,
        "aviso": aviso,
        "repositorio": url_repo(repo),
        "errores": [],
    }
    if series:
        seccion["series"] = []
    else:
        seccion["items"] = []
    return seccion


def listar(cliente: Lector, repo: str) -> list[str]:
    arbol = cliente.json(url_arbol(repo))
    if not isinstance(arbol, dict) or not isinstance(arbol.get("tree"), list):
        raise ErrorDeFuente("El listado del repositorio no tiene el formato esperado.")
    if arbol.get("truncated"):
        raise ErrorDeFuente(
            "El listado del repositorio vino truncado. No se muestra una lista incompleta."
        )
    rutas: list[str] = []
    for nodo in arbol["tree"]:
        if (
            isinstance(nodo, dict)
            and nodo.get("type") == "blob"
            and isinstance(nodo.get("path"), str)
        ):
            rutas.append(nodo["path"])
    return rutas


def es_serie(ruta: str) -> bool:
    partes = ruta.split("/")
    return len(partes) == 2 and partes[0] == "series" and partes[1].endswith(".json")


def es_propuesta(ruta: str) -> bool:
    partes = ruta.split("/")
    return len(partes) == 2 and partes[0] == "propuestas" and partes[1].endswith(".md")


def es_norma(ruta: str) -> bool:
    partes = ruta.split("/")
    return ruta.startswith("normas/") and ruta.endswith(".json") and ".." not in partes


def _fecha_inversa(fecha: str | None) -> tuple[int, int, int]:
    numeros: list[int] = []
    for parte in (fecha or "").split("-")[:3]:
        try:
            numeros.append(-int(parte))
        except ValueError:
            numeros.append(0)
    while len(numeros) < 3:
        numeros.append(0)
    return (numeros[0], numeros[1], numeros[2])


def serie_publica(documento: dict[str, Any], ruta: str) -> dict[str, Any]:
    observaciones = documento.get("observations")
    if not isinstance(observaciones, list):
        raise ValueError("sin observaciones")
    por_fecha: dict[str, int | float] = {}
    for obs in observaciones:
        if not isinstance(obs, dict):
            continue
        fecha = obs.get("data_date")
        valor = obs.get("value")
        if not isinstance(fecha, str) or not _FECHA.fullmatch(fecha):
            continue
        if isinstance(valor, bool) or not isinstance(valor, int | float):
            continue
        por_fecha[fecha] = valor
    puntos = [{"fecha": fecha, "valor": por_fecha[fecha]} for fecha in sorted(por_fecha)]
    indicador = documento.get("indicator")
    if not isinstance(indicador, dict):
        indicador = {}
    fuente = documento.get("source")
    if not isinstance(fuente, dict):
        fuente = {}
    error = documento.get("error")
    if not isinstance(error, str) or not error.strip():
        error = None
    estado = documento.get("status")
    if not isinstance(estado, str) or not estado.strip():
        estado = "desconocido"
    identificador = documento.get("series_id")
    if not isinstance(identificador, str) or not identificador.strip():
        identificador = ruta
    return {
        "id": identificador,
        "codigo": como_texto(indicador.get("code")) or "",
        "nombre": como_texto(indicador.get("name")) or ruta,
        "unidad": como_texto(documento.get("unit")) or "",
        "estado": estado.strip(),
        "error": error.strip() if isinstance(error, str) else None,
        "capturado_en": como_texto(documento.get("captured_at")),
        "organismo": como_texto(fuente.get("organism")) or "",
        "url_fuente": https_url(fuente.get("url")),
        "enlace_repositorio": url_blob(REPO_DATOS, ruta),
        "ultimo": puntos[-1] if puntos else None,
        "puntos": puntos,
    }


def leer_indicadores(cliente: Lector) -> dict[str, Any]:
    try:
        rutas = sorted(ruta for ruta in listar(cliente, REPO_DATOS) if es_serie(ruta))
    except ErrorDeFuente as exc:
        return _fallo(REPO_DATOS, _aviso_repo("de datos (curia_datos)", exc), series=True)
    series: list[dict[str, Any]] = []
    errores: list[str] = []
    for ruta in rutas:
        try:
            documento = json.loads(cliente.texto(url_crudo(REPO_DATOS, ruta)))
            if not isinstance(documento, dict):
                raise ValueError("no es un objeto")
            series.append(serie_publica(documento, ruta))
        except ErrorDeFuente as exc:
            errores.append(f"{ruta}: {exc.aviso}")
        except (ValueError, json.JSONDecodeError):
            errores.append(f"{ruta}: no se pudo leer la serie.")
    series.sort(key=lambda item: (item.get("codigo") or "", item.get("id") or ""))
    if not rutas:
        aviso = "El repositorio de datos no tiene series publicadas."
        ok = True
    elif not series:
        aviso = "No se pudo interpretar ninguna serie. " + errores[0]
        ok = False
    else:
        aviso = None
        ok = True
    return {
        "ok": ok,
        "aviso": aviso,
        "repositorio": url_repo(REPO_DATOS),
        "series": series,
        "errores": errores,
    }


def _cargar_yaml(texto: str) -> Any:
    if yaml is None:
        raise ErrorDeFuente("Falta PyYAML para leer el encabezado.")
    cargador = _cargador_yaml()
    return yaml.load(texto, Loader=cargador)


def _cargador_yaml() -> type[Any]:
    """Safe loader that keeps dates as strings (``2026-10-23`` must not become a date)."""
    assert yaml is not None

    class Cargador(yaml.SafeLoader):
        pass

    resolvers = {
        clave: [
            (etiqueta, patron)
            for etiqueta, patron in entradas
            if etiqueta != "tag:yaml.org,2002:timestamp"
        ]
        for clave, entradas in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    Cargador.yaml_implicit_resolvers = resolvers
    return Cargador


def separar_front_matter(texto: str) -> tuple[dict[str, Any], str]:
    normalizado = texto.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not normalizado.startswith("---\n"):
        raise ValueError("sin encabezado")
    resto = normalizado[4:]
    cierre = resto.find("\n---")
    if cierre < 0:
        raise ValueError("encabezado incompleto")
    encabezado = resto[:cierre]
    cuerpo = resto[cierre + 4 :]
    if cuerpo.startswith("\n"):
        cuerpo = cuerpo[1:]
    datos = _cargar_yaml(encabezado)
    if not isinstance(datos, dict):
        raise ValueError("el encabezado no es un mapa")
    return datos, cuerpo.strip()


def _lista_de_mapas(valor: object) -> list[dict[str, Any]]:
    if not isinstance(valor, list):
        return []
    return [item for item in valor if isinstance(item, dict)]


def propuesta_publica(texto: str, ruta: str) -> dict[str, Any]:
    meta, cuerpo = separar_front_matter(texto)
    titulo = como_texto(meta.get("titulo"))
    if not titulo:
        raise ValueError("sin título")
    identificador = como_texto(meta.get("id")) or Path(ruta).stem
    return {
        "id": identificador,
        "titulo": titulo,
        "tipo": como_texto(meta.get("tipo")) or "",
        "estado": como_texto(meta.get("estado")) or "",
        "autores": [
            {"nombre": nombre, "tipo": como_texto(item.get("tipo")) or ""}
            for item in _lista_de_mapas(meta.get("autores"))
            if (nombre := como_texto(item.get("nombre")))
        ],
        "fecha": como_texto(meta.get("fecha")),
        "normas_relacionadas": [
            {
                "id": como_texto(item.get("id")) or "",
                "titulo": titulo_norma,
                "enlace": https_url(item.get("enlace")),
                "relacion": como_texto(item.get("relacion")) or "",
            }
            for item in _lista_de_mapas(meta.get("normas_relacionadas"))
            if (titulo_norma := como_texto(item.get("titulo")))
        ],
        "kpis_relacionados": [
            {"id": como_texto(item.get("id")) or "", "descripcion": descripcion}
            for item in _lista_de_mapas(meta.get("kpis_relacionados"))
            if (descripcion := como_texto(item.get("descripcion")))
        ],
        "historial_adopcion": [
            {
                "fecha": como_texto(item.get("fecha")),
                "legislador": como_texto(item.get("legislador")) or "",
                "cargo": como_texto(item.get("cargo")) or "",
                "accion": como_texto(item.get("accion")) or "",
                "referencia": como_texto(item.get("referencia")),
                "enlace": https_url(item.get("enlace")),
            }
            for item in _lista_de_mapas(meta.get("historial_adopcion"))
            if como_texto(item.get("legislador")) or como_texto(item.get("accion"))
        ],
        "ejemplo": meta.get("ejemplo") is True,
        "cuerpo_html": markdown_a_html(cuerpo),
        "enlace_repositorio": url_blob(REPO_PROPUESTAS, ruta),
    }


def leer_propuestas(cliente: Lector) -> dict[str, Any]:
    try:
        rutas = sorted(ruta for ruta in listar(cliente, REPO_PROPUESTAS) if es_propuesta(ruta))
    except ErrorDeFuente as exc:
        return _fallo(REPO_PROPUESTAS, _aviso_repo("de propuestas (curia_propuestas)", exc))
    if yaml is None:
        return _fallo(
            REPO_PROPUESTAS,
            "No se pudo leer el repositorio de propuestas (curia_propuestas). "
            "Falta PyYAML en el armado del sitio.",
        )
    items: list[dict[str, Any]] = []
    errores: list[str] = []
    for ruta in rutas:
        try:
            items.append(propuesta_publica(cliente.texto(url_crudo(REPO_PROPUESTAS, ruta)), ruta))
        except ErrorDeFuente as exc:
            errores.append(f"{ruta}: {exc.aviso}")
        except (ValueError, yaml.YAMLError):
            errores.append(f"{ruta}: el encabezado no se pudo leer.")
    items.sort(key=lambda item: (_fecha_inversa(item.get("fecha")), item.get("id") or ""))
    return _cerrar_items(REPO_PROPUESTAS, rutas, items, errores, "propuestas")


def norma_publica(documento: dict[str, Any], ruta: str) -> dict[str, Any]:
    titulo = como_texto(documento.get("titulo"))
    identificador = como_texto(documento.get("id"))
    if not titulo or not identificador:
        raise ValueError("faltan id o título")
    derogada = documento.get("derogada_por")
    if isinstance(derogada, str):
        derogada = derogada.strip() or None
    else:
        derogada = None
    texto = documento.get("texto")
    return {
        "id": identificador,
        "tipo": como_texto(documento.get("tipo")) or "",
        "numero": como_texto(documento.get("numero")) or "",
        "titulo": titulo,
        "organismo": como_texto(documento.get("organismo")) or "",
        "fecha_publicacion": como_texto(documento.get("fecha_publicacion")),
        "estado": como_texto(documento.get("estado")) or "",
        "derogada_por": derogada,
        "fuente": https_url(documento.get("fuente")),
        "version": como_texto(documento.get("version")),
        "texto": texto if isinstance(texto, str) else "",
        "enlace_repositorio": url_blob(REPO_NORMATIVAS, ruta),
    }


def leer_normas(cliente: Lector) -> dict[str, Any]:
    try:
        rutas = sorted(ruta for ruta in listar(cliente, REPO_NORMATIVAS) if es_norma(ruta))
    except ErrorDeFuente as exc:
        return _fallo(REPO_NORMATIVAS, _aviso_repo("de normativas (curia_normativas)", exc))
    items: list[dict[str, Any]] = []
    errores: list[str] = []
    for ruta in rutas:
        try:
            documento = json.loads(cliente.texto(url_crudo(REPO_NORMATIVAS, ruta)))
            if not isinstance(documento, dict):
                raise ValueError("no es un objeto")
            items.append(norma_publica(documento, ruta))
        except ErrorDeFuente as exc:
            errores.append(f"{ruta}: {exc.aviso}")
        except (ValueError, json.JSONDecodeError):
            errores.append(f"{ruta}: no se pudo leer la norma.")
    items.sort(
        key=lambda item: (
            _ORDEN_NORMA.get(item.get("estado") or "", 9),
            _fecha_inversa(item.get("fecha_publicacion")),
            item.get("id") or "",
        )
    )
    return _cerrar_items(REPO_NORMATIVAS, rutas, items, errores, "normas")


def _cerrar_items(
    repo: str,
    rutas: list[str],
    items: list[dict[str, Any]],
    errores: list[str],
    vacio: str,
) -> dict[str, Any]:
    if not rutas:
        return {
            "ok": True,
            "aviso": f"El repositorio no tiene {vacio} publicadas.",
            "repositorio": url_repo(repo),
            "items": [],
            "errores": [],
        }
    if not items:
        return {
            "ok": False,
            "aviso": "No se pudo interpretar ningún archivo. " + errores[0],
            "repositorio": url_repo(repo),
            "items": [],
            "errores": errores,
        }
    return {
        "ok": True,
        "aviso": None,
        "repositorio": url_repo(repo),
        "items": items,
        "errores": errores,
    }


def _en_linea(texto: str) -> str:
    seguro = html.escape(texto, quote=True)
    seguro = re.sub(
        r"\[([^\]]+)\]\((https://[^\s)]+)\)",
        lambda coincidencia: (
            f'<a href="{coincidencia.group(2)}">{coincidencia.group(1)}</a>'
        ),
        seguro,
    )
    seguro = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", seguro)
    seguro = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        r"<em>\1</em>",
        seguro,
    )
    return seguro


def markdown_a_html(texto: str) -> str:
    """Render the small Markdown subset used by proposals. HTML in the source is escaped."""
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    bloques: list[str] = []
    parrafo: list[str] = []
    indice = 0

    def cerrar_parrafo() -> None:
        if parrafo:
            bloques.append("<p>" + " ".join(_en_linea(linea) for linea in parrafo) + "</p>")
            parrafo.clear()

    while indice < len(lineas):
        linea = lineas[indice]
        if not linea.strip():
            cerrar_parrafo()
            indice += 1
            continue
        nivel = 0
        while nivel < len(linea) and linea[nivel] == "#":
            nivel += 1
        if 1 <= nivel <= 3 and linea[nivel : nivel + 1] == " ":
            cerrar_parrafo()
            bloques.append(
                f"<h{nivel}>{_en_linea(linea[nivel + 1 :].strip())}</h{nivel}>"
            )
            indice += 1
            continue
        if linea.startswith("> "):
            cerrar_parrafo()
            citas: list[str] = []
            while indice < len(lineas) and lineas[indice].startswith("> "):
                citas.append(_en_linea(lineas[indice][2:].strip()))
                indice += 1
            bloques.append("<blockquote><p>" + " ".join(citas) + "</p></blockquote>")
            continue
        if re.match(r"^\d+\. ", linea):
            cerrar_parrafo()
            elementos: list[str] = []
            while indice < len(lineas) and re.match(r"^\d+\. ", lineas[indice]):
                elementos.append(_en_linea(re.sub(r"^\d+\. ", "", lineas[indice], count=1)))
                indice += 1
            bloques.append("<ol>" + "".join(f"<li>{item}</li>" for item in elementos) + "</ol>")
            continue
        if linea.startswith("- "):
            cerrar_parrafo()
            elementos = []
            while indice < len(lineas) and lineas[indice].startswith("- "):
                elementos.append(_en_linea(lineas[indice][2:].strip()))
                indice += 1
            bloques.append("<ul>" + "".join(f"<li>{item}</li>" for item in elementos) + "</ul>")
            continue
        parrafo.append(linea.strip())
        indice += 1
    cerrar_parrafo()
    return "\n".join(bloques)


def armar_documento(cliente: Lector, ahora: str | None = None) -> dict[str, Any]:
    return {
        "generado_en": ahora or utc_now(),
        "indicadores": leer_indicadores(cliente),
        "propuestas": leer_propuestas(cliente),
        "normas": leer_normas(cliente),
    }


def codigo_salida(documento: dict[str, Any]) -> int:
    """Fail the job only when every section failed, so one repo cannot wipe the site."""
    secciones = (documento["indicadores"], documento["propuestas"], documento["normas"])
    if all(not seccion.get("ok") for seccion in secciones):
        return 1
    return 0


def ruta_estaticos() -> Path:
    candidatos = [
        Path(__file__).resolve().parents[2] / "web" / "estaticos",
        Path.cwd() / "web" / "estaticos",
    ]
    for candidato in candidatos:
        if (candidato / "index.html").is_file():
            return candidato
    raise ErrorDeSitio("No se encuentran los archivos estáticos en web/estaticos.")


def preparar_destino(destino: Path) -> Path:
    resuelto = destino.expanduser().resolve()
    if resuelto == Path(resuelto.anchor):
        raise ErrorDeSitio("La carpeta de salida no puede ser la raíz del sistema.")
    return resuelto


def publicar(destino: Path, documento: dict[str, Any], estaticos: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for archivo in sorted(estaticos.iterdir()):
        if archivo.is_file():
            shutil.copyfile(archivo, destino / archivo.name)
    (destino / "datos.json").write_text(
        json.dumps(documento, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m curia_maxima.sitio",
        description=(
            "Arma el sitio estático de lectura pública a partir de los repositorios "
            "públicos de datos, propuestas y normativas."
        ),
    )
    parser.add_argument("--salida", required=True, help="Carpeta donde se escribe el sitio.")
    parser.add_argument(
        "--estaticos",
        help="Carpeta con index.html, estilos.css y sitio.js. Por defecto, web/estaticos.",
    )
    args = parser.parse_args(argv)
    if yaml is None:
        print(
            "Falta PyYAML. Instálelo con: python -m pip install 'pyyaml>=6.0.2'",
            file=sys.stderr,
        )
        return 1
    try:
        estaticos = Path(args.estaticos) if args.estaticos else ruta_estaticos()
        if not (estaticos / "index.html").is_file():
            raise ErrorDeSitio(f"No está index.html en {estaticos}.")
        destino = preparar_destino(Path(args.salida))
        documento = armar_documento(ClienteHTTP(token=token_desde_entorno()))
        publicar(destino, documento, estaticos)
    except ErrorDeSitio as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    for nombre in ("indicadores", "propuestas", "normas"):
        seccion = documento[nombre]
        cantidad = len(seccion.get("series", seccion.get("items", [])))
        if seccion["ok"]:
            print(f"{nombre}: {cantidad}")
        else:
            print(f"{nombre}: {seccion['aviso']}", file=sys.stderr)
    print(f"Sitio escrito en {destino}")
    return codigo_salida(documento)


if __name__ == "__main__":
    sys.exit(main())
