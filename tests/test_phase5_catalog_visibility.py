from __future__ import annotations

from app.extensions import db
from app.models import Module
from tests.conftest import (
    auth_header,
    create_category,
    create_course,
    create_enrollment,
    create_user,
)


def _course_with_module(status: str = "draft"):
    category = create_category()
    instructor = create_user("Instructor", "inst@example.com", role="instructor")
    course = create_course(instructor, category, status=status)
    db.session.add(Module(course_id=course.id, title="Start", order=1))
    db.session.commit()
    return category, instructor, course


def test_approval_flow_makes_course_publicly_visible(app, client):
    """Regression: submit -> approve -> course must appear in public listings."""
    category, instructor, course = _course_with_module()
    admin = create_user("Admin", "admin@example.com", role="admin")

    submitted = client.post(
        f"/api/instructor/courses/{course.id}/submit",
        headers=auth_header(instructor),
    )
    assert submitted.status_code == 200
    assert submitted.get_json()["data"]["course"]["status"] == "pending"

    listed_before = client.get("/api/courses")
    assert listed_before.status_code == 200
    assert [item["id"] for item in listed_before.get_json()["data"]["courses"]] == []

    approved = client.patch(
        f"/api/admin/courses/{course.id}/approve",
        headers=auth_header(admin),
    )
    assert approved.status_code == 200
    assert approved.get_json()["data"]["course"]["status"] == "published"

    listed = client.get("/api/courses")
    assert listed.status_code == 200
    assert course.id in [item["id"] for item in listed.get_json()["data"]["courses"]]

    details = client.get(f"/api/courses/{course.id}")
    assert details.status_code == 200
    assert details.get_json()["data"]["course"]["id"] == course.id

    category_listed = client.get(f"/api/categories/{category.id}/courses")
    assert category_listed.status_code == 200
    assert course.id in [item["id"] for item in category_listed.get_json()["data"]["courses"]]


def test_rejected_course_is_hidden_until_resubmitted_and_approved(app, client):
    category, instructor, course = _course_with_module(status="pending")
    admin = create_user("Admin", "admin@example.com", role="admin")

    rejected = client.patch(
        f"/api/admin/courses/{course.id}/reject",
        json={"admin_note": "Improve the curriculum"},
        headers=auth_header(admin),
    )
    assert rejected.status_code == 200
    assert rejected.get_json()["data"]["course"]["status"] == "rejected"
    assert rejected.get_json()["data"]["course"]["admin_note"] == "Improve the curriculum"

    listed = client.get("/api/courses")
    assert [item["id"] for item in listed.get_json()["data"]["courses"]] == []

    edited = client.put(
        f"/api/instructor/courses/{course.id}",
        json={"description": "Improved practical curriculum."},
        headers=auth_header(instructor),
    )
    assert edited.status_code == 200
    assert edited.get_json()["data"]["course"]["status"] == "draft"

    resubmitted = client.post(
        f"/api/instructor/courses/{course.id}/submit",
        headers=auth_header(instructor),
    )
    assert resubmitted.status_code == 200

    approved = client.patch(
        f"/api/admin/courses/{course.id}/approve",
        headers=auth_header(admin),
    )
    assert approved.status_code == 200

    listed = client.get("/api/courses")
    assert course.id in [item["id"] for item in listed.get_json()["data"]["courses"]]


def test_enrolled_count_is_aggregate_only(app, client):
    category, instructor, course = _course_with_module(status="published")
    student = create_user("Student", "student@example.com")
    other = create_user("Other", "other@example.com")
    create_enrollment(student, course)
    create_enrollment(other, course)

    listed = client.get("/api/courses")
    target = next(
        item for item in listed.get_json()["data"]["courses"] if item["id"] == course.id
    )
    assert target["enrolled_count"] == 2
    # Aggregate only: no student identities may be exposed.
    assert "student_id" not in target
    assert "student" not in target