from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models.user import utc_now


ENROLLMENT_STATUSES = ("active", "completed", "cancelled")


class Enrollment(db.Model):
    __tablename__ = "enrollments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id = db.Column(db.Integer, nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default="active", index=True)
    enrolled_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    student = db.relationship("User", back_populates="enrollments")
    course = db.relationship("Course", back_populates="enrollments")

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_enrollments_status_valid",
        ),
        db.Index(
            "uq_enrollments_student_course_active_completed",
            "student_id",
            "course_id",
            unique=True,
            postgresql_where=db.text("status IN ('active', 'completed')"),
            sqlite_where=db.text("status IN ('active', 'completed')"),
        ),
    )

    def to_dict(self, include_course: bool = False, progress_percentage: int | None = None) -> dict:
        data = {
            "id": self.id,
            "student_id": self.student_id,
            "course_id": self.course_id,
            "payment_id": self.payment_id,
            "status": self.status,
            "enrolled_at": self.enrolled_at.isoformat() if self.enrolled_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_course and self.course:
            data["course"] = self.course.to_public_dict()
        if progress_percentage is not None:
            data["progress_percentage"] = int(progress_percentage)
        return data

    def to_admin_dict(self) -> dict:
        data = self.to_dict(include_course=True)
        if self.student:
            data["student"] = self.student.to_public_dict()
        return data
