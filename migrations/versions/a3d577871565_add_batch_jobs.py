"""add_batch_jobs

Revision ID: a3d577871565
Revises: 62ebbec127c2
Create Date: 2026-03-22 17:35:59.643556

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a3d577871565"
down_revision: Union[str, Sequence[str], None] = "62ebbec127c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add batch_jobs table for async batch processing progress tracking."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_jobs (
          job_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          total INTEGER NOT NULL,
          processed INTEGER NOT NULL DEFAULT 0,
          succeeded INTEGER NOT NULL DEFAULT 0,
          failed_count INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )


def downgrade() -> None:
    """Drop batch_jobs table."""
    op.execute("DROP TABLE IF EXISTS batch_jobs")
