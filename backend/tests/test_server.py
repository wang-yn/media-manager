from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
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

[tmdb]
api_key_env = "__MEDIA_MANAGER_TEST_TMDB_KEY__"

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
        self.assertEqual(health.json()["tmdb"], "missing")
        self.assertEqual(libraries.json()[0]["name"], "Movies")
        self.assertEqual(media.json()["items"][0]["title"], "Dune")

    def test_health_reports_tmdb_configured_without_exposing_key(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[paths]
media_dir = "/media"

[tmdb]
api_key = "test"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app())
            response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tmdb"], "configured")
        self.assertNotIn("test", str(response.json()))

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

    def test_health_reports_assrt_configured_without_exposing_token(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text(
                """
[paths]
media_dir = "/media"

[assrt]
token = "test-assrt-token"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            response = TestClient(create_app()).get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["assrt"], "configured")
        self.assertNotIn("test-assrt-token", str(response.json()))

    def test_search_metadata_accepts_query_override_and_blank_fallback(self) -> None:
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

[tmdb]
api_key = "token"

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
            media_id = client.get("/api/media").json()["items"][0]["id"]

            class FakeTMDBClient:
                queries: list[str] = []

                def __init__(self, api_key):
                    pass

                def search(self, query, media_type, year):
                    self.__class__.queries.append(query)
                    return [{"id": 1, "title": query, "media_type": media_type}]

            with patch("media_manager.server.TMDBClient", FakeTMDBClient):
                override = client.post(f"/api/media/{media_id}/metadata/search", json={"query": "沙丘"})
                fallback = client.post(f"/api/media/{media_id}/metadata/search", json={"query": "   "})

        self.assertEqual(override.status_code, 200)
        self.assertEqual(fallback.status_code, 200)
        self.assertEqual(FakeTMDBClient.queries, ["沙丘", "Dune"])

    def test_search_subtitles_uses_video_stem_by_default(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            movie = media_root / "movies" / "The Matrix" / "The.Matrix.1999.1080p.BluRay.x264-GROUP.mkv"
            movie.parent.mkdir(parents=True)
            movie.write_text("", encoding="utf-8")
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[assrt]
token = "token"

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
            media_id = client.get("/api/media").json()["items"][0]["id"]

            class FakeAssrtClient:
                def __init__(self, token):
                    self.token = token

                def search(self, query):
                    self.__class__.query = query
                    return [{"id": 123456, "native_name": "黑客帝国"}]

            with patch("media_manager.server.AssrtClient", FakeAssrtClient):
                response = client.post(f"/api/media/{media_id}/subtitles/search")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["id"], 123456)
        self.assertEqual(FakeAssrtClient.query, "The.Matrix.1999.1080p.BluRay.x264-GROUP")

    def test_download_subtitle_returns_written_path(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            movie = media_root / "movies" / "The Matrix" / "The.Matrix.1999.mkv"
            movie.parent.mkdir(parents=True)
            movie.write_text("", encoding="utf-8")
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[assrt]
token = "token"

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
            media_id = client.get("/api/media").json()["items"][0]["id"]

            class FakeAssrtClient:
                def __init__(self, token):
                    pass

                def detail(self, subtitle_id):
                    return {"filelist": [{"f": "movie.srt", "url": "https://file/sub.srt"}]}

                def download(self, url):
                    return b"subtitle"

            with patch("media_manager.server.AssrtClient", FakeAssrtClient):
                response = client.post(f"/api/media/{media_id}/subtitles/download", json={"subtitle_id": 123456})

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["path"].endswith("The.Matrix.1999.zh.srt"))
            self.assertEqual((movie.parent / "The.Matrix.1999.zh.srt").read_bytes(), b"subtitle")


if __name__ == "__main__":
    unittest.main()
