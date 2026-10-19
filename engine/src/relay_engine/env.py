"""Minimal .env loading: machine-specific settings."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Set KEY=VALUE pairs from `path` without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and value and not key.startswith("#") and key not in os.environ:
            os.environ[key] = value
