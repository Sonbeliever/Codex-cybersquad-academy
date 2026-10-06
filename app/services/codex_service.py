from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from app.extensions import db
from app.models import CodexStudentID, User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_qr_token() -> str:
    """Generate a secure random QR token as SHA-256 hash."""
    random_bytes = secrets.token_bytes(32)
    return hashlib.sha256(random_bytes).hexdigest()


def generate_codex_id(year: int, sequence: int) -> str:
    """Generate a Codex Student ID in format CODEX-YYYY-XXXX."""
    return f"CODEX-{year}-{sequence:04d}"


def issue_codex_id(user: User) -> CodexStudentID:
    """Issue a new Codex Student ID to a user."""
    if user.codex_student_id:
        raise ValueError("User already has a Codex Student ID")
    
    year = utc_now().year
    # Find the highest sequence number for this year
    latest_id = db.session.query(CodexStudentID).filter(
        CodexStudentID.codex_id.like(f"CODEX-{year}-%")
    ).order_by(CodexStudentID.id.desc()).first()
    
    if latest_id:
        # Extract sequence from existing ID (e.g., CODEX-2024-0001 -> 1)
        try:
            sequence = int(latest_id.codex_id.split("-")[-1]) + 1
        except (ValueError, IndexError):
            sequence = 1
    else:
        sequence = 1
    
    codex_id = generate_codex_id(year, sequence)
    qr_token = generate_qr_token()
    
    student_id = CodexStudentID(
        user_id=user.id,
        codex_id=codex_id,
        qr_token=qr_token,
        status="active",
    )
    
    db.session.add(student_id)
    db.session.commit()
    
    return student_id


def resolve_qr_token(qr_token: str) -> CodexStudentID | None:
    """Resolve a QR token to a Codex Student ID."""
    return CodexStudentID.query.filter_by(qr_token=qr_token).first()


def validate_qr_token(qr_token: str) -> tuple[bool, str, CodexStudentID | None]:
    """
    Validate a QR token and return (is_valid, error_code, student_id).
    
    Returns:
        (True, None, student_id) if valid
        (False, error_code, None) if invalid
    """
    if not qr_token or len(qr_token) != 64:
        return False, "INVALID_TOKEN_FORMAT", None
    
    student_id = resolve_qr_token(qr_token)
    if not student_id:
        return False, "INVALID_QR_CODE", None
    
    if not student_id.user:
        return False, "USER_NOT_FOUND", None
    
    if not student_id.user.is_active:
        return False, "ACCOUNT_INACTIVE", None
    
    if student_id.status == "revoked":
        return False, "ID_REVOKED", None
    
    if student_id.status == "suspended":
        return False, "ID_SUSPENDED", None
    
    return True, None, student_id
