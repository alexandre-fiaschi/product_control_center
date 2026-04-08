"""Structured error responses and exception handlers."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.patch_service import InvalidTransitionError, PatchNotFoundError

logger = logging.getLogger("api.errors")


def error_response(status_code: int, detail: str, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {"detail": detail}
    body.update(extra)
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PatchNotFoundError)
    async def patch_not_found(request: Request, exc: PatchNotFoundError) -> JSONResponse:
        logger.warning("Patch not found: %s", exc)
        return error_response(404, str(exc))

    @app.exception_handler(InvalidTransitionError)
    async def invalid_transition(request: Request, exc: InvalidTransitionError) -> JSONResponse:
        logger.warning("Invalid transition: %s", exc)
        return error_response(409, str(exc))

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return error_response(500, "Internal server error")
