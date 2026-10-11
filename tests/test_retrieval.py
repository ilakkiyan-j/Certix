import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.enums import CertificateStatus, JobStatus
from app.db.models import Certificate, GenerationJob
from app.services.storage_service import StorageService
from app.templates.certificate_template import CertificateTemplate


@pytest.fixture
def storage() -> StorageService:
    return StorageService()


@pytest.mark.asyncio
async def test_get_job_status_success(async_client: AsyncClient, db_session: AsyncSession):
    """Verify GET /api/v1/jobs/{job_id} returns accurate counts and progress percentage."""
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.PROCESSING.value,
        event_name="Full Stack Bootcamp",
        completion_date=date(2026, 6, 1),
        total_recipients=4,
        completed_count=2,
        failed_count=1,
        started_at=datetime.now(UTC),
    )
    db_session.add(job)
    await db_session.commit()

    response = await async_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == str(job_id)
    assert data["status"] == "processing"
    assert data["total_recipients"] == 4
    assert data["processed"] == 3
    assert data["completed"] == 2
    assert data["failed"] == 1
    assert data["progress_percentage"] == 75.0
    assert data["started_at"] is not None
    assert data["finished_at"] is None


@pytest.mark.asyncio
async def test_get_job_status_not_found(async_client: AsyncClient):
    """Verify GET /api/v1/jobs/{job_id} returns 404 for unknown job."""
    non_existent_id = uuid.uuid4()
    response = await async_client.get(f"/api/v1/jobs/{non_existent_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "JOB_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_job_status_invalid_uuid(async_client: AsyncClient):
    """Verify GET /api/v1/jobs/{job_id} returns 422 for invalid UUID format."""
    response = await async_client.get("/api/v1/jobs/not-a-valid-uuid")
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_job_certificates_listing_and_pagination(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verify certificate listing returns paginated results with download URLs."""
    job_id = uuid.uuid4()
    job = GenerationJob(
        id=job_id,
        status=JobStatus.COMPLETED_WITH_ERRORS.value,
        event_name="Data Science Workshop",
        completion_date=date(2026, 7, 1),
        total_recipients=3,
        completed_count=2,
        failed_count=1,
    )
    c1 = Certificate(
        id=uuid.uuid4(),
        job_id=job_id,
        recipient_name="Alice Smith",
        recipient_email="alice@example.com",
        status=CertificateStatus.COMPLETED.value,
        file_key="certificates/alice.pdf",
        created_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, 10, 0, 5, tzinfo=UTC),
    )
    c2 = Certificate(
        id=uuid.uuid4(),
        job_id=job_id,
        recipient_name="Bob Jones",
        recipient_email="bob@example.com",
        status=CertificateStatus.COMPLETED.value,
        file_key="certificates/bob.pdf",
        created_at=datetime(2026, 1, 1, 10, 1, 0, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, 10, 1, 5, tzinfo=UTC),
    )
    c3 = Certificate(
        id=uuid.uuid4(),
        job_id=job_id,
        recipient_name=None,
        recipient_email="bad-email",
        status=CertificateStatus.FAILED.value,
        error_code="INVALID_RECIPIENT_DATA",
        error_message="Invalid recipient email",
        created_at=datetime(2026, 1, 1, 10, 2, 0, tzinfo=UTC),
    )
    db_session.add(job)
    db_session.add_all([c1, c2, c3])
    await db_session.commit()

    # Query page 1: limit 2, offset 0
    response = await async_client.get(f"/api/v1/jobs/{job_id}/certificates?limit=2&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == str(job_id)
    assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["results"]) == 2
    assert data["results"][0]["download_url"] == f"/api/v1/certificates/{c1.id}/download"
    assert data["results"][0]["error"] is None

    # Query page 2: limit 2, offset 2
    response2 = await async_client.get(f"/api/v1/jobs/{job_id}/certificates?limit=2&offset=2")
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2["results"]) == 1
    failed_item = data2["results"][0]
    assert failed_item["certificate_id"] == str(c3.id)
    assert failed_item["status"] == "failed"
    assert failed_item["download_url"] is None
    assert failed_item["error"]["code"] == "INVALID_RECIPIENT_DATA"


@pytest.mark.asyncio
async def test_get_job_certificates_not_found(async_client: AsyncClient):
    """Verify GET /api/v1/jobs/{job_id}/certificates returns 404 for unknown job ID."""
    non_existent_id = uuid.uuid4()
    response = await async_client.get(f"/api/v1/jobs/{non_existent_id}/certificates")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "JOB_NOT_FOUND"


@pytest.mark.asyncio
async def test_download_certificate_success(
    async_client: AsyncClient, db_session: AsyncSession, storage: StorageService
):
    """Verify GET /api/v1/certificates/{certificate_id}/download streams the PDF file."""
    job_id = uuid.uuid4()
    cert_id = uuid.uuid4()
    relative_key = f"certificates/{cert_id}.pdf"

    # Render a real physical PDF to the storage path
    temp_render = settings.CERTIFICATE_STORAGE_DIR / f"temp_{cert_id}.pdf"
    CertificateTemplate.render(
        output=temp_render,
        recipient_name="Download Recipient",
        event_name="Download Testing Event",
        completion_date=date(2026, 8, 1),
        certificate_id=cert_id,
    )
    storage.save_file(temp_path=temp_render, relative_key=relative_key)

    job = GenerationJob(
        id=job_id,
        status=JobStatus.COMPLETED.value,
        event_name="Download Testing Event",
        completion_date=date(2026, 8, 1),
        total_recipients=1,
        completed_count=1,
        failed_count=0,
    )
    cert = Certificate(
        id=cert_id,
        job_id=job_id,
        recipient_name="Download Recipient",
        recipient_email="download@example.com",
        status=CertificateStatus.COMPLETED.value,
        file_key=relative_key,
        completed_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.add(cert)
    await db_session.commit()

    try:
        response = await async_client.get(f"/api/v1/certificates/{cert_id}/download")
        assert response.status_code == 200
        assert "application/pdf" in response.headers["content-type"]
        assert f'filename="certificate_{cert_id}.pdf"' in response.headers["content-disposition"]
        assert response.content.startswith(b"%PDF-")
    finally:
        storage.delete_file(relative_key)


@pytest.mark.asyncio
async def test_download_certificate_not_found(async_client: AsyncClient):
    """Verify download returns 404 for unknown certificate ID."""
    non_existent_id = uuid.uuid4()
    response = await async_client.get(f"/api/v1/certificates/{non_existent_id}/download")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "CERTIFICATE_NOT_FOUND"


@pytest.mark.asyncio
async def test_download_certificate_not_ready_conflict(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verify download returns 409 Conflict when certificate status is pending or processing."""
    job_id = uuid.uuid4()
    cert_id = uuid.uuid4()

    job = GenerationJob(
        id=job_id,
        status=JobStatus.PROCESSING.value,
        event_name="Pending Event",
        completion_date=date(2026, 9, 1),
        total_recipients=1,
        completed_count=0,
        failed_count=0,
    )
    cert = Certificate(
        id=cert_id,
        job_id=job_id,
        recipient_name="Pending User",
        recipient_email="pending@example.com",
        status=CertificateStatus.PROCESSING.value,
    )
    db_session.add(job)
    db_session.add(cert)
    await db_session.commit()

    response = await async_client.get(f"/api/v1/certificates/{cert_id}/download")
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "CERTIFICATE_NOT_READY"


@pytest.mark.asyncio
async def test_download_certificate_failed_conflict(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verify download returns 409 Conflict when certificate status is failed."""
    job_id = uuid.uuid4()
    cert_id = uuid.uuid4()

    job = GenerationJob(
        id=job_id,
        status=JobStatus.FAILED.value,
        event_name="Failed Event",
        completion_date=date(2026, 9, 1),
        total_recipients=1,
        completed_count=0,
        failed_count=1,
    )
    cert = Certificate(
        id=cert_id,
        job_id=job_id,
        recipient_name="Failed User",
        recipient_email="failed@example.com",
        status=CertificateStatus.FAILED.value,
        error_code="CERTIFICATE_GENERATION_FAILED",
        error_message="Rendering error",
    )
    db_session.add(job)
    db_session.add(cert)
    await db_session.commit()

    response = await async_client.get(f"/api/v1/certificates/{cert_id}/download")
    assert response.status_code == 409
    data = response.json()
    assert data["error"]["code"] == "CERTIFICATE_FAILED"


@pytest.mark.asyncio
async def test_download_certificate_missing_physical_file(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Verify download returns 404 when database status is completed but physical file is absent."""
    job_id = uuid.uuid4()
    cert_id = uuid.uuid4()

    job = GenerationJob(
        id=job_id,
        status=JobStatus.COMPLETED.value,
        event_name="Missing File Event",
        completion_date=date(2026, 9, 1),
        total_recipients=1,
        completed_count=1,
        failed_count=0,
    )
    cert = Certificate(
        id=cert_id,
        job_id=job_id,
        recipient_name="Missing File User",
        recipient_email="missing@example.com",
        status=CertificateStatus.COMPLETED.value,
        file_key="certificates/does_not_exist_on_disk.pdf",
    )
    db_session.add(job)
    db_session.add(cert)
    await db_session.commit()

    response = await async_client.get(f"/api/v1/certificates/{cert_id}/download")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "FILE_NOT_FOUND"
