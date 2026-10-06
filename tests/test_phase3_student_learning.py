from __future__ import annotations

from app.extensions import db
from app.models import Enrollment, LessonProgress
from tests.conftest import (
    auth_header,
    create_category,
    create_course,
    create_enrollment,
    create_lesson,
    create_module,
    create_user,
)


def published_course_with_lessons():
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    course = create_course(instructor, category, status="published")
    module = create_module(course)
    lesson = create_lesson(module, title="Protected Lesson", order=1, is_preview=False)
    preview = create_lesson(
        module,
        title="Preview Lesson",
        order=2,
        is_preview=True,
        video_url="https://storage.example.com/preview.mp4",
    )
    return course, lesson, preview


def test_student_can_enroll_in_published_course(app, client):
    student = create_user("Student", "student@example.com")
    course, _, _ = published_course_with_lessons()
    course.price = 0
    db.session.commit()

    response = client.post(
        "/api/enrollments",
        json={"course_id": course.id},
        headers=auth_header(student),
    )
    assert response.status_code == 201
    enrollment = response.get_json()["data"]["enrollment"]
    assert enrollment["course_id"] == course.id
    assert enrollment["status"] == "active"


def test_student_cannot_enroll_in_paid_course_without_payment(app, client):
    student = create_user("Student", "student@example.com")
    course, _, _ = published_course_with_lessons()

    response = client.post(
        "/api/enrollments",
        json={"course_id": course.id},
        headers=auth_header(student),
    )
    assert response.status_code == 402
    assert response.get_json()["error"] == "PAYMENT_REQUIRED"


def test_student_cannot_enroll_in_unpublished_course(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    student = create_user("Student", "student@example.com")
    draft = create_course(instructor, category, status="draft")

    response = client.post(
        "/api/enrollments",
        json={"course_id": draft.id},
        headers=auth_header(student),
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "COURSE_NOT_PUBLISHED"


def test_duplicate_enrollment_is_prevented(app, client):
    student = create_user("Student", "student@example.com")
    course, _, _ = published_course_with_lessons()
    create_enrollment(student, course)

    response = client.post(
        "/api/enrollments",
        json={"course_id": course.id},
        headers=auth_header(student),
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "ENROLLMENT_EXISTS"


def test_student_can_view_own_courses(app, client):
    student = create_user("Student", "student@example.com")
    course, _, _ = published_course_with_lessons()
    create_enrollment(student, course)

    response = client.get("/api/my-courses", headers=auth_header(student))
    assert response.status_code == 200
    courses = response.get_json()["data"]["courses"]
    assert len(courses) == 1
    assert courses[0]["course"]["id"] == course.id
    assert courses[0]["progress_percentage"] == 0


def test_student_cannot_view_another_students_enrollment(app, client):
    owner = create_user("Owner", "owner@example.com")
    other = create_user("Other", "other@example.com")
    course, _, _ = published_course_with_lessons()
    enrollment = create_enrollment(owner, course)

    response = client.get(
        f"/api/enrollments/{enrollment.id}",
        headers=auth_header(other),
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "ENROLLMENT_FORBIDDEN"


def test_enrolled_student_can_access_normal_lesson(app, client):
    student = create_user("Student", "student@example.com")
    course, lesson, _ = published_course_with_lessons()
    create_enrollment(student, course)

    response = client.get(f"/api/lessons/{lesson.id}", headers=auth_header(student))
    assert response.status_code == 200
    assert response.get_json()["data"]["lesson"]["video_url"].endswith("video.mp4")


def test_unenrolled_student_cannot_access_normal_lesson_or_video_url(app, client):
    student = create_user("Student", "student@example.com")
    _, lesson, _ = published_course_with_lessons()

    response = client.get(f"/api/lessons/{lesson.id}", headers=auth_header(student))
    assert response.status_code == 403
    assert response.get_json()["error"] == "COURSE_ACCESS_DENIED"
    assert "video_url" not in response.get_data(as_text=True)


def test_authenticated_unenrolled_user_can_access_preview_lesson(app, client):
    student = create_user("Student", "student@example.com")
    _, _, preview = published_course_with_lessons()

    response = client.get(f"/api/lessons/{preview.id}", headers=auth_header(student))
    assert response.status_code == 200
    assert response.get_json()["data"]["lesson"]["video_url"].endswith("preview.mp4")


def test_student_can_update_own_lesson_progress(app, client):
    student = create_user("Student", "student@example.com")
    course, lesson, _ = published_course_with_lessons()
    create_enrollment(student, course)

    response = client.post(
        f"/api/lessons/{lesson.id}/progress",
        json={"watch_time": 320, "completed": True},
        headers=auth_header(student),
    )
    assert response.status_code == 200
    progress = response.get_json()["data"]["progress"]
    assert progress["watch_time"] == 320
    assert progress["completed"] is True


def test_student_cannot_update_progress_for_another_students_course(app, client):
    owner = create_user("Owner", "owner@example.com")
    other = create_user("Other", "other@example.com")
    course, lesson, _ = published_course_with_lessons()
    create_enrollment(owner, course)

    response = client.post(
        f"/api/lessons/{lesson.id}/progress",
        json={"watch_time": 100, "completed": True},
        headers=auth_header(other),
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "COURSE_ACCESS_DENIED"


def test_progress_percentage_is_calculated_by_backend(app, client):
    student = create_user("Student", "student@example.com")
    course, lesson, preview = published_course_with_lessons()
    create_enrollment(student, course)

    client.post(
        f"/api/lessons/{lesson.id}/progress",
        json={"watch_time": 100, "completed": True, "progress_percentage": 100},
        headers=auth_header(student),
    )
    response = client.get(f"/api/courses/{course.id}/progress", headers=auth_header(student))
    assert response.status_code == 200
    data = response.get_json()["data"]["progress"]
    assert data["total_lessons"] == 2
    assert data["completed_lessons"] == 1
    assert data["progress_percentage"] == 50
    assert preview.id


def test_course_becomes_completed_when_all_required_lessons_complete(app, client):
    student = create_user("Student", "student@example.com")
    course, lesson, preview = published_course_with_lessons()
    enrollment = create_enrollment(student, course)

    for item in (lesson, preview):
        client.post(
            f"/api/lessons/{item.id}/progress",
            json={"watch_time": 100, "completed": True},
            headers=auth_header(student),
        )

    db.session.refresh(enrollment)
    assert enrollment.status == "completed"
    assert enrollment.completed_at is not None


def test_course_not_completed_when_frontend_only_claims_100_percent(app, client):
    student = create_user("Student", "student@example.com")
    course, lesson, _ = published_course_with_lessons()
    enrollment = create_enrollment(student, course)

    response = client.post(
        f"/api/lessons/{lesson.id}/progress",
        json={"watch_time": 100, "completed": False, "progress_percentage": 100},
        headers=auth_header(student),
    )
    assert response.status_code == 200
    db.session.refresh(enrollment)
    assert enrollment.status == "active"
    assert enrollment.completed_at is None


def test_student_dashboard_returns_correct_statistics(app, client):
    student = create_user("Student", "student@example.com")
    course, lesson, preview = published_course_with_lessons()
    create_enrollment(student, course)
    for item in (lesson, preview):
        client.post(
            f"/api/lessons/{item.id}/progress",
            json={"watch_time": 100, "completed": True},
            headers=auth_header(student),
        )

    response = client.get("/api/student/dashboard", headers=auth_header(student))
    assert response.status_code == 200
    stats = response.get_json()["data"]["statistics"]
    assert stats["enrolled_courses"] == 1
    assert stats["completed_courses"] == 1
    assert stats["overall_learning_progress"] == 100


def test_student_learning_structure_returns_lesson_progress(app, client):
    student = create_user("Student", "student@example.com")
    course, lesson, preview = published_course_with_lessons()
    create_enrollment(student, course)
    client.post(
        f"/api/lessons/{lesson.id}/progress",
        json={"watch_time": 350, "completed": True},
        headers=auth_header(student),
    )

    response = client.get(
        f"/api/my-courses/{course.id}/learning",
        headers=auth_header(student),
    )
    assert response.status_code == 200
    lessons = response.get_json()["data"]["modules"][0]["lessons"]
    assert lessons[0]["completed"] is True
    assert lessons[0]["watch_time"] == 350
    assert lessons[1]["id"] == preview.id


def test_student_cannot_access_admin_enrollment_endpoint_and_admin_can(app, client):
    student = create_user("Student", "student@example.com")
    admin = create_user("Admin", "admin@example.com", role="admin")
    course, _, _ = published_course_with_lessons()
    create_enrollment(student, course)

    blocked = client.get("/api/admin/enrollments", headers=auth_header(student))
    assert blocked.status_code == 403

    allowed = client.get("/api/admin/enrollments", headers=auth_header(admin))
    assert allowed.status_code == 200
    assert allowed.get_json()["data"]["pagination"]["total"] == 1


def test_course_with_zero_lessons_does_not_divide_by_zero(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    student = create_user("Student", "student@example.com")
    course = create_course(instructor, category, status="published")
    create_enrollment(student, course)

    response = client.get(f"/api/courses/{course.id}/progress", headers=auth_header(student))
    assert response.status_code == 200
    progress = response.get_json()["data"]["progress"]
    assert progress["total_lessons"] == 0
    assert progress["progress_percentage"] == 0


def test_unauthorized_users_cannot_receive_protected_video_urls(app, client):
    course, lesson, _ = published_course_with_lessons()
    response = client.get(f"/api/courses/{course.id}")
    assert response.status_code == 200
    assert "https://storage.example.com/private/video.mp4" not in response.get_data(as_text=True)

    anonymous_lesson = client.get(f"/api/lessons/{lesson.id}")
    assert anonymous_lesson.status_code == 401
    assert "https://storage.example.com/private/video.mp4" not in anonymous_lesson.get_data(as_text=True)


def test_admin_can_view_enrollment_details(app, client):
    student = create_user("Student", "student@example.com")
    admin = create_user("Admin", "admin@example.com", role="admin")
    course, _, _ = published_course_with_lessons()
    enrollment = create_enrollment(student, course)

    response = client.get(f"/api/enrollments/{enrollment.id}", headers=auth_header(admin))
    assert response.status_code == 200
    assert response.get_json()["data"]["enrollment"]["student"]["id"] == student.id


def test_duplicate_lesson_progress_record_is_reused(app, client):
    student = create_user("Student", "student@example.com")
    course, lesson, _ = published_course_with_lessons()
    create_enrollment(student, course)

    for watch_time in (10, 25):
        client.post(
            f"/api/lessons/{lesson.id}/progress",
            json={"watch_time": watch_time, "completed": False},
            headers=auth_header(student),
        )

    count = LessonProgress.query.filter_by(student_id=student.id, lesson_id=lesson.id).count()
    assert count == 1
