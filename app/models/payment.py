from __future__ import annotations

from app.extensions import db
from app.models.user import utc_now


PAYMENT_STATUSES = ("pending", "successful", "failed", "cancelled")


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id = db.Column(
        db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="NGN")
    reference = db.Column(db.String(128), nullable=False, unique=True, index=True)
    provider = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="pending", index=True)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    student = db.relationship("User", back_populates="payments")
    course = db.relationship("Course", back_populates="payments")
    enrollment = db.relationship("Enrollment", back_populates="payment", uselist=False)

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'successful', 'failed', 'cancelled')",
            name="ck_payments_status_valid",
        ),
    )

    def to_dict(self, include_course: bool = False) -> dict:
        data = {
            "id": self.id,
            "student_id": self.student_id,
            "course_id": self.course_id,
            "amount": float(self.amount),
            "currency": self.currency,
            "reference": self.reference,
            "provider": self.provider,
            "status": self.status,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_course and self.course:
            data["course"] = self.course.to_public_dict()
        return data


class PaymentEvent(db.Model):
    __tablename__ = "payment_events"

    id = db.Column(db.Integer, primary_key=True)
    provider_event_id = db.Column(db.String(128), nullable=True, index=True)
    reference = db.Column(db.String(128), nullable=True, index=True)
    event = db.Column(db.String(128), nullable=False, index=True)
    payload = db.Column(db.Text, nullable=True)
    payload_hash = db.Column(db.String(128), nullable=False, unique=True, index=True)
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider_event_id": self.provider_event_id,
            "reference": self.reference,
            "event": self.event,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }
