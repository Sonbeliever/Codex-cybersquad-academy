from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

import requests
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Course, Enrollment, Payment
from app.models.user import utc_now


class PaymentProviderError(Exception):
    """Raised when Paystack cannot provide a trustworthy response."""


class PaymentService:
    paystack_init_url = "https://api.paystack.co/transaction/initialize"
    paystack_verify_url = "https://api.paystack.co/transaction/verify/{reference}"
    pending_provider_statuses = {"pending", "ongoing", "queued", "processing"}
    failed_provider_statuses = {"failed", "declined", "reversed"}
    cancelled_provider_statuses = {"abandoned", "cancelled", "canceled"}

    @staticmethod
    def _provider_response_summary(response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            keys = sorted(str(key) for key in payload.keys())[:12]
            return f"status={response.status_code} keys={keys}"
        return f"status={response.status_code} content_type={response.headers.get('Content-Type', '')}"

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Authorization": f"Bearer {current_app.config.get('PAYSTACK_SECRET_KEY', '')}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def generate_reference() -> str:
        return f"pay_{uuid4().hex}"

    @classmethod
    def initialize_payment(cls, student, course: Course) -> tuple[Payment, dict[str, Any]]:
        if not current_app.config.get("PAYSTACK_SECRET_KEY") and not current_app.testing:
            current_app.logger.error("Paystack initialization unavailable: PAYSTACK_SECRET_KEY is not configured")
            raise PaymentProviderError("Paystack is not configured")

        existing = Payment.query.filter(
            Payment.student_id == student.id,
            Payment.course_id == course.id,
            Payment.status == "pending",
        ).order_by(Payment.created_at.desc()).first()
        if existing:
            return existing, {"status": True, "data": {"reference": existing.reference}}

        payment = Payment(
            student_id=student.id,
            course_id=course.id,
            amount=course.price,
            currency="NGN",
            reference=cls.generate_reference(),
            provider="paystack",
            status="pending",
        )
        db.session.add(payment)
        try:
            db.session.flush()
            response = requests.post(
                cls.paystack_init_url,
                json={
                    "email": student.email,
                    "amount": int(Decimal(course.price) * 100),
                    "reference": payment.reference,
                    "currency": "NGN",
                },
                headers=cls._headers(),
                timeout=10,
            )
            if not 200 <= response.status_code < 300:
                current_app.logger.warning(
                    "Paystack initialization response rejected: %s",
                    cls._provider_response_summary(response),
                )
                raise PaymentProviderError("Paystack initialization failed")
            data = response.json()
            if not isinstance(data, dict) or data.get("status") is not True:
                current_app.logger.warning(
                    "Paystack initialization payload rejected: %s",
                    cls._provider_response_summary(response),
                )
                raise PaymentProviderError("Paystack initialization returned an invalid response")
            db.session.commit()
            current_app.logger.info("Payment initialized: reference=%s student=%s course=%s", payment.reference, student.id, course.id)
            return payment, data
        except (requests.RequestException, ValueError, TypeError, PaymentProviderError, SQLAlchemyError) as exc:
            db.session.rollback()
            current_app.logger.exception("Payment initialization failed: student=%s course=%s", student.id, course.id)
            raise PaymentProviderError("Payment initialization failed") from exc

    @classmethod
    def verify_payment(cls, payment: Payment, provider_data: dict[str, Any] | None = None) -> Payment:
        if payment.status == "successful":
            cls._ensure_enrollment(payment)
            db.session.commit()
            return payment

        if provider_data is None:
            try:
                response = requests.get(
                    cls.paystack_verify_url.format(reference=payment.reference),
                    headers=cls._headers(),
                    timeout=10,
                )
                if not 200 <= response.status_code < 300:
                    raise PaymentProviderError("Paystack verification unavailable")
                provider_data = response.json()
            except (requests.RequestException, ValueError, TypeError) as exc:
                current_app.logger.exception("Payment verification unavailable: reference=%s", payment.reference)
                raise PaymentProviderError("Payment verification unavailable") from exc

        result = cls._provider_result(provider_data)
        if result is None:
            current_app.logger.warning("Unexpected Paystack verification response: reference=%s", payment.reference)
            return payment

        provider_transaction = provider_data.get("data", {})
        if provider_transaction.get("reference") and provider_transaction["reference"] != payment.reference:
            raise PaymentProviderError("Paystack reference mismatch")
        customer = provider_transaction.get("customer") or {}
        if customer.get("email") and customer["email"].lower() != payment.student.email.lower():
            raise PaymentProviderError("Paystack customer mismatch")

        try:
            if result == "successful":
                cls._validate_success_amount(payment, provider_transaction)
                payment.status = "successful"
                payment.paid_at = utc_now()
                cls._ensure_enrollment(payment)
            elif result == "failed":
                payment.status = "failed"
            elif result == "cancelled":
                payment.status = "cancelled"
            db.session.commit()
        except (PaymentProviderError, SQLAlchemyError):
            db.session.rollback()
            raise
        current_app.logger.info("Payment state updated: reference=%s status=%s", payment.reference, payment.status)
        return payment

    @classmethod
    def _ensure_enrollment(cls, payment: Payment) -> Enrollment:
        enrollment = Enrollment.query.filter(
            Enrollment.student_id == payment.student_id,
            Enrollment.course_id == payment.course_id,
            Enrollment.status.in_(("active", "completed")),
        ).first()
        if enrollment:
            if enrollment.payment_id is None:
                enrollment.payment_id = payment.id
            return enrollment
        enrollment = Enrollment(
            student_id=payment.student_id,
            course_id=payment.course_id,
            payment_id=payment.id,
            status="active",
        )
        db.session.add(enrollment)
        db.session.flush()
        return enrollment

    @classmethod
    def _provider_result(cls, response: dict[str, Any]) -> str | None:
        if response.get("status") is not True or not isinstance(response.get("data"), dict):
            return None
        status = str(response["data"].get("status", "")).lower()
        if status == "success":
            return "successful"
        if status in cls.failed_provider_statuses:
            return "failed"
        if status in cls.cancelled_provider_statuses:
            return "cancelled"
        if status in cls.pending_provider_statuses:
            return "pending"
        return None

    @staticmethod
    def _validate_success_amount(payment: Payment, provider_transaction: dict[str, Any]) -> None:
        try:
            provider_amount = Decimal(str(provider_transaction["amount"]))
        except (KeyError, InvalidOperation, TypeError) as exc:
            raise PaymentProviderError("Paystack amount is missing") from exc
        if provider_amount != Decimal(payment.amount) * 100:
            raise PaymentProviderError("Paystack amount mismatch")
        if provider_transaction.get("currency") and provider_transaction["currency"] != payment.currency:
            raise PaymentProviderError("Paystack currency mismatch")

    @staticmethod
    def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
        secret = current_app.config.get("PAYSTACK_SECRET_KEY", "")
        if not secret or not signature:
            return False
        computed = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
        return hmac.compare_digest(computed, signature)
