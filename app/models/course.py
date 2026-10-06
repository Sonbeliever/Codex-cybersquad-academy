from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func

from app.extensions import db
from app.models.enrollment import Enrollment
from app.models.user import utc_now


COURSE_STATUSES = ("draft", "pending", "approved", "published", "rejected")
COURSE_LANGUAGES = ("english", "hausa")
COURSE_LEVELS = ("beginner", "intermediate", "advanced")


class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(220), nullable=False, unique=True, index=True)
    subtitle = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    language = db.Column(db.String(32), nullable=False, index=True)
    level = db.Column(db.String(32), nullable=False, index=True)
    thumbnail = db.Column(db.String(500), nullable=True)
    duration = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(32), nullable=False, default="draft", index=True)
    admin_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    instructor = db.relationship("User", back_populates="courses")
    category = db.relationship("Category", back_populates="courses")
    modules = db.relationship(
        "Module",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Module.order",
    )
    enrollments = db.relationship(
        "Enrollment",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payments = db.relationship(
        "Payment",
        back_populates="course",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        db.CheckConstraint("price >= 0", name="ck_courses_price_non_negative"),
        db.CheckConstraint("duration >= 0", name="ck_courses_duration_non_negative"),
        db.CheckConstraint(
            "status IN ('draft', 'pending', 'approved', 'published', 'rejected')",
            name="ck_courses_status_valid",
        ),
        db.CheckConstraint(
            "language IN ('english', 'hausa')",
            name="ck_courses_language_valid",
        ),
        db.CheckConstraint(
            "level IN ('beginner', 'intermediate', 'advanced')",
            name="ck_courses_level_valid",
        ),
    )

    def active_enrollment_count(self) -> int:
        """Aggregate count of active/completed enrollments (no student identities)."""
        return (
            db.session.query(func.count(Enrollment.id))
            .filter(
                Enrollment.course_id == self.id,
                Enrollment.status.in_(("active", "completed")),
            )
            .scalar()
            or 0
        )

    def to_public_dict(self, include_curriculum: bool = False, enrolled_count: int | None = None) -> dict:
        data = {
            "id": self.id,
            "title": self.title,
            "slug": self.slug,
            "subtitle": self.subtitle,
            "description": self.description,
            "price": float(self.price or Decimal("0")),
            "language": self.language,
            "level": self.level,
            "thumbnail": self.thumbnail,
            "duration": self.duration,
            "status": self.status,
            "enrolled_count": enrolled_count if enrolled_count is not None else self.active_enrollment_count(),
            "rating": {"average": 0, "count": 0},
            "category": self.category.to_dict() if self.category else None,
            "instructor": self.instructor.to_public_dict() if self.instructor else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_curriculum:
            data["modules"] = [module.to_public_dict() for module in self.modules]
        return data

    def to_owner_dict(self, include_curriculum: bool = False) -> dict:
        data = self.to_public_dict(include_curriculum=False)
        data["admin_note"] = self.admin_note
        if include_curriculum:
            data["modules"] = [module.to_owner_dict() for module in self.modules]
        return data
