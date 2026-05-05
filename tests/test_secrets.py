"""Tests for nami_core.secrets — secure secret loading."""

from __future__ import annotations

from pathlib import Path

from nami_core.secrets import load_secret, load_env_file, get_db_connection_string


def test_load_secret_reads_file(tmp_path: Path) -> None:
    secret_file = tmp_path / "test_key"
    secret_file.write_text("my-secret-value\n", encoding="utf-8")

    result = load_secret("test_key", secret_dir=tmp_path)
    assert result == "my-secret-value"


def test_load_secret_returns_empty_for_missing(tmp_path: Path) -> None:
    result = load_secret("nonexistent", secret_dir=tmp_path)
    assert result == ""


def test_load_secret_strips_whitespace(tmp_path: Path) -> None:
    secret_file = tmp_path / "spaced"
    secret_file.write_text("  value  \n", encoding="utf-8")

    result = load_secret("spaced", secret_dir=tmp_path)
    assert result == "value"


def test_load_env_file_parses_key_value(tmp_path: Path) -> None:
    env_file = tmp_path / "test.env"
    env_file.write_text("API_KEY=abc123\nPORT=8080\n# comment\n\nEXTRA=1\n", encoding="utf-8")

    result = load_env_file("test.env", secret_dir=tmp_path)
    assert result == {"API_KEY": "abc123", "PORT": "8080", "EXTRA": "1"}


def test_load_env_file_returns_empty_for_missing(tmp_path: Path) -> None:
    result = load_env_file("missing.env", secret_dir=tmp_path)
    assert result == {}


def test_get_db_connection_string_with_password(tmp_path: Path) -> None:
    pw_file = tmp_path / "postgres_password"
    pw_file.write_text("my_pg_pass\n", encoding="utf-8")

    result = get_db_connection_string("mydb", secret_dir=tmp_path)
    assert result == "postgresql://postgres:my_pg_pass@localhost/mydb"


def test_get_db_connection_string_without_password(tmp_path: Path) -> None:
    result = get_db_connection_string("mydb", secret_dir=tmp_path)
    assert result == "postgresql://postgres@localhost/mydb"
