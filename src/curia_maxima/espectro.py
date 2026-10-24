"""Example political spectrum: axes, questionnaire, fit index.

The fit index, in one sentence: it is the percentage of closeness between
two positions, 100 when they match on every axis and 0 when they sit on
opposite poles.

.. code-block:: text

    ajuste = redondear(100 × (1 − Σ|pᵢ − qᵢ| / (2n)))

``p`` is the person, ``q`` is a proposal or an actor, ``n`` is the number of
axes, and each coordinate is in [−1, +1]. The distance on one axis is at most
2. Halves round up (0.5 goes to the next integer). The same expression lives
in ``web/estaticos/espectro.js``.

A person's coordinate on an axis is the mean of ``(respuesta − 3) / 2`` times
the statement's ``sentido`` (+1 or −1). Answers use the Likert values 1…5.

Answers never reach this module. The browser keeps them in localStorage.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

EJES = ("economia", "libertades", "estado", "territorio")
ARCHIVOS = {
    "ejes": "ejes.json",
    "afirmaciones": "afirmaciones.json",
    "actores": "actores.json",
    "posiciones": "posiciones.json",
    "propuestasEjemplo": "propuestas-ejemplo.json",
}


class ErrorDeEspectro(Exception):
    """The example spectrum files do not satisfy the contract."""


def directorio_datos() -> Path:
    candidatos = [
        Path(__file__).resolve().parents[2] / "datos" / "espectro",
        Path.cwd() / "datos" / "espectro",
    ]
    for candidato in candidatos:
        if (candidato / "ejes.json").is_file():
            return candidato
    raise ErrorDeEspectro("No se encuentran los datos de ejemplo en datos/espectro.")


def _esquema() -> dict[str, Any]:
    ruta = Path(__file__).resolve().parent / "schemas" / "espectro.schema.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def _validador(nombre: str) -> Draft202012Validator:
    esquema = _esquema()
    envoltura = {
        "$id": esquema["$id"],
        "$defs": esquema["$defs"],
        "$ref": f"#/$defs/{nombre}",
    }
    return Draft202012Validator(envoltura)


def validar_documento(nombre: str, documento: Any) -> None:
    """Raise ErrorDeEspectro if ``documento`` does not match one schema definition."""
    try:
        _validador(nombre).validate(documento)
    except ValidationError as exc:
        lugar = ".".join(str(parte) for parte in exc.absolute_path) or "raíz"
        raise ErrorDeEspectro(
            f"El archivo de {nombre} no cumple el esquema ({lugar}): {exc.message}"
        ) from exc


def redondear_mitad_arriba(valor: float) -> int:
    """Round half up after clamping to 0…100. Unlike Python's banker's round."""
    acotado = min(100.0, max(0.0, valor))
    return int(math.floor(acotado + 0.5))


def ajuste(
    persona: dict[str, float],
    posicion: dict[str, float],
    ejes: tuple[str, ...] | list[str] = EJES,
) -> int:
    """Return the 0–100 closeness of ``persona`` and ``posicion`` on ``ejes``."""
    if not ejes:
        raise ErrorDeEspectro("El índice necesita al menos un eje.")
    suma = 0.0
    for eje in ejes:
        try:
            suma += abs(float(persona[eje]) - float(posicion[eje]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ErrorDeEspectro(f"Falta la coordenada {eje} para el índice.") from exc
    bruto = 100.0 * (1.0 - suma / (2.0 * len(ejes)))
    return redondear_mitad_arriba(bruto)


def vector_de_respuestas(
    afirmaciones: list[dict[str, Any]],
    respuestas: dict[str, int],
    ejes: tuple[str, ...] | list[str] = EJES,
) -> dict[str, float]:
    """Map Likert answers to one coordinate per axis, in [−1, +1]."""
    grupos: dict[str, list[float]] = {eje: [] for eje in ejes}
    for afirmacion in afirmaciones:
        eje = afirmacion["eje"]
        if eje not in grupos:
            raise ErrorDeEspectro(f"La afirmación {afirmacion.get('id')} usa un eje desconocido.")
        valor = respuestas.get(afirmacion["id"])
        if valor not in (1, 2, 3, 4, 5):
            raise ErrorDeEspectro(f"Falta una respuesta válida para {afirmacion.get('id')}.")
        grupos[eje].append(((int(valor) - 3) / 2) * int(afirmacion["sentido"]))
    vector: dict[str, float] = {}
    for eje, valores in grupos.items():
        if not valores:
            raise ErrorDeEspectro(f"El eje {eje} no tiene afirmaciones.")
        vector[eje] = sum(valores) / len(valores)
    return vector


def _leer(directorio: Path, nombre: str) -> dict[str, Any]:
    ruta = directorio / ARCHIVOS[nombre]
    try:
        documento = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErrorDeEspectro(f"No se pudo leer {ruta.name}.") from exc
    validar_documento(nombre, documento)
    if not isinstance(documento, dict):
        raise ErrorDeEspectro(f"{ruta.name} no es un objeto.")
    return documento


def _exigir_ejemplo(documento: dict[str, Any], cual: str) -> None:
    if documento.get("ejemplo") is not True:
        raise ErrorDeEspectro(f"{cual} tiene que estar marcado como ejemplo.")


def _validar_cruces(
    ejes: dict[str, Any],
    afirmaciones: dict[str, Any],
    actores: dict[str, Any],
    posiciones: dict[str, Any],
    propuestas: dict[str, Any],
) -> None:
    for documento, cual in (
        (ejes, "ejes.json"),
        (afirmaciones, "afirmaciones.json"),
        (actores, "actores.json"),
        (posiciones, "posiciones.json"),
        (propuestas, "propuestas-ejemplo.json"),
    ):
        _exigir_ejemplo(documento, cual)
    if ejes["cuestionario_id"] != afirmaciones["cuestionario_id"]:
        raise ErrorDeEspectro("El identificador del cuestionario no coincide entre archivos.")
    ids_ejes = [eje["id"] for eje in ejes["ejes"]]
    if ids_ejes != list(EJES):
        raise ErrorDeEspectro(
            "Los ejes tienen que ser economía, libertades, Estado y territorio, en ese orden."
        )
    if len(afirmaciones["escala"]) != 5 or [item["valor"] for item in afirmaciones["escala"]] != [
        1,
        2,
        3,
        4,
        5,
    ]:
        raise ErrorDeEspectro("La escala tiene que ser 1, 2, 3, 4 y 5, en ese orden.")
    vistos: set[str] = set()
    por_eje = dict.fromkeys(EJES, 0)
    for afirmacion in afirmaciones["afirmaciones"]:
        if afirmacion["id"] in vistos:
            raise ErrorDeEspectro(f"Afirmación repetida: {afirmacion['id']}.")
        vistos.add(afirmacion["id"])
        por_eje[afirmacion["eje"]] += 1
    for eje, cuenta in por_eje.items():
        if cuenta < 3:
            raise ErrorDeEspectro(f"El eje {eje} necesita al menos 3 afirmaciones.")
    ids_actores: set[str] = set()
    for actor in actores["actores"]:
        if actor["ejemplo"] is not True:
            raise ErrorDeEspectro(f"El actor {actor['id']} tiene que estar marcado como ejemplo.")
        if actor["id"] in ids_actores:
            raise ErrorDeEspectro(f"Actor repetido: {actor['id']}.")
        ids_actores.add(actor["id"])
    ids_propuestas: set[str] = set()
    for item in propuestas["propuestas"]:
        if item["ejemplo"] is not True:
            raise ErrorDeEspectro(
                f"La propuesta {item['id']} tiene que estar marcada como ejemplo."
            )
        if item["id"] in ids_propuestas:
            raise ErrorDeEspectro(f"Propuesta de ejemplo repetida: {item['id']}.")
        ids_propuestas.add(item["id"])
        _fecha(item["fecha"], item["id"])
    ids_posiciones: set[str] = set()
    for item in posiciones["posiciones"]:
        if item["ejemplo"] is not True:
            raise ErrorDeEspectro(
                f"La posición de {item['propuesta_id']} tiene que estar marcada como ejemplo."
            )
        if item["propuesta_id"] in ids_posiciones:
            raise ErrorDeEspectro(f"Posición repetida: {item['propuesta_id']}.")
        ids_posiciones.add(item["propuesta_id"])


def _fecha(valor: str, identificador: str) -> None:
    anio, mes, dia = (int(parte) for parte in valor.split("-"))
    if not (1 <= mes <= 12 and 1 <= dia <= 31 and anio >= 2000):
        raise ErrorDeEspectro(f"Fecha inválida en {identificador}.")


def cargar(directorio: Path | None = None) -> dict[str, Any]:
    """Load and validate the example spectrum. Returns the public bundle too."""
    carpeta = directorio or directorio_datos()
    ejes = _leer(carpeta, "ejes")
    afirmaciones = _leer(carpeta, "afirmaciones")
    actores = _leer(carpeta, "actores")
    posiciones = _leer(carpeta, "posiciones")
    propuestas = _leer(carpeta, "propuestasEjemplo")
    _validar_cruces(ejes, afirmaciones, actores, posiciones, propuestas)
    return {
        "ejes": ejes,
        "afirmaciones": afirmaciones,
        "actores": actores,
        "posiciones": posiciones,
        "propuestas": propuestas,
        "publico": _publico(ejes, afirmaciones, actores, propuestas),
    }


def _publico(
    ejes: dict[str, Any],
    afirmaciones: dict[str, Any],
    actores: dict[str, Any],
    propuestas: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ejemplo": True,
        "cuestionario_id": ejes["cuestionario_id"],
        "nota": ejes["nota"],
        "formula_frase": ejes["formula_frase"],
        "formula_detalle": ejes["formula_detalle"],
        "ejes": ejes["ejes"],
        "escala": afirmaciones["escala"],
        "afirmaciones": [
            {
                "id": item["id"],
                "eje": item["eje"],
                "sentido": item["sentido"],
                "texto": item["texto"],
            }
            for item in afirmaciones["afirmaciones"]
        ],
        "actores": actores["actores"],
        "nota_actores": actores["nota"],
        "propuestas_ejemplo": [
            {
                "id": item["id"],
                "titulo": item["titulo"],
                "tipo": item["tipo"],
                "estado": item["estado"],
                "autores": item["autores"],
                "fecha": item["fecha"],
                "ejemplo": True,
                "origen": "ejemplo-local",
                "resumen": item["resumen"],
                "posicion": item["posicion"],
            }
            for item in propuestas["propuestas"]
        ],
    }


def aplicar(documento: dict[str, Any], directorio: Path | None = None) -> None:
    """Attach example positions to proposals and add the spectrum bundle."""
    cargado = cargar(directorio)
    por_id = {item["propuesta_id"]: item for item in cargado["posiciones"]["posiciones"]}
    propuestas = documento.get("propuestas") or {}
    for item in propuestas.get("items") or []:
        posicion = por_id.get(item.get("id"))
        if posicion is None:
            item["posicion"] = None
            continue
        item["posicion"] = posicion["posicion"]
        comentario = posicion.get("comentario")
        if isinstance(comentario, str) and comentario.strip():
            item["posicion_comentario"] = comentario.strip()
    documento["espectro"] = cargado["publico"]
