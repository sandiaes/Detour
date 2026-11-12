"""Domain errors with a stable machine-readable code, rendered as ``{"detail", "code"}``."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def invalid(code: str, detail: str) -> ApiError:
    return ApiError(422, code, detail)


def conflict(code: str, detail: str) -> ApiError:
    return ApiError(409, code, detail)


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code}
        )
