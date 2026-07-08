from __future__ import annotations

from io import BytesIO
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

    def test_details_returns_payload(self) -> None:
        def opener(request, timeout=10):
            return FakeResponse(json.dumps({"id": 1, "title": "Dune"}).encode())

        detail = TMDBClient("key", opener=opener).details("movie", 1)

        self.assertEqual(detail["id"], 1)


if __name__ == "__main__":
    unittest.main()
