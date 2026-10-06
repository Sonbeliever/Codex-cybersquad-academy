from __future__ import annotations

from flask import Blueprint, request
from sqlalchemy import func, or_

from app.extensions import db
from app.models import Category, Course, Enrollment
from app.responses import error_response, success_response
from app.routes.helpers import pagination_args, pagination_payload

courses_bp = Blueprint("courses", __name__, url_prefix="/api")


@courses_bp.get("/categories")
def categories_index():
    categories = Category.query.order_by(Category.name.asc()).all()
    return success_response(
        "Categories retrieved",
        {"categories": [category.to_dict() for category in categories]},
    )


@courses_bp.get("/categories/<int:category_id>/courses")
def category_courses(category_id: int):
    category = db.session.get(Category, category_id)
    if not category:
        return error_response("Category was not found", "CATEGORY_NOT_FOUND", 404)

    page, per_page = pagination_args()
    pagination = (
        Course.query.filter_by(category_id=category_id, status="published")
        .order_by(Course.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )
    counts = _enrolled_counts(list(pagination.items))
    return success_response(
        "Category courses retrieved",
        {
            "category": category.to_dict(),
            "courses": [
                course.to_public_dict(enrolled_count=counts.get(course.id, 0))
                for course in pagination.items
            ],
            "pagination": pagination_payload(pagination),
        },
    )


def _enrolled_counts(courses: list[Course]) -> dict[int, int]:
    """Batch aggregate enrollment counts to avoid N+1 queries in listings."""
    ids = [course.id for course in courses]
    if not ids:
        return {}
    rows = (
        db.session.query(Enrollment.course_id, func.count(Enrollment.id))
        .filter(
            Enrollment.course_id.in_(ids),
            Enrollment.status.in_(("active", "completed")),
        )
        .group_by(Enrollment.course_id)
        .all()
    )
    return {course_id: count for course_id, count in rows}


@courses_bp.get("/courses")
def courses_index():
    query = Course.query.filter_by(status="published")

    search = request.args.get("search", "").strip()
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Course.title.ilike(like),
                Course.subtitle.ilike(like),
                Course.description.ilike(like),
            )
        )

    category = request.args.get("category", type=int)
    if category:
        query = query.filter(Course.category_id == category)

    language = request.args.get("language", "").strip().lower()
    if language:
        query = query.filter(Course.language == language)

    level = request.args.get("level", "").strip().lower()
    if level:
        query = query.filter(Course.level == level)

    min_price = request.args.get("min_price", type=float)
    if min_price is not None:
        query = query.filter(Course.price >= min_price)

    max_price = request.args.get("max_price", type=float)
    if max_price is not None:
        query = query.filter(Course.price <= max_price)

    page, per_page = pagination_args()
    pagination = query.order_by(Course.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    counts = _enrolled_counts(list(pagination.items))
    return success_response(
        "Courses retrieved",
        {
            "courses": [
                course.to_public_dict(enrolled_count=counts.get(course.id, 0))
                for course in pagination.items
            ],
            "pagination": pagination_payload(pagination),
        },
    )


@courses_bp.get("/courses/<int:course_id>")
def course_details(course_id: int):
    course = db.session.get(Course, course_id)
    if not course or course.status != "published":
        return error_response("Course was not found", "COURSE_NOT_FOUND", 404)
    return success_response(
        "Course retrieved", {"course": course.to_public_dict(include_curriculum=True)}
    )


@courses_bp.get("/courses/<int:course_id>/lessons")
def course_lessons(course_id: int):
    course = db.session.get(Course, course_id)
    if not course or course.status != "published":
        return error_response("Course was not found", "COURSE_NOT_FOUND", 404)
    return success_response(
        "Course lessons retrieved",
        {"course_id": course.id, "modules": [module.to_public_dict() for module in course.modules]},
    )
