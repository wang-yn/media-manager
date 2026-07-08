from __future__ import annotations

from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import json
import os
from urllib.parse import urlparse

from .config import AppConfig, load_config
from .media import scan_libraries


STATIC_DIR = Path(os.environ.get("MEDIA_MANAGER_STATIC_DIR", "frontend/dist")).resolve()


class Handler(SimpleHTTPRequestHandler):
    app_config: AppConfig

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._json({"status": "ok", "config": str(self.app_config.path), "media_dir": str(self.app_config.media_dir)})
            return
        if self.path == "/api/config":
            self._json(_public_config(self.app_config.raw))
            return
        if self.path == "/api/scan":
            items = [item.to_dict() for item in scan_libraries(self.app_config.libraries)]
            self._json({"count": len(items), "items": items})
            return
        self._static()

    def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self) -> None:
        if not STATIC_DIR.exists():
            self._json({"status": "frontend_not_built", "static_dir": str(STATIC_DIR)}, HTTPStatus.NOT_FOUND)
            return
        request_path = urlparse(self.path).path
        target = (STATIC_DIR / request_path.lstrip("/")).resolve()
        if not target.is_relative_to(STATIC_DIR):
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        if request_path == "/" or not target.exists():
            target = STATIC_DIR / "index.html"
        self.path = "/" + str(target.relative_to(STATIC_DIR))
        super().do_GET()

    def translate_path(self, path: str) -> str:
        return str(STATIC_DIR / path.lstrip("/"))


def run() -> None:
    config = load_config()
    server_config = config.raw.get("server", {})
    host = str(os.environ.get("MEDIA_MANAGER_HOST", server_config.get("host", "0.0.0.0")))
    port = int(os.environ.get("MEDIA_MANAGER_PORT", server_config.get("port", 8000)))
    Handler.app_config = config
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"media-manager backend listening on http://{host}:{port}")
    httpd.serve_forever()


def _public_config(raw: dict[str, Any]) -> dict[str, Any]:
    hidden = {"api_key", "token", "password", "secret"}

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: ("***" if key.lower() in hidden else scrub(item)) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return scrub(raw)


if __name__ == "__main__":
    run()
