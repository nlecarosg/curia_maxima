"""Allow ``python -m curia_maxima``."""

from __future__ import annotations

import sys

from curia_maxima.cli import main

if __name__ == "__main__":
    sys.exit(main())
