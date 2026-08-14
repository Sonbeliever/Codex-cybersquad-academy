from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db
from app.models import Category, Course, Enrollment, Lesson, Module, User
from app.security import generate_access_token


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


def create_category(name: str = "Software Development") -> Category:
    category = Category(
        name=name,
        slug=name.lower().replace(" ", "-"),
        description=f"{name} courses",
    )
    db.session.add(category)
    db.session.commit()
    return category


def create_course(
    instructor: User,
    category: Category,
    title: str = "Python Foundations",
    status: str = "draft",
) -> Course:
    course = Course(
        instructor_id=instructor.id,
        category_id=category.id,
        title=title,
        slug=title.lower().replace(" ", "-"),
        description="Learn practical programming foundations.",
        price=5000,
        language="english",
        level="beginner",
        duration=120,
        status=status,
    )
    db.session.add(course)
    db.session.commit()
    return course


def create_module(course: Course, title: str = "Getting Started", order: int = 1) -> Module:
    module = Module(course_id=course.id, title=title, order=order)
    db.session.add(module)
    db.session.commit()
    return module


def create_lesson(
    module: Module,
    title: str = "Welcome",
    order: int = 1,
    is_preview: bool = False,
    video_url: str = "https://storage.example.com/private/video.mp4",
) -> Lesson:
    lesson = Lesson(
        module_id=module.id,
        title=title,
        order=order,
        duration=10,
        is_preview=is_preview,
        video_url=video_url,
    )
    db.session.add(lesson)
    db.session.commit()
    return lesson


def create_enrollment(student: User, course: Course, status: str = "active") -> Enrollment:
    enrollment = Enrollment(student_id=student.id, course_id=course.id, status=status)
    db.session.add(enrollment)
    db.session.commit()
    return enrollment
