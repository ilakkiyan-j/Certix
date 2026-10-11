import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CertificateStatus, JobStatus
from app.db.models import Certificate, GenerationJob


@pytest.mark.asyncio
async def test_create_job_and_certificates_persistence(db_session: AsyncSession) -> None:
    """Verify persisting a generation job with multiple recipient certificates."""
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.QUEUED.value,
        event_name="Mastering AI Architecture",
        completion_date=date(2026, 10, 10),
        total_recipients=2,
        completed_count=0,
        failed_count=0,
    )

    cert1 = Certificate(
        id=uuid.uuid4(),
        job_id=job_id,
        recipient_name="Alice Smith",
        recipient_email="alice@example.com",
        status=CertificateStatus.PENDING.value,
    )
    cert2 = Certificate(
        id=uuid.uuid4(),
        job_id=job_id,
        recipient_name="Bob Jones",
        recipient_email="bob@example.com",
        status=CertificateStatus.PENDING.value,
    )

    db_session.add(job)
    db_session.add_all([cert1, cert2])
    await db_session.commit()

    # Query back
    stmt = select(GenerationJob).where(GenerationJob.id == job_id)
    result = await db_session.scalar(stmt)

    assert result is not None
    assert result.event_name == "Mastering AI Architecture"
    assert result.status == JobStatus.QUEUED.value
    assert result.total_recipients == 2
    assert result.created_at is not None

    # Verify relationship
    cert_stmt = select(Certificate).where(Certificate.job_id == job_id)
    certs = (await db_session.scalars(cert_stmt)).all()
    assert len(certs) == 2
    names = {c.recipient_name for c in certs}
    assert names == {"Alice Smith", "Bob Jones"}


@pytest.mark.asyncio
async def test_job_count_constraints_prevent_invalid_sums(db_session: AsyncSession) -> None:
    """Verify check constraint prevents completed_count + failed_count > total_recipients."""
    job = GenerationJob(
        id=uuid.uuid4(),
        status=JobStatus.PROCESSING.value,
        event_name="Constraint Testing",
        completion_date=date(2026, 10, 10),
        total_recipients=2,
        completed_count=2,
        failed_count=1,  # 2 + 1 = 3 > 2 (violates ck_generation_jobs_counts_sum)
    )
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_job_total_recipients_constraint(db_session: AsyncSession) -> None:
    """Verify check constraint prevents total_recipients < 1."""
    job = GenerationJob(
        id=uuid.uuid4(),
        status=JobStatus.QUEUED.value,
        event_name="Zero Recipients",
        completion_date=date(2026, 10, 10),
        total_recipients=0,  # violates total_recipients >= 1
    )
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_cascade_delete_job_removes_certificates(db_session: AsyncSession) -> None:
    """Verify deleting a job cascades and deletes its child certificates."""
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.QUEUED.value,
        event_name="Cascade Event",
        completion_date=date(2026, 10, 10),
        total_recipients=1,
    )
    cert = Certificate(
        id=uuid.uuid4(),
        job_id=job_id,
        recipient_name="Charlie Brown",
        recipient_email="charlie@example.com",
    )
    db_session.add(job)
    db_session.add(cert)
    await db_session.commit()

    # Delete job
    await db_session.delete(job)
    await db_session.commit()

    # Verify certificate is gone
    cert_result = await db_session.scalar(select(Certificate).where(Certificate.job_id == job_id))
    assert cert_result is None


@pytest.mark.asyncio
async def test_certificate_status_transitions_and_updates(db_session: AsyncSession) -> None:
    """Verify certificate transitions and metadata updates."""
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.PROCESSING.value,
        event_name="Status Flow",
        completion_date=date(2026, 10, 10),
        total_recipients=1,
    )
    cert = Certificate(
        id=uuid.uuid4(),
        job_id=job_id,
        recipient_name="Dana Scully",
        recipient_email="scully@example.com",
        status=CertificateStatus.PENDING.value,
    )
    db_session.add(job)
    db_session.add(cert)
    await db_session.commit()

    # Transition to processing
    cert.status = CertificateStatus.PROCESSING.value
    await db_session.commit()

    # Transition to completed with file_key
    cert.status = CertificateStatus.COMPLETED.value
    cert.file_key = f"certificates/{cert.id}.pdf"
    job.completed_count = 1
    job.status = JobStatus.COMPLETED.value
    await db_session.commit()

    # Verify persisted state
    updated_cert = await db_session.get(Certificate, cert.id)
    assert updated_cert is not None
    assert updated_cert.status == CertificateStatus.COMPLETED.value
    assert updated_cert.file_key == f"certificates/{cert.id}.pdf"
