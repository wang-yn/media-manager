from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        detail: str | None = None,
        path: str | None = None,
        status: int = HTTPStatus.BAD_REQUEST,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
        self.path = path
        self.status = status

    def payload(self) -> dict[str, object]:
        error = {"code": self.code, "message": self.message}
        if self.detail:
            error["detail"] = self.detail
        if self.path:
            error["path"] = self.path
        return {"error": error}
