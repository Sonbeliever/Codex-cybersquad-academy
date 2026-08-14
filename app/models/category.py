from __future__ import annotations

from app.extensions import db
from app.models.user import utc_now


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    slug = db.Column(db.String(160), nullable=False, unique=True, index=True)
    description = db.Column(db.Text, nullable=True)
    image = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    courses = db.relationship("Course", back_populates="category")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "image": self.image,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
