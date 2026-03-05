from __future__ import annotations

from pathlib import Path

from .exceptions import ConfigurationError


def read_required_text(path: Path) -> str:
    if not path.exists():
        raise ConfigurationError(f"Required document is missing: {path}")
    return path.read_text(encoding="utf-8")
