"""The INE collector publishes a series and refuses a broken payload."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from curia_maxima.collectors.ine_remuneraciones import (
    SERIES_ID,
    IneRemuneracionesCollector,
)
from curia_maxima.hashing import raw_hash
from curia_maxima.validation import validate_series

FIXTURE = Path(__file__).parent / "fixtures" / "ine_ir2023_min.json"
CLOCK = "2026-10-23T17:00:00Z"


def _collector(tmp_path: Path, fetcher) -> IneRemuneracionesCollector:
    return IneRemuneracionesCollector(tmp_path, fetcher=fetcher, clock=lambda: CLOCK)


def _load(tmp_path: Path) -> dict:
    path = tmp_path / "series" / f"{SERIES_ID}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    validate_series(document)
    return document


def test_publishes_the_index_series_with_history_and_hash(tmp_path: Path) -> None:
    body = FIXTURE.read_bytes()

    def fetcher(url: str) -> tuple[int, bytes]:
        assert "CL01,DF_IR2023,1.0" in url
        assert "startPeriod=2023-01" in url
        assert "endPeriod=2026-10" in url
        return 200, body

    code = _collector(tmp_path, fetcher).run()

    document = _load(tmp_path)
    assert code == 0
    assert document["status"] == "vigente"
    assert document["error"] is None
    assert document["source"]["organism"] == "Instituto Nacional de Estadísticas (INE)"
    assert document["unit"] == "índice (base 2023=100)"
    assert [(item["data_date"], item["value"]) for item in document["observations"]] == [
        ("2024-01-01", 104.08),
        ("2026-08-01", 124.64),
    ]
    assert all(item["status"] == "vigente" for item in document["observations"])
    assert all(item["raw_hash"] == raw_hash(body) for item in document["observations"])
    assert all(item["captured_at"] == CLOCK for item in document["observations"])
    assert 6.19 not in {item["value"] for item in document["observations"]}
    assert (tmp_path / "raw" / f"{SERIES_ID}.body").read_bytes() == body
    assert not list(tmp_path.rglob("*.tmp"))


def test_rerun_updates_the_same_dates_without_duplicating_history(tmp_path: Path) -> None:
    body = FIXTURE.read_bytes()
    collector = _collector(tmp_path, lambda url: (200, body))
    collector.run()
    later = "2026-10-23T18:00:00Z"
    collector.clock = lambda: later
    collector.run()

    document = _load(tmp_path)
    assert [item["data_date"] for item in document["observations"]] == [
        "2024-01-01",
        "2026-08-01",
    ]
    assert document["captured_at"] == later


def test_keeps_months_absent_from_a_later_capture(tmp_path: Path) -> None:
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    january = copy.deepcopy(original)
    del january["data"]["dataSets"][0]["series"]["0:0:0:1"]["observations"]["2"]
    august = copy.deepcopy(original)
    del august["data"]["dataSets"][0]["series"]["0:0:0:1"]["observations"]["0"]
    payloads = iter(
        [
            json.dumps(january).encode(),
            json.dumps(august).encode(),
        ]
    )
    collector = _collector(tmp_path, lambda url: (200, next(payloads)))
    collector.run()
    collector.run()

    document = _load(tmp_path)
    assert [item["data_date"] for item in document["observations"]] == [
        "2024-01-01",
        "2026-08-01",
    ]


def test_format_change_is_marked_stale_and_does_not_publish(tmp_path: Path) -> None:
    good = FIXTURE.read_bytes()
    broken = json.loads(good)
    broken["data"]["structure"]["dimensions"]["series"][3]["values"][1]["id"] = "INDEX"
    broken["data"]["dataSets"][0]["series"]["0:0:0:1"]["observations"]["2"][0] = 999.99
    broken_body = json.dumps(broken).encode()
    responses = iter([good, broken_body])
    collector = _collector(tmp_path, lambda url: (200, next(responses)))

    assert collector.run() == 0
    before = copy.deepcopy(_load(tmp_path)["observations"])

    code = collector.run()
    document = _load(tmp_path)

    assert code == 1
    assert document["status"] == "no actualizado"
    assert document["error"].startswith("Cambio de formato:")
    assert "no está el valor IX" in document["error"]
    assert raw_hash(broken_body) in document["error"]
    assert document["observations"] == before
    assert 999.99 not in {item["value"] for item in document["observations"]}
    assert (tmp_path / "raw" / f"{SERIES_ID}.body").read_bytes() == good


def test_first_failure_writes_a_verifiable_error_without_observations(tmp_path: Path) -> None:
    code = _collector(tmp_path, lambda url: (503, b"caido")).run()

    document = _load(tmp_path)
    assert code == 1
    assert document["status"] == "no actualizado"
    assert document["observations"] == []
    assert document["error"].startswith("Fuente no disponible: HTTP 503")
    assert "sha256:" in document["error"]
    assert not (tmp_path / "raw").exists()


def test_invalid_json_and_http_failure_do_not_replace_history(tmp_path: Path) -> None:
    body = FIXTURE.read_bytes()
    responses = iter([(200, body), (200, b"<html>cambio"), (500, b"error")])
    collector = _collector(tmp_path, lambda url: next(responses))
    collector.run()
    before = copy.deepcopy(_load(tmp_path)["observations"])
    raw_before = (tmp_path / "raw" / f"{SERIES_ID}.body").read_bytes()

    assert collector.run() == 1
    stale = _load(tmp_path)
    assert stale["status"] == "no actualizado"
    assert "no es JSON válido" in stale["error"]
    assert stale["observations"] == before
    assert (tmp_path / "raw" / f"{SERIES_ID}.body").read_bytes() == raw_before

    assert collector.run() == 1
    failed = _load(tmp_path)
    assert failed["error"].startswith("Fuente no disponible: HTTP 500")
    assert failed["observations"] == before


def test_recovery_clears_the_error(tmp_path: Path) -> None:
    body = FIXTURE.read_bytes()
    responses = iter([(500, b"error"), (200, body)])
    collector = _collector(tmp_path, lambda url: next(responses))
    assert collector.run() == 1
    assert collector.run() == 0

    document = _load(tmp_path)
    assert document["status"] == "vigente"
    assert document["error"] is None
    assert len(document["observations"]) == 2
