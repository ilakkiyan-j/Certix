import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.db.enums import CertificateStatus, JobStatus
from app.db.models import Certificate, GenerationJob
from app.schemas.job import JobCreateRequest, RecipientInput
from app.services.certificate_generator import (
    CertificateGenerationError,
    CertificateGeneratorService,
)
from app.services.job_service import JobService
from app.services.storage_service import StorageService
from app.workers.certificate_worker import process_bulk_certificate_job
from tests.conftest import sync_session_factory_test


@pytest.fixture
def temp_storage(tmp_path) -> StorageService:
    return StorageService(root_dir=tmp_path / "generated")


def test_worker_all_recipients_successful(temp_storage: StorageService):
    """Verify worker processes all valid recipients to COMPLETED status and creates files."""
    job_id = uuid.uuid4()
    cert_id1 = uuid.uuid4()
    cert_id2 = uuid.uuid4()

    with sync_session_factory_test() as session:
        job = GenerationJob(
            id=job_id,
            status=JobStatus.QUEUED.value,
            event_name="Cloud Architecture Masterclass",
            completion_date=date(2026, 5, 20),
            total_recipients=2,
            completed_count=0,
            failed_count=0,
        )
        c1 = Certificate(
            id=cert_id1,
            job_id=job_id,
            recipient_name="Alice Wonderland",
            recipient_email="alice@example.com",
            status=CertificateStatus.PENDING.value,
        )
        c2 = Certificate(
            id=cert_id2,
            job_id=job_id,
            recipient_name="Bob Builder",
            recipient_email="bob@example.com",
            status=CertificateStatus.PENDING.value,
        )
        session.add(job)
        session.add_all([c1, c2])
        session.commit()

    generator = CertificateGeneratorService(storage_service=temp_storage)

    # Execute worker task
    process_bulk_certificate_job(
        job_id=job_id,
        session_factory=sync_session_factory_test,
        generator_service=generator,
    )

    # Verify database state
    with sync_session_factory_test() as session:
        updated_job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
        assert updated_job.status == JobStatus.COMPLETED.value
        assert updated_job.completed_count == 2
        assert updated_job.failed_count == 0
        assert updated_job.started_at is not None
        assert updated_job.finished_at is not None

        certs = session.scalars(select(Certificate).where(Certificate.job_id == job_id)).all()
        assert len(certs) == 2
        for c in certs:
            assert c.status == CertificateStatus.COMPLETED.value
            assert c.file_key is not None
            assert c.completed_at is not None
            assert c.error_code is None
            # Verify file exists in storage
            assert temp_storage.file_exists(c.file_key)


def test_worker_partial_validation_failure(temp_storage: StorageService):
    """Verify worker handles a mix of validation-failed and valid recipients."""
    job_id = uuid.uuid4()
    cert_valid = uuid.uuid4()
    cert_invalid = uuid.uuid4()

    with sync_session_factory_test() as session:
        job = GenerationJob(
            id=job_id,
            status=JobStatus.QUEUED.value,
            event_name="Security Summit 2026",
            completion_date=date(2026, 6, 15),
            total_recipients=2,
            completed_count=0,
            failed_count=1,  # 1 failed validation at submission
        )
        c_valid = Certificate(
            id=cert_valid,
            job_id=job_id,
            recipient_name="Valid User",
            recipient_email="valid@example.com",
            status=CertificateStatus.PENDING.value,
        )
        c_invalid = Certificate(
            id=cert_invalid,
            job_id=job_id,
            recipient_name=None,
            recipient_email="invalid-email",
            status=CertificateStatus.FAILED.value,
            error_code="INVALID_RECIPIENT_DATA",
            error_message="Recipient name cannot be empty.",
        )
        session.add(job)
        session.add_all([c_valid, c_invalid])
        session.commit()

    generator = CertificateGeneratorService(storage_service=temp_storage)

    process_bulk_certificate_job(
        job_id=job_id,
        session_factory=sync_session_factory_test,
        generator_service=generator,
    )

    with sync_session_factory_test() as session:
        updated_job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
        assert updated_job.status == JobStatus.COMPLETED_WITH_ERRORS.value
        assert updated_job.completed_count == 1
        assert updated_job.failed_count == 1

        cv = session.scalar(select(Certificate).where(Certificate.id == cert_valid))
        assert cv.status == CertificateStatus.COMPLETED.value
        assert cv.file_key is not None

        ci = session.scalar(select(Certificate).where(Certificate.id == cert_invalid))
        assert ci.status == CertificateStatus.FAILED.value
        assert ci.error_code == "INVALID_RECIPIENT_DATA"


def test_worker_generation_failure_isolated(temp_storage: StorageService):
    """Verify that if one recipient fails PDF rendering, the failure is isolated."""
    job_id = uuid.uuid4()
    cert_good = uuid.uuid4()
    cert_bad = uuid.uuid4()

    with sync_session_factory_test() as session:
        job = GenerationJob(
            id=job_id,
            status=JobStatus.QUEUED.value,
            event_name="AI Workshop",
            completion_date=date(2026, 7, 10),
            total_recipients=2,
            completed_count=0,
            failed_count=0,
        )
        c_good = Certificate(
            id=cert_good,
            job_id=job_id,
            recipient_name="Good Recipient",
            recipient_email="good@example.com",
            status=CertificateStatus.PENDING.value,
        )
        c_bad = Certificate(
            id=cert_bad,
            job_id=job_id,
            recipient_name="Bad Recipient",
            recipient_email="bad@example.com",
            status=CertificateStatus.PENDING.value,
        )
        session.add(job)
        session.add_all([c_good, c_bad])
        session.commit()

    real_generator = CertificateGeneratorService(storage_service=temp_storage)
    mock_generator = MagicMock()

    def side_effect(recipient_name, event_name, completion_date, certificate_id):
        if certificate_id == cert_bad:
            raise CertificateGenerationError("Simulated font rendering crash")
        return real_generator.generate_certificate(
            recipient_name, event_name, completion_date, certificate_id
        )

    mock_generator.generate_certificate.side_effect = side_effect

    process_bulk_certificate_job(
        job_id=job_id,
        session_factory=sync_session_factory_test,
        generator_service=mock_generator,
    )

    with sync_session_factory_test() as session:
        updated_job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
        assert updated_job.status == JobStatus.COMPLETED_WITH_ERRORS.value
        assert updated_job.completed_count == 1
        assert updated_job.failed_count == 1

        cg = session.scalar(select(Certificate).where(Certificate.id == cert_good))
        assert cg.status == CertificateStatus.COMPLETED.value
        assert cg.file_key is not None

        cb = session.scalar(select(Certificate).where(Certificate.id == cert_bad))
        assert cb.status == CertificateStatus.FAILED.value
        assert cb.error_code == "CERTIFICATE_GENERATION_FAILED"
        assert "Simulated font rendering crash" in cb.error_message


def test_worker_all_generation_failures():
    """Verify that when all recipients fail PDF rendering, job status is FAILED."""
    job_id = uuid.uuid4()
    cert_id = uuid.uuid4()

    with sync_session_factory_test() as session:
        job = GenerationJob(
            id=job_id,
            status=JobStatus.QUEUED.value,
            event_name="Crash Event",
            completion_date=date(2026, 8, 1),
            total_recipients=1,
            completed_count=0,
            failed_count=0,
        )
        c = Certificate(
            id=cert_id,
            job_id=job_id,
            recipient_name="Doomed Recipient",
            recipient_email="doomed@example.com",
            status=CertificateStatus.PENDING.value,
        )
        session.add(job)
        session.add(c)
        session.commit()

    mock_generator = MagicMock()
    mock_generator.generate_certificate.side_effect = CertificateGenerationError("Disk full error")

    process_bulk_certificate_job(
        job_id=job_id,
        session_factory=sync_session_factory_test,
        generator_service=mock_generator,
    )

    with sync_session_factory_test() as session:
        updated_job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
        assert updated_job.status == JobStatus.FAILED.value
        assert updated_job.completed_count == 0
        assert updated_job.failed_count == 1


def test_worker_idempotency(temp_storage: StorageService):
    """Verify that re-running the worker on an already completed job does nothing."""
    job_id = uuid.uuid4()
    cert_id = uuid.uuid4()

    with sync_session_factory_test() as session:
        job = GenerationJob(
            id=job_id,
            status=JobStatus.COMPLETED.value,
            event_name="Already Done Event",
            completion_date=date(2026, 9, 1),
            total_recipients=1,
            completed_count=1,
            failed_count=0,
        )
        c = Certificate(
            id=cert_id,
            job_id=job_id,
            recipient_name="Finished User",
            recipient_email="finished@example.com",
            status=CertificateStatus.COMPLETED.value,
            file_key="certificates/existing.pdf",
        )
        session.add(job)
        session.add(c)
        session.commit()

    mock_generator = MagicMock()

    process_bulk_certificate_job(
        job_id=job_id,
        session_factory=sync_session_factory_test,
        generator_service=mock_generator,
    )

    mock_generator.generate_certificate.assert_not_called()


@pytest.mark.asyncio
async def test_all_invalid_submission_marks_job_failed_immediately(db_session):
    """Verify submitting a job where 100% of recipients are invalid marks job FAILED immediately."""
    service = JobService(db=db_session)
    request = JobCreateRequest(
        event_name="Validation Fail Event",
        completion_date=date(2026, 10, 1),
        recipients=[
            RecipientInput(name="User One", email="not-an-email"),
            RecipientInput(name="User Two", email="bad@invalid-domain-syntax"),
        ],
    )

    with patch("app.services.job_service.enqueue_bulk_job") as mock_enqueue:
        response = await service.create_bulk_job(request)
        assert response.status == JobStatus.FAILED.value
        assert response.total_recipients == 2
        assert response.completed == 0
        assert response.failed == 2
        mock_enqueue.assert_not_called()


def test_worker_nonexistent_job_handled_gracefully():
    """Verify that worker handles non-existent job ID without raising an uncaught exception."""
    random_id = uuid.uuid4()
    # Should log error and return cleanly
    process_bulk_certificate_job(
        job_id=random_id,
        session_factory=sync_session_factory_test,
    )
