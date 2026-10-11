from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """An expected failure, returned to clients as application/problem+json (RFC 9457)."""

    def __init__(self, status: int, title: str, detail: str | None = None, **extra: Any):
        super().__init__(title)
        self.status = status
        self.title = title
        self.detail = detail
        self.extra = extra


def not_found(what: str) -> AppError:
    return AppError(404, f"{what} not found")


def problem(status: int, title: str, detail: str | None = None, **extra: Any) -> JSONResponse:
    body = {"type": "about:blank", "title": title, "status": status, **({"detail": detail} if detail else {}), **extra}
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return problem(exc.status, exc.title, exc.detail, **exc.extra)
