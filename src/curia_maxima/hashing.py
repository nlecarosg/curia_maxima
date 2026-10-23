"""Hash of a raw source response."""

from __future__ import annotations

import hashlib


def raw_hash(body: bytes) -> str:
    """Return the SHA-256 of the raw response bytes, prefixed with ``sha256:``."""
    digest = hashlib.sha256(body).hexdigest()
    return f"sha256:{digest}"
