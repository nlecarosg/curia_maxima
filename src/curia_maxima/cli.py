"""Command line entry point for the trial collector."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from curia_maxima.collectors.ine_remuneraciones import IneRemuneracionesCollector
from curia_maxima.store import StoreError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="curia-collect",
        description=(
            "Recolecta el índice nominal de remuneraciones del INE y lo escribe "
            "en una ruta elegida. Esa ruta no forma parte de este repositorio."
        ),
        epilog=(
            "Ejemplo:\n"
            "  python -m curia_maxima --output /ruta/del/repo-de-datos\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        help="Directorio de salida. Si se omite, se usa la variable CURIA_OUTPUT_DIR.",
    )
    args = parser.parse_args(argv)
    output = args.output or os.environ.get("CURIA_OUTPUT_DIR")
    if not output:
        print(
            "Indique la ruta de salida con --output o con la variable CURIA_OUTPUT_DIR.",
            file=sys.stderr,
        )
        return 2

    collector = IneRemuneracionesCollector(Path(output))
    try:
        return collector.run()
    except StoreError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
