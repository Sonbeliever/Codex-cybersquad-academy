"""add payment events table

Revision ID: 202608150005
Revises: 202608110004
Create Date: 2026-08-15 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "202608150005"
down_revision = "202608110004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_event_id", sa.String(length=128), nullable=True),
        sa.Column("reference", sa.String(length=128), nullable=True),
        sa.Column("event", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_events_provider_event_id"), "payment_events", ["provider_event_id"], unique=False)
    op.create_index(op.f("ix_payment_events_reference"), "payment_events", ["reference"], unique=False)
    op.create_index(op.f("ix_payment_events_event"), "payment_events", ["event"], unique=False)
    op.create_index(op.f("ix_payment_events_payload_hash"), "payment_events", ["payload_hash"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_payment_events_payload_hash"), table_name="payment_events")
    op.drop_index(op.f("ix_payment_events_event"), table_name="payment_events")
    op.drop_index(op.f("ix_payment_events_reference"), table_name="payment_events")
    op.drop_index(op.f("ix_payment_events_provider_event_id"), table_name="payment_events")
    op.drop_table("payment_events")
