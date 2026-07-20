from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import unittest
import warnings

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated.*")
from fastapi.testclient import TestClient

from media_manager import config as config_module


class ServerTest(unittest.TestCase):
    def test_initializes_default_config_before_persisting_library(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            library_path = media_root / "movies"
            config_path = root / "config" / "config.toml"
            example_path = root / "image" / "config.example.toml"
            library_path.mkdir(parents=True)
            example_path.parent.mkdir()
            example_contents = f'[paths]\nmedia_dir = "{media_root}"\n'
            example_path.write_text(example_contents, encoding="utf-8")

            with (
                patch.dict(os.environ, {"MEDIA_MANAGER_CONFIG": str(config_path)}, clear=True),
                patch.object(config_module, "DEFAULT_CONFIG", config_path),
                patch.object(config_module, "EXAMPLE_CONFIG", example_path),
            ):
                from media_manager.server import create_app

                client = TestClient(create_app(auth_enabled=False))
                response = client.post(
                    "/api/libraries",
                    json={"name": "Movies", "kind": "movie", "path": str(library_path)},
                )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(config_path.exists())
            self.assertEqual(config_module.load_config(config_path).libraries[0].name, "Movies")
            self.assertEqual(example_path.read_text(encoding="utf-8"), example_contents)

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

            client = TestClient(create_app(auth_enabled=False))
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

            client = TestClient(create_app(auth_enabled=False))
            response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tmdb"], "configured")
        self.assertNotIn("test", str(response.json()))

    def test_audit_endpoint_returns_grouped_relative_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            empty = media_root / "movies" / "Empty"
            empty.mkdir(parents=True)
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

            response = TestClient(create_app(auth_enabled=False)).get("/api/audit")

        self.assertTrue(response.headers["content-type"].startswith("application/json"))
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["libraries"][0]["name"], "Movies")
        self.assertEqual(data["libraries"][0]["type"], "movie")
        self.assertNotIn("path", data["libraries"][0])
        self.assertEqual(data["libraries"][0]["issues"][0]["relative_path"], "Empty")
        self.assertNotIn(str(media_root), str(data))

    def test_audit_endpoint_rejects_missing_library_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "Movies"
kind = "movie"
path = "{media_root / "missing"}"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            response = TestClient(create_app(auth_enabled=False)).get("/api/audit")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_library_path")

    def test_error_response_is_structured(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.toml"
            config_path.write_text("[paths]\nmedia_dir = \"/media\"\n", encoding="utf-8")
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app(auth_enabled=False))
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

            client = TestClient(create_app(auth_enabled=False))
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

            client = TestClient(create_app(auth_enabled=False))
            response = client.post("/api/libraries", json={"name": "Missing", "kind": "movie", "path": str(media_root / "missing")})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_library_path")

    def test_delete_library_removes_config_entry_without_deleting_files(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            movies = media_root / "movies"
            tv = media_root / "tv"
            movie = movies / "Dune (2021)" / "Dune (2021).mkv"
            episode = tv / "Pantheon (2022)" / "Season 01" / "Pantheon - S01E01.mkv"
            movie.parent.mkdir(parents=True)
            episode.parent.mkdir(parents=True)
            movie.write_text("", encoding="utf-8")
            episode.write_text("", encoding="utf-8")
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "Movies"
kind = "movie"
path = "{movies}"

[[libraries]]
name = "TV"
kind = "series"
path = "{tv}"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app(auth_enabled=False))
            response = client.request("DELETE", "/api/libraries", json={"kind": "movie", "path": str(movies)})
            libraries = client.get("/api/libraries").json()
            media = client.get("/api/media").json()
            movie_exists = movie.exists()

        self.assertEqual(response.status_code, 200)
        self.assertEqual([library["name"] for library in libraries], ["TV"])
        self.assertEqual([item["library"] for item in media["items"]], ["TV"])
        self.assertTrue(movie_exists)

    def test_delete_library_returns_404_when_config_entry_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            media_root.mkdir()
            config_path.write_text(f"[paths]\nmedia_dir = \"{media_root}\"\n", encoding="utf-8")
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            response = TestClient(create_app(auth_enabled=False)).request(
                "DELETE",
                "/api/libraries",
                json={"kind": "movie", "path": str(media_root / "movies")},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "library_not_found")

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

            response = TestClient(create_app(auth_enabled=False)).get("/api/health")

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

            client = TestClient(create_app(auth_enabled=False))
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

            client = TestClient(create_app(auth_enabled=False))
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

            client = TestClient(create_app(auth_enabled=False))
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

    def test_delete_series_removes_show_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            show = media_root / "tv" / "Pantheon (2022)"
            episode = show / "Season 01" / "Pantheon - S01E03.mkv"
            episode.parent.mkdir(parents=True)
            episode.write_text("", encoding="utf-8")
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "TV"
kind = "series"
path = "{media_root / "tv"}"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app(auth_enabled=False))
            media_id = client.get("/api/media").json()["items"][0]["id"]
            response = client.delete(f"/api/media/{media_id}")
            count_after_delete = client.get("/api/media").json()["count"]
            show_exists = show.exists()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_path"], str(show))
        self.assertFalse(show_exists)
        self.assertEqual(count_after_delete, 0)

    def test_delete_movie_removes_movie_directory(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            movie_dir = media_root / "movies" / "Dune (2021)"
            movie = movie_dir / "Dune (2021).mkv"
            subtitle = movie_dir / "Dune (2021).zh.srt"
            nfo = movie_dir / "movie.nfo"
            movie_dir.mkdir(parents=True)
            movie.write_text("video", encoding="utf-8")
            subtitle.write_text("subtitle", encoding="utf-8")
            nfo.write_text("<movie />", encoding="utf-8")
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

            client = TestClient(create_app(auth_enabled=False))
            media_id = client.get("/api/media").json()["items"][0]["id"]
            response = client.delete(f"/api/media/{media_id}")
            count_after_delete = client.get("/api/media").json()["count"]
            movie_dir_exists = movie_dir.exists()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_path"], str(movie_dir))
        self.assertFalse(movie_dir_exists)
        self.assertEqual(count_after_delete, 0)

    def test_delete_movie_rejects_library_root(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            movies = media_root / "movies"
            config_path = root / "config.toml"
            movie = movies / "Loose.Movie.2024.mkv"
            movies.mkdir(parents=True)
            movie.write_text("video", encoding="utf-8")
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "Movies"
kind = "movie"
path = "{movies}"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app(auth_enabled=False))
            media_id = client.get("/api/media").json()["items"][0]["id"]
            response = client.delete(f"/api/media/{media_id}")
            movies_exists = movies.exists()
            movie_exists = movie.exists()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_delete_target")
        self.assertTrue(movies_exists)
        self.assertTrue(movie_exists)

    def test_media_files_lists_directory_files_recursively(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            season = media_root / "tv" / "Pantheon (2022)" / "Season 01"
            episode = season / "Pantheon - S01E03.mkv"
            note = season / "extras" / "note.txt"
            show_nfo = season.parent / "tvshow.nfo"
            thumb = season / ".@__thumb" / "cached.jpg"
            note.parent.mkdir(parents=True)
            thumb.parent.mkdir()
            episode.write_bytes(b"video")
            note.write_bytes(b"note")
            thumb.write_bytes(b"ignored")
            show_nfo.write_text("<tvshow />", encoding="utf-8")
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "TV"
kind = "series"
path = "{media_root / "tv"}"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app(auth_enabled=False))
            item = client.get("/api/media").json()["items"][0]
            response = client.get(f"/api/media/{item['id']}/files")

        self.assertEqual(item["directory_size_bytes"], 19)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["root_path"], str(season.parent))
        self.assertEqual(response.json()["total_size_bytes"], 19)
        self.assertEqual(
            response.json()["files"],
            [
                {"path": "Season 01/Pantheon - S01E03.mkv", "size_bytes": 5},
                {"path": "Season 01/extras/note.txt", "size_bytes": 4},
                {"path": "tvshow.nfo", "size_bytes": 10},
            ],
        )

    def test_media_list_reports_metadata_and_rename_status(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            canonical = media_root / "movies" / "Dune (2021)" / "Dune (2021).mkv"
            missing_metadata = media_root / "movies" / "Arrival (2016)" / "arrival.mkv"
            canonical.parent.mkdir(parents=True)
            missing_metadata.parent.mkdir(parents=True)
            canonical.write_text("", encoding="utf-8")
            missing_metadata.write_text("", encoding="utf-8")
            (canonical.parent / "movie.nfo").write_text("<movie />", encoding="utf-8")
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

            items = TestClient(create_app(auth_enabled=False)).get("/api/media").json()["items"]

        by_path = {item["path"]: item for item in items}
        self.assertTrue(by_path[str(canonical)]["has_metadata"])
        self.assertFalse(by_path[str(canonical)]["rename_needed"])
        self.assertFalse(by_path[str(missing_metadata)]["has_metadata"])
        self.assertTrue(by_path[str(missing_metadata)]["rename_needed"])

    def test_batch_rename_preview_series_has_no_side_effects(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            show = media_root / "tv" / "Pantheon (2022)"
            first = show / "Season 01" / "Pantheon - S01E03.mkv"
            second = show / "Season 02" / "Pantheon - S02E01.mp4"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_text("", encoding="utf-8")
            second.write_text("", encoding="utf-8")
            (show / "tvshow.nfo").write_text(
                """
<tvshow>
  <title>万神殿</title>
  <originaltitle>Pantheon</originaltitle>
  <year>2022</year>
</tvshow>
""".strip(),
                encoding="utf-8",
            )
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "TV"
kind = "series"
path = "{media_root / "tv"}"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app(auth_enabled=False))
            media_id = client.get("/api/media").json()["items"][0]["id"]
            response = client.post(f"/api/media/{media_id}/rename/batch/preview")
            target_show = media_root / "tv" / "Pantheon - 万神殿 (2022)"

            first_exists = first.exists()
            second_exists = second.exists()
            target_exists = target_show.exists()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["can_apply"])
        self.assertGreaterEqual(len(response.json()["changes"]), 3)
        self.assertTrue(first_exists)
        self.assertTrue(second_exists)
        self.assertFalse(target_exists)

    def test_batch_rename_preview_reports_conflict_without_side_effects(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            show = media_root / "tv" / "Pantheon (2022)"
            source = show / "Season 01" / "Pantheon - S01E03.mkv"
            target = media_root / "tv" / "Pantheon - 万神殿 (2022)" / "Season 01" / "Pantheon - 万神殿 - S01E03.mkv"
            source.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            source.write_text("source", encoding="utf-8")
            target.write_text("target", encoding="utf-8")
            (show / "tvshow.nfo").write_text(
                """
<tvshow>
  <title>万神殿</title>
  <originaltitle>Pantheon</originaltitle>
  <year>2022</year>
</tvshow>
""".strip(),
                encoding="utf-8",
            )
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "TV"
kind = "series"
path = "{media_root / "tv"}"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app(auth_enabled=False))
            media_id = client.get("/api/media").json()["items"][0]["id"]
            response = client.post(f"/api/media/{media_id}/rename/batch/preview")
            source_text = source.read_text(encoding="utf-8")
            target_text = target.read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["can_apply"])
        self.assertIn("target_exists", response.json()["conflicts"])
        self.assertEqual(source_text, "source")
        self.assertEqual(target_text, "target")

    def test_batch_rename_preview_rejects_movie_item(self) -> None:
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

            client = TestClient(create_app(auth_enabled=False))
            media_id = client.get("/api/media").json()["items"][0]["id"]
            response = client.post(f"/api/media/{media_id}/rename/batch/preview")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "unsupported_batch_rename_target")

    def test_batch_rename_series_renames_all_episodes(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            media_root = root / "media"
            config_path = root / "config.toml"
            show = media_root / "tv" / "Pantheon (2022)"
            first = show / "Season 01" / "Pantheon - S01E03.mkv"
            second = show / "Season 02" / "Pantheon - S02E01.mp4"
            tvshow_nfo = show / "tvshow.nfo"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_text("", encoding="utf-8")
            second.write_text("", encoding="utf-8")
            tvshow_nfo.write_text(
                """
<tvshow>
  <title>万神殿</title>
  <originaltitle>Pantheon</originaltitle>
  <year>2022</year>
</tvshow>
""".strip(),
                encoding="utf-8",
            )
            config_path.write_text(
                f"""
[paths]
media_dir = "{media_root}"

[[libraries]]
name = "TV"
kind = "series"
path = "{media_root / "tv"}"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            os.environ["MEDIA_MANAGER_CONFIG"] = str(config_path)
            from media_manager.server import create_app

            client = TestClient(create_app(auth_enabled=False))
            media_id = client.get("/api/media").json()["items"][0]["id"]
            response = client.post(f"/api/media/{media_id}/rename/batch")

            renamed_show = media_root / "tv" / "Pantheon - 万神殿 (2022)"
            first_exists = (renamed_show / "Season 01" / "Pantheon - 万神殿 - S01E03.mkv").exists()
            second_exists = (renamed_show / "Season 02" / "Pantheon - 万神殿 - S02E01.mp4").exists()
            nfo_exists = (renamed_show / "tvshow.nfo").exists()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(first_exists)
        self.assertTrue(second_exists)
        self.assertTrue(nfo_exists)
        self.assertGreaterEqual(len(response.json()["changes"]), 3)


if __name__ == "__main__":
    unittest.main()
