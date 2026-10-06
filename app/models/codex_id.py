from __future__ import annotations

from app.extensions import db
from app.models.user import utc_now


class CodexStudentID(db.Model):
    __tablename__ = "codex_student_ids"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    codex_id = db.Column(db.String(20), nullable=False, unique=True, index=True)
    qr_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    status = db.Column(db.String(32), nullable=False, default="active", index=True)
    issued_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    user = db.relationship("User", back_populates="codex_student_id")
    attendance_records = db.relationship(
        "AttendanceRecord", back_populates="student_identity", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active', 'suspended', 'revoked')",
            name="ck_codex_student_ids_status_valid",
        ),
    )

    def to_dict(self, include_user: bool = False, include_qr: bool = False) -> dict:
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "codex_id": self.codex_id,
            "status": self.status,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_qr:
            data["qr_token"] = self.qr_token
        if include_user and self.user:
            data["user"] = self.user.to_public_dict()
        return data

    def to_verification_dict(self) -> dict:
        """Minimal dict for QR verification (no sensitive data)."""
        return {
            "codex_id": self.codex_id,
            "status": self.status,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
        }
