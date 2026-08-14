from __future__ import annotations

from app.extensions import db
from app.models.user import utc_now


class Lesson(db.Model):
    __tablename__ = "lessons"

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(
        db.Integer, db.ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    video_url = db.Column(db.String(1000), nullable=True)
    duration = db.Column(db.Integer, nullable=False, default=0)
    order = db.Column(db.Integer, nullable=False, default=1)
    is_preview = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    module = db.relationship("Module", back_populates="lessons")
    resources = db.relationship(
        "LessonResource",
        back_populates="lesson",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    progress_records = db.relationship(
        "LessonProgress",
        back_populates="lesson",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        db.CheckConstraint("duration >= 0", name="ck_lessons_duration_non_negative"),
        db.CheckConstraint('"order" >= 0', name="ck_lessons_order_non_negative"),
        db.UniqueConstraint("module_id", "order", name="uq_lessons_module_order"),
    )

    def to_public_dict(self) -> dict:
        data = {
            "id": self.id,
            "module_id": self.module_id,
            "title": self.title,
            "description": self.description,
            "duration": self.duration,
            "order": self.order,
            "is_preview": self.is_preview,
            "resources": [resource.to_dict() for resource in self.resources],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if self.is_preview:
            data["video_url"] = self.video_url
        return data

    def to_owner_dict(self) -> dict:
        data = self.to_public_dict()
        data["video_url"] = self.video_url
        return data


class LessonResource(db.Model):
    __tablename__ = "lesson_resources"

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(
        db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = db.Column(db.String(180), nullable=False)
    file_url = db.Column(db.String(1000), nullable=False)
    file_type = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    lesson = db.relationship("Lesson", back_populates="resources")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lesson_id": self.lesson_id,
            "name": self.name,
            "file_url": self.file_url,
            "file_type": self.file_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
