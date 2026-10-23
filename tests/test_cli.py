"""The command requires an output directory and does not assume one in the repo."""

from __future__ import annotations

import json
from pathlib import Path

from curia_maxima.cli import main
from curia_maxima.collectors.ine_remuneraciones import SERIES_ID
from curia_maxima.hashing import raw_hash

FIXTURE = Path(__file__).parent / "fixtures" / "ine_ir2023_min.json"


def test_cli_requires_an_output_path(monkeypatch) -> None:
    monkeypatch.delenv("CURIA_OUTPUT_DIR", raising=False)
    assert main([]) == 2


def test_cli_writes_only_inside_the_given_directory(tmp_path: Path, monkeypatch) -> None:
    body = FIXTURE.read_bytes()

    def fetcher(url: str) -> tuple[int, bytes]:
        return 200, body

    monkeypatch.setattr(
        "curia_maxima.collectors.ine_remuneraciones.fetch",
        fetcher,
    )
    code = main(["--output", str(tmp_path)])

    written = tmp_path / "series" / f"{SERIES_ID}.json"
    document = json.loads(written.read_text(encoding="utf-8"))
    assert code == 0
    assert document["observations"][0]["raw_hash"] == raw_hash(body)


def test_cli_accepts_the_output_environment_variable(tmp_path: Path, monkeypatch) -> None:
    body = FIXTURE.read_bytes()
    monkeypatch.setenv("CURIA_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "curia_maxima.collectors.ine_remuneraciones.fetch",
        lambda url: (200, body),
    )
    assert main([]) == 0
    assert (tmp_path / "series" / f"{SERIES_ID}.json").is_file()
