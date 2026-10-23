"""Read and write series files outside this repository."""

from __future__ import annotations

import json
from pathlib import Path

from curia_maxima.validation import SchemaError, validate_series


class StoreError(ValueError):
    """The existing series file cannot be used and was left untouched."""


def series_path(output_dir: Path, series_id: str) -> Path:
    return Path(output_dir) / "series" / f"{series_id}.json"


def load_series(path: Path) -> dict:
    """Load a series file. Refuse to continue if it is unreadable or invalid."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StoreError(
            f"El archivo de serie existente no se pudo leer y no se modificó: {path}"
        ) from exc
    if not isinstance(document, dict):
        raise StoreError(
            f"El archivo de serie existente no cumple el esquema y no se modificó: {path}"
        )
    try:
        validate_series(document)
    except SchemaError as exc:
        raise StoreError(
            "El archivo de serie existente no cumple el esquema y no se modificó: "
            f"{path}. {exc}"
        ) from exc
    return document


def save_series(path: Path, document: dict) -> None:
    """Validate and replace the series file. Nothing is written if validation fails."""
    validate_series(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
