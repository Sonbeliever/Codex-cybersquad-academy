from __future__ import annotations

from flask import Blueprint
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Course, InstructorApplication, Lesson, LessonResource, Module
from app.models.user import utc_now
from app.responses import error_response, success_response
from app.routes.helpers import (
    json_body,
    owned_course_or_404,
    owned_lesson_or_404,
    owned_module_or_404,
    parse_non_negative_int,
    require_approved_instructor,
    unique_slug,
    validate_course_payload,
)
from app.security import current_user, login_required
from app.services import storage_service

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
        return error_response("Instructor application was not found", "APPLICATION_NOT_FOUND", 404)
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
    if course.status == "published":
        return error_response("Published courses cannot be edited", "COURSE_ALREADY_PUBLISHED", 409)

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

    db.session.commit()
    return success_response("Course updated successfully", {"course": course.to_owner_dict()})


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
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("Module order already exists for this course", "MODULE_ORDER_EXISTS", 409)
    return success_response("Module created successfully", {"module": module.to_owner_dict()}, 201)


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

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("Module order already exists for this course", "MODULE_ORDER_EXISTS", 409)
    return success_response("Module updated successfully", {"module": module.to_owner_dict()})


@instructors_bp.delete("/modules/<int:module_id>")
@login_required
def delete_module(module_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    module, response = owned_module_or_404(module_id)
    if response:
        return response
    db.session.delete(module)
    db.session.commit()
    return success_response("Module deleted successfully")


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
    if not title:
        errors["title"] = "Lesson title is required."
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    lesson = Lesson(
        module_id=module.id,
        title=title,
        description=str(payload.get("description", "")).strip() or None,
        video_url=str(payload.get("video_url", "")).strip() or None,
        duration=duration,
        order=order,
        is_preview=bool(payload.get("is_preview", False)),
    )
    db.session.add(lesson)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("Lesson order already exists for this module", "LESSON_ORDER_EXISTS", 409)
    return success_response("Lesson created successfully", {"lesson": lesson.to_owner_dict()}, 201)


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
    for field in ("title", "description", "video_url"):
        if field in payload:
            value = str(payload.get(field, "")).strip()
            if field == "title" and not value:
                errors["title"] = "Lesson title is required."
            setattr(lesson, field, value or None)
    if "duration" in payload:
        lesson.duration = parse_non_negative_int(payload.get("duration"), "duration", errors)
    if "order" in payload:
        lesson.order = parse_non_negative_int(payload.get("order"), "order", errors)
    if "is_preview" in payload:
        lesson.is_preview = bool(payload.get("is_preview"))
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("Lesson order already exists for this module", "LESSON_ORDER_EXISTS", 409)
    return success_response("Lesson updated successfully", {"lesson": lesson.to_owner_dict()})


@instructors_bp.delete("/lessons/<int:lesson_id>")
@login_required
def delete_lesson(lesson_id: int):
    guard = require_approved_instructor()
    if guard:
        return guard
    lesson, response = owned_lesson_or_404(lesson_id)
    if response:
        return response
    db.session.delete(lesson)
    db.session.commit()
    return success_response("Lesson deleted successfully")


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
    db.session.commit()
    return success_response(
        "Lesson resource created successfully", {"resource": resource.to_dict()}, 201
    )
