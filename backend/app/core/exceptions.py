"""
Global exception handlers for Rabeeh AI.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import logger


class RabeehAIException(Exception):
    """Base exception for Rabeeh AI."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def rabeeh_exception_handler(
    request: Request,
    exc: RabeehAIException,
):
    logger.error(exc.message)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
        },
    )


async def global_exception_handler(
    request: Request,
    exc: Exception,
):
    logger.exception("Unhandled exception")

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal Server Error",
        },
    )


def register_exception_handlers(app: FastAPI):
    app.add_exception_handler(
        RabeehAIException,
        rabeeh_exception_handler,
    )

    app.add_exception_handler(
        Exception,
        global_exception_handler,
    )