"""create users and token blocklist

Revision ID: 202608110001
Revises:
Create Date: 2026-08-11 00:01:00
"""
from alembic import op
import sqlalchemy as sa


revision = "202608110001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("profile_image", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('student', 'instructor', 'admin')",
            name="ck_users_role_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_is_active"), "users", ["is_active"], unique=False)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)

    op.create_table(
        "token_blocklist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("jti", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_token_blocklist_expires_at"),
        "token_blocklist",
        ["expires_at"],
        unique=False,
    )
    op.create_index(op.f("ix_token_blocklist_jti"), "token_blocklist", ["jti"], unique=True)
    op.create_index(
        op.f("ix_token_blocklist_user_id"),
        "token_blocklist",
        ["user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_token_blocklist_user_id"), table_name="token_blocklist")
    op.drop_index(op.f("ix_token_blocklist_jti"), table_name="token_blocklist")
    op.drop_index(op.f("ix_token_blocklist_expires_at"), table_name="token_blocklist")
    op.drop_table("token_blocklist")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_is_active"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
