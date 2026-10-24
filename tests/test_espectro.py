"""The example spectrum is versioned, validated, and the fit index is stable."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from curia_maxima import espectro

ESTATICOS = Path(__file__).resolve().parents[1] / "web" / "estaticos"
CERO = dict.fromkeys(espectro.EJES, 0.0)
UNO = dict.fromkeys(espectro.EJES, 1.0)
MENOS_UNO = dict.fromkeys(espectro.EJES, -1.0)


def test_los_archivos_de_ejemplo_cumplen_el_esquema() -> None:
    cargado = espectro.cargar()
    publico = cargado["publico"]
    assert publico["ejemplo"] is True
    assert publico["cuestionario_id"] == "ejemplo-1"
    assert [eje["id"] for eje in publico["ejes"]] == list(espectro.EJES)
    assert len(publico["afirmaciones"]) == 16
    assert len(publico["actores"]) == 6
    assert all(
        actor["ejemplo"] is True and "ejemplo" in actor["nombre"] for actor in publico["actores"]
    )
    assert all(item["origen"] == "ejemplo-local" for item in publico["propuestas_ejemplo"])
    assert "100" in publico["formula_frase"] and "0" in publico["formula_frase"]


def test_el_indice_es_100_si_coinciden_y_0_si_son_opuestos() -> None:
    assert espectro.ajuste(UNO, dict(UNO)) == 100
    assert espectro.ajuste(CERO, dict(CERO)) == 100
    assert espectro.ajuste(UNO, MENOS_UNO) == 0
    assert espectro.ajuste(CERO, UNO) == 50


def test_el_medio_sube_y_no_usa_el_redondeo_del_banquero() -> None:
    assert espectro.redondear_mitad_arriba(87.5) == 88
    assert espectro.redondear_mitad_arriba(88.5) == 89
    assert espectro.redondear_mitad_arriba(-10) == 0
    assert espectro.redondear_mitad_arriba(140) == 100
    persona = dict(CERO)
    posicion = dict(CERO)
    posicion["economia"] = 1
    assert espectro.ajuste(persona, posicion) == 88


def test_el_vector_promedia_el_sentido_de_cada_eje() -> None:
    cargado = espectro.cargar()
    afirmaciones = cargado["afirmaciones"]["afirmaciones"]
    hacia_positivo = {
        item["id"]: 5 if item["sentido"] == 1 else 1 for item in afirmaciones
    }
    assert espectro.vector_de_respuestas(afirmaciones, hacia_positivo) == dict.fromkeys(
        espectro.EJES, 1.0
    )
    neutras = {item["id"]: 3 for item in afirmaciones}
    assert espectro.vector_de_respuestas(afirmaciones, neutras) == dict.fromkeys(espectro.EJES, 0.0)
    assert espectro.ajuste(espectro.vector_de_respuestas(afirmaciones, neutras), UNO) == 50


def test_una_respuesta_invalida_no_arma_vector() -> None:
    with pytest.raises(espectro.ErrorDeEspectro):
        espectro.vector_de_respuestas(
            [{"id": "ej-01", "eje": "economia", "sentido": 1}],
            {},
            ejes=("economia",),
        )


def test_rechaza_un_actor_sin_la_marca_de_ejemplo(tmp_path: Path) -> None:
    destino = tmp_path / "espectro"
    shutil.copytree(espectro.directorio_datos(), destino)
    ruta = destino / "actores.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["actores"][0]["nombre"] = "Senadora Inventada"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(espectro.ErrorDeEspectro, match="esquema"):
        espectro.cargar(destino)


def test_rechaza_ejemplo_en_falso(tmp_path: Path) -> None:
    destino = tmp_path / "espectro"
    shutil.copytree(espectro.directorio_datos(), destino)
    ruta = destino / "ejes.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["ejemplo"] = False
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(espectro.ErrorDeEspectro):
        espectro.cargar(destino)


def test_la_formula_del_navegador_es_la_misma_y_no_hay_rastreo() -> None:
    js = (ESTATICOS / "espectro.js").read_text(encoding="utf-8")
    assert "100 * (1 - suma / (2 * ejes.length))" in js
    assert "Math.floor(acotado + 0.5)" in js
    assert "localStorage" in js
    assert "No se envían a ningún servidor" in js
    assert "fetch(" not in js
    assert "innerHTML" not in js
    for marca in ("sendBeacon", "XMLHttpRequest", "google-analytics", "navigator.send"):
        assert marca not in js
