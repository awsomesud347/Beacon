from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.contract import ApiError, ErrorCode


class ApiException(Exception):
    def __init__(
        self, status_code: int, code: ErrorCode, message: str, details: list[str] | None = None
    ):
        self.status_code = status_code
        self.error = ApiError(code=code, message=message, details=details or [])


def not_implemented(what: str) -> ApiException:
    return ApiException(501, ErrorCode.not_implemented, f"{what} is not implemented yet")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiException)
    async def _api(_: Request, exc: ApiException) -> JSONResponse:
        return JSONResponse(exc.error.model_dump(mode="json"), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
        err = ApiError(code=ErrorCode.invalid_request, message="Invalid request", details=details)
        return JSONResponse(err.model_dump(mode="json"), status_code=422)
