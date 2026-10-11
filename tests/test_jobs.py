import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CertificateStatus, JobStatus
from app.db.models import Certificate, GenerationJob


@pytest.mark.asyncio
async def test_create_bulk_job_success(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify submitting a valid bulk job returns 202 and creates records in the database."""
    payload = {
        "event_name": "AI Systems Engineering 2026",
        "completion_date": "2026-10-10",
        "recipients": [
            {"name": "Arun Kumar", "email": "arun@example.com"},
            {"name": "Priya Sharma", "email": "priya@example.com"},
        ],
    }

    response = await async_client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()

    assert "job_id" in data
    job_id = uuid.UUID(data["job_id"])
    assert data["status"] == "queued"
    assert data["total_recipients"] == 2
    assert data["completed"] == 0
    assert data["failed"] == 0
    assert data["status_url"] == f"/api/v1/jobs/{job_id}"

    # Verify persisted job in DB
    job = await db_session.get(GenerationJob, job_id)
    assert job is not None
    assert job.event_name == "AI Systems Engineering 2026"
    assert job.status == JobStatus.QUEUED.value
    assert job.total_recipients == 2
    assert job.completed_count == 0
    assert job.failed_count == 0

    # Verify persisted certificates
    stmt = select(Certificate).where(Certificate.job_id == job_id)
    certs = (await db_session.scalars(stmt)).all()
    assert len(certs) == 2
    for cert in certs:
        assert cert.status == CertificateStatus.PENDING.value
        assert cert.file_key is None


@pytest.mark.asyncio
async def test_create_bulk_job_with_unicode_and_whitespace(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify Unicode names and surrounding whitespace are normalized and handled safely."""
    payload = {
        "event_name": "   Deep Learning Certification   ",
        "completion_date": "2026-10-10",
        "recipients": [
            {"name": "  José María González  ", "email": "jose@example.com"},
            {"name": "李小龙 (Bruce Lee)", "email": "bruce@example.com"},
        ],
    }

    response = await async_client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()
    job_id = uuid.UUID(data["job_id"])

    job = await db_session.get(GenerationJob, job_id)
    assert job is not None
    assert job.event_name == "Deep Learning Certification"

    stmt = select(Certificate).where(Certificate.job_id == job_id)
    certs = (await db_session.scalars(stmt)).all()
    names = {c.recipient_name for c in certs}
    assert "José María González" in names
    assert "李小龙 (Bruce Lee)" in names


@pytest.mark.asyncio
async def test_create_bulk_job_mixed_recipient_validation_isolation(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify that an invalid recipient email is marked failed without blocking valid recipients."""
    payload = {
        "event_name": "Cloud Architecture Workshop",
        "completion_date": "2026-10-10",
        "recipients": [
            {"name": "Valid Recipient", "email": "valid@example.com"},
            {"name": "Invalid Recipient", "email": "not-an-email"},
        ],
    }

    response = await async_client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()

    assert data["total_recipients"] == 2
    assert data["failed"] == 1
    assert data["completed"] == 0

    job_id = uuid.UUID(data["job_id"])
    stmt = select(Certificate).where(Certificate.job_id == job_id)
    certs = (await db_session.scalars(stmt)).all()
    assert len(certs) == 2

    valid_cert = next(c for c in certs if c.recipient_name == "Valid Recipient")
    assert valid_cert.status == CertificateStatus.PENDING.value
    assert valid_cert.error_code is None

    invalid_cert = next(c for c in certs if c.recipient_name == "Invalid Recipient")
    assert invalid_cert.status == CertificateStatus.FAILED.value
    assert invalid_cert.error_code == "INVALID_RECIPIENT_DATA"
    assert "Invalid recipient email address" in (invalid_cert.error_message or "")
