from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, request
from sqlalchemy import select

from app.extensions import db
from app.models import AttendanceRecord, AttendanceSession, Category, CodexStudentID, Course, Enrollment, InstructorApplication
from app.models import Payment
from app.models.user import utc_now
from app.responses import error_response, success_response
from app.routes.helpers import json_body, pagination_args, pagination_payload, unique_slug
from app.security import admin_required
from app.services.codex_service import issue_codex_id, validate_qr_token

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.post("/categories")
@admin_required
def create_category():
    payload = json_body()
    errors: dict[str, str] = {}
    name = str(payload.get("name", "")).strip()
    if not name:
        errors["name"] = "Category name is required."
    if len(name) > 120:
        errors["name"] = "Category name must be 120 characters or fewer."
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    category = Category(
        name=name,
        slug=unique_slug(Category, name),
        description=str(payload.get("description", "")).strip() or None,
        image=str(payload.get("image", "")).strip() or None,
    )
    db.session.add(category)
    db.session.commit()
    return success_response("Category created successfully", {"category": category.to_dict()}, 201)


@admin_bp.get("/instructor-applications")
@admin_required
def instructor_applications():
    page, per_page = pagination_args()
    pagination = InstructorApplication.query.order_by(
        InstructorApplication.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    return success_response(
        "Instructor applications retrieved",
        {
            "applications": [
                application.to_dict(include_user=True) for application in pagination.items
            ],
            "pagination": pagination_payload(pagination),
        },
    )


@admin_bp.patch("/instructor-applications/<int:application_id>/approve")
@admin_required
def approve_instructor_application(application_id: int):
    application = db.session.get(InstructorApplication, application_id)
    if not application:
        return error_response("Instructor application was not found", "APPLICATION_NOT_FOUND", 404)
    if application.status == "approved":
        return error_response("Application is already approved", "APPLICATION_ALREADY_APPROVED", 409)

    application.status = "approved"
    application.admin_note = str(json_body().get("admin_note", "")).strip() or None
    application.reviewed_at = utc_now()
    application.user.role = "instructor"
    db.session.commit()
    return success_response(
        "Instructor application approved", {"application": application.to_dict(include_user=True)}
    )


@admin_bp.patch("/instructor-applications/<int:application_id>/reject")
@admin_required
def reject_instructor_application(application_id: int):
    application = db.session.get(InstructorApplication, application_id)
    if not application:
        return error_response("Instructor application was not found", "APPLICATION_NOT_FOUND", 404)

    application.status = "rejected"
    application.admin_note = str(json_body().get("admin_note", "")).strip() or None
    application.reviewed_at = utc_now()
    db.session.commit()
    return success_response(
        "Instructor application rejected", {"application": application.to_dict(include_user=True)}
    )


@admin_bp.get("/courses/pending")
@admin_required
def pending_courses():
    page, per_page = pagination_args()
    pagination = Course.query.filter_by(status="pending").order_by(
        Course.created_at.asc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    return success_response(
        "Pending courses retrieved",
        {
            "courses": [course.to_owner_dict(include_curriculum=True) for course in pagination.items],
            "pagination": pagination_payload(pagination),
        },
    )


@admin_bp.patch("/courses/<int:course_id>/approve")
@admin_required
def approve_course(course_id: int):
    course = db.session.get(Course, course_id)
    if not course:
        return error_response("Course was not found", "COURSE_NOT_FOUND", 404)
    if course.status != "pending":
        return error_response("Only pending courses can be approved", "COURSE_NOT_PENDING", 409)

    course.status = "published"
    course.admin_note = str(json_body().get("admin_note", "")).strip() or None
    db.session.commit()
    return success_response("Course approved and published", {"course": course.to_owner_dict()})


@admin_bp.patch("/courses/<int:course_id>/reject")
@admin_required
def reject_course(course_id: int):
    course = db.session.get(Course, course_id)
    if not course:
        return error_response("Course was not found", "COURSE_NOT_FOUND", 404)
    if course.status != "pending":
        return error_response("Only pending courses can be rejected", "COURSE_NOT_PENDING", 409)

    course.status = "rejected"
    course.admin_note = str(json_body().get("admin_note", "")).strip() or None
    db.session.commit()
    return success_response("Course rejected", {"course": course.to_owner_dict()})


@admin_bp.get("/enrollments")
@admin_required
def enrollments_index():
    query = Enrollment.query

    course_id = request.args.get("course_id", type=int)
    if course_id:
        query = query.filter(Enrollment.course_id == course_id)

    student_id = request.args.get("student_id", type=int)
    if student_id:
        query = query.filter(Enrollment.student_id == student_id)

    status = request.args.get("status", "").strip()
    if status:
        query = query.filter(Enrollment.status == status)

    page, per_page = pagination_args()
    pagination = query.order_by(Enrollment.enrolled_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return success_response(
        "Enrollments retrieved",
        {
            "enrollments": [enrollment.to_admin_dict() for enrollment in pagination.items],
            "pagination": pagination_payload(pagination),
        },
    )


@admin_bp.get("/payments")
@admin_required
def payments_index():
    query = Payment.query

    course_id = request.args.get("course_id", type=int)
    if course_id:
        query = query.filter(Payment.course_id == course_id)

    student_id = request.args.get("student_id", type=int)
    if student_id:
        query = query.filter(Payment.student_id == student_id)

    status = request.args.get("status", "").strip()
    if status:
        query = query.filter(Payment.status == status)

    reference = request.args.get("reference", "").strip()
    if reference:
        query = query.filter(Payment.reference == reference)

    page, per_page = pagination_args()
    pagination = query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    items = [p.to_dict(include_course=True) for p in pagination.items]

    # aggregates
    total = query.count()
    successful_count = query.filter(Payment.status == "successful").count()
    pending_count = query.filter(Payment.status == "pending").count()
    failed_count = query.filter(Payment.status == "failed").count()
    filtered_payment_ids = query.with_entities(Payment.id).subquery()
    total_revenue = db.session.query(db.func.coalesce(db.func.sum(Payment.amount), 0)).filter(
        Payment.status == "successful", Payment.id.in_(select(filtered_payment_ids.c.id))
    ).scalar() or 0

    return success_response(
        "Payments retrieved",
        {
            "payments": items,
            "pagination": pagination_payload(pagination),
            "aggregates": {
                "total_payments": int(total),
                "successful_payments": int(successful_count),
                "pending_payments": int(pending_count),
                "failed_payments": int(failed_count),
                "total_successful_revenue": float(total_revenue),
            },
        },
    )


# Codex Student ID Management


@admin_bp.get("/codex-ids")
@admin_required
def list_codex_ids():
    """List all Codex Student IDs."""
    query = CodexStudentID.query

    status = request.args.get("status", "").strip()
    if status:
        query = query.filter(CodexStudentID.status == status)

    search = request.args.get("search", "").strip()
    if search:
        query = query.filter(CodexStudentID.codex_id.ilike(f"%{search}%"))

    page, per_page = pagination_args()
    pagination = query.order_by(CodexStudentID.issued_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return success_response(
        "Codex Student IDs retrieved",
        {
            "codex_ids": [student_id.to_dict(include_user=True) for student_id in pagination.items],
            "pagination": pagination_payload(pagination),
        },
    )


@admin_bp.post("/codex-ids")
@admin_required
def issue_codex_student_id():
    """Issue a new Codex Student ID to a student."""
    payload = json_body()
    user_id = payload.get("user_id")
    if not user_id:
        return error_response("User ID is required", "VALIDATION_ERROR", 422, {"user_id": "User ID is required"})

    from app.models import User
    user = db.session.get(User, user_id)
    if not user:
        return error_response("User not found", "USER_NOT_FOUND", 404)

    if user.role != "student":
        return error_response("Codex IDs can only be issued to students", "INVALID_USER_ROLE", 400)

    try:
        student_id = issue_codex_id(user)
    except ValueError as e:
        return error_response(str(e), "CODEX_ID_EXISTS", 409)

    return success_response(
        "Codex Student ID issued",
        {"codex_id": student_id.to_dict(include_user=True)},
        201,
    )


@admin_bp.get("/codex-ids/<int:id>")
@admin_required
def get_codex_student_id(id: int):
    """Get Codex Student ID details."""
    student_id = db.session.get(CodexStudentID, id)
    if not student_id:
        return error_response("Codex Student ID not found", "CODEX_ID_NOT_FOUND", 404)

    return success_response(
        "Codex Student ID retrieved",
        {"codex_id": student_id.to_dict(include_user=True)},
    )


@admin_bp.patch("/codex-ids/<int:id>/status")
@admin_required
def update_codex_student_id_status(id: int):
    """Update Codex Student ID status."""
    student_id = db.session.get(CodexStudentID, id)
    if not student_id:
        return error_response("Codex Student ID not found", "CODEX_ID_NOT_FOUND", 404)

    payload = json_body()
    status = payload.get("status")
    if status not in ("active", "suspended", "revoked"):
        return error_response("Invalid status value", "VALIDATION_ERROR", 422, {"status": "Status must be active, suspended, or revoked"})

    student_id.status = status
    db.session.commit()
    return success_response(
        "Codex Student ID status updated",
        {"codex_id": student_id.to_dict(include_user=True)},
    )


# Attendance Session Management (Admin has full access)


@admin_bp.get("/attendance/sessions")
@admin_required
def list_all_attendance_sessions():
    """List all attendance sessions (admin only)."""
    query = AttendanceSession.query

    status = request.args.get("status", "").strip()
    if status:
        query = query.filter(AttendanceSession.status == status)

    page, per_page = pagination_args()
    pagination = query.order_by(AttendanceSession.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return success_response(
        "Attendance sessions retrieved",
        {
            "sessions": [session.to_dict(include_creator=True, include_records_count=True) for session in pagination.items],
            "pagination": pagination_payload(pagination),
        },
    )


@admin_bp.get("/attendance/sessions/<int:session_id>")
@admin_required
def get_any_attendance_session(session_id: int):
    """Get any attendance session details (admin only)."""
    session = db.session.get(AttendanceSession, session_id)
    if not session:
        return error_response("Attendance session not found", "SESSION_NOT_FOUND", 404)

    return success_response(
        "Attendance session retrieved",
        {"session": session.to_dict(include_creator=True, include_records_count=True)},
    )


@admin_bp.patch("/attendance/sessions/<int:session_id>")
@admin_required
def update_any_attendance_session(session_id: int):
    """Update any attendance session (admin only)."""
    session = db.session.get(AttendanceSession, session_id)
    if not session:
        return error_response("Attendance session not found", "SESSION_NOT_FOUND", 404)

    payload = json_body()
    status = payload.get("status")
    if status not in ("draft", "active", "closed"):
        return error_response("Invalid status value", "VALIDATION_ERROR", 422, {"status": "Status must be draft, active, or closed"})

    session.status = status
    db.session.commit()
    return success_response(
        "Attendance session updated",
        {"session": session.to_dict(include_creator=True)},
    )


@admin_bp.post("/attendance/sessions/<int:session_id>/scan")
@admin_required
def admin_scan_qr_for_attendance(session_id: int):
    """Admin scan QR code to record attendance."""
    session = db.session.get(AttendanceSession, session_id)
    if not session:
        return error_response("Attendance session not found", "SESSION_NOT_FOUND", 404)

    if session.status != "active":
        return error_response("Session is not active", "SESSION_NOT_ACTIVE", 403)

    payload = json_body()
    qr_token = payload.get("qr_token")
    if not qr_token:
        return error_response("QR token is required", "VALIDATION_ERROR", 422, {"qr_token": "QR token is required"})

    # Validate QR token
    is_valid, error_code, student_id = validate_qr_token(qr_token)
    if not is_valid:
        if error_code == "INVALID_TOKEN_FORMAT":
            return error_response("Invalid QR token format", "INVALID_TOKEN_FORMAT", 400)
        if error_code == "INVALID_QR_CODE":
            return error_response("Invalid QR code", "INVALID_QR_CODE", 404)
        if error_code == "USER_NOT_FOUND":
            return error_response("User not found", "USER_NOT_FOUND", 404)
        if error_code == "ACCOUNT_INACTIVE":
            return error_response("Account is inactive", "ACCOUNT_INACTIVE", 403)
        if error_code == "ID_REVOKED":
            return error_response("ID has been revoked", "ID_REVOKED", 403)
        if error_code == "ID_SUSPENDED":
            return error_response("ID is suspended", "ID_SUSPENDED", 403)

    # Check for duplicate attendance
    existing = AttendanceRecord.query.filter_by(
        session_id=session_id, student_identity_id=student_id.id
    ).first()
    if existing:
        return error_response(
            f"Already recorded at {existing.scanned_at.isoformat()}",
            "ALREADY_RECORDED",
            409,
            {"first_recorded_at": existing.scanned_at.isoformat()},
        )

    # Create attendance record
    from app.security import current_user
    record = AttendanceRecord(
        session_id=session_id,
        student_identity_id=student_id.id,
        scanned_by=current_user().id,
        verification_method="qr",
        status="present",
    )
    db.session.add(record)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return error_response("Already recorded", "ALREADY_RECORDED", 409)

    return success_response(
        "Attendance recorded successfully",
        {"record": record.to_dict(include_student=True)},
        201,
    )


@admin_bp.get("/attendance/sessions/<int:session_id>/records")
@admin_required
def get_any_attendance_records(session_id: int):
    """Get attendance records for any session (admin only)."""
    session = db.session.get(AttendanceSession, session_id)
    if not session:
        return error_response("Attendance session not found", "SESSION_NOT_FOUND", 404)

    from sqlalchemy.orm import joinedload
    records = (
        AttendanceRecord.query.options(
            joinedload(AttendanceRecord.student_identity).joinedload(CodexStudentID.user),
            joinedload(AttendanceRecord.scanner),
        )
        .filter_by(session_id=session_id)
        .order_by(AttendanceRecord.scanned_at.desc())
        .all()
    )
    return success_response(
        "Attendance records retrieved",
        {"records": [record.to_dict(include_student=True, include_scanner=True) for record in records]},
    )


@admin_bp.get("/codex-id/verify/<token>")
@admin_required
def admin_verify_student_qr(token: str):
    """Admin verify student QR code (no attendance recording)."""
    # Validate QR token
    is_valid, error_code, student_id = validate_qr_token(token)
    if not is_valid:
        if error_code == "INVALID_TOKEN_FORMAT":
            return error_response("Invalid QR token format", "INVALID_TOKEN_FORMAT", 400)
        if error_code == "INVALID_QR_CODE":
            return error_response("Invalid QR code", "INVALID_QR_CODE", 404)
        if error_code == "USER_NOT_FOUND":
            return error_response("User not found", "USER_NOT_FOUND", 404)
        if error_code == "ACCOUNT_INACTIVE":
            return error_response("Account is inactive", "ACCOUNT_INACTIVE", 403)
        if error_code == "ID_REVOKED":
            return error_response("ID has been revoked", "ID_REVOKED", 403)
        if error_code == "ID_SUSPENDED":
            return error_response("ID is suspended", "ID_SUSPENDED", 403)

    return success_response(
        "Valid Codex Student ID",
        {
            "student": student_id.user.to_public_dict(),
            "codex_id": student_id.to_verification_dict(),
        },
    )
