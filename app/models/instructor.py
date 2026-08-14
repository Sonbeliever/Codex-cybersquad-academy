from __future__ import annotations

from app.extensions import db
from app.models.user import utc_now


class InstructorApplication(db.Model):
    __tablename__ = "instructor_applications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expertise = db.Column(db.String(255), nullable=False)
    experience = db.Column(db.Text, nullable=False)
    bio = db.Column(db.Text, nullable=False)
    phone = db.Column(db.String(32), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="pending", index=True)
    admin_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    user = db.relationship("User", back_populates="instructor_applications")

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_instructor_applications_status_valid",
        ),
    )

    def to_dict(self, include_user: bool = False) -> dict:
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "expertise": self.expertise,
            "experience": self.experience,
            "bio": self.bio,
            "phone": self.phone,
            "status": self.status,
            "admin_note": self.admin_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }
        if include_user and self.user:
            data["user"] = self.user.to_dict()
        return data
