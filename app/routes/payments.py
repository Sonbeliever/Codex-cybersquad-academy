from __future__ import annotations

import hashlib
import json

from flask import Blueprint, current_app, request
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Course, Enrollment, Payment, PaymentEvent
from app.models.user import utc_now
from app.responses import error_response, success_response
from app.routes.helpers import json_body, pagination_args, pagination_payload
from app.security import current_user, login_required, student_required
from app.services.payment_service import PaymentProviderError, PaymentService

payments_bp = Blueprint("payments", __name__, url_prefix="/api")


@payments_bp.post("/payments/initialize")
@student_required
def initialize_payment():
    payload = json_body()
    course_id = payload.get("course_id")
    course = db.session.get(Course, course_id) if course_id is not None else None
    if not course:
        return error_response("Course was not found", "COURSE_NOT_FOUND", 404)
    if course.status != "published":
        return error_response("Students can only purchase published courses", "COURSE_NOT_PUBLISHED", 403)

    existing_enrollment = Enrollment.query.filter(
        Enrollment.student_id == current_user().id,
        Enrollment.course_id == course.id,
        Enrollment.status.in_(("active", "completed")),
    ).first()
    if existing_enrollment:
        return error_response("You are already enrolled in this course", "ENROLLMENT_EXISTS", 409)

    if float(course.price or 0) == 0:
        payment = Payment(
            student_id=current_user().id,
            course_id=course.id,
            amount=0,
            currency="NGN",
            reference=PaymentService.generate_reference(),
            provider="internal",
            status="successful",
            paid_at=utc_now(),
        )
        db.session.add(payment)
        db.session.flush()
        db.session.add(Enrollment(student_id=current_user().id, course_id=course.id, payment_id=payment.id, status="active"))
        db.session.commit()
        return success_response("Enrollment created for free course", {"payment": payment.to_dict()}, 201)

    try:
        payment, provider_data = PaymentService.initialize_payment(current_user(), course)
    except PaymentProviderError:
        return error_response("Payment provider is unavailable", "PAYMENT_PROVIDER_ERROR", 502)
    return success_response("Payment initialized", {"payment": {"id": payment.id, "reference": payment.reference, "amount": float(payment.amount), "currency": payment.currency, "provider_data": provider_data.get("data")}}, 201)


@payments_bp.get("/payments/verify/<string:reference>")
@login_required
def verify_payment(reference: str):
    payment = Payment.query.filter_by(reference=reference).first()
    if not payment:
        return error_response("Payment was not found", "PAYMENT_NOT_FOUND", 404)
    if current_user().role != "admin" and payment.student_id != current_user().id:
        return error_response("You cannot access this payment", "PAYMENT_FORBIDDEN", 403)

    try:
        result = PaymentService.verify_payment(payment)
    except PaymentProviderError as exc:
        current_app.logger.warning("Payment verification rejected: reference=%s reason=%s", reference, exc)
        return error_response("Payment verification failed", "VERIFICATION_FAILED", 400)
    if result.status == "successful":
        return success_response("Payment verified", {"payment": result.to_dict()}, 200)
    if result.status == "pending":
        return success_response("Payment is still pending", {"payment": result.to_dict()}, 202)
    return error_response("Payment was not successful", "PAYMENT_NOT_SUCCESSFUL", 400, {"payment": result.to_dict()})


@payments_bp.get("/student/payments")
@student_required
def student_payments():
    page, per_page = pagination_args()
    pagination = Payment.query.filter_by(student_id=current_user().id).order_by(Payment.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    items = pagination.items
    payments = [p.to_dict(include_course=True) for p in items]
    return success_response("Payments retrieved", {"payments": payments, "pagination": pagination_payload(pagination)})


@payments_bp.post("/webhooks/paystack")
def paystack_webhook():
    signature = request.headers.get("x-paystack-signature", "")
    raw = request.get_data()
    if not PaymentService.verify_webhook_signature(raw, signature):
        current_app.logger.warning("Rejected Paystack webhook with invalid signature")
        return error_response("Invalid webhook signature", "INVALID_SIGNATURE", 401)

    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return error_response("Malformed webhook payload", "MALFORMED_WEBHOOK", 400)
    event = payload.get("event")
    data = payload["data"]
    reference = data.get("reference")
    if not isinstance(event, str) or not reference or not isinstance(reference, str):
        return error_response("Missing reference", "MISSING_REFERENCE", 400)

    payload_hash = hashlib.sha256(raw).hexdigest()
    provider_event_id = str(data["id"]) if data.get("id") is not None else None
    existing_event = PaymentEvent.query.filter(
        (PaymentEvent.payload_hash == payload_hash)
        | ((PaymentEvent.provider_event_id == provider_event_id) & (provider_event_id is not None))
    ).first()
    if existing_event:
        if existing_event.processed_at:
            return success_response("Webhook already processed", {"reference": reference})
        event_record = existing_event
    else:
        event_record = PaymentEvent(
            provider_event_id=provider_event_id,
            reference=reference,
            event=event,
            payload=raw.decode("utf-8", errors="replace"),
            payload_hash=payload_hash,
        )
        db.session.add(event_record)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            event_record = PaymentEvent.query.filter_by(payload_hash=payload_hash).first()
            if event_record and event_record.processed_at:
                return success_response("Webhook already processed", {"reference": reference})

    payment = Payment.query.filter_by(reference=reference).first()
    if not payment:
        event_record.processed_at = utc_now()
        db.session.commit()
        return success_response("Webhook ignored", {"reference": reference})

    try:
        verified = PaymentService.verify_payment(payment)
    except PaymentProviderError:
        db.session.rollback()
        current_app.logger.warning("Paystack webhook processing failed: reference=%s", reference)
        return error_response("Unable to verify payment", "VERIFICATION_FAILED", 400)

    event_record.processed_at = utc_now()
    db.session.commit()
    current_app.logger.info("Paystack webhook processed: reference=%s status=%s", reference, verified.status)
    return success_response("Webhook processed", {"payment": verified.to_dict()})
