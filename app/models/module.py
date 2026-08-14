from __future__ import annotations

from app.extensions import db
from app.models.user import utc_now


class Module(db.Model):
    __tablename__ = "modules"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    order = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    course = db.relationship("Course", back_populates="modules")
    lessons = db.relationship(
        "Lesson",
        back_populates="module",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Lesson.order",
    )

    __table_args__ = (
        db.CheckConstraint('"order" >= 0', name="ck_modules_order_non_negative"),
        db.UniqueConstraint("course_id", "order", name="uq_modules_course_order"),
    )

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "course_id": self.course_id,
            "title": self.title,
            "description": self.description,
            "order": self.order,
            "lessons": [lesson.to_public_dict() for lesson in self.lessons],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_owner_dict(self) -> dict:
        data = self.to_public_dict()
        data["lessons"] = [lesson.to_owner_dict() for lesson in self.lessons]
        return data
