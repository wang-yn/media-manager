from __future__ import annotations

from typing import Callable
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import json

from .errors import AppError


Opener = Callable[[Request, int], object]


class AssrtClient:
    def __init__(self, token: str | None, opener: Opener | None = None) -> None:
        self.token = token or ""
        self.opener = opener or urlopen

    def search(self, keyword: str, cnt: int = 20) -> list[dict[str, object]]:
        self._require_token()
        keyword = keyword.strip()
        if len(keyword) < 3:
            raise AppError("assrt_keyword_too_short", "ASSRT 搜索关键词太短")
        payload = self._api_get("search", {"q": keyword, "cnt": cnt, "no_muxer": 1})
        subs = self._subs(payload)
        return [self._candidate(item) for item in subs if isinstance(item, dict)]

    def detail(self, subtitle_id: int) -> dict[str, object]:
        self._require_token()
        payload = self._api_get("detail", {"id": subtitle_id})
        subs = self._subs(payload)
        if not subs or not isinstance(subs[0], dict):
            raise AppError("assrt_subtitle_not_found", "ASSRT 字幕不存在")
        return subs[0]

    def download(self, url: str) -> bytes:
        scheme = urlparse(url).scheme
        if scheme not in {"http", "https"}:
            raise AppError("assrt_request_failed", "ASSRT 请求失败", "invalid download url")
        try:
            with self.opener(Request(url), timeout=10) as response:
                return response.read()
        except AppError:
            raise
        except Exception as exc:
            raise AppError("assrt_request_failed", "ASSRT 请求失败", str(exc)) from exc

    def _require_token(self) -> None:
        if not self.token:
            raise AppError("assrt_missing_token", "缺少 ASSRT Token")

    def _api_get(self, endpoint: str, params: dict[str, object]) -> dict[str, object]:
        payload = self._request_json(f"https://api.assrt.net/v1/sub/{endpoint}?{urlencode(params)}")
        status = payload.get("status")
        if status == 0:
            return payload
        if status == 30900:
            raise AppError("assrt_quota_exceeded", "ASSRT 请求额度已用尽", self._message(payload))
        if isinstance(status, int):
            raise AppError("assrt_api_error", "ASSRT API 返回错误", self._message(payload))
        raise AppError("assrt_request_failed", "ASSRT 请求失败", "malformed payload")

    def _request_json(self, url: str) -> dict[str, object]:
        request = Request(url, headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"})
        try:
            with self.opener(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except AppError:
            raise
        except Exception as exc:
            raise AppError("assrt_request_failed", "ASSRT 请求失败", str(exc)) from exc
        if not isinstance(payload, dict):
            raise AppError("assrt_request_failed", "ASSRT 请求失败", "malformed payload")
        return payload

    def _subs(self, payload: dict[str, object]) -> list[object]:
        sub = payload.get("sub")
        if not isinstance(sub, dict) or not isinstance(sub.get("subs"), list):
            raise AppError("assrt_request_failed", "ASSRT 请求失败", "malformed payload")
        return sub["subs"]

    def _candidate(self, item: dict[str, object]) -> dict[str, object]:
        lang = item.get("lang")
        return {
            "id": item.get("id"),
            "native_name": item.get("native_name"),
            "videoname": item.get("videoname"),
            "lang": lang.get("desc") if isinstance(lang, dict) else lang,
            "subtype": item.get("subtype"),
            "vote_score": item.get("vote_score"),
            "release_site": item.get("release_site"),
            "upload_time": item.get("upload_time"),
        }

    def _message(self, payload: dict[str, object]) -> str | None:
        message = payload.get("message")
        return message if isinstance(message, str) else None
