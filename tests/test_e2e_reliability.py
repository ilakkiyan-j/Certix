import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.enums import CertificateStatus, JobStatus
from app.db.models import Certificate, GenerationJob
from app.schemas.job import RecipientInput
from app.services.certificate_generator import (
    CertificateGenerationError,
    CertificateGeneratorService,
)
from app.services.storage_service import StorageService
from app.workers.certificate_worker import process_bulk_certificate_job
from tests.conftest import sync_session_factory_test


@pytest.fixture
def storage() -> StorageService:
    return StorageService()


@pytest.mark.asyncio
async def test_e2e_successful_bulk_flow(async_client: AsyncClient, storage: StorageService):
    """End-to-End Test: Full submission, worker processing, progress query, and PDF download."""
    recipients = [
        RecipientInput(name="María José García", email="maria.garcia@example.com"),
        RecipientInput(name="François René", email="francois.rene@example.org"),
        RecipientInput(name="Akira Tanaka", email="akira.tanaka@example.jp"),
        RecipientInput(name="Alexander Bartholomew Montgomery III", email="alexander@example.com"),
        RecipientInput(name="Dr. Jane Doe, PhD", email="jane.doe@university.edu"),
    ]

    payload = {
        "event_name": "International AI & Systems Symposium 2026",
        "completion_date": "2026-10-15",
        "recipients": [r.model_dump() for r in recipients],
    }

    # Step 1: Submit bulk job
    submit_response = await async_client.post("/api/v1/jobs", json=payload)
    assert submit_response.status_code == 202
    submit_data = submit_response.json()
    job_id = uuid.UUID(submit_data["job_id"])
    assert submit_data["status"] == "queued"
    assert submit_data["total_recipients"] == 5
    assert submit_data["completed"] == 0
    assert submit_data["failed"] == 0
    assert submit_data["status_url"] == f"/api/v1/jobs/{job_id}"

    # Step 2: Background worker processes the job
    process_bulk_certificate_job(
        job_id=job_id,
        session_factory=sync_session_factory_test,
    )

    # Step 3: Verify Job Status via API
    status_response = await async_client.get(f"/api/v1/jobs/{job_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["status"] == "completed"
    assert status_data["total_recipients"] == 5
    assert status_data["processed"] == 5
    assert status_data["completed"] == 5
    assert status_data["failed"] == 0
    assert status_data["progress_percentage"] == 100.0
    assert status_data["started_at"] is not None
    assert status_data["finished_at"] is not None

    # Step 4: List certificates via API
    list_response = await async_client.get(f"/api/v1/jobs/{job_id}/certificates?limit=10")
    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["total"] == 5
    assert len(list_data["results"]) == 5

    # Step 5: Download and verify every generated PDF
    created_file_keys = []
    try:
        for item in list_data["results"]:
            assert item["status"] == "completed"
            assert item["download_url"] is not None
            assert item["error"] is None

            download_response = await async_client.get(item["download_url"])
            assert download_response.status_code == 200
            assert "application/pdf" in download_response.headers["content-type"]
            assert download_response.content.startswith(b"%PDF-")
            assert b"%%EOF" in download_response.content
            assert len(download_response.content) > 1000  # Non-trivial PDF size

            cert_id = item["certificate_id"]
            created_file_keys.append(f"certificates/{cert_id}.pdf")
    finally:
        for key in created_file_keys:
            storage.delete_file(key)


@pytest.mark.asyncio
async def test_e2e_partial_failure_flow(async_client: AsyncClient, storage: StorageService):
    """End-to-End Test: Job with upfront validation error and simulated generation crash."""
    recipients = [
        {"name": "Good Recipient One", "email": "good1@example.com"},
        {"name": "Crash Recipient Two", "email": "crash2@example.com"},
        {"name": "Bad Email Recipient", "email": "invalid-email-format-without-at"},
    ]

    payload = {
        "event_name": "Resilience & Fault Isolation Workshop",
        "completion_date": "2026-11-01",
        "recipients": recipients,
    }

    # Step 1: Submit job
    submit_response = await async_client.post("/api/v1/jobs", json=payload)
    assert submit_response.status_code == 202
    submit_data = submit_response.json()
    job_id = uuid.UUID(submit_data["job_id"])
    assert submit_data["status"] == "queued"
    assert submit_data["total_recipients"] == 3
    assert submit_data["failed"] == 1  # 1 failed upfront validation

    # Step 2: Background worker runs with mock crash on Recipient Two
    real_generator = CertificateGeneratorService(storage_service=storage)
    mock_generator = MagicMock()

    def mock_render(recipient_name, event_name, completion_date, certificate_id):
        if "Crash" in recipient_name:
            raise CertificateGenerationError("Simulated canvas render crash")
        return real_generator.generate_certificate(
            recipient_name, event_name, completion_date, certificate_id
        )

    mock_generator.generate_certificate.side_effect = mock_render

    process_bulk_certificate_job(
        job_id=job_id,
        session_factory=sync_session_factory_test,
        generator_service=mock_generator,
    )

    # Step 3: Verify Job Status
    status_response = await async_client.get(f"/api/v1/jobs/{job_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["status"] == "completed_with_errors"
    assert status_data["total_recipients"] == 3
    assert status_data["processed"] == 3
    assert status_data["completed"] == 1
    assert status_data["failed"] == 2
    assert status_data["progress_percentage"] == 100.0

    # Step 4: Verify certificate listing details
    list_response = await async_client.get(f"/api/v1/jobs/{job_id}/certificates")
    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["total"] == 3

    success_items = [c for c in list_data["results"] if c["status"] == "completed"]
    failed_items = [c for c in list_data["results"] if c["status"] == "failed"]

    assert len(success_items) == 1
    assert len(failed_items) == 2

    # Verify error codes
    error_codes = {f["error"]["code"] for f in failed_items}
    assert "INVALID_RECIPIENT_DATA" in error_codes
    assert "CERTIFICATE_GENERATION_FAILED" in error_codes

    # Step 5: Test download responses
    # Success item should download successfully
    good_cert_id = success_items[0]["certificate_id"]
    try:
        good_download = await async_client.get(f"/api/v1/certificates/{good_cert_id}/download")
        assert good_download.status_code == 200
        assert good_download.content.startswith(b"%PDF-")
    finally:
        storage.delete_file(f"certificates/{good_cert_id}.pdf")

    # Failed items should return 409 Conflict
    for failed_cert in failed_items:
        fc_id = failed_cert["certificate_id"]
        fc_download = await async_client.get(f"/api/v1/certificates/{fc_id}/download")
        assert fc_download.status_code == 409
        assert fc_download.json()["error"]["code"] == "CERTIFICATE_FAILED"


@pytest.mark.asyncio
async def test_concurrent_bulk_jobs_isolation(async_client: AsyncClient, storage: StorageService):
    """Verify that multiple concurrently processed jobs maintain strictly isolated state."""
    job_ids = []
    file_keys_to_clean = []

    try:
        # Submit 3 distinct jobs
        for i in range(1, 4):
            payload = {
                "event_name": f"Concurrent Event {i}",
                "completion_date": f"2026-10-0{i}",
                "recipients": [
                    {"name": f"User {i}-A", "email": f"user{i}a@example.com"},
                    {"name": f"User {i}-B", "email": f"user{i}b@example.com"},
                ],
            }
            res = await async_client.post("/api/v1/jobs", json=payload)
            assert res.status_code == 202
            job_ids.append(uuid.UUID(res.json()["job_id"]))

        # Process all 3 jobs
        for jid in job_ids:
            process_bulk_certificate_job(
                job_id=jid,
                session_factory=sync_session_factory_test,
            )

        # Verify each job is independently completed
        for jid in job_ids:
            status_res = await async_client.get(f"/api/v1/jobs/{jid}")
            assert status_res.status_code == 200
            sdata = status_res.json()
            assert sdata["status"] == "completed"
            assert sdata["completed"] == 2
            assert sdata["failed"] == 0

            certs_res = await async_client.get(f"/api/v1/jobs/{jid}/certificates")
            assert certs_res.status_code == 200
            cdata = certs_res.json()
            assert len(cdata["results"]) == 2
            for c in cdata["results"]:
                file_keys_to_clean.append(f"certificates/{c['certificate_id']}.pdf")

    finally:
        for key in file_keys_to_clean:
            storage.delete_file(key)


def test_worker_crash_recovery_resilience():
    """Verify worker sets job status to FAILED when an unhandled top-level exception occurs."""
    job_id = uuid.uuid4()
    with sync_session_factory_test() as session:
        job = GenerationJob(
            id=job_id,
            status=JobStatus.QUEUED.value,
            event_name="Crash Recovery Event",
            completion_date=date(2026, 12, 1),
            total_recipients=1,
            completed_count=0,
            failed_count=0,
        )
        c = Certificate(
            id=uuid.uuid4(),
            job_id=job_id,
            recipient_name="Crash Target",
            recipient_email="crash@example.com",
            status=CertificateStatus.PENDING.value,
        )
        session.add(job)
        session.add(c)
        session.commit()

    # Mock generator to raise an unexpected base Exception (not CertificateGenerationError)
    mock_gen = MagicMock()
    mock_gen.generate_certificate.side_effect = SystemError("Catastrophic hardware fault")

    process_bulk_certificate_job(
        job_id=job_id,
        session_factory=sync_session_factory_test,
        generator_service=mock_gen,
    )

    with sync_session_factory_test() as session:
        updated_job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
        assert updated_job.status == JobStatus.FAILED.value
        assert updated_job.failed_count == 1
        assert updated_job.finished_at is not None


def test_pdf_binary_structural_integrity(storage: StorageService):
    """Verify that generated PDF contains valid PDF standard structural markers."""
    cert_id = uuid.uuid4()
    key = f"certificates/{cert_id}.pdf"
    generator = CertificateGeneratorService(storage_service=storage)

    try:
        relative_key = generator.generate_certificate(
            recipient_name="Structural Verification User",
            event_name="PDF Standard Verification Course",
            completion_date=date(2026, 10, 10),
            certificate_id=cert_id,
        )
        assert relative_key == key
        file_path = storage.resolve_safe_path(relative_key)

        with open(file_path, "rb") as f:
            pdf_bytes = f.read()

        # Check standard PDF elements
        assert pdf_bytes.startswith(b"%PDF-")
        assert b"/Type /Catalog" in pdf_bytes or b"/Catalog" in pdf_bytes
        assert b"/Pages" in pdf_bytes
        assert b"%%EOF" in pdf_bytes
        assert len(pdf_bytes) > 2000

    finally:
        storage.delete_file(key)
