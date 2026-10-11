import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import JobStatus

if TYPE_CHECKING:
    from app.db.models.certificate import Certificate


class GenerationJob(Base):
    """Represents a bulk certificate generation request and aggregate status."""

    __tablename__ = "generation_jobs"

    __table_args__ = (
        CheckConstraint("total_recipients >= 1", name="ck_generation_jobs_total_recipients"),
        CheckConstraint("completed_count >= 0", name="ck_generation_jobs_completed_count"),
        CheckConstraint("failed_count >= 0", name="ck_generation_jobs_failed_count"),
        CheckConstraint(
            "completed_count + failed_count <= total_recipients",
            name="ck_generation_jobs_counts_sum",
        ),
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'completed_with_errors', 'failed')",
            name="ck_generation_jobs_status",
        ),
        Index("ix_generation_jobs_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=JobStatus.QUEUED.value,
        nullable=False,
    )
    event_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    completion_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    total_recipients: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    completed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    failed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Certificate.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<GenerationJob id={self.id} status={self.status} "
            f"total={self.total_recipients} completed={self.completed_count} "
            f"failed={self.failed_count}>"
        )
