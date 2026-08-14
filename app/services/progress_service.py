from __future__ import annotations

from sqlalchemy import func

from app.extensions import db
from app.models import Course, Enrollment, Lesson, LessonProgress, Module
from app.models.user import utc_now


def course_lesson_ids(course_id: int) -> list[int]:
    rows = (
        db.session.query(Lesson.id)
        .join(Module, Lesson.module_id == Module.id)
        .filter(Module.course_id == course_id)
        .all()
    )
    return [row[0] for row in rows]


def calculate_course_progress(student_id: int, course_id: int) -> dict:
    lesson_ids = course_lesson_ids(course_id)
    total_lessons = len(lesson_ids)
    if total_lessons == 0:
        completed_lessons = 0
    else:
        completed_lessons = (
            db.session.query(func.count(LessonProgress.id))
            .filter(
                LessonProgress.student_id == student_id,
                LessonProgress.lesson_id.in_(lesson_ids),
                LessonProgress.completed.is_(True),
            )
            .scalar()
            or 0
        )

    remaining_lessons = max(total_lessons - completed_lessons, 0)
    percentage = int(round((completed_lessons / total_lessons) * 100)) if total_lessons else 0
    return {
        "course_id": course_id,
        "total_lessons": total_lessons,
        "completed_lessons": completed_lessons,
        "remaining_lessons": remaining_lessons,
        "progress_percentage": percentage,
    }


def sync_enrollment_completion(enrollment: Enrollment) -> dict:
    progress = calculate_course_progress(enrollment.student_id, enrollment.course_id)
    if progress["total_lessons"] > 0 and progress["remaining_lessons"] == 0:
        if enrollment.status != "completed":
            enrollment.status = "completed"
            enrollment.completed_at = utc_now()
    elif enrollment.status == "completed":
        enrollment.status = "active"
        enrollment.completed_at = None
    return progress


def student_has_course_access(student_id: int, course_id: int) -> Enrollment | None:
    return Enrollment.query.filter(
        Enrollment.student_id == student_id,
        Enrollment.course_id == course_id,
        Enrollment.status.in_(("active", "completed")),
    ).first()


def course_total_lessons(course: Course) -> int:
    return sum(len(module.lessons) for module in course.modules)
