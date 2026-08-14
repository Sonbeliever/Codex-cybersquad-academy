"""add course management engine

Revision ID: 202608110002
Revises: 202608110001
Create Date: 2026-08-11 00:02:00
"""
from alembic import op
import sqlalchemy as sa


revision = "202608110002"
down_revision = "202608110001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_categories_slug"), "categories", ["slug"], unique=True)

    op.create_table(
        "instructor_applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expertise", sa.String(length=255), nullable=False),
        sa.Column("experience", sa.Text(), nullable=False),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_instructor_applications_status_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_instructor_applications_status"),
        "instructor_applications",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_instructor_applications_user_id"),
        "instructor_applications",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("instructor_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("subtitle", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("thumbnail", sa.String(length=500), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("duration >= 0", name="ck_courses_duration_non_negative"),
        sa.CheckConstraint(
            "language IN ('english', 'hausa')",
            name="ck_courses_language_valid",
        ),
        sa.CheckConstraint(
            "level IN ('beginner', 'intermediate', 'advanced')",
            name="ck_courses_level_valid",
        ),
        sa.CheckConstraint("price >= 0", name="ck_courses_price_non_negative"),
        sa.CheckConstraint(
            "status IN ('draft', 'pending', 'approved', 'published', 'rejected')",
            name="ck_courses_status_valid",
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["instructor_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_courses_category_id"), "courses", ["category_id"], unique=False)
    op.create_index(op.f("ix_courses_instructor_id"), "courses", ["instructor_id"], unique=False)
    op.create_index(op.f("ix_courses_language"), "courses", ["language"], unique=False)
    op.create_index(op.f("ix_courses_level"), "courses", ["level"], unique=False)
    op.create_index(op.f("ix_courses_slug"), "courses", ["slug"], unique=True)
    op.create_index(op.f("ix_courses_status"), "courses", ["status"], unique=False)

    op.create_table(
        "modules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('"order" >= 0', name="ck_modules_order_non_negative"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "order", name="uq_modules_course_order"),
    )
    op.create_index(op.f("ix_modules_course_id"), "modules", ["course_id"], unique=False)

    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("video_url", sa.String(length=1000), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("is_preview", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("duration >= 0", name="ck_lessons_duration_non_negative"),
        sa.CheckConstraint('"order" >= 0', name="ck_lessons_order_non_negative"),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_id", "order", name="uq_lessons_module_order"),
    )
    op.create_index(op.f("ix_lessons_is_preview"), "lessons", ["is_preview"], unique=False)
    op.create_index(op.f("ix_lessons_module_id"), "lessons", ["module_id"], unique=False)

    op.create_table(
        "lesson_resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("file_url", sa.String(length=1000), nullable=False),
        sa.Column("file_type", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_lesson_resources_lesson_id"),
        "lesson_resources",
        ["lesson_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_lesson_resources_lesson_id"), table_name="lesson_resources")
    op.drop_table("lesson_resources")
    op.drop_index(op.f("ix_lessons_module_id"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_is_preview"), table_name="lessons")
    op.drop_table("lessons")
    op.drop_index(op.f("ix_modules_course_id"), table_name="modules")
    op.drop_table("modules")
    op.drop_index(op.f("ix_courses_status"), table_name="courses")
    op.drop_index(op.f("ix_courses_slug"), table_name="courses")
    op.drop_index(op.f("ix_courses_level"), table_name="courses")
    op.drop_index(op.f("ix_courses_language"), table_name="courses")
    op.drop_index(op.f("ix_courses_instructor_id"), table_name="courses")
    op.drop_index(op.f("ix_courses_category_id"), table_name="courses")
    op.drop_table("courses")
    op.drop_index(op.f("ix_instructor_applications_user_id"), table_name="instructor_applications")
    op.drop_index(op.f("ix_instructor_applications_status"), table_name="instructor_applications")
    op.drop_table("instructor_applications")
    op.drop_index(op.f("ix_categories_slug"), table_name="categories")
    op.drop_table("categories")
