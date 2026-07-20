from __future__ import annotations

from pathlib import Path
from typing import Any
import os
import shutil

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
import uvicorn

from .assrt import AssrtClient, download_subtitle, subtitle_query
from .auth import (
    OAUTH_COOKIE_NAME,
    OAUTH_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    AuthConfig,
    GitHubOAuthClient,
    GitHubOAuthError,
    create_oauth_request,
    error_page,
    forbidden_page,
    issue_session_cookie,
    load_auth_config,
    login_page,
    read_session_cookie,
    verify_oauth_state,
)
from .config import AppConfig, append_library, load_config, remove_library
from .errors import AppError
from .media import MediaItem, audit_libraries, directory_files, scan_libraries
from .nfo import write_nfo
from .rename import apply_batch_rename, apply_rename, preview_batch_rename, preview_rename
from .tmdb import TMDBClient


STATIC_DIR = Path(os.environ.get("MEDIA_MANAGER_STATIC_DIR", "frontend/dist")).resolve()
PUBLIC_PATHS = {"/login", "/auth/github/login", "/auth/github/callback"}
AUTH_PATHS = PUBLIC_PATHS | {"/auth/logout"}


class LibraryInput(BaseModel):
    name: str
    kind: str
    path: str


class LibraryDeleteInput(BaseModel):
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


def create_app(
    config: AppConfig | None = None,
    *,
    auth_enabled: bool = True,
    auth_config: AuthConfig | None = None,
    github_client: GitHubOAuthClient | None = None,
) -> FastAPI:
    app = FastAPI(title="Media Manager")
    app.state.config = config or load_config()
    app.state.auth_enabled = auth_enabled
    app.state.auth_config = (auth_config or load_auth_config()) if auth_enabled else None
    app.state.github_client = github_client or GitHubOAuthClient()

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(exc.payload(), status_code=exc.status)

    @app.middleware("http")
    async def require_auth(request: Request, call_next):
        if not app.state.auth_enabled:
            if request.url.path in AUTH_PATHS:
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return await call_next(request)
        if request.method == "GET" and request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        user = read_session_cookie(app.state.auth_config, request.cookies.get(SESSION_COOKIE_NAME))
        if user is None:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"error": {"code": "authentication_required", "message": "需要登录"}}, status_code=401)
            return RedirectResponse("/login", status_code=303)
        request.state.github_user = user
        return await call_next(request)

    if auth_enabled:
        @app.get("/login")
        def login(request: Request) -> Response:
            if read_session_cookie(app.state.auth_config, request.cookies.get(SESSION_COOKIE_NAME)):
                return RedirectResponse("/", status_code=303)
            return HTMLResponse(login_page())

        @app.get("/auth/github/login")
        def github_login() -> Response:
            oauth = create_oauth_request(app.state.auth_config)
            response = RedirectResponse(oauth.authorize_url, status_code=303)
            response.set_cookie(OAUTH_COOKIE_NAME, oauth.cookie_value, max_age=OAUTH_TTL_SECONDS, secure=True, httponly=True, samesite="Lax", path="/")
            return response

        @app.get("/auth/github/callback")
        def github_callback(request: Request) -> Response:
            code = request.query_params.get("code")
            state = request.query_params.get("state")
            verifier = verify_oauth_state(app.state.auth_config, request.cookies.get(OAUTH_COOKIE_NAME), state)
            if not code or verifier is None:
                return _drop_oauth_cookie(HTMLResponse(error_page(), status_code=400))
            try:
                user = app.state.github_client.authenticate(app.state.auth_config, code, verifier)
            except GitHubOAuthError:
                return _drop_oauth_cookie(HTMLResponse(error_page(), status_code=502))
            if not app.state.auth_config.allows(user.login):
                return _drop_oauth_cookie(HTMLResponse(forbidden_page(user.login), status_code=403))
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(SESSION_COOKIE_NAME, issue_session_cookie(app.state.auth_config, user), max_age=SESSION_TTL_SECONDS, secure=True, httponly=True, samesite="Lax", path="/")
            return _drop_oauth_cookie(response)

        @app.post("/auth/logout")
        def logout() -> Response:
            response = JSONResponse({"redirect": "/login"})
            response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="Lax")
            return response

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

    @app.delete("/api/libraries")
    def delete_library(input: LibraryDeleteInput) -> list[dict[str, str]]:
        if input.kind not in {"movie", "series"}:
            raise AppError("invalid_library_path", "媒体目录类型必须是 movie 或 series", input.kind, input.path)
        try:
            removed = remove_library(_config(app).path, input.kind, Path(input.path))
        except OSError as exc:
            raise AppError("config_write_failed", "写入配置失败", str(exc), input.path) from exc
        if not removed:
            raise AppError("library_not_found", "媒体库不存在", input.path, status=404)
        app.state.config = load_config(_config(app).path)
        return [_library_dict(library) for library in _config(app).libraries]

    @app.get("/api/media")
    def media() -> dict[str, object]:
        items = [_media_dict(item) for item in _scan(app)]
        return {"count": len(items), "items": items}

    @app.get("/api/audit")
    def audit() -> dict[str, object]:
        libraries = _config(app).libraries
        for library in libraries:
            if not Path(library.path).is_dir():
                raise AppError("invalid_library_path", "媒体库目录不存在或不可访问", path=str(library.path))
        return {"libraries": [result.to_dict() for result in audit_libraries(libraries)]}

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

    @app.post("/api/media/{media_id}/rename/batch/preview")
    def rename_batch_preview(media_id: str) -> dict[str, object]:
        item = _find_media(app, media_id)
        if item.kind != "series":
            raise AppError("unsupported_batch_rename_target", "批量重命名预览只支持剧集", item.kind, item.path)
        return preview_batch_rename(_series_items(app, item))

    @app.post("/api/media/{media_id}/rename/batch")
    def rename_batch(media_id: str) -> dict[str, object]:
        item = _find_media(app, media_id)
        return apply_batch_rename(_series_items(app, item))

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

    @app.get("/api/media/{media_id}/files")
    def media_files(media_id: str) -> dict[str, object]:
        root = _item_directory(_find_media(app, media_id))
        files = directory_files(root)
        return {"root_path": str(root), "total_size_bytes": sum(int(file["size_bytes"]) for file in files), "files": files}

    @app.delete("/api/media/{media_id}")
    def delete_media(media_id: str) -> dict[str, str]:
        item = _find_media(app, media_id)
        path = _item_directory(item).resolve()
        library_root = Path(item.library_path).resolve()
        if path == library_root:
            raise AppError("invalid_delete_target", "不能删除媒体库根目录", str(library_root), item.path)
        try:
            shutil.rmtree(path)
        except OSError as exc:
            raise AppError("delete_failed", "删除媒体目录失败", str(exc), str(path), status=500) from exc
        return {"deleted_path": str(path)}

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


def _drop_oauth_cookie(response: Response) -> Response:
    response.delete_cookie(OAUTH_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="Lax")
    return response


def _config(app: FastAPI) -> AppConfig:
    return app.state.config


def _scan(app: FastAPI) -> list[MediaItem]:
    return scan_libraries(_config(app).libraries)


def _find_media(app: FastAPI, media_id: str) -> MediaItem:
    for item in _scan(app):
        if item.id == media_id:
            return item
    raise AppError("media_not_found", "媒体条目不存在或已经移动", media_id, status=404)


def _media_dict(item: MediaItem) -> dict[str, object]:
    data = item.to_dict()
    preview = preview_rename(item)
    data["rename_needed"] = any(Path(change["from"]).resolve() != Path(change["to"]).resolve() for change in preview["changes"])
    return data


def _item_directory(item: MediaItem) -> Path:
    if item.kind == "series":
        return _series_directory(item)
    library_root = Path(item.library_path).resolve()
    directory = Path(item.path).resolve().parent
    if not directory.is_relative_to(library_root) or not directory.is_dir():
        raise AppError("invalid_file_list_target", "无法读取媒体目录", str(library_root), item.path)
    return directory


def _series_items(app: FastAPI, item: MediaItem) -> list[MediaItem]:
    root = _series_directory(item).resolve()
    return [candidate for candidate in _scan(app) if candidate.kind == "series" and _series_directory(candidate).resolve() == root]


def _series_directory(item: MediaItem) -> Path:
    if item.kind != "series":
        raise AppError("unsupported_delete_target", "当前只支持删除剧集目录", item.kind)
    library_root = Path(item.library_path).resolve()
    video = Path(item.path).resolve()
    try:
        relative = video.relative_to(library_root)
    except ValueError as exc:
        raise AppError("invalid_delete_target", "媒体文件不在媒体库目录内", str(library_root), item.path) from exc
    if len(relative.parts) < 2:
        raise AppError("invalid_delete_target", "无法识别剧集目录", item.path)
    show_dir = (library_root / relative.parts[0]).resolve()
    if show_dir == library_root or not show_dir.is_relative_to(library_root) or not show_dir.is_dir():
        raise AppError("invalid_delete_target", "无法识别剧集目录", item.path)
    return show_dir


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
