"""initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-10-10 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create generation_jobs table
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("event_name", sa.String(length=200), nullable=False),
        sa.Column("completion_date", sa.Date(), nullable=False),
        sa.Column("total_recipients", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("total_recipients >= 1", name="ck_generation_jobs_total_recipients"),
        sa.CheckConstraint("completed_count >= 0", name="ck_generation_jobs_completed_count"),
        sa.CheckConstraint("failed_count >= 0", name="ck_generation_jobs_failed_count"),
        sa.CheckConstraint(
            "completed_count + failed_count <= total_recipients",
            name="ck_generation_jobs_counts_sum",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'completed_with_errors', 'failed')",
            name="ck_generation_jobs_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generation_jobs"),
    )
    op.create_index(
        "ix_generation_jobs_status_created_at",
        "generation_jobs",
        ["status", "created_at"],
        unique=False,
    )

    # Create certificates table
    op.create_table(
        "certificates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_name", sa.String(length=200), nullable=True),
        sa.Column("recipient_email", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("file_key", sa.String(length=500), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_certificates_status",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["generation_jobs.id"],
            name="fk_certificates_job_id_generation_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_certificates"),
    )
    op.create_index("ix_certificates_job_id", "certificates", ["job_id"], unique=False)
    op.create_index("ix_certificates_created_at", "certificates", ["created_at"], unique=False)
    op.create_index(
        "ix_certificates_job_id_status",
        "certificates",
        ["job_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_certificates_job_id_status", table_name="certificates")
    op.drop_index("ix_certificates_created_at", table_name="certificates")
    op.drop_index("ix_certificates_job_id", table_name="certificates")
    op.drop_table("certificates")
    op.drop_index("ix_generation_jobs_status_created_at", table_name="generation_jobs")
    op.drop_table("generation_jobs")
