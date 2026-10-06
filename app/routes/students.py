from __future__ import annotations

from flask import Blueprint
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models import AttendanceRecord, AttendanceSession, CodexStudentID, Course, Enrollment, Lesson, LessonProgress, Module
from app.models.user import utc_now
from app.responses import error_response, success_response
from app.routes.helpers import json_body, parse_non_negative_int
from app.security import current_user, login_required, student_required
from app.services.progress_service import (
    calculate_course_progress,
    student_has_course_access,
    sync_enrollment_completion,
)

students_bp = Blueprint("students", __name__, url_prefix="/api")


def _lesson_course(lesson: Lesson) -> Course:
    return lesson.module.course


def _enrollment_or_denied(student_id: int, course_id: int):
    enrollment = student_has_course_access(student_id, course_id)
    if not enrollment:
        return None, error_response(
            "You must enroll in this course to access this lesson",
            "COURSE_ACCESS_DENIED",
            403,
        )
    return enrollment, None


def _lesson_payload_for_student(lesson: Lesson, include_video: bool) -> dict:
    data = lesson.to_owner_dict() if include_video else lesson.to_public_dict()
    progress = LessonProgress.query.filter_by(
        student_id=current_user().id, lesson_id=lesson.id
    ).first()
    data["progress"] = progress.to_dict() if progress else None
    return data


@students_bp.post("/enrollments")
@student_required
def create_enrollment():
    payload = json_body()
    course_id = payload.get("course_id")
    course = db.session.get(Course, course_id) if course_id is not None else None
    if not course:
        return error_response("Course was not found", "COURSE_NOT_FOUND", 404)
    if course.status != "published":
        return error_response("Students can only enroll in published courses", "COURSE_NOT_PUBLISHED", 403)

    existing = Enrollment.query.filter(
        Enrollment.student_id == current_user().id,
        Enrollment.course_id == course.id,
        Enrollment.status.in_(("active", "completed")),
    ).first()
    if existing:
        return error_response("You are already enrolled in this course", "ENROLLMENT_EXISTS", 409)

    if float(course.price or 0) > 0:
        return error_response(
            "Paid courses must be purchased through the payment flow",
            "PAYMENT_REQUIRED",
            402,
        )

    enrollment = Enrollment(student_id=current_user().id, course_id=course.id, status="active")
    db.session.add(enrollment)
    db.session.commit()
    progress = calculate_course_progress(current_user().id, course.id)
    return success_response(
        "Enrollment created successfully",
        {"enrollment": enrollment.to_dict(include_course=True, progress_percentage=progress["progress_percentage"])},
        201,
    )


@students_bp.get("/my-courses")
@student_required
def my_courses():
    enrollments = (
        Enrollment.query.options(
            joinedload(Enrollment.course).options(
                joinedload(Course.instructor),
                joinedload(Course.category),
                selectinload(Course.modules).selectinload(Module.lessons),
            ),
        )
        .filter_by(student_id=current_user().id)
        .order_by(Enrollment.enrolled_at.desc())
        .all()
    )
    items = []
    for enrollment in enrollments:
        progress = calculate_course_progress(current_user().id, enrollment.course_id)
        item = enrollment.to_dict(include_course=True, progress_percentage=progress["progress_percentage"])
        items.append(item)
    return success_response("My courses retrieved", {"courses": items})


@students_bp.get("/enrollments/<int:enrollment_id>")
@login_required
def enrollment_details(enrollment_id: int):
    enrollment = db.session.get(Enrollment, enrollment_id)
    if not enrollment:
        return error_response("Enrollment was not found", "ENROLLMENT_NOT_FOUND", 404)
    user = current_user()
    if user.role != "admin" and enrollment.student_id != user.id:
        return error_response("You cannot access this enrollment", "ENROLLMENT_FORBIDDEN", 403)
    progress = calculate_course_progress(enrollment.student_id, enrollment.course_id)
    payload = (
        enrollment.to_admin_dict()
        if user.role == "admin"
        else enrollment.to_dict(include_course=True)
    )
    payload["progress"] = progress
    return success_response("Enrollment retrieved", {"enrollment": payload})


@students_bp.get("/lessons/<int:lesson_id>")
@login_required
def lesson_details(lesson_id: int):
    lesson = (
        Lesson.query.options(
            joinedload(Lesson.module).joinedload(Module.course),
            selectinload(Lesson.resources),
        )
        .filter_by(id=lesson_id)
        .first()
    )
    if not lesson:
        return error_response("Lesson was not found", "LESSON_NOT_FOUND", 404)

    course = _lesson_course(lesson)
    include_video = False
    if lesson.is_preview:
        include_video = True
    else:
        enrollment, response = _enrollment_or_denied(current_user().id, course.id)
        if response:
            return response
        include_video = bool(enrollment)

    return success_response(
        "Lesson retrieved",
        {
            "lesson": _lesson_payload_for_student(lesson, include_video),
            "course": course.to_public_dict(),
        },
    )


@students_bp.post("/lessons/<int:lesson_id>/progress")
@student_required
def update_lesson_progress(lesson_id: int):
    lesson = (
        Lesson.query.options(joinedload(Lesson.module).joinedload(Module.course))
        .filter_by(id=lesson_id)
        .first()
    )
    if not lesson:
        return error_response("Lesson was not found", "LESSON_NOT_FOUND", 404)

    course = _lesson_course(lesson)
    enrollment, response = _enrollment_or_denied(current_user().id, course.id)
    if response:
        return response

    payload = json_body()
    errors: dict[str, str] = {}
    watch_time = parse_non_negative_int(payload.get("watch_time", 0), "watch_time", errors)
    completed = bool(payload.get("completed", False))
    if errors:
        return error_response("Validation failed", "VALIDATION_ERROR", 422, errors)

    progress = LessonProgress.query.filter_by(
        student_id=current_user().id, lesson_id=lesson.id
    ).first()
    if not progress:
        progress = LessonProgress(student_id=current_user().id, lesson_id=lesson.id)
        db.session.add(progress)

    progress.watch_time = watch_time
    if completed and not progress.completed:
        progress.completed_at = utc_now()
    elif not completed:
        progress.completed_at = None
    progress.completed = completed

    course_progress = sync_enrollment_completion(enrollment)
    db.session.commit()
    course_progress = calculate_course_progress(current_user().id, course.id)
    sync_enrollment_completion(enrollment)
    db.session.commit()

    return success_response(
        "Lesson progress updated",
        {
            "progress": progress.to_dict(),
            "course_progress": course_progress,
            "enrollment": enrollment.to_dict(),
        },
    )


@students_bp.get("/courses/<int:course_id>/progress")
@student_required
def course_progress(course_id: int):
    course = db.session.get(Course, course_id)
    if not course:
        return error_response("Course was not found", "COURSE_NOT_FOUND", 404)
    enrollment = student_has_course_access(current_user().id, course.id)
    if not enrollment:
        return error_response("You are not enrolled in this course", "COURSE_ACCESS_DENIED", 403)
    progress = sync_enrollment_completion(enrollment)
    db.session.commit()
    return success_response("Course progress retrieved", {"progress": progress})


@students_bp.get("/student/dashboard")
@student_required
def student_dashboard():
    student = current_user()
    enrollments = (
        Enrollment.query.options(
            joinedload(Enrollment.course).options(
                joinedload(Course.instructor),
                joinedload(Course.category),
                selectinload(Course.modules).selectinload(Module.lessons),
            ),
        )
        .filter_by(student_id=student.id)
        .order_by(Enrollment.enrolled_at.desc())
        .all()
    )

    active = [enrollment for enrollment in enrollments if enrollment.status == "active"]
    completed = [enrollment for enrollment in enrollments if enrollment.status == "completed"]
    progress_values = [
        calculate_course_progress(student.id, enrollment.course_id)["progress_percentage"]
        for enrollment in enrollments
    ]
    overall_progress = int(round(sum(progress_values) / len(progress_values))) if progress_values else 0

    return success_response(
        "Student dashboard retrieved",
        {
            "student": student.to_dict(),
            "statistics": {
                "enrolled_courses": len(enrollments),
                "active_courses": len(active),
                "completed_courses": len(completed),
                "overall_learning_progress": overall_progress,
            },
            "recent_courses": [
                enrollment.to_dict(include_course=True) for enrollment in enrollments[:5]
            ],
            "continue_learning": [
                enrollment.to_dict(
                    include_course=True,
                    progress_percentage=calculate_course_progress(student.id, enrollment.course_id)[
                        "progress_percentage"
                    ],
                )
                for enrollment in active[:5]
            ],
            "completed_courses": [
                enrollment.to_dict(include_course=True) for enrollment in completed[:5]
            ],
        },
    )


@students_bp.get("/my-courses/<int:course_id>/learning")
@student_required
def course_learning(course_id: int):
    enrollment = student_has_course_access(current_user().id, course_id)
    if not enrollment:
        return error_response("You are not enrolled in this course", "COURSE_ACCESS_DENIED", 403)

    course = (
        Course.query.options(
            joinedload(Course.instructor),
            joinedload(Course.category),
            selectinload(Course.modules).selectinload(Module.lessons),
        )
        .filter_by(id=course_id)
        .first()
    )
    progress_records = {
        progress.lesson_id: progress
        for progress in LessonProgress.query.join(Lesson)
        .join(Module)
        .filter(
            LessonProgress.student_id == current_user().id,
            Module.course_id == course_id,
        )
        .all()
    }

    modules = []
    for module in course.modules:
        lessons = []
        for lesson in module.lessons:
            progress = progress_records.get(lesson.id)
            lesson_data = lesson.to_owner_dict()
            lesson_data["completed"] = bool(progress.completed) if progress else False
            lesson_data["watch_time"] = progress.watch_time if progress else 0
            lessons.append(lesson_data)
        modules.append(
            {
                "id": module.id,
                "title": module.title,
                "description": module.description,
                "order": module.order,
                "lessons": lessons,
            }
        )

    progress = calculate_course_progress(current_user().id, course_id)
    return success_response(
        "Course learning structure retrieved",
        {
            "course": course.to_public_dict(),
            "enrollment": enrollment.to_dict(),
            "modules": modules,
            "progress": progress,
        },
    )


@students_bp.get("/student/codex-id")
@student_required
def student_codex_id():
    """Get own Codex Student ID and QR information."""
    student_id = CodexStudentID.query.filter_by(user_id=current_user().id).first()
    if not student_id:
        return error_response("Codex Student ID not issued", "CODEX_ID_NOT_ISSUED", 404)
    
    # Get most recent enrollment for academic data
    enrollment = (
        Enrollment.query.options(joinedload(Enrollment.course))
        .filter_by(student_id=current_user().id)
        .filter(Enrollment.status.in_(("active", "completed")))
        .order_by(Enrollment.enrolled_at.desc())
        .first()
    )
    
    enrollment_data = None
    if enrollment and enrollment.course:
        enrollment_data = {
            "course_title": enrollment.course.title,
            "enrolled_at": enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
        }
    
    response_data = student_id.to_dict(include_user=True, include_qr=True)
    response_data["enrollment"] = enrollment_data
    
    return success_response(
        "Codex Student ID retrieved",
        {"codex_id": response_data},
    )


@students_bp.get("/student/attendance")
@student_required
def student_attendance():
    """Get own attendance history."""
    records = (
        AttendanceRecord.query.options(
            joinedload(AttendanceRecord.session),
            joinedload(AttendanceRecord.student_identity).joinedload(CodexStudentID.user),
        )
        .join(AttendanceSession)
        .filter(AttendanceRecord.student_identity.has(user_id=current_user().id))
        .order_by(AttendanceRecord.scanned_at.desc())
        .all()
    )
    return success_response(
        "Attendance history retrieved",
        {"attendance": [record.to_dict(include_student=True, include_scanner=True) for record in records]},
    )


@students_bp.get("/student/activity")
@student_required
def student_activity():
    """Get activity profile with attendance statistics and history."""
    student = current_user()
    
    # Get Codex ID
    student_id = CodexStudentID.query.filter_by(user_id=student.id).first()
    
    # Get attendance records
    records = (
        AttendanceRecord.query.options(
            joinedload(AttendanceRecord.session),
            joinedload(AttendanceRecord.student_identity).joinedload(CodexStudentID.user),
        )
        .join(AttendanceSession)
        .filter(AttendanceRecord.student_identity.has(user_id=student.id))
        .order_by(AttendanceRecord.scanned_at.desc())
        .all()
    )
    
    # Get enrollments for learning progress
    enrollments = (
        Enrollment.query.options(
            joinedload(Enrollment.course).options(
                joinedload(Course.instructor),
                joinedload(Course.category),
            ),
        )
        .filter_by(student_id=student.id)
        .order_by(Enrollment.enrolled_at.desc())
        .all()
    )
    
    # Calculate learning progress
    progress_values = [
        calculate_course_progress(student.id, enrollment.course_id)["progress_percentage"]
        for enrollment in enrollments
    ]
    overall_progress = int(round(sum(progress_values) / len(progress_values))) if progress_values else 0
    
    return success_response(
        "Activity profile retrieved",
        {
            "student": student.to_dict(),
            "codex_id": student_id.to_dict() if student_id else None,
            "attendance": {
                "total_events": len(records),
                "recent_records": [record.to_dict(include_student=True) for record in records[:10]],
            },
            "learning": {
                "enrolled_courses": len(enrollments),
                "overall_progress": overall_progress,
            },
        },
    )
