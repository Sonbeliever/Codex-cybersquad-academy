from __future__ import annotations

from flask import Blueprint, request

from app.extensions import db
from app.models import Category, Course, Enrollment, InstructorApplication
from app.models.user import utc_now
from app.responses import error_response, success_response
from app.routes.helpers import json_body, pagination_args, pagination_payload, unique_slug
from app.security import admin_required

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
