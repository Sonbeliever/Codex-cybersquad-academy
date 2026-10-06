from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import create_app
from app.extensions import db
from app.models import AttendanceRecord, AttendanceSession, CodexStudentID, User
from app.security import generate_access_token
from app.services.codex_service import generate_qr_token, issue_codex_id, validate_qr_token


@pytest.fixture()
def app():
    app = create_app("config.TestingConfig")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def create_user(
    full_name: str,
    email: str,
    role: str = "student",
    password: str = "securepass123",
) -> User:
    user = User(full_name=full_name, email=email, role=role, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def auth_header(user: User) -> dict:
    return {"Authorization": f"Bearer {generate_access_token(user)}"}


# Codex Student ID Tests


def test_student_can_view_own_codex_id(client):
    """Student can view own Codex ID."""
    student = create_user("Test Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    
    response = client.get("/api/student/codex-id", headers=auth_header(student))
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["codex_id"]["codex_id"] == student_id.codex_id
    assert data["data"]["codex_id"]["qr_token"] == student_id.qr_token


def test_student_without_codex_id_returns_404(client):
    """Student without Codex ID returns 404."""
    student = create_user("Test Student", "student@test.com", "student")
    
    response = client.get("/api/student/codex-id", headers=auth_header(student))
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "CODEX_ID_NOT_ISSUED"


def test_admin_can_issue_codex_id(client):
    """Admin can issue student ID."""
    admin = create_user("Admin User", "admin@test.com", "admin")
    student = create_user("Test Student", "student@test.com", "student")
    
    response = client.post(
        "/api/admin/codex-ids",
        headers=auth_header(admin),
        json={"user_id": student.id},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["codex_id"]["codex_id"].startswith("CODEX-")


def test_admin_cannot_issue_duplicate_id(client):
    """Admin cannot issue duplicate ID."""
    admin = create_user("Admin User", "admin@test.com", "admin")
    student = create_user("Test Student", "student@test.com", "student")
    issue_codex_id(student)
    
    response = client.post(
        "/api/admin/codex-ids",
        headers=auth_header(admin),
        json={"user_id": student.id},
    )
    assert response.status_code == 409
    data = response.get_json()
    assert data["error"] == "CODEX_ID_EXISTS"


def test_admin_can_suspend_student_id(client):
    """Admin can suspend student ID."""
    admin = create_user("Admin User", "admin@test.com", "admin")
    student = create_user("Test Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    
    response = client.patch(
        f"/api/admin/codex-ids/{student_id.id}/status",
        headers=auth_header(admin),
        json={"status": "suspended"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["codex_id"]["status"] == "suspended"


def test_admin_can_revoke_student_id(client):
    """Admin can revoke student ID."""
    admin = create_user("Admin User", "admin@test.com", "admin")
    student = create_user("Test Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    
    response = client.patch(
        f"/api/admin/codex-ids/{student_id.id}/status",
        headers=auth_header(admin),
        json={"status": "revoked"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["codex_id"]["status"] == "revoked"


# QR Token Security Tests


def test_qr_token_is_cryptographically_random(client):
    """QR token is cryptographically random."""
    token1 = generate_qr_token()
    token2 = generate_qr_token()
    assert token1 != token2
    assert len(token1) == 64  # SHA-256 hex string


def test_qr_token_is_unique_per_student(client):
    """QR token is unique per student."""
    student1 = create_user("Student 1", "student1@test.com", "student")
    student2 = create_user("Student 2", "student2@test.com", "student")
    id1 = issue_codex_id(student1)
    id2 = issue_codex_id(student2)
    assert id1.qr_token != id2.qr_token


def test_invalid_qr_token_returns_404(client):
    """Invalid QR token returns 404."""
    is_valid, error_code, student_id = validate_qr_token("invalidtoken123")
    assert is_valid is False
    assert error_code == "INVALID_TOKEN_FORMAT"


def test_malformed_token_returns_400(client):
    """Malformed token returns 400."""
    is_valid, error_code, student_id = validate_qr_token("short")
    assert is_valid is False
    assert error_code == "INVALID_TOKEN_FORMAT"


# Attendance Session Tests


def test_instructor_can_create_session(client):
    """Instructor can create attendance session."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    
    response = client.post(
        "/api/instructor/attendance/sessions",
        headers=auth_header(instructor),
        json={
            "title": "Workshop",
            "session_type": "workshop",
            "starts_at": datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc).isoformat(),
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["session"]["title"] == "Workshop"


def test_instructor_can_view_own_sessions(client):
    """Instructor can view own sessions."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    
    client.post(
        "/api/instructor/attendance/sessions",
        headers=auth_header(instructor),
        json={
            "title": "Workshop",
            "session_type": "workshop",
            "starts_at": datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc).isoformat(),
        },
    )
    
    response = client.get("/api/instructor/attendance/sessions", headers=auth_header(instructor))
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["data"]["sessions"]) == 1


def test_instructor_cannot_view_other_sessions(client):
    """Instructor cannot view other's sessions."""
    instructor1 = create_user("Instructor 1", "instructor1@test.com", "instructor")
    instructor2 = create_user("Instructor 2", "instructor2@test.com", "instructor")
    
    session = AttendanceSession(
        created_by=instructor2.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="draft",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.get(
        f"/api/instructor/attendance/sessions/{session.id}",
        headers=auth_header(instructor1),
    )
    assert response.status_code == 403


def test_instructor_can_activate_session(client):
    """Instructor can activate session."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="draft",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.patch(
        f"/api/instructor/attendance/sessions/{session.id}",
        headers=auth_header(instructor),
        json={"status": "active"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["session"]["status"] == "active"


def test_instructor_can_close_session(client):
    """Instructor can close session."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.patch(
        f"/api/instructor/attendance/sessions/{session.id}",
        headers=auth_header(instructor),
        json={"status": "closed"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["session"]["status"] == "closed"


# Attendance Recording Tests


def test_instructor_can_record_attendance(client):
    """Instructor can record attendance via QR scan."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    student = create_user("Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.post(
        f"/api/instructor/attendance/sessions/{session.id}/scan",
        headers=auth_header(instructor),
        json={"qr_token": student_id.qr_token},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["record"]["status"] == "present"


def test_duplicate_scan_is_prevented(client):
    """Duplicate scan is prevented."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    student = create_user("Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    db.session.add(session)
    db.session.commit()
    
    # First scan
    client.post(
        f"/api/instructor/attendance/sessions/{session.id}/scan",
        headers=auth_header(instructor),
        json={"qr_token": student_id.qr_token},
    )
    
    # Second scan
    response = client.post(
        f"/api/instructor/attendance/sessions/{session.id}/scan",
        headers=auth_header(instructor),
        json={"qr_token": student_id.qr_token},
    )
    assert response.status_code == 409
    data = response.get_json()
    assert data["error"] == "ALREADY_RECORDED"


def test_closed_session_rejects_scans(client):
    """Closed session rejects scans."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    student = create_user("Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="closed",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.post(
        f"/api/instructor/attendance/sessions/{session.id}/scan",
        headers=auth_header(instructor),
        json={"qr_token": student_id.qr_token},
    )
    assert response.status_code == 403
    data = response.get_json()
    assert data["error"] == "SESSION_NOT_ACTIVE"


def test_inactive_user_cannot_be_recorded(client):
    """Inactive user cannot be recorded."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    student = create_user("Student", "student@test.com", "student")
    student.is_active = False
    db.session.commit()
    student_id = issue_codex_id(student)
    
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.post(
        f"/api/instructor/attendance/sessions/{session.id}/scan",
        headers=auth_header(instructor),
        json={"qr_token": student_id.qr_token},
    )
    assert response.status_code == 403
    data = response.get_json()
    assert data["error"] == "ACCOUNT_INACTIVE"


def test_suspended_id_cannot_be_recorded(client):
    """Suspended ID cannot be recorded."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    student = create_user("Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    student_id.status = "suspended"
    db.session.commit()
    
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.post(
        f"/api/instructor/attendance/sessions/{session.id}/scan",
        headers=auth_header(instructor),
        json={"qr_token": student_id.qr_token},
    )
    assert response.status_code == 403
    data = response.get_json()
    assert data["error"] == "ID_SUSPENDED"


def test_revoked_id_cannot_be_recorded(client):
    """Revoked ID cannot be recorded."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    student = create_user("Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    student_id.status = "revoked"
    db.session.commit()
    
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.post(
        f"/api/instructor/attendance/sessions/{session.id}/scan",
        headers=auth_header(instructor),
        json={"qr_token": student_id.qr_token},
    )
    assert response.status_code == 403
    data = response.get_json()
    assert data["error"] == "ID_REVOKED"


# Verification Mode Tests (No Session)


def test_verification_mode_shows_student_info(client):
    """Verification mode shows student info without recording."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    student = create_user("Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    
    response = client.get(
        f"/api/instructor/codex-id/verify/{student_id.qr_token}",
        headers=auth_header(instructor),
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["student"]["full_name"] == student.full_name
    assert data["data"]["codex_id"]["codex_id"] == student_id.codex_id


def test_verification_mode_does_not_create_record(client):
    """Verification mode does not create attendance record."""
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    student = create_user("Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    
    client.get(
        f"/api/instructor/codex-id/verify/{student_id.qr_token}",
        headers=auth_header(instructor),
    )
    
    # No attendance record should exist
    records = AttendanceRecord.query.all()
    assert len(records) == 0


# Permission Tests


def test_student_cannot_create_session(client):
    """Student cannot create attendance session."""
    student = create_user("Student", "student@test.com", "student")
    
    response = client.post(
        "/api/instructor/attendance/sessions",
        headers=auth_header(student),
        json={
            "title": "Workshop",
            "session_type": "workshop",
            "starts_at": "2026-09-20T09:00:00Z",
        },
    )
    assert response.status_code == 403


def test_student_cannot_scan_others(client):
    """Student cannot scan others."""
    student = create_user("Student", "student@test.com", "student")
    other_student = create_user("Other", "other@test.com", "student")
    other_id = issue_codex_id(other_student)
    
    session = AttendanceSession(
        created_by=student.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.post(
        f"/api/instructor/attendance/sessions/{session.id}/scan",
        headers=auth_header(student),
        json={"qr_token": other_id.qr_token},
    )
    assert response.status_code == 403


def test_admin_has_full_access(client):
    """Admin has full access to all sessions."""
    admin = create_user("Admin", "admin@test.com", "admin")
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="draft",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.get(
        f"/api/admin/attendance/sessions/{session.id}",
        headers=auth_header(admin),
    )
    assert response.status_code == 200


def test_admin_can_modify_any_session(client):
    """Admin can modify any session."""
    admin = create_user("Admin", "admin@test.com", "admin")
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="draft",
    )
    db.session.add(session)
    db.session.commit()
    
    response = client.patch(
        f"/api/admin/attendance/sessions/{session.id}",
        headers=auth_header(admin),
        json={"status": "active"},
    )
    assert response.status_code == 200


# Student Attendance History Tests


def test_student_can_view_attendance_history(client):
    """Student can view attendance history."""
    student = create_user("Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    db.session.add(session)
    db.session.commit()
    
    record = AttendanceRecord(
        session_id=session.id,
        student_identity_id=student_id.id,
        scanned_by=instructor.id,
        verification_method="qr",
        status="present",
    )
    db.session.add(record)
    db.session.commit()
    
    response = client.get("/api/student/attendance", headers=auth_header(student))
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["data"]["attendance"]) == 1


def test_student_can_view_activity_profile(client):
    """Student can view activity profile."""
    student = create_user("Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    
    response = client.get("/api/student/activity", headers=auth_header(student))
    assert response.status_code == 200
    data = response.get_json()
    assert data["data"]["codex_id"]["codex_id"] == student_id.codex_id
    assert "attendance" in data["data"]
    assert "learning" in data["data"]


# Concurrency / Duplicate Race Condition Tests


def test_duplicate_scan_prevented_by_database_constraint(client):
    """Database unique constraint prevents duplicate attendance records."""
    from sqlalchemy.exc import IntegrityError

    student = create_user("Student", "student@test.com", "student")
    student_id = issue_codex_id(student)
    instructor = create_user("Instructor", "instructor@test.com", "instructor")
    
    session = AttendanceSession(
        created_by=instructor.id,
        title="Workshop",
        session_type="workshop",
        starts_at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    db.session.add(session)
    db.session.commit()

    # Create first attendance record
    record1 = AttendanceRecord(
        session_id=session.id,
        student_identity_id=student_id.id,
        scanned_by=instructor.id,
        verification_method="qr",
        status="present",
    )
    db.session.add(record1)
    db.session.commit()

    # Attempt to create duplicate record
    record2 = AttendanceRecord(
        session_id=session.id,
        student_identity_id=student_id.id,
        scanned_by=instructor.id,
        verification_method="qr",
        status="present",
    )
    db.session.add(record2)
    
    # Database should raise IntegrityError due to unique constraint
    with pytest.raises(IntegrityError):
        db.session.commit()
    
    db.session.rollback()

    # Verify only one record exists
    records = AttendanceRecord.query.filter_by(
        session_id=session.id,
        student_identity_id=student_id.id
    ).all()
    assert len(records) == 1

