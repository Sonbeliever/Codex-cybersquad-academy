from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import AttendanceRecord, AttendanceSession, CodexStudentID, Course, InstructorApplication, Lesson, LessonResource, Module
from app.models.user import utc_now
from app.responses import error_response, success_response
from app.routes.helpers import (
    json_body,
    normalize_lesson_video_url,
    owned_course_or_404,
    owned_lesson_or_404,
    owned_module_or_404,
    parse_non_negative_int,
    queue_published_course_for_review,
    require_approved_instructor,
    unique_slug,
    validate_course_payload,
)
from app.security import current_user, login_required
from app.services import storage_service
from app.services.codex_service import validate_qr_token

instructors_bp = Blueprint("instructors", __name__, url_prefix="/api/instructor")


@instructors_bp.post("/apply")
@login_required
def apply():
    user = current_user()
    if user.role == "instructor":
        return error_response("You are already an instructor", "ALREADY_INSTRUCTOR", 409)

    existing = (
        InstructorApplication.query.filter_by(user_id=user.id)
        .order_by(InstructorApplication.created_at.desc())
        .first()
    )
    if existing and existing.status == "pending":
        return error_response(
            "You already have a pending instructor application",
            "APPLICATION_ALREADY_PENDING",
            409,
        )

    payload = json_body()
    errors: dict[str, str] = {}
    expertise = str(payload.get("expertise", "")).strip()
    experience = str(payload.get("experience", "")).strip()
    bio = str(payload.get("bio", "")).strip()
    phone = str(payload.get("phone", user.phone or "")).strip() or None

    if not expertise:
        errors["expertise"] = "Expertise is required."
    if not experience:
        errors["experience"] = "Experience is required."
    if not bio:
        errors["bio"] = "Bio is required."
    if phone and len(phone) > 32:
        errors["phone"] = "Phone number must be 32 characters or fewer."
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    application = InstructorApplication(
        user_id=user.id,
        expertise=expertise,
        experience=experience,
        bio=bio,
        phone=phone,
        status="pending",
    )
    db.session.add(application)
    db.session.commit()
    return success_response(
        "Instructor application submitted",
        {"application": application.to_dict()},
        201,
    )


@instructors_bp.get("/application")
@login_required
def application_status():
    application = (
        InstructorApplication.query.filter_by(user_id=current_user().id)
        .order_by(InstructorApplication.created_at.desc())
        .first()
    )
    if not application:
        return success_response(
            "No instructor application found",
            {"application": None},
        )
    return success_response(
        "Instructor application retrieved", {"application": application.to_dict()}
    )


@instructors_bp.post("/courses")
@login_required
def create_course():
    guard = require_approved_instructor()
    if guard:
        return guard

    payload = json_body()
    data, errors = validate_course_payload(payload)
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    course = Course(
        instructor_id=current_user().id,
        category_id=data["category_id"],
        title=data["title"],
        slug=unique_slug(Course, data["title"]),
        subtitle=data.get("subtitle"),
        description=data["description"],
        price=data["price"],
        language=data["language"],
        level=data["level"],
        thumbnail=data.get("thumbnail"),
        duration=data["duration"],
        status="draft",
    )
    db.session.add(course)
    db.session.commit()
    return success_response("Course created successfully", {"course": course.to_owner_dict()}, 201)


@instructors_bp.get("/courses")
@login_required
def instructor_courses():
    guard = require_approved_instructor()
    if guard:
        return guard

    courses = (
        Course.query.filter_by(instructor_id=current_user().id)
        .order_by(Course.created_at.desc())
        .all()
    )
    return success_response(
        "Instructor courses retrieved",
        {"courses": [course.to_owner_dict() for course in courses]},
    )


@instructors_bp.get("/courses/<int:course_id>")
@login_required
def instructor_course_details(course_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    course, response = owned_course_or_404(course_id)
    if response:
        return response
    return success_response(
        "Instructor course retrieved", {"course": course.to_owner_dict(include_curriculum=True)}
    )


@instructors_bp.put("/courses/<int:course_id>")
@login_required
def update_course(course_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    course, response = owned_course_or_404(course_id)
    if response:
        return response

    payload = json_body()
    data, errors = validate_course_payload(payload, partial=True)
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    title_changed = "title" in data and data["title"] != course.title
    for field, value in data.items():
        setattr(course, field, value)
    if title_changed:
        course.slug = unique_slug(Course, course.title, existing_id=course.id)
    if course.status == "rejected":
        course.status = "draft"
        course.admin_note = None

    queued = queue_published_course_for_review(course)
    db.session.commit()
    message = (
        "Course updated and submitted for admin re-review"
        if queued
        else "Course updated successfully"
    )
    return success_response(message, {"course": course.to_owner_dict()})


@instructors_bp.delete("/courses/<int:course_id>")
@login_required
def delete_course(course_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    course, response = owned_course_or_404(course_id)
    if response:
        return response
    if course.status not in {"draft", "rejected"}:
        return error_response("Only draft or rejected courses can be deleted", "COURSE_DELETE_DENIED", 409)

    db.session.delete(course)
    db.session.commit()
    return success_response("Course deleted successfully")


@instructors_bp.post("/courses/<int:course_id>/submit")
@login_required
def submit_course(course_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    course, response = owned_course_or_404(course_id)
    if response:
        return response
    if course.status not in {"draft", "rejected"}:
        return error_response("Only draft or rejected courses can be submitted", "COURSE_SUBMIT_DENIED", 409)
    if not course.modules:
        return error_response("Add at least one module before submitting", "COURSE_EMPTY", 422)

    course.status = "pending"
    course.admin_note = None
    db.session.commit()
    return success_response("Course submitted for admin review", {"course": course.to_owner_dict()})


@instructors_bp.post("/courses/<int:course_id>/modules")
@login_required
def create_module(course_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    course, response = owned_course_or_404(course_id)
    if response:
        return response

    payload = json_body()
    errors: dict[str, str] = {}
    title = str(payload.get("title", "")).strip()
    order = parse_non_negative_int(payload.get("order", 1), "order", errors, default=1)
    if not title:
        errors["title"] = "Module title is required."
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    module = Module(
        course_id=course.id,
        title=title,
        description=str(payload.get("description", "")).strip() or None,
        order=order,
    )
    db.session.add(module)
    queued = queue_published_course_for_review(course)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response(
            "Module order already exists for this course. Choose a different order number.",
            "MODULE_ORDER_EXISTS",
            409,
        )
    message = (
        "Module created successfully. Published course moved to pending review."
        if queued
        else "Module created successfully"
    )
    return success_response(message, {"module": module.to_owner_dict(), "course_status": course.status}, 201)


@instructors_bp.put("/modules/<int:module_id>")
@login_required
def update_module(module_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    module, response = owned_module_or_404(module_id)
    if response:
        return response

    payload = json_body()
    errors: dict[str, str] = {}
    if "title" in payload:
        title = str(payload.get("title", "")).strip()
        if not title:
            errors["title"] = "Module title is required."
        module.title = title
    if "description" in payload:
        module.description = str(payload.get("description", "")).strip() or None
    if "order" in payload:
        module.order = parse_non_negative_int(payload.get("order"), "order", errors)
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    queued = queue_published_course_for_review(module.course)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response(
            "Module order already exists for this course. Choose a different order number.",
            "MODULE_ORDER_EXISTS",
            409,
        )
    message = (
        "Module updated successfully. Published course moved to pending review."
        if queued
        else "Module updated successfully"
    )
    return success_response(message, {"module": module.to_owner_dict(), "course_status": module.course.status})


@instructors_bp.delete("/modules/<int:module_id>")
@login_required
def delete_module(module_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    module, response = owned_module_or_404(module_id)
    if response:
        return response
    course = module.course
    db.session.delete(module)
    queued = queue_published_course_for_review(course)
    db.session.commit()
    message = (
        "Module deleted successfully. Published course moved to pending review."
        if queued
        else "Module deleted successfully"
    )
    return success_response(message, {"course_status": course.status})


@instructors_bp.post("/modules/<int:module_id>/lessons")
@login_required
def create_lesson(module_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    module, response = owned_module_or_404(module_id)
    if response:
        return response

    payload = json_body()
    errors: dict[str, str] = {}
    title = str(payload.get("title", "")).strip()
    duration = parse_non_negative_int(payload.get("duration", 0), "duration", errors)
    order = parse_non_negative_int(payload.get("order", 1), "order", errors, default=1)
    video_url, video_error = normalize_lesson_video_url(payload.get("video_url"))
    if video_error:
        errors["video_url"] = video_error
    if not title:
        errors["title"] = "Lesson title is required."
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    lesson = Lesson(
        module_id=module.id,
        title=title,
        description=str(payload.get("description", "")).strip() or None,
        video_url=video_url,
        duration=duration,
        order=order,
        is_preview=bool(payload.get("is_preview", False)),
    )
    db.session.add(lesson)
    queued = queue_published_course_for_review(module.course)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response(
            "Lesson order already exists for this module. Choose a different order number.",
            "LESSON_ORDER_EXISTS",
            409,
        )
    message = (
        "Lesson created successfully. Published course moved to pending review."
        if queued
        else "Lesson created successfully"
    )
    return success_response(message, {"lesson": lesson.to_owner_dict(), "course_status": module.course.status}, 201)


@instructors_bp.put("/lessons/<int:lesson_id>")
@login_required
def update_lesson(lesson_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    lesson, response = owned_lesson_or_404(lesson_id)
    if response:
        return response

    payload = json_body()
    errors: dict[str, str] = {}
    for field in ("title", "description"):
        if field in payload:
            value = str(payload.get(field, "")).strip()
            if field == "title" and not value:
                errors["title"] = "Lesson title is required."
            setattr(lesson, field, value or None)
    if "video_url" in payload:
        video_url, video_error = normalize_lesson_video_url(payload.get("video_url"))
        if video_error:
            errors["video_url"] = video_error
        else:
            lesson.video_url = video_url
    if "duration" in payload:
        lesson.duration = parse_non_negative_int(payload.get("duration"), "duration", errors)
    if "order" in payload:
        lesson.order = parse_non_negative_int(payload.get("order"), "order", errors)
    if "is_preview" in payload:
        lesson.is_preview = bool(payload.get("is_preview"))
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    queued = queue_published_course_for_review(lesson.module.course)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response(
            "Lesson order already exists for this module. Choose a different order number.",
            "LESSON_ORDER_EXISTS",
            409,
        )
    message = (
        "Lesson updated successfully. Published course moved to pending review."
        if queued
        else "Lesson updated successfully"
    )
    return success_response(
        message, {"lesson": lesson.to_owner_dict(), "course_status": lesson.module.course.status}
    )


@instructors_bp.delete("/lessons/<int:lesson_id>")
@login_required
def delete_lesson(lesson_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    lesson, response = owned_lesson_or_404(lesson_id)
    if response:
        return response
    course = lesson.module.course
    db.session.delete(lesson)
    queued = queue_published_course_for_review(course)
    db.session.commit()
    message = (
        "Lesson deleted successfully. Published course moved to pending review."
        if queued
        else "Lesson deleted successfully"
    )
    return success_response(message, {"course_status": course.status})


@instructors_bp.post("/lessons/<int:lesson_id>/resources")
@login_required
def create_lesson_resource(lesson_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    lesson, response = owned_lesson_or_404(lesson_id)
    if response:
        return response

    payload = json_body()
    name = str(payload.get("name", "")).strip()
    file_url = str(payload.get("file_url", "")).strip()
    file_type = str(payload.get("file_type", "")).strip().lower()
    errors = storage_service.validate_resource_reference(name, file_url, file_type)
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    resource = LessonResource(
        lesson_id=lesson.id,
        name=name,
        file_url=file_url,
        file_type=file_type,
    )
    db.session.add(resource)
    queued = queue_published_course_for_review(lesson.module.course)
    db.session.commit()
    message = (
        "Lesson resource created successfully. Published course moved to pending review."
        if queued
        else "Lesson resource created successfully"
    )
    return success_response(
        message,
        {"resource": resource.to_dict(), "course_status": lesson.module.course.status},
        201,
    )


# Attendance Session Management


@instructors_bp.post("/attendance/sessions")
@login_required
def create_attendance_session():
    """Create a new attendance session."""
    user = current_user()
    if user.role not in ("instructor", "admin"):
        return error_response("Only instructors and admins can create attendance sessions", "FORBIDDEN", 403)

    payload = json_body()
    errors: dict[str, str] = {}
    title = str(payload.get("title", "")).strip()
    session_type = str(payload.get("session_type", "")).strip()
    description = str(payload.get("description", "")).strip() or None
    location = str(payload.get("location", "")).strip() or None
    starts_at = payload.get("starts_at")
    ends_at = payload.get("ends_at")

    # Parse datetime strings
    if starts_at and isinstance(starts_at, str):
        try:
            starts_at = datetime.fromisoformat(starts_at.replace('Z', '+00:00'))
        except ValueError:
            errors["starts_at"] = "Invalid datetime format."
    if ends_at and isinstance(ends_at, str):
        try:
            ends_at = datetime.fromisoformat(ends_at.replace('Z', '+00:00'))
        except ValueError:
            errors["ends_at"] = "Invalid datetime format."

    if not title:
        errors["title"] = "Session title is required."
    if not session_type:
        errors["session_type"] = "Session type is required."
    if not starts_at:
        errors["starts_at"] = "Start time is required."
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    session = AttendanceSession(
        created_by=user.id,
        title=title,
        session_type=session_type,
        description=description,
        location=location,
        starts_at=starts_at,
        ends_at=ends_at,
        status="draft",
    )
    db.session.add(session)
    db.session.commit()
    return success_response(
        "Attendance session created",
        {"session": session.to_dict(include_creator=True)},
        201,
    )


@instructors_bp.get("/attendance/sessions")
@login_required
def list_attendance_sessions():
    """List own attendance sessions (instructors) or all sessions (admin)."""
    user = current_user()
    if user.role not in ("instructor", "admin"):
        return error_response("Only instructors and admins can view attendance sessions", "FORBIDDEN", 403)

    if user.role == "instructor":
        sessions = (
            AttendanceSession.query.filter_by(created_by=user.id)
            .order_by(AttendanceSession.created_at.desc())
            .all()
        )
    else:  # admin
        sessions = AttendanceSession.query.order_by(AttendanceSession.created_at.desc()).all()

    return success_response(
        "Attendance sessions retrieved",
        {"sessions": [session.to_dict(include_creator=True, include_records_count=True) for session in sessions]},
    )


@instructors_bp.get("/attendance/sessions/<int:session_id>")
@login_required
def get_attendance_session(session_id: int):
    """Get attendance session details."""
    user = current_user()
    if user.role not in ("instructor", "admin"):
        return error_response("Only instructors and admins can view attendance sessions", "FORBIDDEN", 403)

    session = db.session.get(AttendanceSession, session_id)
    if not session:
        return error_response("Attendance session not found", "SESSION_NOT_FOUND", 404)

    if user.role == "instructor" and session.created_by != user.id:
        return error_response("You can only view your own sessions", "SESSION_FORBIDDEN", 403)

    return success_response(
        "Attendance session retrieved",
        {"session": session.to_dict(include_creator=True, include_records_count=True)},
    )


@instructors_bp.patch("/attendance/sessions/<int:session_id>")
@login_required
def update_attendance_session(session_id: int):
    """Update attendance session (activate/close)."""
    user = current_user()
    if user.role not in ("instructor", "admin"):
        return error_response("Only instructors and admins can update attendance sessions", "FORBIDDEN", 403)

    session = db.session.get(AttendanceSession, session_id)
    if not session:
        return error_response("Attendance session not found", "SESSION_NOT_FOUND", 404)

    if user.role == "instructor" and session.created_by != user.id:
        return error_response("You can only update your own sessions", "SESSION_FORBIDDEN", 403)

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


@instructors_bp.get("/attendance/sessions/<int:session_id>/records")
@login_required
def get_attendance_records(session_id: int):
    """Get attendance records for a session."""
    user = current_user()
    if user.role not in ("instructor", "admin"):
        return error_response("Only instructors and admins can view attendance records", "FORBIDDEN", 403)

    session = db.session.get(AttendanceSession, session_id)
    if not session:
        return error_response("Attendance session not found", "SESSION_NOT_FOUND", 404)

    if user.role == "instructor" and session.created_by != user.id:
        return error_response("You can only view records for your own sessions", "SESSION_FORBIDDEN", 403)

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


@instructors_bp.post("/attendance/sessions/<int:session_id>/scan")
@login_required
def scan_qr_for_attendance(session_id: int):
    """Scan QR code to record attendance (requires active session)."""
    user = current_user()
    if user.role not in ("instructor", "admin"):
        return error_response("Only instructors and admins can scan for attendance", "FORBIDDEN", 403)

    session = db.session.get(AttendanceSession, session_id)
    if not session:
        return error_response("Attendance session not found", "SESSION_NOT_FOUND", 404)

    if user.role == "instructor" and session.created_by != user.id:
        return error_response("You can only scan for your own sessions", "SESSION_FORBIDDEN", 403)

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
    record = AttendanceRecord(
        session_id=session_id,
        student_identity_id=student_id.id,
        scanned_by=user.id,
        verification_method="qr",
        status="present",
    )
    db.session.add(record)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("Already recorded", "ALREADY_RECORDED", 409)

    return success_response(
        "Attendance recorded successfully",
        {"record": record.to_dict(include_student=True)},
        201,
    )


@instructors_bp.get("/codex-id/verify/<token>")
@login_required
def verify_student_qr(token: str):
    """Verify student QR code (no attendance recording)."""
    user = current_user()
    if user.role not in ("instructor", "admin"):
        return error_response("Only instructors and admins can verify QR codes", "FORBIDDEN", 403)

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
