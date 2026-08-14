from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import uuid4

import jwt
from flask import current_app, g, request

from app.extensions import db
from app.models import TokenBlocklist, User
from app.responses import error_response


def generate_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=current_app.config["JWT_ACCESS_TOKEN_MINUTES"])
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])


def _bearer_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def current_user() -> User:
    return g.current_user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        token = _bearer_token()
        if not token:
            return error_response("Authentication is required", "AUTHENTICATION_REQUIRED", 401)

        try:
            payload = decode_access_token(token)
        except jwt.ExpiredSignatureError:
            return error_response("Authentication token has expired", "TOKEN_EXPIRED", 401)
        except jwt.InvalidTokenError:
            return error_response("Invalid authentication token", "INVALID_TOKEN", 401)

        revoked = TokenBlocklist.query.filter_by(jti=payload.get("jti")).first()
        if revoked:
            return error_response("Authentication token has been revoked", "TOKEN_REVOKED", 401)

        user = db.session.get(User, int(payload["sub"]))
        if not user:
            return error_response("User account was not found", "USER_NOT_FOUND", 401)
        if not user.is_active:
            return error_response("This account is inactive", "ACCOUNT_INACTIVE", 403)

        g.current_user = user
        request.jwt_payload = payload
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles: str):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user().role not in roles:
                return error_response("You do not have permission", "FORBIDDEN", 403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


student_required = roles_required("student")
instructor_required = roles_required("instructor")
admin_required = roles_required("admin")
