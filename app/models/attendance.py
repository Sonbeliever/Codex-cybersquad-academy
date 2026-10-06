from __future__ import annotations

from app.extensions import db
from app.models.user import utc_now


class AttendanceSession(db.Model):
    __tablename__ = "attendance_sessions"

    id = db.Column(db.Integer, primary_key=True)
    created_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = db.Column(db.String(180), nullable=False)
    session_type = db.Column(db.String(64), nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(255), nullable=True)
    starts_at = db.Column(db.DateTime(timezone=True), nullable=False)
    ends_at = db.Column(db.DateTime(timezone=True), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="draft", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    creator = db.relationship("User", back_populates="attendance_sessions")
    attendance_records = db.relationship(
        "AttendanceRecord", back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('draft', 'active', 'closed')",
            name="ck_attendance_sessions_status_valid",
        ),
        db.CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="ck_attendance_sessions_time_valid"),
    )

    def to_dict(self, include_creator: bool = False, include_records_count: bool = False) -> dict:
        data = {
            "id": self.id,
            "created_by": self.created_by,
            "title": self.title,
            "session_type": self.session_type,
            "description": self.description,
            "location": self.location,
            "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_creator and self.creator:
            data["creator"] = self.creator.to_public_dict()
        if include_records_count:
            data["attendance_count"] = len(self.attendance_records)
        return data


class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_identity_id = db.Column(
        db.Integer, db.ForeignKey("codex_student_ids.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scanned_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    scanned_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    verification_method = db.Column(db.String(32), nullable=False, default="qr")
    status = db.Column(db.String(32), nullable=False, default="present", index=True)

    session = db.relationship("AttendanceSession", back_populates="attendance_records")
    student_identity = db.relationship("CodexStudentID", back_populates="attendance_records")
    scanner = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('present', 'absent', 'excused')",
            name="ck_attendance_records_status_valid",
        ),
        db.UniqueConstraint("session_id", "student_identity_id", name="uq_attendance_records_session_student"),
    )

    def to_dict(self, include_student: bool = False, include_scanner: bool = False) -> dict:
        data = {
            "id": self.id,
            "session_id": self.session_id,
            "student_identity_id": self.student_identity_id,
            "scanned_by": self.scanned_by,
            "scanned_at": self.scanned_at.isoformat() if self.scanned_at else None,
            "verification_method": self.verification_method,
            "status": self.status,
        }
        if include_student and self.student_identity:
            data["student"] = {
                "codex_id": self.student_identity.codex_id,
                "user": self.student_identity.user.to_public_dict() if self.student_identity.user else None,
            }
        if include_scanner and self.scanner:
            data["scanner"] = self.scanner.to_public_dict()
        return data
