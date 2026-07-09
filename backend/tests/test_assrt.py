from __future__ import annotations

from io import BytesIO
import json
import unittest

from media_manager.assrt import AssrtClient
from media_manager.errors import AppError


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


if __name__ == "__main__":
    unittest.main()
