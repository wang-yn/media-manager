# assrt 字幕下载 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为单个媒体条目增加 assrt.net 手动字幕搜索、候选选择和旁路字幕下载能力。

**Architecture:** 沿用现有同步 FastAPI API 和 React 单页工作台，不引入后台任务、队列或新依赖。后端新增一个很薄的 `AssrtClient`，负责 assrt 请求和响应映射；字幕保存规则放在同一模块，避免为首版做 provider 抽象。前端增加一个字幕弹窗，复用当前 `request()`、`messageFrom()` 和媒体列表刷新逻辑。

**Tech Stack:** Python 标准库 `urllib.request`/`json`/`pathlib`、现有 `AppError`、FastAPI、unittest、React + TypeScript + Vite、CSS。

---

## 文件结构

- 新增 `backend/src/media_manager/assrt.py`：assrt API 客户端、候选字段映射、字幕直链选择和旁路字幕写入。
- 新增 `backend/tests/test_assrt.py`：客户端、错误映射、字幕文件选择和写入规则的单元测试。
- 修改 `backend/src/media_manager/server.py`：增加 assrt token 读取、健康状态、字幕搜索和字幕下载 API。
- 修改 `backend/tests/test_server.py`：覆盖 assrt 健康状态和两个新增 API 的 HTTP 行为。
- 修改 `config/config.example.toml`：增加 `[assrt] token_env = "ASSRT_API_TOKEN"`。
- 修改 `frontend/src/App.tsx`：增加字幕候选类型、弹窗状态、搜索/下载动作和行级“字幕”按钮。
- 修改 `frontend/src/style.css`：增加弹窗、字幕候选列表和紧凑表单样式。

不修改 TMDB、NFO、重命名、Dockerfile。不实现 `/api/subtitles/quota`，首版避免多消耗一次 assrt 配额。

## Task 1: assrt 客户端

**Files:**
- Create: `backend/src/media_manager/assrt.py`
- Test: `backend/tests/test_assrt.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_assrt.py`：

```python
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
        self.assertIn("no_muxer=1", str(seen["url"]))
        self.assertEqual(seen["authorization"], "Bearer token")
        self.assertEqual(results[0]["id"], 123456)
        self.assertEqual(results[0]["native_name"], "黑客帝国/The Matrix")
        self.assertEqual(results[0]["lang"], "中英双语")

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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_assrt
```

Expected: 失败，报 `ModuleNotFoundError: No module named 'media_manager.assrt'`。

- [ ] **Step 3: 实现最小客户端**

创建 `backend/src/media_manager/assrt.py`：

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from .errors import AppError


Opener = Callable[[Request, int], object]
DIRECT_SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa"}


class AssrtClient:
    def __init__(self, token: str | None, opener: Opener | None = None) -> None:
        self.token = token or ""
        self.opener = opener or urlopen

    def search(self, query: str, count: int = 10) -> list[dict[str, object]]:
        self._require_token()
        query = query.strip()
        if len(query) < 3:
            raise AppError("assrt_keyword_too_short", "字幕搜索关键词至少 3 个字符")
        payload = self._get("sub/search", {"q": query, "cnt": count, "no_muxer": 1})
        subs = payload.get("sub", {}).get("subs", []) if isinstance(payload.get("sub"), dict) else []
        return [_candidate(item) for item in subs if isinstance(item, dict)]

    def detail(self, subtitle_id: int) -> dict[str, object]:
        self._require_token()
        payload = self._get("sub/detail", {"id": subtitle_id})
        subs = payload.get("sub", {}).get("subs", []) if isinstance(payload.get("sub"), dict) else []
        if not subs:
            raise AppError("assrt_subtitle_not_found", "字幕不存在或详情为空")
        return dict(subs[0])

    def quota(self) -> dict[str, object]:
        self._require_token()
        payload = self._get("user/quota", {})
        user = payload.get("user", {})
        return dict(user) if isinstance(user, dict) else {}

    def download(self, url: str) -> bytes:
        if not url.startswith(("http://", "https://")):
            raise AppError("assrt_request_failed", "ASSRT 下载地址无效", url)
        request = Request(url, headers={"Accept": "*/*"})
        try:
            with self.opener(request, timeout=10) as response:
                return response.read()
        except Exception as exc:
            raise AppError("assrt_request_failed", "ASSRT 请求失败", str(exc)) from exc

    def _require_token(self) -> None:
        if not self.token:
            raise AppError("assrt_missing_token", "缺少 ASSRT API token")

    def _get(self, endpoint: str, params: dict[str, object]) -> dict[str, object]:
        url = f"https://api.assrt.net/v1/{endpoint}?{urlencode(params)}"
        request = Request(url, headers={"Accept": "application/json", "Authorization": f"Bearer {self.token}"})
        try:
            with self.opener(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise AppError("assrt_request_failed", "ASSRT 请求失败", str(exc)) from exc
        return _checked_payload(payload)


def _checked_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise AppError("assrt_request_failed", "ASSRT 响应格式错误")
    status = payload.get("status")
    if status == 0:
        return payload
    detail = str(payload.get("message") or payload.get("error") or payload)
    if status == 30900:
        raise AppError("assrt_quota_exceeded", "ASSRT 配额已用完，请稍后再试", detail)
    raise AppError("assrt_api_error", "ASSRT 返回错误", detail)


def _candidate(item: dict[str, object]) -> dict[str, object]:
    lang = item.get("lang", {})
    lang_desc = lang.get("desc", "") if isinstance(lang, dict) else ""
    return {
        "id": item.get("id"),
        "native_name": item.get("native_name", ""),
        "videoname": item.get("videoname", ""),
        "lang": lang_desc,
        "subtype": item.get("subtype", ""),
        "vote_score": item.get("vote_score", 0),
        "release_site": item.get("release_site", ""),
        "upload_time": item.get("upload_time", ""),
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_assrt
```

Expected: `OK`。

## Task 2: 字幕选择和旁路写入

**Files:**
- Modify: `backend/src/media_manager/assrt.py`
- Modify: `backend/tests/test_assrt.py`

- [ ] **Step 1: 写失败测试**

在 `AssrtClientTest` 后追加：

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from media_manager.assrt import download_subtitle, subtitle_query
from media_manager.media import MediaItem


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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_assrt.SubtitleDownloadTest
```

Expected: 失败，报 `cannot import name 'download_subtitle'` 或 `subtitle_query`。

- [ ] **Step 3: 实现字幕写入辅助函数**

在 `backend/src/media_manager/assrt.py` 末尾追加：

```python
from .media import MediaItem


def subtitle_query(item: MediaItem) -> str:
    return Path(item.path).stem


def download_subtitle(item: MediaItem, subtitle_id: int, client: object) -> Path:
    detail = client.detail(subtitle_id)
    entry = _direct_subtitle_entry(detail)
    source_name = str(entry["f"])
    source_url = str(entry["url"])
    extension = Path(source_name).suffix.lower()
    target = Path(item.path).with_name(f"{Path(item.path).stem}.zh{extension}")
    if target.exists():
        raise AppError("subtitle_target_exists", "字幕文件已存在", path=str(target))
    content = client.download(source_url)
    try:
        target.write_bytes(content)
    except OSError as exc:
        raise AppError("subtitle_write_failed", "写入字幕文件失败", str(exc), str(target)) from exc
    return target


def _direct_subtitle_entry(detail: dict[str, object]) -> dict[str, object]:
    filelist = detail.get("filelist", [])
    if isinstance(filelist, list):
        for item in filelist:
            if isinstance(item, dict) and _direct_subtitle_name(str(item.get("f", ""))) and item.get("url"):
                return item
    filename = str(detail.get("filename", ""))
    if _direct_subtitle_name(filename) and detail.get("url"):
        return {"f": filename, "url": detail["url"]}
    raise AppError("assrt_unsupported_archive", "当前只支持直接下载 srt、ass、ssa 字幕文件")


def _direct_subtitle_name(name: str) -> bool:
    return Path(name).suffix.lower() in DIRECT_SUBTITLE_EXTENSIONS
```

- [ ] **Step 4: 运行 assrt 测试确认通过**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_assrt
```

Expected: `OK`。

## Task 3: 后端 API 接入

**Files:**
- Modify: `backend/src/media_manager/server.py`
- Modify: `backend/tests/test_server.py`
- Modify: `config/config.example.toml`

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_server.py` 顶部补充：

```python
from unittest.mock import patch
```

在 `ServerTest` 中追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_server
```

Expected: 失败，健康响应缺少 `assrt` 或新 API 返回 404。

- [ ] **Step 3: 增加配置示例**

在 `config/config.example.toml` 的 `[tmdb]` 后追加：

```toml
[assrt]
token_env = "ASSRT_API_TOKEN"
```

- [ ] **Step 4: 修改后端 API**

在 `backend/src/media_manager/server.py` 中导入：

```python
from .assrt import AssrtClient, download_subtitle, subtitle_query
```

增加输入模型：

```python
class SubtitleSearchInput(BaseModel):
    query: str | None = None


class SubtitleDownloadInput(BaseModel):
    subtitle_id: int
```

将 `health()` 返回值改成：

```python
return {
    "status": "ok",
    "config": str(cfg.path),
    "media_dir": str(cfg.media_dir),
    "tmdb": "configured" if _tmdb_api_key(cfg) else "missing",
    "assrt": "configured" if _assrt_token(cfg) else "missing",
}
```

在重命名 API 后增加：

```python
    @app.post("/api/media/{media_id}/subtitles/search")
    def subtitle_search(media_id: str, input: SubtitleSearchInput | None = None) -> dict[str, object]:
        item = _find_media(app, media_id)
        query = (input.query.strip() if input and input.query else "") or subtitle_query(item)
        return {"query": query, "results": _assrt(app).search(query)}

    @app.post("/api/media/{media_id}/subtitles/download")
    def subtitle_download(media_id: str, input: SubtitleDownloadInput) -> dict[str, str]:
        item = _find_media(app, media_id)
        path = download_subtitle(item, input.subtitle_id, _assrt(app))
        return {"path": str(path)}
```

在 `_tmdb()` 附近增加：

```python
def _assrt(app: FastAPI) -> AssrtClient:
    return AssrtClient(_assrt_token(_config(app)))


def _assrt_token(config: AppConfig) -> str:
    raw = config.raw
    assrt_config = raw.get("assrt", {})
    token_env = str(assrt_config.get("token_env", "ASSRT_API_TOKEN"))
    return os.environ.get(token_env) or str(assrt_config.get("token", ""))
```

- [ ] **Step 5: 运行服务端测试确认通过**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest backend.tests.test_server
```

Expected: `OK`。

## Task 4: 前端字幕弹窗

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 增加类型和状态**

在 `frontend/src/App.tsx` 中扩展 `Health`：

```ts
assrt: "configured" | "missing";
```

在 `Candidate` 后增加：

```ts
type SubtitleCandidate = {
  id: number;
  native_name?: string;
  videoname?: string;
  lang?: string;
  subtype?: string;
  vote_score?: number;
  release_site?: string;
  upload_time?: string;
};

type SubtitleDialog = {
  item: MediaItem;
  query: string;
  results: SubtitleCandidate[];
  selectedId?: number;
  error?: string;
};
```

在 `App()` 状态区增加：

```ts
const [subtitleDialog, setSubtitleDialog] = useState<SubtitleDialog | null>(null);
```

- [ ] **Step 2: 增加前端动作函数**

在 `applyRename()` 后增加：

```ts
async function openSubtitleDialog(item: MediaItem) {
  const query = videoStem(item.path);
  const dialog: SubtitleDialog = { item, query, results: [] };
  setSubtitleDialog(dialog);
  await searchSubtitles(dialog);
}

async function searchSubtitles(dialog: SubtitleDialog) {
  setBusy(`subtitle-search:${dialog.item.id}`);
  setError(null);
  try {
    const result = await request<{ results: SubtitleCandidate[] }>(`/api/media/${dialog.item.id}/subtitles/search`, {
      method: "POST",
      body: JSON.stringify({ query: dialog.query }),
    });
    setSubtitleDialog({ ...dialog, results: result.results, selectedId: undefined, error: undefined });
  } catch (err) {
    setSubtitleDialog({ ...dialog, error: messageFrom(err) });
  } finally {
    setBusy(null);
  }
}

async function downloadSelectedSubtitle(dialog: SubtitleDialog) {
  if (!dialog.selectedId) {
    return;
  }
  setBusy(`subtitle-download:${dialog.item.id}`);
  try {
    await request<{ path: string }>(`/api/media/${dialog.item.id}/subtitles/download`, {
      method: "POST",
      body: JSON.stringify({ subtitle_id: dialog.selectedId }),
    });
    setSubtitleDialog(null);
    await refreshContent();
  } catch (err) {
    setSubtitleDialog({ ...dialog, error: messageFrom(err) });
  } finally {
    setBusy(null);
  }
}
```

在文件底部工具函数区增加：

```ts
function videoStem(path: string) {
  const name = path.split(/[\\/]/).pop() ?? path;
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}
```

- [ ] **Step 3: 把字幕动作传给表格**

给 `LibraryDetailView`、`MediaTable`、`Row` 的 props 增加：

```ts
onSearchSubtitle: (item: MediaItem) => void;
```

在 `App()` 渲染 `LibraryDetailView` 时传入：

```tsx
onSearchSubtitle={openSubtitleDialog}
```

在 `Row` 操作按钮里追加：

```tsx
<button type="button" onClick={() => onSearchSubtitle(item)} disabled={busy === `subtitle-search:${item.id}`}>
  字幕
</button>
```

- [ ] **Step 4: 增加弹窗组件**

在 `Row` 组件前增加：

```tsx
function SubtitleDialogView({
  dialog,
  busy,
  onChange,
  onSearch,
  onSelect,
  onDownload,
  onClose,
}: {
  dialog: SubtitleDialog;
  busy: string | null;
  onChange: (query: string) => void;
  onSearch: () => void;
  onSelect: (id: number) => void;
  onDownload: () => void;
  onClose: () => void;
}) {
  const isSearching = busy === `subtitle-search:${dialog.item.id}`;
  const isDownloading = busy === `subtitle-download:${dialog.item.id}`;
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="modal" role="dialog" aria-modal="true" aria-label="搜索字幕">
        <div className="section-head">
          <h2>搜索字幕</h2>
          <button type="button" className="link-button" onClick={onClose}>
            关闭
          </button>
        </div>
        <p className="path">{dialog.item.path}</p>
        <div className="dialog-form">
          <input value={dialog.query} onChange={(event) => onChange(event.target.value)} />
          <button type="button" onClick={onSearch} disabled={isSearching}>
            {isSearching ? "搜索中" : "重新搜索"}
          </button>
        </div>
        {dialog.error ? <p className="notice error">{dialog.error}</p> : null}
        <div className="subtitle-results">
          {dialog.results.map((candidate) => (
            <button
              key={candidate.id}
              type="button"
              className={dialog.selectedId === candidate.id ? "subtitle-candidate selected" : "subtitle-candidate"}
              onClick={() => onSelect(candidate.id)}
            >
              <strong>{candidate.native_name || `字幕 ${candidate.id}`}</strong>
              <span>{candidate.videoname || "-"}</span>
              <small>
                {[candidate.lang, candidate.subtype, candidate.release_site, candidate.upload_time].filter(Boolean).join(" / ")}
              </small>
            </button>
          ))}
          {dialog.results.length === 0 && !isSearching ? <p className="empty">暂无候选</p> : null}
        </div>
        <div className="dialog-actions">
          <button type="button" onClick={onDownload} disabled={!dialog.selectedId || isDownloading}>
            {isDownloading ? "下载中" : "下载字幕"}
          </button>
        </div>
      </section>
    </div>
  );
}
```

在 `App()` 的 `</main>` 前渲染：

```tsx
{subtitleDialog ? (
  <SubtitleDialogView
    dialog={subtitleDialog}
    busy={busy}
    onChange={(query) => setSubtitleDialog({ ...subtitleDialog, query })}
    onSearch={() => searchSubtitles(subtitleDialog)}
    onSelect={(selectedId) => setSubtitleDialog({ ...subtitleDialog, selectedId })}
    onDownload={() => downloadSelectedSubtitle(subtitleDialog)}
    onClose={() => setSubtitleDialog(null)}
  />
) : null}
```

- [ ] **Step 5: 增加样式**

在 `frontend/src/style.css` 末尾追加：

```css
.modal-backdrop {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgb(15 23 42 / 0.42);
  z-index: 10;
}

.modal {
  display: grid;
  gap: 12px;
  width: min(760px, 100%);
  max-height: min(720px, calc(100vh - 40px));
  overflow: auto;
  padding: 16px;
  border: 1px solid #d6dee1;
  border-radius: 8px;
  background: #fff;
}

.dialog-form,
.dialog-actions {
  display: flex;
  gap: 10px;
}

.dialog-form input {
  flex: 1;
}

.subtitle-results {
  display: grid;
  gap: 8px;
}

.subtitle-candidate {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 10px;
  border-color: #d6dee1;
  background: #fff;
  color: inherit;
  text-align: left;
}

.subtitle-candidate.selected {
  border-color: #1f6f64;
  background: #eef8f6;
}

.subtitle-candidate span,
.subtitle-candidate small {
  color: #52616b;
}
```

- [ ] **Step 6: 构建验证**

Run:

```bash
cd frontend && npm run build
```

Expected: `tsc --noEmit && vite build` 退出码为 0。

## Task 5: 全量验证和提交

**Files:**
- Review: all changed files

- [ ] **Step 1: 运行后端全量测试**

Run:

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
```

Expected: 所有测试 `OK`。

- [ ] **Step 2: 运行前端构建**

Run:

```bash
cd frontend && npm run build
```

Expected: `✓ built`，退出码为 0。

- [ ] **Step 3: 检查空白错误**

Run:

```bash
git diff --check
```

Expected: 无输出，退出码为 0。

- [ ] **Step 4: 检查测试 token 没有进入仓库**

Run:

```bash
rg -n --no-ignore 'token\s*=\s*"[A-Za-z0-9]{20,}"|api_key\s*=\s*"[A-Za-z0-9]{20,}"' . -g '!frontend/node_modules/**' -g '!frontend/dist/**' -g '!.venv/**' -g '!.git/**'
```

Expected: 无输出，退出码为 1。若只命中文档里的占位说明或环境变量名，不视为泄露；真实测试 token 绝不能出现。

- [ ] **Step 5: 提交代码**

Run:

```bash
git status --short
git add backend/src/media_manager/assrt.py backend/src/media_manager/server.py backend/tests/test_assrt.py backend/tests/test_server.py config/config.example.toml frontend/src/App.tsx frontend/src/style.css
git commit -m "feat: add assrt subtitle download"
```

Expected: 提交成功，提交中不包含 `config/config.toml`、真实 token 或媒体样例文件。

## 自检

- spec 的单条媒体手动搜索、候选选择、下载到视频旁边均有任务覆盖。
- spec 的 `<视频文件名>.zh.<字幕扩展名>` 命名由 Task 2 覆盖。
- spec 的缺 token、API 错误、配额超限、压缩包不支持、目标已存在由 Task 1/2/3 覆盖。
- 没有后台任务、批量下载、自动下载、provider 抽象或新依赖。
- 没有把用户提供的测试 token 写入计划正文。
