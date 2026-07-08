from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from media_manager.config import append_library, load_config


class ConfigTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
