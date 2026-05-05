"""Secure secret loading from /etc/nami-harness.

All secrets live under /etc/nami-harness/ (root-only, 700/600).
This module provides safe loading functions that:
- Only read from the designated secret directory
- Never log secret values
- Return empty string / None for missing secrets (no exception on missing)
"""

from __future__ import annotations

import os
from pathlib import Path

SECRET_DIR = Path("/etc/nami-harness")


def load_secret(name: str, *, secret_dir: str | Path | None = None) -> str:
    """Load a single secret file by name.

    Returns the file content stripped of whitespace.
    Returns empty string if the file does not exist.
    """
    base = Path(secret_dir) if secret_dir else SECRET_DIR
    path = base / name

    if not path.exists():
        return ""

    content = path.read_text(encoding="utf-8").strip()
    return content


def load_env_file(name: str, *, secret_dir: str | Path | None = None) -> dict[str, str]:
    """Load a .env-style file from the secret directory.

    Format: KEY=VALUE per line, # comments, blank lines ignored.
    Returns a dict of key-value pairs.
    """
    base = Path(secret_dir) if secret_dir else SECRET_DIR
    path = base / name

    if not path.exists():
        return {}

    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def get_ai_config_path(*, secret_dir: str | Path | None = None) -> Path:
    """Return the path to the real ai_config.json (with provider secrets)."""
    base = Path(secret_dir) if secret_dir else SECRET_DIR
    return base / "ai_config.json"


def get_db_connection_string(dbname: str = "glodbyproza", *, secret_dir: str | Path | None = None) -> str:
    """Build a PostgreSQL connection string from the stored password."""
    base = Path(secret_dir) if secret_dir else SECRET_DIR
    password_file = base / "postgres_password"

    if not password_file.exists():
        return f"postgresql://postgres@localhost/{dbname}"

    password = password_file.read_text(encoding="utf-8").strip()
    return f"postgresql://postgres:{password}@localhost/{dbname}"
