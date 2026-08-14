from __future__ import annotations

from flask import jsonify


def success_response(message: str, data: dict | None = None, status_code: int = 200):
    payload = {"success": True, "message": message, "data": data or {}}
    return jsonify(payload), status_code


def error_response(
    message: str,
    error: str,
    status_code: int = 400,
    details: dict | None = None,
):
    payload = {"success": False, "message": message, "error": error}
    if details:
        payload["details"] = details
    return jsonify(payload), status_code
