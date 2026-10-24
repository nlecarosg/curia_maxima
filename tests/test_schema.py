"""Validation of the common observation contract."""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from curia_maxima.validation import (
    SCHEMA_DIR,
    SchemaError,
    observation_schema,
    series_schema,
    validate_observation,
    validate_series,
)

HASH = "sha256:" + "ab" * 32


def observation(**overrides: object) -> dict:
    document = {
        "series_id": "ine.ir2023.nacional.indice",
        "value": 124.64,
        "unit": "índice (base 2023=100)",
        "source": {
            "organism": "Instituto Nacional de Estadísticas (INE)",
            "url": "https://sdmx.ine.gob.cl/rest/data/CL01,DF_IR2023,1.0",
        },
        "data_date": "2026-08-01",
        "captured_at": "2026-10-23T17:00:00Z",
        "raw_hash": HASH,
        "status": "vigente",
    }
    document.update(overrides)
    return document


def series(**overrides: object) -> dict:
    document = {
        "schema_version": "1",
        "series_id": "ine.ir2023.nacional.indice",
        "indicator": {
            "code": "IR2023",
            "name": "Índice nominal de remuneraciones (base 2023 = 100)",
        },
        "unit": "índice (base 2023=100)",
        "source": {
            "organism": "Instituto Nacional de Estadísticas (INE)",
            "url": "https://sdmx.ine.gob.cl/rest/data/CL01,DF_IR2023,1.0",
        },
        "status": "vigente",
        "error": None,
        "captured_at": "2026-10-23T17:00:00Z",
        "observations": [observation()],
    }
    document.update(overrides)
    return document


def test_schema_documents_are_valid_json_schema() -> None:
    Draft202012Validator.check_schema(observation_schema())
    Draft202012Validator.check_schema(series_schema())


def test_schema_files_are_the_contract_on_disk() -> None:
    names = sorted(path.name for path in SCHEMA_DIR.glob("*.json"))
    assert names == [
        "espectro.schema.json",
        "observation.schema.json",
        "series.schema.json",
    ]
    for name in names:
        document = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_valid_observation_and_series() -> None:
    validate_observation(observation())
    validate_series(series())


def test_observation_requires_source_organism() -> None:
    document = observation()
    del document["source"]["organism"]
    with pytest.raises(SchemaError, match="organism"):
        validate_observation(document)


def test_observation_rejects_unknown_status_extra_fields_and_bad_hash() -> None:
    with pytest.raises(SchemaError, match="status"):
        validate_observation(observation(status="pendiente"))
    with pytest.raises(SchemaError, match="raw_hash"):
        validate_observation(observation(raw_hash="abc"))
    with pytest.raises(SchemaError):
        validate_observation(observation(nota="no pertenece al contrato"))


def test_observation_rejects_impossible_dates_and_non_numeric_values() -> None:
    with pytest.raises(SchemaError, match="Fecha del dato"):
        validate_observation(observation(data_date="2024-13-01"))
    with pytest.raises(SchemaError):
        validate_observation(observation(captured_at="2026-10-23 17:00:00"))
    with pytest.raises(SchemaError):
        validate_observation(observation(value=True))


def test_current_series_needs_data_and_no_error() -> None:
    with pytest.raises(SchemaError):
        validate_series(series(observations=[]))
    with pytest.raises(SchemaError):
        validate_series(series(error="no debería estar"))


def test_stale_series_requires_an_error_and_may_have_no_observations() -> None:
    with pytest.raises(SchemaError):
        validate_series(series(status="no actualizado", error=None, observations=[]))
    validate_series(
        series(
            status="no actualizado",
            error="Cambio de formato: falta la unidad IX",
            observations=[],
        )
    )


def test_series_rejects_an_observation_missing_unit() -> None:
    document = series()
    del document["observations"][0]["unit"]
    with pytest.raises(SchemaError, match="unit"):
        validate_series(document)
