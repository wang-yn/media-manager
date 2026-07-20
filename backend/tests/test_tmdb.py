from __future__ import annotations

from io import BytesIO
from urllib.parse import parse_qs, urlparse
import json
import unittest

from media_manager.errors import AppError
from media_manager.tmdb import TMDBClient


class FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TMDBTest(unittest.TestCase):
    def test_requires_api_key(self) -> None:
        with self.assertRaises(AppError) as context:
            TMDBClient("").search("Dune", "movie")

        self.assertEqual(context.exception.code, "tmdb_missing_api_key")

    def test_search_maps_candidates(self) -> None:
        def opener(request, timeout=10):
            payload = {"results": [{"id": 1, "title": "Dune", "release_date": "2021-09-15", "overview": "Spice."}]}
            return FakeResponse(json.dumps(payload).encode())

        results = TMDBClient("key", opener=opener).search("Dune", "movie", year=2021)

        self.assertEqual(results[0]["id"], 1)
        self.assertEqual(results[0]["title"], "Dune")
        self.assertEqual(results[0]["year"], 2021)

    def test_details_returns_payload_with_english_movie_title(self) -> None:
        calls: list[tuple[str, str]] = []

        def opener(request, timeout=10):
            parsed = urlparse(request.full_url)
            language = parse_qs(parsed.query)["language"][0]
            calls.append((parsed.path, language))
            payload = (
                {"id": 1, "title": "Kim Ji-young, Born 1982", "original_title": "82년생 김지영"}
                if language == "en-US"
                else {"id": 1, "title": "82年生的金智英", "original_title": "82년생 김지영"}
            )
            return FakeResponse(json.dumps(payload).encode())

        detail = TMDBClient("key", opener=opener).details("movie", 1)

        self.assertEqual(detail["id"], 1)
        self.assertEqual(detail["title"], "82年生的金智英")
        self.assertEqual(detail["original_title"], "82년생 김지영")
        self.assertEqual(detail["english_title"], "Kim Ji-young, Born 1982")
        self.assertEqual(calls, [("/3/movie/1", "zh-CN"), ("/3/movie/1", "en-US")])

    def test_details_returns_payload_with_english_series_title(self) -> None:
        def opener(request, timeout=10):
            parsed = urlparse(request.full_url)
            language = parse_qs(parsed.query)["language"][0]
            payload = {"id": 1, "name": "English Show"} if language == "en-US" else {"id": 1, "name": "中文剧名"}
            return FakeResponse(json.dumps(payload).encode())

        detail = TMDBClient("key", opener=opener).details("series", 1)

        self.assertEqual(detail["name"], "中文剧名")
        self.assertEqual(detail["english_title"], "English Show")


if __name__ == "__main__":
    unittest.main()
