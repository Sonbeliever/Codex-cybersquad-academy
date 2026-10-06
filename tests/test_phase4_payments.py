from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

from app.extensions import db
from app.models import Payment, Enrollment
from app.models import PaymentEvent
from tests.conftest import (
    auth_header,
    create_category,
    create_course,
    create_user,
    create_module,
    create_lesson,
)


def published_paid_course_fixture():
    category = create_category()
    instructor = create_user("Instructor", "inst2@example.com", role="instructor")
    course = create_course(instructor, category, status="published")
    module = create_module(course)
    _ = create_lesson(module, title="L1", is_preview=False)
    return course


def test_free_course_enrollment(app, client):
    student = create_user("S", "s@example.com")
    category = create_category()
    instructor = create_user("I", "i@example.com", role="instructor")
    course = create_course(instructor, category, status="published")
    # make it free
    course.price = 0
    db.session.commit()

    response = client.post("/api/payments/initialize", json={"course_id": course.id}, headers=auth_header(student))
    assert response.status_code == 201
    data = response.get_json()["data"]["payment"]
    assert data["amount"] == 0
    assert Payment.query.filter_by(course_id=course.id, student_id=student.id).count() == 1
    assert Enrollment.query.filter_by(course_id=course.id, student_id=student.id).count() == 1


@patch("app.services.payment_service.requests.post")
def test_paid_course_initialization(mock_post, app, client):
    student = create_user("S2", "s2@example.com")
    course = published_paid_course_fixture()
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"status": True, "data": {"authorization_url": "https://pay", "reference": "ref_123"}}
    response = client.post("/api/payments/initialize", json={"course_id": course.id}, headers=auth_header(student))
    assert response.status_code == 201
    payload = response.get_json()["data"]["payment"]
    assert "reference" in payload


@patch("app.services.payment_service.requests.get")
def test_successful_payment_verification(mock_get, app, client):
    student = create_user("S3", "s3@example.com")
    course = published_paid_course_fixture()
    # initialize payment record
    from app.services.payment_service import PaymentService

    with patch("app.services.payment_service.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": True, "data": {}}
        payment, _ = PaymentService.initialize_payment(student, course)
    # mock verify returns success with matching amount
    mock_get.return_value.json.return_value = {"status": True, "data": {"status": "success", "amount": int(float(payment.amount) * 100)}}
    mock_get.return_value.status_code = 200
    response = client.get(f"/api/payments/verify/{payment.reference}", headers=auth_header(student))
    assert response.status_code == 200
    p = Payment.query.filter_by(reference=payment.reference).first()
    assert p.status == "successful"
    assert Enrollment.query.filter_by(student_id=student.id, course_id=course.id).count() == 1


@patch("app.services.payment_service.requests.get")
def test_failed_payment_verification(mock_get, app, client):
    student = create_user("S4", "s4@example.com")
    course = published_paid_course_fixture()
    with patch("app.services.payment_service.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": True, "data": {}}
        payment, _ = __import__("app.services.payment_service", fromlist=["PaymentService"]).PaymentService.initialize_payment(student, course)
    mock_get.return_value.json.return_value = {"status": True, "data": {"status": "failed", "amount": int(float(payment.amount) * 100)}}
    mock_get.return_value.status_code = 200
    response = client.get(f"/api/payments/verify/{payment.reference}", headers=auth_header(student))
    assert response.status_code in (400, 200)


def test_admin_payments_report(app, client):
    admin = create_user("Admin2", "admin2@example.com", role="admin")
    student = create_user("Buyer", "buyer@example.com")
    instructor = create_user("I2", "i2@example.com", role="instructor")
    category = create_category()
    course = create_course(instructor, category, status="published")
    # create payments
    from app.models import Payment
    p1 = Payment(student_id=student.id, course_id=course.id, amount=1000, currency="NGN", reference="r1", provider="paystack", status="successful")
    p2 = Payment(student_id=student.id, course_id=course.id, amount=2000, currency="NGN", reference="r2", provider="paystack", status="pending")
    db.session.add_all([p1, p2])
    db.session.commit()

    # admin can access
    resp = client.get("/api/admin/payments", headers=auth_header(admin))
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["aggregates"]["total_successful_revenue"] >= 1000
    # student cannot access
    resp2 = client.get("/api/admin/payments", headers=auth_header(student))
    assert resp2.status_code == 403


@patch("app.services.payment_service.requests.post")
def test_repeated_initialization_reuses_pending_payment(mock_post, app, client):
    student = create_user("Repeat", "payment-repeat@example.com")
    course = published_paid_course_fixture()
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"status": True, "data": {"authorization_url": "https://pay"}}
    headers = auth_header(student)

    first = client.post("/api/payments/initialize", json={"course_id": course.id}, headers=headers)
    second = client.post("/api/payments/initialize", json={"course_id": course.id}, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.get_json()["data"]["payment"]["reference"] == second.get_json()["data"]["payment"]["reference"]
    assert Payment.query.filter_by(student_id=student.id, course_id=course.id).count() == 1
    mock_post.assert_called_once()


@patch("app.services.payment_service.requests.get")
def test_repeated_successful_verification_is_idempotent(mock_get, app, client):
    student = create_user("Repeat Verify", "payment-repeat-verify@example.com")
    course = published_paid_course_fixture()
    payment = Payment(student_id=student.id, course_id=course.id, amount=5000, currency="NGN", reference="repeat-verify", provider="paystack", status="pending")
    db.session.add(payment)
    db.session.commit()
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"status": True, "data": {"status": "success", "reference": payment.reference, "amount": 500000, "currency": "NGN"}}
    headers = auth_header(student)

    first = client.get(f"/api/payments/verify/{payment.reference}", headers=headers)
    second = client.get(f"/api/payments/verify/{payment.reference}", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert Payment.query.filter_by(reference=payment.reference).count() == 1
    assert Enrollment.query.filter_by(student_id=student.id, course_id=course.id).count() == 1
    mock_get.assert_called_once()


def test_payment_verification_is_student_scoped(app, client):
    owner = create_user("Owner", "payment-owner@example.com")
    other = create_user("Other", "payment-other@example.com")
    course = published_paid_course_fixture()
    payment = Payment(student_id=owner.id, course_id=course.id, amount=5000, currency="NGN", reference="owned-ref", provider="paystack", status="pending")
    db.session.add(payment)
    db.session.commit()

    response = client.get(f"/api/payments/verify/{payment.reference}", headers=auth_header(other))
    assert response.status_code == 403
    assert response.get_json()["error"] == "PAYMENT_FORBIDDEN"


@patch("app.services.payment_service.requests.get")
def test_unknown_provider_state_stays_pending(mock_get, app, client):
    student = create_user("Pending", "payment-pending@example.com")
    course = published_paid_course_fixture()
    payment = Payment(student_id=student.id, course_id=course.id, amount=5000, currency="NGN", reference="pending-ref", provider="paystack", status="pending")
    db.session.add(payment)
    db.session.commit()
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"status": True, "data": {"status": "unrecognized"}}

    response = client.get(f"/api/payments/verify/{payment.reference}", headers=auth_header(student))
    db.session.refresh(payment)
    assert response.status_code == 202
    assert payment.status == "pending"
    assert Enrollment.query.filter_by(student_id=student.id, course_id=course.id).count() == 0


@patch("app.services.payment_service.requests.get")
def test_successful_webhook_is_stored_and_idempotent(mock_get, app, client):
    app.config["PAYSTACK_SECRET_KEY"] = "test-paystack-secret"
    student = create_user("Webhook", "payment-webhook@example.com")
    course = published_paid_course_fixture()
    payment = Payment(student_id=student.id, course_id=course.id, amount=5000, currency="NGN", reference="webhook-ref", provider="paystack", status="pending")
    db.session.add(payment)
    db.session.commit()
    body = {"event": "charge.success", "data": {"id": 99, "reference": payment.reference, "status": "success", "amount": 500000, "currency": "NGN"}}
    raw = json.dumps(body, separators=(",", ":")).encode()
    signature = hmac.new(b"test-paystack-secret", raw, hashlib.sha512).hexdigest()
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"status": True, "data": {"status": "success", "reference": payment.reference, "amount": 500000, "currency": "NGN"}}

    headers = {"x-paystack-signature": signature, "Content-Type": "application/json"}
    first = client.post("/api/webhooks/paystack", data=raw, headers=headers)
    second = client.post("/api/webhooks/paystack", data=raw, headers=headers)
    db.session.refresh(payment)
    assert first.status_code == 200
    assert second.status_code == 200
    assert payment.status == "successful"
    assert payment.paid_at is not None
    assert PaymentEvent.query.count() == 1
    assert PaymentEvent.query.first().processed_at is not None
    assert Enrollment.query.filter_by(student_id=student.id, course_id=course.id).count() == 1


def test_invalid_webhook_signature_is_rejected(app, client):
    body = json.dumps({"event": "charge.success", "data": {"reference": "unknown"}}).encode()
    response = client.post("/api/webhooks/paystack", data=body, headers={"x-paystack-signature": "invalid"})
    assert response.status_code == 401
    assert PaymentEvent.query.count() == 0


@patch("app.services.payment_service.requests.get")
def test_paystack_amount_mismatch_does_not_grant_access(mock_get, app, client):
    student = create_user("Mismatch", "payment-mismatch@example.com")
    course = published_paid_course_fixture()
    payment = Payment(student_id=student.id, course_id=course.id, amount=5000, currency="NGN", reference="mismatch-ref", provider="paystack", status="pending")
    db.session.add(payment)
    db.session.commit()
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"status": True, "data": {"status": "success", "reference": payment.reference, "amount": 1, "currency": "NGN"}}

    response = client.get(f"/api/payments/verify/{payment.reference}", headers=auth_header(student))
    db.session.refresh(payment)
    assert response.status_code == 400
    assert payment.status == "pending"
    assert Enrollment.query.filter_by(student_id=student.id, course_id=course.id).count() == 0
