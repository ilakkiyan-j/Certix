import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import CertificateStatus

if TYPE_CHECKING:
    from app.db.models.generation_job import GenerationJob


class Certificate(Base):
    """Represents an individual recipient record and certificate generation outcome."""

    __tablename__ = "certificates"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_certificates_status",
        ),
        Index("ix_certificates_job_id_status", "job_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )
    recipient_email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=CertificateStatus.PENDING.value,
        nullable=False,
    )
    file_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    job: Mapped["GenerationJob"] = relationship(
        back_populates="certificates",
    )

    def __repr__(self) -> str:
        return (
            f"<Certificate id={self.id} job_id={self.job_id} "
            f"name={self.recipient_name!r} status={self.status}>"
        )
