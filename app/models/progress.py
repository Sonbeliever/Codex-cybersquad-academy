from __future__ import annotations

from app.extensions import db
from app.models.user import utc_now


class LessonProgress(db.Model):
    __tablename__ = "lesson_progress"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lesson_id = db.Column(
        db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    completed = db.Column(db.Boolean, nullable=False, default=False, index=True)
    watch_time = db.Column(db.Integer, nullable=False, default=0)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    student = db.relationship("User", back_populates="lesson_progress")
    lesson = db.relationship("Lesson", back_populates="progress_records")

    __table_args__ = (
        db.CheckConstraint("watch_time >= 0", name="ck_lesson_progress_watch_time_non_negative"),
        db.UniqueConstraint("student_id", "lesson_id", name="uq_lesson_progress_student_lesson"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "student_id": self.student_id,
            "lesson_id": self.lesson_id,
            "completed": self.completed,
            "watch_time": self.watch_time,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
