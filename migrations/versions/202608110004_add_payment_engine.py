"""add payment engine

Revision ID: 202608110004
Revises: 202608110003
Create Date: 2026-08-15 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "202608110004"
down_revision = "202608110003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("reference", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'successful', 'failed', 'cancelled')",
            name="ck_payments_status_valid",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payments_student_id"), "payments", ["student_id"], unique=False)
    op.create_index(op.f("ix_payments_course_id"), "payments", ["course_id"], unique=False)
    op.create_index(op.f("ix_payments_reference"), "payments", ["reference"], unique=False)
    op.create_index(op.f("ix_payments_status"), "payments", ["status"], unique=False)

    # add FK on enrollments.payment_id
    op.create_foreign_key(
        "fk_enrollments_payment_id_payments",
        "enrollments",
        "payments",
        ["payment_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_enrollments_payment_id_payments", "enrollments", type_="foreignkey")
    op.drop_index(op.f("ix_payments_status"), table_name="payments")
    op.drop_index(op.f("ix_payments_reference"), table_name="payments")
    op.drop_index(op.f("ix_payments_course_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_student_id"), table_name="payments")
    op.drop_table("payments")
