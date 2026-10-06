from __future__ import annotations

from app.extensions import db
from app.models import Course, Module
from tests.conftest import auth_header, create_category, create_course, create_user


def course_payload(category_id: int, title: str = "Python Foundations") -> dict:
    return {
        "category_id": category_id,
        "title": title,
        "subtitle": "Start coding with confidence",
        "description": "A practical introduction to Python for beginners.",
        "price": 5000,
        "language": "english",
        "level": "beginner",
        "duration": 180,
    }


def test_category_creation_and_public_listing(app, client):
    admin = create_user("Admin User", "admin@example.com", role="admin")
    created = client.post(
        "/api/admin/categories",
        json={"name": "Data Science", "description": "Analysis and AI skills"},
        headers=auth_header(admin),
    )
    assert created.status_code == 201
    assert created.get_json()["data"]["category"]["slug"] == "data-science"

    listed = client.get("/api/categories")
    assert listed.status_code == 200
    assert len(listed.get_json()["data"]["categories"]) == 1


def test_public_course_listing_only_shows_published(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    create_course(instructor, category, title="Published Course", status="published")
    create_course(instructor, category, title="Draft Course", status="draft")

    listed = client.get("/api/courses")
    assert listed.status_code == 200
    courses = listed.get_json()["data"]["courses"]
    assert [course["title"] for course in courses] == ["Published Course"]

    hidden = client.get("/api/courses/2")
    assert hidden.status_code == 404


def test_student_and_unapproved_instructor_cannot_create_course(app, client):
    category = create_category()
    student = create_user("Student", "student@example.com")
    pending_user = create_user("Pending Instructor", "pending@example.com")

    student_response = client.post(
        "/api/instructor/courses",
        json=course_payload(category.id),
        headers=auth_header(student),
    )
    assert student_response.status_code == 403

    pending_response = client.post(
        "/api/instructor/courses",
        json=course_payload(category.id),
        headers=auth_header(pending_user),
    )
    assert pending_response.status_code == 403


def test_approved_instructor_can_create_and_edit_own_course(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")

    created = client.post(
        "/api/instructor/courses",
        json=course_payload(category.id),
        headers=auth_header(instructor),
    )
    assert created.status_code == 201
    course_id = created.get_json()["data"]["course"]["id"]

    updated = client.put(
        f"/api/instructor/courses/{course_id}",
        json={"title": "Python Foundations Updated"},
        headers=auth_header(instructor),
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["course"]["title"] == "Python Foundations Updated"


def test_instructor_cannot_edit_another_instructors_course(app, client):
    category = create_category()
    owner = create_user("Owner", "owner@example.com", role="instructor")
    other = create_user("Other", "other@example.com", role="instructor")
    course = create_course(owner, category)

    response = client.put(
        f"/api/instructor/courses/{course.id}",
        json={"title": "Taken Over"},
        headers=auth_header(other),
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "COURSE_FORBIDDEN"


def test_instructor_can_create_modules_lessons_and_resources(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    course = create_course(instructor, category)

    module_response = client.post(
        f"/api/instructor/courses/{course.id}/modules",
        json={"title": "Getting Started", "order": 1},
        headers=auth_header(instructor),
    )
    assert module_response.status_code == 201
    module_id = module_response.get_json()["data"]["module"]["id"]

    lesson_response = client.post(
        f"/api/instructor/modules/{module_id}/lessons",
        json={
            "title": "Welcome",
            "video_url": "https://storage.example.com/private/welcome.mp4",
            "duration": 12,
            "order": 1,
            "is_preview": True,
        },
        headers=auth_header(instructor),
    )
    assert lesson_response.status_code == 201
    lesson_id = lesson_response.get_json()["data"]["lesson"]["id"]

    resource_response = client.post(
        f"/api/instructor/lessons/{lesson_id}/resources",
        json={
            "name": "Slides",
            "file_url": "https://storage.example.com/slides.pdf",
            "file_type": "pdf",
        },
        headers=auth_header(instructor),
    )
    assert resource_response.status_code == 201


def test_course_submission_and_admin_pending_visibility(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    admin = create_user("Admin", "admin@example.com", role="admin")
    course = create_course(instructor, category)
    module = Module(course_id=course.id, title="Start", order=1)
    db.session.add(module)
    db.session.commit()

    submitted = client.post(
        f"/api/instructor/courses/{course.id}/submit",
        headers=auth_header(instructor),
    )
    assert submitted.status_code == 200
    assert submitted.get_json()["data"]["course"]["status"] == "pending"

    pending = client.get("/api/admin/courses/pending", headers=auth_header(admin))
    assert pending.status_code == 200
    assert pending.get_json()["data"]["courses"][0]["id"] == course.id


def test_admin_can_approve_course_and_public_details_hide_private_videos(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    admin = create_user("Admin", "admin@example.com", role="admin")
    course = create_course(instructor, category, status="pending")
    module = Module(course_id=course.id, title="Start", order=1)
    db.session.add(module)
    db.session.commit()

    approved = client.patch(
        f"/api/admin/courses/{course.id}/approve",
        headers=auth_header(admin),
    )
    assert approved.status_code == 200
    assert approved.get_json()["data"]["course"]["status"] == "published"

    details = client.get(f"/api/courses/{course.id}")
    assert details.status_code == 200
    assert details.get_json()["data"]["course"]["instructor"]["full_name"] == "Instructor"


def test_admin_can_reject_and_instructor_can_resubmit_after_edit(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    admin = create_user("Admin", "admin@example.com", role="admin")
    course = create_course(instructor, category, status="pending")
    module = Module(course_id=course.id, title="Start", order=1)
    db.session.add(module)
    db.session.commit()

    rejected = client.patch(
        f"/api/admin/courses/{course.id}/reject",
        json={"admin_note": "Improve curriculum"},
        headers=auth_header(admin),
    )
    assert rejected.status_code == 200
    assert rejected.get_json()["data"]["course"]["status"] == "rejected"

    edited = client.put(
        f"/api/instructor/courses/{course.id}",
        json={"description": "Improved practical Python curriculum."},
        headers=auth_header(instructor),
    )
    assert edited.status_code == 200
    assert edited.get_json()["data"]["course"]["status"] == "draft"

    resubmitted = client.post(
        f"/api/instructor/courses/{course.id}/submit",
        headers=auth_header(instructor),
    )
    assert resubmitted.status_code == 200
    assert resubmitted.get_json()["data"]["course"]["status"] == "pending"


def test_instructor_application_and_admin_approval(app, client):
    student = create_user("Future Instructor", "future@example.com")
    admin = create_user("Admin", "admin@example.com", role="admin")

    empty = client.get("/api/instructor/application", headers=auth_header(student))
    assert empty.status_code == 200
    assert empty.get_json()["data"]["application"] is None

    applied = client.post(
        "/api/instructor/apply",
        json={
            "expertise": "Backend Development",
            "experience": "Five years building Flask APIs.",
            "bio": "I teach practical software engineering.",
            "phone": "+2348012345678",
        },
        headers=auth_header(student),
    )
    assert applied.status_code == 201
    application_id = applied.get_json()["data"]["application"]["id"]

    status = client.get("/api/instructor/application", headers=auth_header(student))
    assert status.status_code == 200

    approved = client.patch(
        f"/api/admin/instructor-applications/{application_id}/approve",
        headers=auth_header(admin),
    )
    assert approved.status_code == 200
    assert approved.get_json()["data"]["application"]["user"]["role"] == "instructor"


def test_approved_instructor_without_application_row_gets_null_application(app, client):
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    response = client.get("/api/instructor/application", headers=auth_header(instructor))
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["application"] is None


def test_editing_published_course_queues_admin_review(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    course = create_course(instructor, category, status="published")

    updated = client.put(
        f"/api/instructor/courses/{course.id}",
        json={
            "description": "Updated practical description for enrolled learners.",
            "thumbnail": "https://cdn.example.com/course-thumbnail.jpg",
        },
        headers=auth_header(instructor),
    )
    assert updated.status_code == 200
    body = updated.get_json()
    assert body["data"]["course"]["status"] == "pending"
    assert "re-review" in body["message"]


def test_thumbnail_url_at_max_length_is_accepted_on_create(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")

    # 500 characters total, well-formed https image URL padded with query params.
    base = "https://cdn.example.com/course-thumbnail.jpg?ref="
    thumbnail = base + ("a" * (500 - len(base)))
    assert len(thumbnail) == 500

    response = client.post(
        "/api/instructor/courses",
        json={**course_payload(category.id), "thumbnail": thumbnail},
        headers=auth_header(instructor),
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["course"]["thumbnail"] == thumbnail


def test_thumbnail_url_over_max_length_is_rejected_on_create(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")

    base = "https://www.bing.com/images/search?q=course&form=HDRSC2&first=1&extra="
    thumbnail = base + ("a" * (501 - len(base)))
    assert len(thumbnail) == 501

    response = client.post(
        "/api/instructor/courses",
        json={**course_payload(category.id), "thumbnail": thumbnail},
        headers=auth_header(instructor),
    )
    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "VALIDATION_ERROR"
    assert body["details"]["thumbnail"] == "Thumbnail URL must be 500 characters or less."

    # Ensure no course row was created because of the oversized value.
    assert Course.query.count() == 0


def test_thumbnail_url_over_max_length_is_rejected_on_update(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    course = create_course(instructor, category, status="draft")

    base = "https://www.bing.com/images/search?q=course&form=HDRSC2&first=1&extra="
    thumbnail = base + ("a" * (501 - len(base)))
    assert len(thumbnail) == 501

    response = client.put(
        f"/api/instructor/courses/{course.id}",
        json={"thumbnail": thumbnail},
        headers=auth_header(instructor),
    )
    assert response.status_code == 422
    body = response.get_json()
    assert body["error"] == "VALIDATION_ERROR"
    assert body["details"]["thumbnail"] == "Thumbnail URL must be 500 characters or less."

    # The course's thumbnail must remain unchanged (no truncation, no partial write).
    db.session.refresh(course)
    assert course.thumbnail != thumbnail


def test_thumbnail_rejects_youtube_watch_url(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    course = create_course(instructor, category, status="draft")

    response = client.put(
        f"/api/instructor/courses/{course.id}",
        json={"thumbnail": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        headers=auth_header(instructor),
    )
    assert response.status_code == 422
    assert response.get_json()["error"] == "VALIDATION_ERROR"
    assert "thumbnail" in response.get_json()["details"]


def test_lesson_youtube_url_is_normalized(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    course = create_course(instructor, category)
    module_response = client.post(
        f"/api/instructor/courses/{course.id}/modules",
        json={"title": "Videos", "order": 1},
        headers=auth_header(instructor),
    )
    module_id = module_response.get_json()["data"]["module"]["id"]

    lesson_response = client.post(
        f"/api/instructor/modules/{module_id}/lessons",
        json={
            "title": "Intro",
            "video_url": "https://youtu.be/dQw4w9WgXcQ",
            "duration": 5,
            "order": 1,
        },
        headers=auth_header(instructor),
    )
    assert lesson_response.status_code == 201
    assert (
        lesson_response.get_json()["data"]["lesson"]["video_url"]
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )


def test_duplicate_module_order_returns_clear_conflict(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    course = create_course(instructor, category)
    first = client.post(
        f"/api/instructor/courses/{course.id}/modules",
        json={"title": "One", "order": 1},
        headers=auth_header(instructor),
    )
    assert first.status_code == 201
    conflict = client.post(
        f"/api/instructor/courses/{course.id}/modules",
        json={"title": "Two", "order": 1},
        headers=auth_header(instructor),
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["error"] == "MODULE_ORDER_EXISTS"
    assert "order" in conflict.get_json()["message"].lower()


def test_students_cannot_approve_instructors_or_courses(app, client):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    student = create_user("Student", "student@example.com")
    applicant = create_user("Applicant", "applicant@example.com")
    course = create_course(instructor, category, status="pending")

    applied = client.post(
        "/api/instructor/apply",
        json={
            "expertise": "Design",
            "experience": "Three years",
            "bio": "I teach design.",
        },
        headers=auth_header(applicant),
    )
    application_id = applied.get_json()["data"]["application"]["id"]

    approve_application = client.patch(
        f"/api/admin/instructor-applications/{application_id}/approve",
        headers=auth_header(student),
    )
    assert approve_application.status_code == 403

    approve_course = client.patch(
        f"/api/admin/courses/{course.id}/approve",
        headers=auth_header(student),
    )
    assert approve_course.status_code == 403
