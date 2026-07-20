from __future__ import annotations

from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from .errors import AppError


Opener = Callable[[Request, int], object]


class TMDBClient:
    def __init__(self, api_key: str | None, opener: Opener | None = None) -> None:
        self.api_key = api_key or ""
        self.opener = opener or urlopen

    def search(self, query: str, media_type: str, year: int | None = None) -> list[dict[str, object]]:
        self._require_key()
        endpoint = "search/tv" if media_type == "series" else "search/movie"
        params: dict[str, object] = {"api_key": self.api_key, "query": query, "language": "zh-CN"}
        if year:
            params["first_air_date_year" if media_type == "series" else "year"] = year
        payload = self._get(endpoint, params)
        return [self._candidate(item, media_type) for item in payload.get("results", [])]

    def details(self, media_type: str, tmdb_id: int) -> dict[str, object]:
        self._require_key()
        endpoint = f"tv/{tmdb_id}" if media_type == "series" else f"movie/{tmdb_id}"
        details = self._get(endpoint, {"api_key": self.api_key, "language": "zh-CN"})
        english = self._get(endpoint, {"api_key": self.api_key, "language": "en-US"})
        english_title = english.get("name") if media_type == "series" else english.get("title")
        if english_title:
            details["english_title"] = english_title
        return details

    def _require_key(self) -> None:
        if not self.api_key:
            raise AppError("tmdb_missing_api_key", "缺少 TMDB API 密钥")

    def _get(self, endpoint: str, params: dict[str, object]) -> dict[str, object]:
        url = f"https://api.themoviedb.org/3/{endpoint}?{urlencode(params)}"
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with self.opener(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise AppError("tmdb_request_failed", "TMDB 请求失败", str(exc)) from exc

    def _candidate(self, item: dict[str, object], media_type: str) -> dict[str, object]:
        title = item.get("name") if media_type == "series" else item.get("title")
        date = item.get("first_air_date") if media_type == "series" else item.get("release_date")
        year = None
        if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
            year = int(date[:4])
        return {
            "id": item.get("id"),
            "title": title or item.get("original_title") or item.get("original_name") or "",
            "year": year,
            "overview": item.get("overview", ""),
            "media_type": media_type,
        }
