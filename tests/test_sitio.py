"""The public site is assembled from repository snapshots, including when one source fails."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from curia_maxima import sitio

ESTATICOS = Path(__file__).resolve().parents[1] / "web" / "estaticos"
RASTREO = (
    "google-analytics",
    "googletagmanager",
    "googleadservices",
    "facebook.net",
    "doubleclick",
    "hotjar",
    "plausible.io",
    "fonts.googleapis",
    "cdn.jsdelivr",
)


class ClienteFalso:
    def __init__(self, mapa: dict[str, object]) -> None:
        self.mapa = mapa

    def texto(self, url: str) -> str:
        if url not in self.mapa:
            raise sitio.ErrorDeFuente(f"ausente en la prueba: {url}")
        valor = self.mapa[url]
        if isinstance(valor, sitio.ErrorDeFuente):
            raise valor
        if isinstance(valor, (dict, list)):
            return json.dumps(valor)
        return str(valor)

    def json(self, url: str) -> object:
        return json.loads(self.texto(url))


def _arbol(*rutas: str, truncated: bool = False) -> dict:
    return {
        "truncated": truncated,
        "tree": [{"path": ruta, "type": "blob"} for ruta in rutas],
    }


def _serie() -> dict:
    return {
        "series_id": "ine.ir2023.nacional.indice",
        "indicator": {"code": "IR2023", "name": "Índice de prueba"},
        "unit": "índice (base 2023=100)",
        "source": {
            "organism": "Instituto Nacional de Estadísticas (INE)",
            "url": "https://sdmx.ine.gob.cl/rest/data/ejemplo",
        },
        "status": "vigente",
        "error": None,
        "captured_at": "2026-10-23T21:07:22Z",
        "observations": [
            {"data_date": "2023-02-01", "value": 97.5},
            {"data_date": "2023-01-01", "value": 98.0},
            {"data_date": "2023-01-01", "value": 98.01},
            {"data_date": "mala", "value": 1},
            {"data_date": "2023-03-01", "value": True},
        ],
    }


def _propuesta() -> str:
    return """---
id: PROP-2026-000
titulo: "EJEMPLO — Publicación de los plazos"
tipo: nueva
estado: borrador
autores:
  - nombre: bot-ejemplo
    tipo: bot
fecha: 2026-10-23
normas_relacionadas:
  - id: ley-19880
    titulo: "Ley N° 19.880"
    enlace: https://example.com/ley
    relacion: complementa
kpis_relacionados:
  - id: plazo-mediano
    descripcion: "Mediana de días hábiles entre ingreso y resolución."
historial_adopcion: []
ejemplo: true
---

> **EJEMPLO.** No es una propuesta real.

1. **Un fundamento.** Sigue el texto.
2. Otro punto.

Artículo 1°.- Texto con <script>alert(1)</script> y [malo](javascript:alert(1)) y [bien](https://example.com/a?q=1&x=2).
"""


def _norma(identificador: str, estado: str, fecha: str, derogada_por: str | None) -> dict:
    return {
        "id": identificador,
        "tipo": "ley",
        "numero": "21206",
        "titulo": f"TITULO {identificador}",
        "organismo": "MINISTERIO",
        "fecha_publicacion": fecha,
        "estado": estado,
        "derogada_por": derogada_por,
        "fuente": "https://www.bcn.cl/leychile/navegar?idNorma=1",
        "version": fecha,
        "texto": "Texto de la norma.",
    }


def _mapa() -> dict[str, object]:
    return {
        sitio.url_arbol(sitio.REPO_DATOS): _arbol(
            "series/ine.ir2023.nacional.indice.json",
            "README.md",
            "series/anidada/no.json",
        ),
        sitio.url_crudo(sitio.REPO_DATOS, "series/ine.ir2023.nacional.indice.json"): _serie(),
        sitio.url_arbol(sitio.REPO_PROPUESTAS): _arbol(
            "propuestas/EJEMPLO-PROP-2026-000.md",
            "propuestas/rota.md",
            "plantillas/propuesta.md",
        ),
        sitio.url_crudo(
            sitio.REPO_PROPUESTAS, "propuestas/EJEMPLO-PROP-2026-000.md"
        ): _propuesta(),
        sitio.url_crudo(sitio.REPO_PROPUESTAS, "propuestas/rota.md"): "sin encabezado\n",
        sitio.url_arbol(sitio.REPO_NORMATIVAS): _arbol(
            "normas/congreso/ley-21206/2020-01-27.json",
            "normas/congreso/ley-21695/2024-10-10.json",
            "tests/fixtures/norma-invalida.json",
        ),
        sitio.url_crudo(
            sitio.REPO_NORMATIVAS, "normas/congreso/ley-21206/2020-01-27.json"
        ): _norma("ley-21206", "derogada", "2020-01-27", "ley-21477"),
        sitio.url_crudo(
            sitio.REPO_NORMATIVAS, "normas/congreso/ley-21695/2024-10-10.json"
        ): _norma("ley-21695", "vigente", "2024-10-10", None),
    }


def test_arma_las_tres_secciones_y_escapa_el_texto(tmp_path: Path) -> None:
    documento = sitio.armar_documento(ClienteFalso(_mapa()), ahora="2026-10-24T03:00:00Z")
    serie = documento["indicadores"]["series"][0]
    assert documento["generado_en"] == "2026-10-24T03:00:00Z"
    assert serie["codigo"] == "IR2023"
    assert serie["puntos"] == [
        {"fecha": "2023-01-01", "valor": 98.01},
        {"fecha": "2023-02-01", "valor": 97.5},
    ]
    assert serie["ultimo"]["valor"] == 97.5
    assert serie["url_fuente"] == "https://sdmx.ine.gob.cl/rest/data/ejemplo"
    propuesta = documento["propuestas"]["items"][0]
    assert propuesta["fecha"] == "2026-10-23"
    assert propuesta["ejemplo"] is True
    assert propuesta["autores"] == [{"nombre": "bot-ejemplo", "tipo": "bot"}]
    assert "<script>" not in propuesta["cuerpo_html"]
    assert "&lt;script&gt;" in propuesta["cuerpo_html"]
    assert 'href="javascript:' not in propuesta["cuerpo_html"]
    assert "[malo](javascript:alert(1))" in propuesta["cuerpo_html"]
    assert 'href="https://example.com/a?q=1&amp;x=2"' in propuesta["cuerpo_html"]
    assert "<strong>EJEMPLO.</strong>" in propuesta["cuerpo_html"]
    assert "<strong>Un fundamento.</strong>" in propuesta["cuerpo_html"]
    assert documento["propuestas"]["errores"] == [
        "propuestas/rota.md: el encabezado no se pudo leer."
    ]
    ids = [item["id"] for item in documento["normas"]["items"]]
    assert ids == ["ley-21695", "ley-21206"]
    assert documento["normas"]["items"][1]["derogada_por"] == "ley-21477"
    assert sitio.codigo_salida(documento) == 0

    sitio.publicar(tmp_path, documento, ESTATICOS)
    escrito = json.loads((tmp_path / "datos.json").read_text(encoding="utf-8"))
    assert "Índice de prueba" in (tmp_path / "datos.json").read_text(encoding="utf-8")
    assert escrito["propuestas"]["items"][0]["titulo"].startswith("EJEMPLO")
    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "sitio.js").is_file()


def test_un_repositorio_caido_no_borra_las_otras_secciones() -> None:
    mapa = _mapa()
    mapa[sitio.url_arbol(sitio.REPO_DATOS)] = sitio.ErrorDeFuente(
        "GitHub respondió con HTTP 503.", reintentar=True
    )
    documento = sitio.armar_documento(ClienteFalso(mapa), ahora="2026-10-24T03:00:00Z")
    assert documento["indicadores"]["ok"] is False
    assert "curia_datos" in documento["indicadores"]["aviso"]
    assert documento["indicadores"]["series"] == []
    assert documento["propuestas"]["ok"] is True
    assert documento["normas"]["ok"] is True
    assert sitio.codigo_salida(documento) == 0


def test_si_fallan_las_tres_fuentes_el_trabajo_no_publica() -> None:
    mapa = {
        sitio.url_arbol(sitio.REPO_DATOS): sitio.ErrorDeFuente("sin red"),
        sitio.url_arbol(sitio.REPO_PROPUESTAS): sitio.ErrorDeFuente("sin red"),
        sitio.url_arbol(sitio.REPO_NORMATIVAS): sitio.ErrorDeFuente("sin red"),
    }
    documento = sitio.armar_documento(ClienteFalso(mapa))
    assert sitio.codigo_salida(documento) == 1
    assert all(not documento[nombre]["ok"] for nombre in ("indicadores", "propuestas", "normas"))


def test_listado_truncado_se_rechaza() -> None:
    mapa = _mapa()
    mapa[sitio.url_arbol(sitio.REPO_NORMATIVAS)] = _arbol("normas/a.json", truncated=True)
    documento = sitio.armar_documento(ClienteFalso(mapa))
    assert documento["normas"]["ok"] is False
    assert "truncado" in documento["normas"]["aviso"]


def test_serie_no_actualizada_conserva_el_error_y_el_valor() -> None:
    serie = _serie()
    serie["status"] = "no actualizado"
    serie["error"] = "Fuente no disponible: tiempo de espera agotado"
    mapa = _mapa()
    mapa[sitio.url_crudo(sitio.REPO_DATOS, "series/ine.ir2023.nacional.indice.json")] = serie
    documento = sitio.armar_documento(ClienteFalso(mapa))
    publicada = documento["indicadores"]["series"][0]
    assert publicada["estado"] == "no actualizado"
    assert "tiempo de espera" in publicada["error"]
    assert publicada["ultimo"]["fecha"] == "2023-02-01"


def test_rechaza_enlaces_que_no_son_https() -> None:
    assert sitio.https_url("javascript:alert(1)") is None
    assert sitio.https_url("http://example.com") is None
    assert sitio.https_url("https://example.com/a") == "https://example.com/a"


def test_repositorio_vacio_avisa_sin_marcar_fallo() -> None:
    mapa = _mapa()
    mapa[sitio.url_arbol(sitio.REPO_PROPUESTAS)] = _arbol("README.md")
    documento = sitio.armar_documento(ClienteFalso(mapa))
    assert documento["propuestas"]["ok"] is True
    assert documento["propuestas"]["items"] == []
    assert "no tiene propuestas" in documento["propuestas"]["aviso"]


def test_la_salida_no_puede_ser_la_raiz() -> None:
    with pytest.raises(sitio.ErrorDeSitio):
        sitio.preparar_destino(Path("/"))


def test_main_exige_la_carpeta_de_salida() -> None:
    with pytest.raises(SystemExit):
        sitio.main([])


def test_estaticos_no_cargan_rastreadores() -> None:
    for nombre in ("index.html", "estilos.css", "sitio.js"):
        texto = (ESTATICOS / nombre).read_text(encoding="utf-8").lower()
        for marca in RASTREO:
            assert marca not in texto
    html = (ESTATICOS / "index.html").read_text(encoding="utf-8")
    assert 'lang="es"' in html
    assert "Indicadores" in html and "Propuestas" in html and "Normas" in html
    assert "CC0" in html and "MIT" in html
    assert "piloto" in html.lower()


class _Respuesta:
    def __init__(self, cuerpo: bytes) -> None:
        self._cuerpo = cuerpo

    def read(self, cantidad: int = -1) -> bytes:
        if cantidad < 0 or cantidad >= len(self._cuerpo):
            datos, self._cuerpo = self._cuerpo, b""
            return datos
        datos, self._cuerpo = self._cuerpo[:cantidad], self._cuerpo[cantidad:]
        return datos

    def __enter__(self) -> _Respuesta:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_el_token_solo_viaja_a_la_api(monkeypatch: pytest.MonkeyPatch) -> None:
    vistas: list[tuple[str, str | None]] = []

    def abrir(solicitud: urllib.request.Request, timeout: float = 0) -> _Respuesta:
        vistas.append((solicitud.full_url, solicitud.get_header("Authorization")))
        return _Respuesta(b"ok")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args, **kwargs: type(
        "Opener", (), {"open": staticmethod(abrir)}
    )())
    cliente = sitio.ClienteHTTP(token="secreto-no-publicar", reintentos=1)
    assert cliente.texto("https://raw.githubusercontent.com/a/b/main/c.txt") == "ok"
    assert cliente.texto("https://api.github.com/repos/a/b") == "ok"
    assert vistas[0][1] is None
    assert vistas[1][1] == "Bearer secreto-no-publicar"


def test_404_no_se_reintenta_y_503_si(monkeypatch: pytest.MonkeyPatch) -> None:
    llamadas = {"n": 0, "inestable": 0}

    def abrir(solicitud: urllib.request.Request, timeout: float = 0) -> _Respuesta:
        llamadas["n"] += 1
        if "falta" in solicitud.full_url:
            raise urllib.error.HTTPError(solicitud.full_url, 404, "no", hdrs=None, fp=None)
        if "inestable" in solicitud.full_url and llamadas["inestable"] < 1:
            llamadas["inestable"] += 1
            raise urllib.error.HTTPError(solicitud.full_url, 503, "no", hdrs=None, fp=None)
        return _Respuesta(b'{"ok": true}')

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args, **kwargs: type(
        "Opener", (), {"open": staticmethod(abrir)}
    )())
    cliente = sitio.ClienteHTTP(reintentos=2, espera=0)
    with pytest.raises(sitio.ErrorDeFuente, match="404"):
        cliente.texto("https://example.com/falta")
    assert llamadas["n"] == 1
    assert cliente.json("https://example.com/inestable") == {"ok": True}
    assert llamadas["n"] == 3


def test_no_sigue_redirecciones(monkeypatch: pytest.MonkeyPatch) -> None:
    def abrir(solicitud: urllib.request.Request, timeout: float = 0) -> _Respuesta:
        raise urllib.error.HTTPError(solicitud.full_url, 302, "redir", hdrs=None, fp=None)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args, **kwargs: type(
        "Opener", (), {"open": staticmethod(abrir)}
    )())
    cliente = sitio.ClienteHTTP(token="secreto-no-publicar", reintentos=2, espera=0)
    with pytest.raises(sitio.ErrorDeFuente, match="redirección") as exc:
        cliente.texto("https://api.github.com/repos/a/b")
    assert "secreto-no-publicar" not in str(exc.value)
