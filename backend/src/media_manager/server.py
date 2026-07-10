from __future__ import annotations

from pathlib import Path
from typing import Any
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
import uvicorn

from .assrt import AssrtClient, download_subtitle, subtitle_query
from .config import AppConfig, append_library, load_config
from .errors import AppError
from .media import MediaItem, scan_libraries
from .nfo import write_nfo
from .rename import apply_rename, preview_rename
from .tmdb import TMDBClient


STATIC_DIR = Path(os.environ.get("MEDIA_MANAGER_STATIC_DIR", "frontend/dist")).resolve()


class LibraryInput(BaseModel):
    name: str
    kind: str
    path: str


class MetadataApplyInput(BaseModel):
    tmdb_id: int


class MetadataSearchInput(BaseModel):
    query: str | None = None


class SubtitleSearchInput(BaseModel):
    query: str | None = None


class SubtitleDownloadInput(BaseModel):
    subtitle_id: int


def create_app(config: AppConfig | None = None) -> FastAPI:
    app = FastAPI(title="Media Manager")
    app.state.config = config or load_config()

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(exc.payload(), status_code=exc.status)

    @app.get("/api/health")
    def health() -> dict[str, object]:
        cfg = _config(app)
        return {
            "status": "ok",
            "config": str(cfg.path),
            "media_dir": str(cfg.media_dir),
            "tmdb": "configured" if _tmdb_api_key(cfg) else "missing",
            "assrt": "configured" if _assrt_token(cfg) else "missing",
        }

    @app.get("/api/libraries")
    def libraries() -> list[dict[str, str]]:
        return [_library_dict(library) for library in _config(app).libraries]

    @app.post("/api/libraries")
    def add_library(input: LibraryInput) -> list[dict[str, str]]:
        if input.kind not in {"movie", "series"}:
            raise AppError("invalid_library_path", "媒体目录类型必须是 movie 或 series", input.kind, input.path)
        library_path = Path(input.path)
        media_dir = _config(app).media_dir.resolve()
        if not library_path.is_absolute() or not library_path.resolve().is_relative_to(media_dir):
            raise AppError("invalid_library_path", "媒体目录必须是媒体根目录内的绝对路径", str(media_dir), input.path)
        if not library_path.is_dir():
            raise AppError("invalid_library_path", "媒体目录不存在或不是目录", path=input.path)
        try:
            append_library(_config(app).path, input.name, input.kind, library_path)
        except OSError as exc:
            raise AppError("config_write_failed", "写入配置失败", str(exc), input.path) from exc
        app.state.config = load_config(_config(app).path)
        return [_library_dict(library) for library in _config(app).libraries]

    @app.get("/api/media")
    def media() -> dict[str, object]:
        items = [item.to_dict() for item in _scan(app)]
        return {"count": len(items), "items": items}

    @app.post("/api/media/{media_id}/metadata/search")
    def metadata_search(media_id: str, input: MetadataSearchInput | None = None) -> dict[str, object]:
        item = _find_media(app, media_id)
        query = (input.query.strip() if input and input.query else "") or item.title
        results = _tmdb(app).search(query, item.kind, item.year)
        return {"query": query, "results": results}

    @app.post("/api/media/{media_id}/metadata/apply")
    def metadata_apply(media_id: str, input: MetadataApplyInput) -> dict[str, str]:
        item = _find_media(app, media_id)
        metadata = _tmdb(app).details(item.kind, input.tmdb_id)
        nfo_path = write_nfo(item, metadata)
        return {"nfo_path": str(nfo_path)}

    @app.post("/api/media/{media_id}/rename/preview")
    def rename_preview(media_id: str) -> dict[str, object]:
        return preview_rename(_find_media(app, media_id))

    @app.post("/api/media/{media_id}/rename/apply")
    def rename_apply(media_id: str) -> dict[str, object]:
        return apply_rename(_find_media(app, media_id))

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

    @app.get("/{path:path}")
    def static(path: str) -> Response:
        if not STATIC_DIR.exists():
            return JSONResponse({"status": "frontend_not_built", "static_dir": str(STATIC_DIR)}, status_code=404)
        target = (STATIC_DIR / path).resolve()
        if not target.is_relative_to(STATIC_DIR):
            return JSONResponse({"error": "not found"}, status_code=404)
        if not path or not target.exists():
            target = STATIC_DIR / "index.html"
        return FileResponse(target)

    return app


def run() -> None:
    config = load_config()
    server_config = config.raw.get("server", {})
    host = str(os.environ.get("MEDIA_MANAGER_HOST", server_config.get("host", "0.0.0.0")))
    port = int(os.environ.get("MEDIA_MANAGER_PORT", server_config.get("port", 8000)))
    uvicorn.run(create_app(config), host=host, port=port)


def _config(app: FastAPI) -> AppConfig:
    return app.state.config


def _scan(app: FastAPI) -> list[MediaItem]:
    return scan_libraries(_config(app).libraries)


def _find_media(app: FastAPI, media_id: str) -> MediaItem:
    for item in _scan(app):
        if item.id == media_id:
            return item
    raise AppError("media_not_found", "媒体条目不存在或已经移动", media_id, status=404)


def _tmdb(app: FastAPI) -> TMDBClient:
    return TMDBClient(_tmdb_api_key(_config(app)))


def _assrt(app: FastAPI) -> AssrtClient:
    return AssrtClient(_assrt_token(_config(app)))


def _tmdb_api_key(config: AppConfig) -> str:
    raw = config.raw
    tmdb_config = raw.get("tmdb", {})
    api_key_env = str(tmdb_config.get("api_key_env", "TMDB_API_KEY"))
    return os.environ.get(api_key_env) or str(tmdb_config.get("api_key", ""))


def _assrt_token(config: AppConfig) -> str:
    raw = config.raw
    assrt_config = raw.get("assrt", {})
    token_env = str(assrt_config.get("token_env", "ASSRT_API_TOKEN"))
    return os.environ.get(token_env) or str(assrt_config.get("token", ""))


def _library_dict(library: Any) -> dict[str, str]:
    return {"name": library.name, "kind": library.kind, "path": str(library.path)}


if __name__ == "__main__":
    run()
