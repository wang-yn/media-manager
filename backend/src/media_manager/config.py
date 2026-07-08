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
    return EXAMPLE_CONFIG


def load_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or config_path()
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
