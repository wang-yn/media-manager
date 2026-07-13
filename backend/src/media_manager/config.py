from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os
import tomllib


DEFAULT_CONFIG = Path("/config/config.toml")
EXAMPLE_CONFIG = Path(__file__).resolve().parents[3] / "config" / "config.example.toml"


@dataclass(frozen=True)
class Library:
    name: str
    kind: str
    path: Path


@dataclass(frozen=True)
class AppConfig:
    path: Path
    raw: dict[str, Any]
    libraries: list[Library]

    @property
    def media_dir(self) -> Path:
        return Path(self.raw.get("paths", {}).get("media_dir", "/media"))


def config_path() -> Path:
    configured = os.environ.get("MEDIA_MANAGER_CONFIG")
    if configured:
        return Path(configured)
    if DEFAULT_CONFIG.exists():
        return DEFAULT_CONFIG
    development_config = EXAMPLE_CONFIG.with_name("config.toml")
    if development_config.exists():
        return development_config
    return EXAMPLE_CONFIG


def load_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or config_path()
    if cfg_path == DEFAULT_CONFIG and not cfg_path.exists():
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_bytes(EXAMPLE_CONFIG.read_bytes())
    with cfg_path.open("rb") as file:
        raw = tomllib.load(file)
    libraries = [
        Library(
            name=str(item.get("name", item.get("path", "media"))),
            kind=str(item.get("kind", "movie")),
            path=Path(str(item.get("path", raw.get("paths", {}).get("media_dir", "/media")))),
        )
        for item in raw.get("libraries", [])
    ]
    return AppConfig(path=cfg_path, raw=raw, libraries=libraries)


def append_library(path: Path, name: str, kind: str, library_path: Path) -> None:
    if kind not in {"movie", "series"}:
        raise ValueError("library kind must be movie or series")
    raw: dict[str, Any] = {}
    if path.exists():
        with path.open("rb") as file:
            raw = tomllib.load(file)
    libraries = list(raw.get("libraries", []))
    libraries.append({"name": name, "kind": kind, "path": str(library_path)})
    raw["libraries"] = libraries
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_toml(raw), encoding="utf-8")


def _dump_toml(raw: dict[str, Any]) -> str:
    lines: list[str] = []
    _dump_sections(lines, raw)
    for key, value in raw.items():
        if key == "libraries" or not _is_array_of_tables(value):
            continue
        for item in value:
            lines.append(f"[[{key}]]")
            _dump_values(lines, item)
            lines.append("")
    for library in raw.get("libraries", []):
        lines.append("[[libraries]]")
        lines.append(f"name = {_toml_value(str(library.get('name', 'media')))}")
        lines.append(f"kind = {_toml_value(str(library.get('kind', 'movie')))}")
        lines.append(f"path = {_toml_value(str(library.get('path', '/media')))}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _dump_sections(lines: list[str], table: dict[str, Any], prefix: str = "") -> None:
    values = {
        key: value
        for key, value in table.items()
        if key != "libraries" and not isinstance(value, dict) and not _is_array_of_tables(value)
    }
    if prefix and values:
        lines.append(f"[{prefix}]")
        _dump_values(lines, values)
        lines.append("")
    for key, value in table.items():
        if key == "libraries" or not isinstance(value, dict):
            continue
        _dump_sections(lines, value, f"{prefix}.{key}" if prefix else key)


def _dump_values(lines: list[str], values: dict[str, Any]) -> None:
    for item_key, item_value in values.items():
        lines.append(f"{item_key} = {_toml_value(item_value)}")


def _is_array_of_tables(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
