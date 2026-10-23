"""Collector for the INE nominal wage index.

The source is the public SDMX API of the Instituto Nacional de Estadísticas
(SIMEL). No API key is required. The pinned response is SDMX-JSON 1.0 wrapped
in ``meta``, ``data`` and ``errors``.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from curia_maxima.hashing import raw_hash
from curia_maxima.store import load_series, save_series, series_path

SERIES_ID = "ine.ir2023.nacional.indice"
INDICATOR_CODE = "IR2023"
INDICATOR_NAME = "Índice nominal de remuneraciones (base 2023 = 100)"
UNIT = "índice (base 2023=100)"
ORGANISM = "Instituto Nacional de Estadísticas (INE)"
STATUS_CURRENT = "vigente"
STATUS_STALE = "no actualizado"
START_PERIOD = "2023-01"
SOURCE_BASE = "https://sdmx.ine.gob.cl/rest/data/CL01,DF_IR2023,1.0"
ACCEPT = "application/vnd.sdmx.data+json; version=1.0; charset=utf-8"
USER_AGENT = "curia-maxima/0.1 (recolector de prueba; +https://github.com/nlecarosg/curia_maxima)"

EXPECTED_DIMENSIONS = ["AREA_REF", "FREQ", "INDICADOR", "UNIDAD"]
EXPECTED_VALUES = {
    "AREA_REF": "_T",
    "FREQ": "M",
    "INDICADOR": "IR2023",
    "UNIDAD": "IX",
}

Fetcher = Callable[[str], tuple[int, bytes]]
Clock = Callable[[], str]


class CollectorError(Exception):
    """The source could not be published."""


class SourceError(CollectorError):
    """The source did not return a usable response."""


class FormatError(CollectorError):
    """The response no longer has the structure this collector understands."""


@dataclass(frozen=True)
class ParsedPoint:
    data_date: str
    value: float


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, timeout: float = 30.0) -> tuple[int, bytes]:
    """GET a URL. Network failures become SourceError. HTTP errors return the status."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": ACCEPT,
            "Accept-Language": "es",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except TimeoutError as exc:
        raise SourceError("Fuente no disponible: tiempo de espera agotado") from exc
    except urllib.error.URLError as exc:
        raise SourceError(f"Fuente no disponible: {exc.reason}") from exc


class IneRemuneracionesCollector:
    """Publish the national IR2023 index, or mark the series stale without new data."""

    def __init__(
        self,
        output_dir: Path,
        fetcher: Fetcher | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.fetcher = fetcher if fetcher is not None else fetch
        self.clock = clock if clock is not None else utc_now

    @property
    def path(self) -> Path:
        return series_path(self.output_dir, SERIES_ID)

    def source_url(self) -> str:
        end_period = self.clock()[:7]
        return f"{SOURCE_BASE}?startPeriod={START_PERIOD}&endPeriod={end_period}"

    def run(self) -> int:
        """Return 0 when the series is vigente and 1 when it is no actualizado."""
        url = self.source_url()
        existing = self._read_existing()
        body: bytes | None = None
        try:
            status, body = self.fetcher(url)
            if status != 200:
                raise SourceError(f"Fuente no disponible: HTTP {status}")
            points = parse_remuneraciones(body)
            if not points:
                raise SourceError("Sin datos publicables: la serie IX no trae valores numéricos")
        except CollectorError as exc:
            detail = f"{exc} | url={url}"
            if body is not None:
                detail = f"{detail} | {raw_hash(body)}"
            return self._mark_stale(existing, url, detail)
        return self._publish(existing, url, body, points)

    def _read_existing(self) -> dict | None:
        if not self.path.exists():
            return None
        return load_series(self.path)

    def _mark_stale(self, existing: dict | None, url: str, message: str) -> int:
        if len(message) > 1000:
            message = message[:1000] + "…"
        now = self.clock()
        if existing is None:
            document = _blank_series(url, now)
        else:
            document = existing
        document["status"] = STATUS_STALE
        document["error"] = message
        document["captured_at"] = now
        save_series(self.path, document)
        _report(document, self.path)
        return 1

    def _publish(
        self,
        existing: dict | None,
        url: str,
        body: bytes,
        points: list[ParsedPoint],
    ) -> int:
        now = self.clock()
        digest = raw_hash(body)
        if existing is None:
            document = _blank_series(url, now)
        else:
            document = existing
        by_date = {
            observation["data_date"]: observation for observation in document["observations"]
        }
        for point in points:
            by_date[point.data_date] = {
                "series_id": SERIES_ID,
                "value": point.value,
                "unit": UNIT,
                "source": {"organism": ORGANISM, "url": url},
                "data_date": point.data_date,
                "captured_at": now,
                "raw_hash": digest,
                "status": STATUS_CURRENT,
            }
        document["observations"] = [by_date[key] for key in sorted(by_date)]
        document["status"] = STATUS_CURRENT
        document["error"] = None
        document["captured_at"] = now
        document["source"] = {"organism": ORGANISM, "url": url}
        document["unit"] = UNIT
        save_series(self.path, document)
        self._write_raw(body)
        _report(document, self.path)
        return 0

    def _write_raw(self, body: bytes) -> None:
        """Keep the response bytes so the stored hash can be recomputed.

        A later request to the INE changes ``meta.id`` and ``meta.prepared``
        even when the figures stay the same, so the hash is of this capture.
        """
        path = self.output_dir / "raw" / f"{SERIES_ID}.body"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(body)
        temporary.replace(path)


def parse_remuneraciones(body: bytes) -> list[ParsedPoint]:
    """Parse the pinned SDMX-JSON envelope into dated index points."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceError("Fuente no disponible: la respuesta no es JSON válido") from exc
    if not isinstance(payload, dict):
        raise FormatError("Cambio de formato: la respuesta no es un objeto JSON")
    errors = payload.get("errors")
    if not isinstance(errors, list):
        raise FormatError("Cambio de formato: falta la lista errors")
    if errors:
        raise SourceError("Fuente no disponible: la respuesta informa errores")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise FormatError("Cambio de formato: falta el objeto data")
    datasets = data.get("dataSets")
    if not isinstance(datasets, list) or len(datasets) != 1 or not isinstance(datasets[0], dict):
        raise FormatError("Cambio de formato: se esperaba un único dataSets")
    structure = data.get("structure")
    if not isinstance(structure, dict):
        raise FormatError("Cambio de formato: falta structure")
    dimensions = structure.get("dimensions")
    if not isinstance(dimensions, dict):
        raise FormatError("Cambio de formato: falta structure.dimensions")

    series_key = _series_key(dimensions.get("series"))
    periods = _periods(dimensions.get("observation"))
    decimals_position, decimal_values = _decimals(structure.get("attributes"))

    series_map = datasets[0].get("series")
    if not isinstance(series_map, dict) or series_key not in series_map:
        raise FormatError("Cambio de formato: no está la serie nacional mensual del índice")
    series = series_map[series_key]
    if not isinstance(series, dict):
        raise FormatError("Cambio de formato: no está la serie nacional mensual del índice")
    observations = series.get("observations")
    if not isinstance(observations, dict):
        raise FormatError("Cambio de formato: la serie no trae observaciones")

    points: list[ParsedPoint] = []
    seen: set[str] = set()
    for index, raw in observations.items():
        if not isinstance(index, str) or not index.isdigit():
            raise FormatError("Cambio de formato: el índice de una observación no es numérico")
        position = int(index)
        if position >= len(periods) or not isinstance(periods[position], dict):
            raise FormatError("Cambio de formato: una observación apunta a un periodo inexistente")
        if not isinstance(raw, list) or not raw:
            raise FormatError("Cambio de formato: una observación no tiene la forma esperada")
        value = raw[0]
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FormatError("Cambio de formato: una observación no trae un valor numérico")
        # The observation array is [value, attribute...]. Attribute 0 is index 1.
        decimals_index = 1 + decimals_position
        if len(raw) <= decimals_index:
            raise FormatError("Cambio de formato: una observación no trae los decimales")
        decimals = _decimal_places(raw[decimals_index], decimal_values)
        data_date = _data_date(periods[position])
        if data_date in seen:
            raise FormatError("Cambio de formato: hay dos observaciones para la misma fecha")
        seen.add(data_date)
        points.append(ParsedPoint(data_date=data_date, value=_round(value, decimals)))
    return points


def _series_key(series_dimensions: object) -> str:
    if not isinstance(series_dimensions, list):
        raise FormatError("Cambio de formato: faltan las dimensiones de la serie")
    identifiers = [item.get("id") if isinstance(item, dict) else None for item in series_dimensions]
    if identifiers != EXPECTED_DIMENSIONS:
        raise FormatError(
            "Cambio de formato: las dimensiones de la serie cambiaron "
            f"({identifiers})"
        )
    indexes: list[str] = []
    for dimension in series_dimensions:
        values = dimension.get("values")
        if not isinstance(values, list):
            raise FormatError(
                f"Cambio de formato: la dimensión {dimension.get('id')} no trae valores"
            )
        wanted = EXPECTED_VALUES[dimension["id"]]
        value_ids = [value.get("id") for value in values if isinstance(value, dict)]
        if wanted not in value_ids:
            raise FormatError(
                f"Cambio de formato: no está el valor {wanted} en la dimensión {dimension['id']}"
            )
        indexes.append(str(value_ids.index(wanted)))
    return ":".join(indexes)


def _periods(observation_dimensions: object) -> list:
    if not isinstance(observation_dimensions, list):
        raise FormatError("Cambio de formato: la dimensión temporal no es TIME_PERIOD")
    identifiers = [
        item.get("id") if isinstance(item, dict) else None for item in observation_dimensions
    ]
    if identifiers != ["TIME_PERIOD"]:
        raise FormatError("Cambio de formato: la dimensión temporal no es TIME_PERIOD")
    periods = observation_dimensions[0].get("values")
    if not isinstance(periods, list) or not periods:
        raise FormatError("Cambio de formato: no hay periodos")
    return periods


def _decimals(attributes: object) -> tuple[int, list]:
    if not isinstance(attributes, dict):
        raise FormatError("Cambio de formato: falta el atributo DECIMALS")
    observation_attributes = attributes.get("observation")
    if not isinstance(observation_attributes, list):
        raise FormatError("Cambio de formato: falta el atributo DECIMALS")
    for position, attribute in enumerate(observation_attributes):
        if isinstance(attribute, dict) and attribute.get("id") == "DECIMALS":
            values = attribute.get("values")
            if isinstance(values, list) and values:
                return position, values
    raise FormatError("Cambio de formato: falta el atributo DECIMALS")


def _decimal_places(index: object, values: list) -> int:
    if isinstance(index, bool) or not isinstance(index, int):
        raise FormatError("Cambio de formato: los decimales de una observación no son válidos")
    if index < 0 or index >= len(values) or not isinstance(values[index], dict):
        raise FormatError("Cambio de formato: los decimales de una observación no son válidos")
    identifier = values[index].get("id")
    if not isinstance(identifier, str) or not identifier.isdigit():
        raise FormatError("Cambio de formato: los decimales de una observación no son válidos")
    decimals = int(identifier)
    if decimals > 6:
        raise FormatError("Cambio de formato: los decimales de una observación no son válidos")
    return decimals


def _data_date(period: dict) -> str:
    start = period.get("start")
    if isinstance(start, str) and len(start) >= 10:
        date = start[:10]
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise FormatError("Cambio de formato: un periodo no trae fecha reconocible") from exc
        return date
    identifier = period.get("id")
    if isinstance(identifier, str) and len(identifier) == 8 and identifier[4:6] == "-M":
        date = f"{identifier[:4]}-{identifier[5:7]}-01"
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise FormatError("Cambio de formato: un periodo no trae fecha reconocible") from exc
        return date
    raise FormatError("Cambio de formato: un periodo no trae fecha reconocible")


def _round(value: float, decimals: int) -> float:
    quantum = Decimal("1").scaleb(-decimals)
    rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    return float(rounded)


def _blank_series(url: str, captured_at: str) -> dict:
    return {
        "schema_version": "1",
        "series_id": SERIES_ID,
        "indicator": {"code": INDICATOR_CODE, "name": INDICATOR_NAME},
        "unit": UNIT,
        "source": {"organism": ORGANISM, "url": url},
        "status": STATUS_CURRENT,
        "error": None,
        "captured_at": captured_at,
        "observations": [],
    }


def _report(document: dict, path: Path) -> None:
    print(
        f"Serie {document['series_id']}: {document['status']} "
        f"({len(document['observations'])} observaciones) → {path}"
    )
    if document["error"]:
        print(f"Error: {document['error']}", file=sys.stderr)
