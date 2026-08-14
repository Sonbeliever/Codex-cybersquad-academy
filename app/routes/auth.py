from __future__ import annotations

import re
from datetime import datetime, timezone

from flask import Blueprint, current_app, request
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import TokenBlocklist, User
from app.responses import error_response, success_response
from app.security import current_user, generate_access_token, login_required

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _json_body() -> dict:
    if not request.is_json:
        return {}
    return request.get_json(silent=True) or {}


def _validate_registration(payload: dict) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    full_name = str(payload.get("full_name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    phone = str(payload.get("phone", "")).strip() or None
    password = str(payload.get("password", ""))

    if not full_name:
        errors["full_name"] = "Full name is required."
    elif len(full_name) > 150:
        errors["full_name"] = "Full name must be 150 characters or fewer."

    if not email:
        errors["email"] = "Email is required."
    elif len(email) > 255 or not EMAIL_RE.match(email):
        errors["email"] = "A valid email address is required."

    if not password:
        errors["password"] = "Password is required."
    elif len(password) < 8:
        errors["password"] = "Password must be at least 8 characters."

    if phone and len(phone) > 32:
        errors["phone"] = "Phone number must be 32 characters or fewer."

    data = {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "password": password,
    }
    return data, errors


@auth_bp.post("/register")
def register():
    payload = _json_body()
    data, errors = _validate_registration(payload)
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    existing_user = User.query.filter_by(email=data["email"]).first()
    if existing_user:
        return error_response("Email is already registered", "EMAIL_ALREADY_EXISTS", 409)

    user = User(
        full_name=data["full_name"],
        email=data["email"],
        phone=data["phone"],
        role="student",
    )
    user.set_password(data["password"])

    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("Email is already registered", "EMAIL_ALREADY_EXISTS", 409)

    token = generate_access_token(user)
    return success_response(
        "Registration successful",
        {"user": user.to_dict(), "access_token": token, "token_type": "Bearer"},
        201,
    )


@auth_bp.post("/login")
def login():
    payload = _json_body()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    if not email or not password:
        return error_response(
            "Email and password are required",
            "MISSING_CREDENTIALS",
            422,
            {"email": "Required.", "password": "Required."},
        )

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return error_response("Invalid email or password", "INVALID_CREDENTIALS", 401)

    if not user.is_active:
        return error_response("This account is inactive", "ACCOUNT_INACTIVE", 403)

    token = generate_access_token(user)
    dashboard_path = {
        "student": "/student/dashboard",
        "instructor": "/instructor/dashboard",
        "admin": "/admin/dashboard",
    }.get(user.role, "/student/dashboard")

    return success_response(
        "Login successful",
        {
            "user": user.to_dict(),
            "access_token": token,
            "token_type": "Bearer",
            "dashboard": dashboard_path,
        },
    )


@auth_bp.post("/logout")
@login_required
def logout():
    token_payload = request.jwt_payload
    jti = token_payload["jti"]
    existing = TokenBlocklist.query.filter_by(jti=jti).first()

    if not existing:
        expires_at = datetime.fromtimestamp(token_payload["exp"], timezone.utc)
        db.session.add(
            TokenBlocklist(jti=jti, user_id=current_user().id, expires_at=expires_at)
        )
        db.session.commit()

    return success_response("Logout successful")


@auth_bp.get("/me")
@login_required
def me():
    return success_response("Current user retrieved", {"user": current_user().to_dict()})


@auth_bp.post("/forgot-password")
def forgot_password():
    payload = _json_body()
    email = str(payload.get("email", "")).strip().lower()

    if not email or len(email) > 255 or not EMAIL_RE.match(email):
        return error_response(
            "A valid email address is required",
            "VALIDATION_ERROR",
            422,
            {"email": "A valid email address is required."},
        )

    current_app.logger.info("Password reset requested for %s", email)
    return success_response(
        "If the email exists, password reset instructions will be sent."
    )
