from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
import warnings

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated.*")
from fastapi.testclient import TestClient


class ServerTest(unittest.TestCase):
    def test_health_libraries_and_media(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            movie = media_root / "movies" / "Dune (2021)" / "Dune (2021).mkv"
            movie.parent.mkdir(parents=True)
            movie.write_text("", encoding="utf-8")
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "Movies"
kind = "movie"
path = "{media_root / "movies"}"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app())
            health = client.get("/api/health")
            libraries = client.get("/api/libraries")
            media = client.get("/api/media")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(libraries.json()[0]["name"], "Movies")
        self.assertEqual(media.json()["items"][0]["title"], "Dune")

    def test_error_response_is_structured(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text("[paths]\nmedia_dir = \"/media\"\n", encoding="utf-8")
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app())
            response = client.post("/api/libraries", json={"name": "Bad", "kind": "music", "path": "/media/music"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_library_path")

    def test_rejects_library_outside_media_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            config_path.write_text(f"[paths]\nmedia_dir = \"{media_root}\"\n", encoding="utf-8")
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app())
            response = client.post("/api/libraries", json={"name": "Outside", "kind": "movie", "path": str(root / "outside")})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_library_path")

    def test_rejects_missing_library_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            media_root.mkdir()
            config_path = root / "config.toml"
            config_path.write_text(f"[paths]\nmedia_dir = \"{media_root}\"\n", encoding="utf-8")
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app())
            response = client.post("/api/libraries", json={"name": "Missing", "kind": "movie", "path": str(media_root / "missing")})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_library_path")


if __name__ == "__main__":
    unittest.main()
