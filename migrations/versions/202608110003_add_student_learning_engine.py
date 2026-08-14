"""add student learning engine

Revision ID: 202608110003
Revises: 202608110002
Create Date: 2026-08-11 00:03:00
"""
from alembic import op
import sqlalchemy as sa


revision = "202608110003"
down_revision = "202608110002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "enrollments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_enrollments_status_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_enrollments_course_id"), "enrollments", ["course_id"], unique=False)
    op.create_index(op.f("ix_enrollments_payment_id"), "enrollments", ["payment_id"], unique=False)
    op.create_index(op.f("ix_enrollments_status"), "enrollments", ["status"], unique=False)
    op.create_index(op.f("ix_enrollments_student_id"), "enrollments", ["student_id"], unique=False)
    op.create_index(
        "uq_enrollments_student_course_active_completed",
        "enrollments",
        ["student_id", "course_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'completed')"),
        sqlite_where=sa.text("status IN ('active', 'completed')"),
    )

    op.create_table(
        "lesson_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("watch_time", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "watch_time >= 0",
            name="ck_lesson_progress_watch_time_non_negative",
        ),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id",
            "lesson_id",
            name="uq_lesson_progress_student_lesson",
        ),
    )
    op.create_index(
        op.f("ix_lesson_progress_completed"),
        "lesson_progress",
        ["completed"],
        unique=False,
    )
    op.create_index(
        op.f("ix_lesson_progress_lesson_id"),
        "lesson_progress",
        ["lesson_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_lesson_progress_student_id"),
        "lesson_progress",
        ["student_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_lesson_progress_student_id"), table_name="lesson_progress")
    op.drop_index(op.f("ix_lesson_progress_lesson_id"), table_name="lesson_progress")
    op.drop_index(op.f("ix_lesson_progress_completed"), table_name="lesson_progress")
    op.drop_table("lesson_progress")
    op.drop_index("uq_enrollments_student_course_active_completed", table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_student_id"), table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_status"), table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_payment_id"), table_name="enrollments")
    op.drop_index(op.f("ix_enrollments_course_id"), table_name="enrollments")
    op.drop_table("enrollments")
