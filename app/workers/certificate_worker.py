import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.logging import logger
from app.db.enums import CertificateStatus, JobStatus
from app.db.models import Certificate, GenerationJob
from app.db.session import sync_session_factory
from app.services.certificate_generator import CertificateGeneratorService


def process_bulk_certificate_job(
    job_id: str | uuid.UUID,
    session_factory: Any | None = None,
    generator_service: CertificateGeneratorService | None = None,
) -> None:
    """Synchronous RQ task for bulk certificate processing with fault isolation.

    Workflow:
    1. Loads the GenerationJob from the database using a sync session.
    2. Enforces idempotency (ignores jobs already in a terminal state).
    3. Transitions job to PROCESSING status.
    4. Iterates over PENDING recipients, rendering each PDF individually.
    5. Commits each recipient's COMPLETED or FAILED state independently.
    6. Reconciles final completed/failed counters and transitions the job to
       COMPLETED, COMPLETED_WITH_ERRORS, or FAILED.
    """
    parsed_job_id = uuid.UUID(str(job_id))
    logger.info("Starting bulk certificate worker task for job_id=%s", parsed_job_id)

    db_factory = session_factory or sync_session_factory
    generator = generator_service or CertificateGeneratorService()

    with db_factory() as session:
        try:
            job = session.scalar(select(GenerationJob).where(GenerationJob.id == parsed_job_id))

            if not job:
                logger.error("Job %s not found in database. Worker aborting.", parsed_job_id)
                return

            # Idempotency guard: do not re-process jobs already terminated
            terminal_statuses = {
                JobStatus.COMPLETED.value,
                JobStatus.COMPLETED_WITH_ERRORS.value,
                JobStatus.FAILED.value,
            }
            if job.status in terminal_statuses:
                logger.warning(
                    "Job %s is already in terminal status %r. Skipping execution.",
                    parsed_job_id,
                    job.status,
                )
                return

            # Transition Job to PROCESSING
            job.status = JobStatus.PROCESSING.value
            job.started_at = datetime.now(UTC)
            session.commit()
            logger.info("Job %s transitioned to PROCESSING", parsed_job_id)

            # Retrieve all certificates for this job
            certs = session.scalars(
                select(Certificate).where(Certificate.job_id == parsed_job_id)
            ).all()

            for cert in certs:
                # Only process recipients that are still pending
                if cert.status != CertificateStatus.PENDING.value:
                    continue

                # Transition individual cert to PROCESSING
                cert.status = CertificateStatus.PROCESSING.value
                session.commit()

                try:
                    # PDF Generation step
                    file_key = generator.generate_certificate(
                        recipient_name=cert.recipient_name or "",
                        event_name=job.event_name,
                        completion_date=job.completion_date,
                        certificate_id=cert.id,
                    )

                    cert.file_key = file_key
                    cert.status = CertificateStatus.COMPLETED.value
                    cert.completed_at = datetime.now(UTC)
                    cert.error_code = None
                    cert.error_message = None
                    session.commit()
                    logger.debug("Recipient cert %s completed successfully", cert.id)

                except Exception as exc:
                    logger.error(
                        "Error generating certificate %s for recipient %r: %s",
                        cert.id,
                        cert.recipient_name,
                        exc,
                    )
                    cert.status = CertificateStatus.FAILED.value
                    cert.error_code = "CERTIFICATE_GENERATION_FAILED"
                    cert.error_message = str(exc)
                    session.commit()

            # Post-processing counter reconciliation
            all_certs = session.scalars(
                select(Certificate).where(Certificate.job_id == parsed_job_id)
            ).all()

            completed_count = sum(
                1 for c in all_certs if c.status == CertificateStatus.COMPLETED.value
            )
            failed_count = sum(1 for c in all_certs if c.status == CertificateStatus.FAILED.value)

            # Determine final job status
            if completed_count == job.total_recipients:
                final_status = JobStatus.COMPLETED.value
            elif completed_count > 0 and failed_count > 0:
                final_status = JobStatus.COMPLETED_WITH_ERRORS.value
            else:
                final_status = JobStatus.FAILED.value

            job.completed_count = completed_count
            job.failed_count = failed_count
            job.status = final_status
            job.finished_at = datetime.now(UTC)
            session.commit()

            logger.info(
                "Bulk job %s finished with status %s (completed: %d, failed: %d, total: %d)",
                parsed_job_id,
                final_status,
                completed_count,
                failed_count,
                job.total_recipients,
            )

        except Exception as unhandled_err:
            logger.critical(
                "Unhandled exception in bulk worker for job %s: %s",
                parsed_job_id,
                unhandled_err,
                exc_info=True,
            )
            try:
                # Attempt to mark job as FAILED if crash occurred
                fallback_job = session.scalar(
                    select(GenerationJob).where(GenerationJob.id == parsed_job_id)
                )
                if fallback_job and fallback_job.status == JobStatus.PROCESSING.value:
                    fallback_job.status = JobStatus.FAILED.value
                    fallback_job.finished_at = datetime.now(UTC)
                    session.commit()
            except Exception as recovery_err:
                logger.error("Failed to update job status during recovery: %s", recovery_err)
            raise
