from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from flask import request

from app.extensions import db
from app.models import Category, Course, Lesson, Module
from app.responses import error_response
from app.security import current_user


SLUG_RE = re.compile(r"[^a-z0-9]+")


def json_body() -> dict:
    if not request.is_json:
        return {}
    return request.get_json(silent=True) or {}


def slugify(value: str) -> str:
    slug = SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return slug or "course"


def unique_slug(model, value: str, existing_id: int | None = None) -> str:
    base = slugify(value)
    slug = base
    counter = 2
    while True:
        query = model.query.filter_by(slug=slug)
        if existing_id is not None:
            query = query.filter(model.id != existing_id)
        if not query.first():
            return slug
        slug = f"{base}-{counter}"
        counter += 1


def parse_non_negative_decimal(value, field: str, errors: dict) -> Decimal:
    try:
        amount = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError):
        errors[field] = f"{field} must be a valid number."
        return Decimal("0")
    if amount < 0:
        errors[field] = f"{field} must be greater than or equal to 0."
    return amount.quantize(Decimal("0.01"))


def parse_non_negative_int(value, field: str, errors: dict, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors[field] = f"{field} must be a whole number."
        return default
    if parsed < 0:
        errors[field] = f"{field} must be greater than or equal to 0."
    return parsed


def pagination_args() -> tuple[int, int]:
    page = max(request.args.get("page", default=1, type=int), 1)
    per_page = request.args.get("per_page", default=12, type=int)
    per_page = min(max(per_page, 1), 50)
    return page, per_page


def pagination_payload(pagination) -> dict:
    return {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }


def validate_course_payload(payload: dict, partial: bool = False) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    required = ("title", "description", "category_id", "language", "level")
    data: dict = {}

    for field in required:
        value = payload.get(field)
        if value is None:
            if not partial:
                errors[field] = f"{field} is required."
            continue
        if field in {"title", "description", "language", "level"}:
            cleaned = str(value).strip()
            if not cleaned:
                errors[field] = f"{field} is required."
            data[field] = cleaned
        else:
            data[field] = value

    if "title" in data and len(data["title"]) > 180:
        errors["title"] = "title must be 180 characters or fewer."

    if "category_id" in data:
        category = db.session.get(Category, data["category_id"])
        if not category:
            errors["category_id"] = "Category was not found."

    if "language" in data:
        data["language"] = data["language"].lower()
        if data["language"] not in {"english", "hausa"}:
            errors["language"] = "language must be english or hausa."

    if "level" in data:
        data["level"] = data["level"].lower()
        if data["level"] not in {"beginner", "intermediate", "advanced"}:
            errors["level"] = "level must be beginner, intermediate, or advanced."

    for optional in ("subtitle", "thumbnail"):
        if optional in payload:
            data[optional] = str(payload.get(optional) or "").strip() or None

    if "price" in payload or not partial:
        data["price"] = parse_non_negative_decimal(payload.get("price", 0), "price", errors)
    if "duration" in payload or not partial:
        data["duration"] = parse_non_negative_int(
            payload.get("duration", 0), "duration", errors
        )

    return data, errors


def instructor_is_approved() -> bool:
    return current_user().role == "instructor"


def require_approved_instructor():
    if not instructor_is_approved():
        return error_response(
            "Only approved instructors can perform this action",
            "APPROVED_INSTRUCTOR_REQUIRED",
            403,
        )
    return None


def owned_course_or_404(course_id: int):
    course = db.session.get(Course, course_id)
    if not course:
        return None, error_response("Course was not found", "COURSE_NOT_FOUND", 404)
    if course.instructor_id != current_user().id:
        return None, error_response("You cannot access this course", "COURSE_FORBIDDEN", 403)
    return course, None


def owned_module_or_404(module_id: int):
    module = db.session.get(Module, module_id)
    if not module:
        return None, error_response("Module was not found", "MODULE_NOT_FOUND", 404)
    if module.course.instructor_id != current_user().id:
        return None, error_response("You cannot access this module", "MODULE_FORBIDDEN", 403)
    return module, None


def owned_lesson_or_404(lesson_id: int):
    lesson = db.session.get(Lesson, lesson_id)
    if not lesson:
        return None, error_response("Lesson was not found", "LESSON_NOT_FOUND", 404)
    if lesson.module.course.instructor_id != current_user().id:
        return None, error_response("You cannot access this lesson", "LESSON_FORBIDDEN", 403)
    return lesson, None
