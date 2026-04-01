"""initial

Revision ID: 62ebbec127c2
Revises:
Create Date: 2026-03-22 17:23:06.428415

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "62ebbec127c2"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create core tables: items, audit_log, llm_call_log."""
    op.create_table(
        "items",
        sa.Column("item_id", sa.Text, primary_key=True),
        sa.Column("message_id", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("extraction_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Text, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("details_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_table(
        "llm_call_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Text, nullable=True),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("prompt_version", sa.Text, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Float, nullable=False),
        sa.Column("latency_ms", sa.Float, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index(
        "idx_items_message_id",
        "items",
        ["message_id"],
        unique=True,
    )
    op.create_index(
        "idx_audit_item_id",
        "audit_log",
        ["item_id"],
    )


def downgrade() -> None:
    """Drop core tables."""
    op.drop_index("idx_audit_item_id", table_name="audit_log")
    op.drop_index("idx_items_message_id", table_name="items")
    op.drop_table("llm_call_log")
    op.drop_table("audit_log")
    op.drop_table("items")
