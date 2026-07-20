from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from media_manager import config as config_module
from media_manager.config import append_library, load_config, remove_library


class ConfigTest(unittest.TestCase):
    def test_prefers_development_config_over_example_config(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            local_config = root / "config.toml"
            example_config = root / "config.example.toml"
            local_config.write_text("[paths]\nmedia_dir = \"/local-media\"\n", encoding="utf-8")
            example_config.write_text("[paths]\nmedia_dir = \"/example-media\"\n", encoding="utf-8")

            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(config_module, "DEFAULT_CONFIG", root / "missing.toml"),
                patch.object(config_module, "EXAMPLE_CONFIG", example_config),
            ):
                config_path = config_module.config_path()

        self.assertEqual(config_path, local_config)

    def test_appends_library_to_existing_config(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[server]
host = "127.0.0.1"
port = 8000

[paths]
config_dir = "/config"
media_dir = "/media"

[organizer.movie]
directory_template = "{title} ({year})"
file_template = "{title} ({year})"

[[libraries]]
name = "Movies"
kind = "movie"
path = "/media/movies"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            append_library(config_path, "TV", "series", Path("/media/tv"))
            config = load_config(config_path)

        self.assertEqual([library.name for library in config.libraries], ["Movies", "TV"])
        self.assertEqual(config.libraries[1].kind, "series")
        self.assertEqual(config.libraries[1].path, Path("/media/tv"))
        self.assertEqual(config.raw["organizer"]["movie"]["directory_template"], "{title} ({year})")

    def test_rejects_invalid_library_kind(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text("[paths]\nmedia_dir = \"/media\"\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                append_library(config_path, "Bad", "music", Path("/media/music"))

    def test_removes_library_from_existing_config(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[paths]
media_dir = "/media"

[tmdb]
api_key_env = "TMDB_API_KEY"

[[libraries]]
name = "Movies"
kind = "movie"
path = "/media/movies"

[[libraries]]
name = "TV"
kind = "series"
path = "/media/tv"
""".strip()
                + "\n",
                encoding="utf-8",
            )

            removed = remove_library(config_path, "movie", Path("/media/movies"))
            config = load_config(config_path)

        self.assertTrue(removed)
        self.assertEqual([library.name for library in config.libraries], ["TV"])
        self.assertEqual(config.raw["tmdb"]["api_key_env"], "TMDB_API_KEY")


if __name__ == "__main__":
    unittest.main()
