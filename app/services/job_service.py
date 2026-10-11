import uuid
from datetime import UTC, datetime
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.enums import CertificateStatus, JobStatus
from app.db.models import Certificate, GenerationJob
from app.schemas.certificate import CertificateListResponse, CertificateResultItem
from app.schemas.error import ErrorDetail
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobStatusResponse
from app.services.storage_service import InvalidPathError, StorageService
from app.workers.queue import enqueue_bulk_job


class JobService:
    """Service for orchestrating bulk generation jobs and recipient lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_bulk_job(self, request: JobCreateRequest) -> JobCreateResponse:
        """Create a bulk generation job and its individual recipient records atomically.

        Validates each recipient individually:
        - Valid recipients are saved with status PENDING.
        - Malformed recipient entries are recorded as FAILED with an explanatory error_code,
          ensuring isolation so valid recipients are never blocked.
        """
        job_id = uuid.uuid4()
        initial_failed_count = 0
        certificates: list[Certificate] = []

        for recipient in request.recipients:
            cert_id = uuid.uuid4()
            name = recipient.name.strip() if recipient.name else ""
            raw_email = str(recipient.email).strip() if recipient.email else ""

            # Evaluate recipient validity
            is_valid = True
            error_code: str | None = None
            error_message: str | None = None
            validated_email = raw_email

            if not name:
                is_valid = False
                error_code = "INVALID_RECIPIENT_DATA"
                error_message = "Recipient name cannot be empty."
            else:
                try:
                    valid = validate_email(raw_email, check_deliverability=False)
                    validated_email = valid.normalized
                except EmailNotValidError as e:
                    is_valid = False
                    error_code = "INVALID_RECIPIENT_DATA"
                    error_message = f"Invalid recipient email address: {e}"

            if is_valid:
                cert_status = CertificateStatus.PENDING.value
            else:
                cert_status = CertificateStatus.FAILED.value
                initial_failed_count += 1
                logger.warning(
                    "Recipient validation failed for cert_id=%s in job_id=%s: %s",
                    cert_id,
                    job_id,
                    error_message,
                )

            certificates.append(
                Certificate(
                    id=cert_id,
                    job_id=job_id,
                    recipient_name=name if name else None,
                    recipient_email=validated_email if validated_email else None,
                    status=cert_status,
                    error_code=error_code,
                    error_message=error_message,
                )
            )

        # Check if all recipients failed validation on submission
        has_valid_recipients = initial_failed_count < len(request.recipients)
        initial_job_status = (
            JobStatus.QUEUED.value if has_valid_recipients else JobStatus.FAILED.value
        )
        finished_at = None if has_valid_recipients else datetime.now(UTC)

        job = GenerationJob(
            id=job_id,
            status=initial_job_status,
            event_name=request.event_name,
            completion_date=request.completion_date,
            total_recipients=len(request.recipients),
            completed_count=0,
            failed_count=initial_failed_count,
            finished_at=finished_at,
        )

        self.db.add(job)
        self.db.add_all(certificates)
        await self.db.commit()
        await self.db.refresh(job)

        logger.info(
            "Created bulk job %s (total: %d, pending: %d, failed_validation: %d, status: %s)",
            job.id,
            job.total_recipients,
            job.total_recipients - initial_failed_count,
            initial_failed_count,
            job.status,
        )

        # Enqueue background processing if there are valid recipients
        if has_valid_recipients:
            enqueue_bulk_job(job.id)

        return JobCreateResponse(
            job_id=job.id,
            status=job.status,
            total_recipients=job.total_recipients,
            completed=job.completed_count,
            failed=job.failed_count,
            status_url=f"/api/v1/jobs/{job.id}",
        )

    async def get_job_status(self, job_id: uuid.UUID) -> JobStatusResponse:
        """Fetch status, progress counters, and percentage for a generation job."""
        job = await self.db.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "JOB_NOT_FOUND",
                        "message": f"Job with ID '{job_id}' was not found.",
                    }
                },
            )

        processed = job.completed_count + job.failed_count
        progress_percentage = (
            round((processed / job.total_recipients) * 100.0, 2)
            if job.total_recipients > 0
            else 0.0
        )

        return JobStatusResponse(
            job_id=job.id,
            status=job.status,
            total_recipients=job.total_recipients,
            processed=processed,
            completed=job.completed_count,
            failed=job.failed_count,
            progress_percentage=progress_percentage,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    async def get_job_certificates(
        self,
        job_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> CertificateListResponse:
        """Fetch paginated certificate results for a specific job."""
        job = await self.db.scalar(select(GenerationJob).where(GenerationJob.id == job_id))
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "JOB_NOT_FOUND",
                        "message": f"Job with ID '{job_id}' was not found.",
                    }
                },
            )

        total_count = (
            await self.db.scalar(
                select(func.count(Certificate.id)).where(Certificate.job_id == job_id)
            )
            or 0
        )

        query = (
            select(Certificate)
            .where(Certificate.job_id == job_id)
            .order_by(Certificate.created_at.asc(), Certificate.id.asc())
            .limit(limit)
            .offset(offset)
        )
        certs = (await self.db.scalars(query)).all()

        results: list[CertificateResultItem] = []
        for c in certs:
            download_url = (
                f"/api/v1/certificates/{c.id}/download"
                if c.status == CertificateStatus.COMPLETED.value and c.file_key
                else None
            )
            error = (
                ErrorDetail(
                    code=c.error_code or "UNKNOWN_ERROR",
                    message=c.error_message or "An unexpected error occurred.",
                )
                if c.status == CertificateStatus.FAILED.value
                else None
            )

            results.append(
                CertificateResultItem(
                    certificate_id=c.id,
                    recipient_name=c.recipient_name,
                    recipient_email=c.recipient_email,
                    status=c.status,
                    download_url=download_url,
                    error=error,
                )
            )

        return CertificateListResponse(
            job_id=job.id,
            total=total_count,
            limit=limit,
            offset=offset,
            results=results,
        )

    async def get_certificate_download(
        self,
        certificate_id: uuid.UUID,
        storage: StorageService,
    ) -> tuple[Path, str]:
        """Fetch and validate a certificate file for download.

        Returns:
            tuple[Path, str]: A tuple of (resolved safe Path, suggested filename).
        """
        cert = await self.db.scalar(select(Certificate).where(Certificate.id == certificate_id))
        if not cert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "CERTIFICATE_NOT_FOUND",
                        "message": f"Certificate with ID '{certificate_id}' was not found.",
                    }
                },
            )

        if cert.status in (CertificateStatus.PENDING.value, CertificateStatus.PROCESSING.value):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "CERTIFICATE_NOT_READY",
                        "message": (
                            f"Certificate is in '{cert.status}' state and has not been generated."
                        ),
                    }
                },
            )

        if cert.status == CertificateStatus.FAILED.value:
            err_msg = cert.error_message or "Unknown error"
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": {
                        "code": "CERTIFICATE_FAILED",
                        "message": f"Certificate generation failed: {err_msg}",
                    }
                },
            )

        if not cert.file_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": "Certificate file record is missing.",
                    }
                },
            )

        try:
            safe_path = storage.resolve_safe_path(cert.file_key)
        except InvalidPathError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": {
                        "code": "INVALID_FILE_PATH",
                        "message": f"Invalid certificate storage path: {e}",
                    }
                },
            ) from e

        if not safe_path.exists() or not safe_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "FILE_NOT_FOUND",
                        "message": "The generated certificate file was not found in storage.",
                    }
                },
            )

        return safe_path, f"certificate_{cert.id}.pdf"
