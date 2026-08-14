from __future__ import annotations

from flask import Flask
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

from app.responses import error_response


class APIError(Exception):
    def __init__(
        self,
        message: str,
        error_code: str = "API_ERROR",
        status_code: int = 400,
        details: dict | None = None,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details
        super().__init__(message)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(error: APIError):
        return error_response(
            error.message, error.error_code, error.status_code, error.details
        )

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return error_response(
            error.description or "Request failed",
            error.name.upper().replace(" ", "_"),
            error.code or 500,
        )

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error: SQLAlchemyError):
        app.logger.exception("Database error: %s", error)
        return error_response("A database error occurred", "DATABASE_ERROR", 500)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("Unhandled error: %s", error)
        return error_response("An unexpected error occurred", "INTERNAL_SERVER_ERROR", 500)
