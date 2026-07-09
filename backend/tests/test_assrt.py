from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from media_manager.assrt import AssrtClient, download_subtitle, subtitle_query
from media_manager.errors import AppError
from media_manager.media import MediaItem


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class AssrtClientTest(unittest.TestCase):
    def test_requires_token(self) -> None:
        with self.assertRaises(AppError) as context:
            AssrtClient("").search("The.Matrix.1999")

        self.assertEqual(context.exception.code, "assrt_missing_token")

    def test_search_uses_bearer_token_and_maps_candidates(self) -> None:
        seen: dict[str, object] = {}

        def opener(request, timeout=10):
            seen["url"] = request.full_url
            seen["authorization"] = request.headers.get("Authorization")
            payload = {
                "status": 0,
                "sub": {
                    "subs": [
                        {
                            "id": 123456,
                            "native_name": "黑客帝国/The Matrix",
                            "videoname": "The.Matrix.1999.1080p.BluRay.x264-GROUP",
                            "lang": {"desc": "中英双语"},
                            "subtype": "Subrip(srt)",
                            "vote_score": 8,
                            "release_site": "个人",
                            "upload_time": "2020-01-01 00:00:00",
                        }
                    ]
                },
            }
            return FakeResponse(json.dumps(payload).encode())

        results = AssrtClient("token", opener=opener).search("The.Matrix.1999.1080p.BluRay.x264-GROUP")

        self.assertIn("/v1/sub/search?", str(seen["url"]))
        self.assertIn("cnt=10", str(seen["url"]))
        self.assertIn("no_muxer=1", str(seen["url"]))
        self.assertEqual(seen["authorization"], "Bearer token")
        self.assertEqual(results[0]["id"], 123456)
        self.assertEqual(results[0]["native_name"], "黑客帝国/The Matrix")
        self.assertEqual(results[0]["lang"], "中英双语")

    def test_search_accepts_count_keyword(self) -> None:
        seen: dict[str, object] = {}

        def opener(request, timeout=10):
            seen["url"] = request.full_url
            return FakeResponse(json.dumps({"status": 0, "sub": {"subs": []}}).encode())

        AssrtClient("token", opener=opener).search("Matrix", count=5)

        self.assertIn("cnt=5", str(seen["url"]))

    def test_short_keyword_is_rejected_before_request(self) -> None:
        def opener(request, timeout=10):
            raise AssertionError("should not request assrt")

        with self.assertRaises(AppError) as context:
            AssrtClient("token", opener=opener).search("ab")

        self.assertEqual(context.exception.code, "assrt_keyword_too_short")

    def test_api_error_and_quota_error_are_structured(self) -> None:
        def api_error(request, timeout=10):
            return FakeResponse(json.dumps({"status": 101, "message": "length of keyword must be longer than 3"}).encode())

        with self.assertRaises(AppError) as context:
            AssrtClient("token", opener=api_error).search("Matrix")
        self.assertEqual(context.exception.code, "assrt_api_error")

        def quota_error(request, timeout=10):
            return FakeResponse(json.dumps({"status": 30900, "message": "you are exceeding request limits"}).encode())

        with self.assertRaises(AppError) as quota_context:
            AssrtClient("token", opener=quota_error).search("Matrix")
        self.assertEqual(quota_context.exception.code, "assrt_quota_exceeded")

    def test_malformed_payload_is_structured(self) -> None:
        def opener(request, timeout=10):
            return FakeResponse(json.dumps({"status": 0, "sub": []}).encode())

        with self.assertRaises(AppError) as context:
            AssrtClient("token", opener=opener).search("Matrix")

        self.assertEqual(context.exception.code, "assrt_request_failed")

    def test_detail_returns_first_subtitle(self) -> None:
        def opener(request, timeout=10):
            payload = {"status": 0, "sub": {"subs": [{"id": 123456, "filelist": [{"f": "movie.srt", "url": "https://file/sub.srt"}]}]}}
            return FakeResponse(json.dumps(payload).encode())

        detail = AssrtClient("token", opener=opener).detail(123456)

        self.assertEqual(detail["id"], 123456)

    def test_download_returns_bytes(self) -> None:
        def opener(request, timeout=10):
            return FakeResponse(b"subtitle")

        content = AssrtClient("token", opener=opener).download("https://file/sub.srt")

        self.assertEqual(content, b"subtitle")


class FakeSubtitleClient:
    def __init__(self, detail_payload: dict[str, object], content: bytes = b"subtitle") -> None:
        self.detail_payload = detail_payload
        self.content = content
        self.downloaded_url = ""

    def detail(self, subtitle_id: int) -> dict[str, object]:
        return self.detail_payload

    def download(self, url: str) -> bytes:
        self.downloaded_url = url
        return self.content


class SubtitleDownloadTest(unittest.TestCase):
    def test_subtitle_query_uses_video_stem(self) -> None:
        item = MediaItem("movie", "The Matrix", "/media/The.Matrix.1999.1080p.BluRay.x264-GROUP.mkv", "Movies", "/media")

        self.assertEqual(subtitle_query(item), "The.Matrix.1999.1080p.BluRay.x264-GROUP")

    def test_download_subtitle_writes_direct_file_next_to_video(self) -> None:
        with TemporaryDirectory() as tmp:
            video = Path(tmp) / "The.Matrix.1999.1080p.BluRay.x264-GROUP.mkv"
            video.write_text("", encoding="utf-8")
            item = MediaItem("movie", "The Matrix", str(video), "Movies", str(Path(tmp)))
            client = FakeSubtitleClient({"filelist": [{"f": "movie.srt", "url": "https://file/sub.srt"}]}, b"hello")

            target = download_subtitle(item, 123456, client)

            self.assertEqual(target.name, "The.Matrix.1999.1080p.BluRay.x264-GROUP.zh.srt")
            self.assertEqual(client.downloaded_url, "https://file/sub.srt")
            self.assertEqual(target.read_bytes(), b"hello")

    def test_download_subtitle_rejects_existing_target(self) -> None:
        with TemporaryDirectory() as tmp:
            video = Path(tmp) / "Pantheon - S01E03.mkv"
            target = Path(tmp) / "Pantheon - S01E03.zh.ass"
            video.write_text("", encoding="utf-8")
            target.write_text("old", encoding="utf-8")
            item = MediaItem("series", "Pantheon", str(video), "TV", str(Path(tmp)), season=1, episode=3)
            client = FakeSubtitleClient({"filelist": [{"f": "episode.ass", "url": "https://file/sub.ass"}]})

            with self.assertRaises(AppError) as context:
                download_subtitle(item, 123456, client)

        self.assertEqual(context.exception.code, "subtitle_target_exists")

    def test_download_subtitle_rejects_archive_only_result(self) -> None:
        with TemporaryDirectory() as tmp:
            video = Path(tmp) / "movie.mkv"
            video.write_text("", encoding="utf-8")
            item = MediaItem("movie", "Movie", str(video), "Movies", str(Path(tmp)))
            client = FakeSubtitleClient({"filename": "movie.rar", "url": "https://file/movie.rar"})

            with self.assertRaises(AppError) as context:
                download_subtitle(item, 123456, client)

        self.assertEqual(context.exception.code, "assrt_unsupported_archive")


if __name__ == "__main__":
    unittest.main()
