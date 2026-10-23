"""Validate observations and series against the JSON Schemas."""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
OBSERVATION_SCHEMA_NAME = "observation.schema.json"
SERIES_SCHEMA_NAME = "series.schema.json"


class SchemaError(ValueError):
    """A document does not satisfy the observation contract."""


def observation_schema() -> dict:
    return _load(OBSERVATION_SCHEMA_NAME)


def series_schema() -> dict:
    return _load(SERIES_SCHEMA_NAME)


def validate_observation(document: dict) -> None:
    """Raise SchemaError if the observation is not publishable."""
    _raise(_validators()[0], document, "observación")
    _check_day(document["data_date"])
    _check_stamp(document["captured_at"])


def validate_series(document: dict) -> None:
    """Raise SchemaError if the series file is not publishable."""
    _raise(_validators()[1], document, "serie")
    _check_stamp(document["captured_at"])
    for observation in document["observations"]:
        _check_day(observation["data_date"])
        _check_stamp(observation["captured_at"])


def _load(name: str) -> dict:
    path = SCHEMA_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _validators() -> tuple[Draft202012Validator, Draft202012Validator]:
    observation = observation_schema()
    series = series_schema()
    registry = Registry().with_resources(
        [
            (observation["$id"], Resource.from_contents(observation)),
            (series["$id"], Resource.from_contents(series)),
        ]
    )
    return (
        Draft202012Validator(observation, registry=registry),
        Draft202012Validator(series, registry=registry),
    )


def _raise(validator: Draft202012Validator, document: dict, kind: str) -> None:
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: ([str(part) for part in error.absolute_path], error.message),
    )
    if not errors:
        return
    error = errors[0]
    location = ".".join(str(part) for part in error.absolute_path) or "raíz"
    raise SchemaError(f"La {kind} no cumple el esquema ({location}): {error.message}")


def _check_day(value: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SchemaError(f"Fecha del dato inválida: {value}") from exc


def _check_stamp(value: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise SchemaError(f"Fecha de captura inválida: {value}") from exc
