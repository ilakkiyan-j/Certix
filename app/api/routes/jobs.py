import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi import Path as FastAPIPath
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.certificate import CertificateListResponse
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobStatusResponse
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit Bulk Certificate Generation Job",
    description=(
        "Accepts a list of recipients and creates an asynchronous certificate generation job."
    ),
)
async def create_job(
    request: JobCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> JobCreateResponse:
    """Creates a generation job and persists recipient records atomically."""
    service = JobService(db)
    return await service.create_bulk_job(request)


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Job Status and Progress",
    description=(
        "Returns the current processing status, recipient counters, progress percentage, "
        "and timestamps for the specified generation job."
    ),
)
async def get_job_status(
    job_id: Annotated[uuid.UUID, FastAPIPath(description="UUID of the bulk generation job")],
    db: AsyncSession = Depends(get_db),
) -> JobStatusResponse:
    """Retrieves status and progress metrics for a bulk generation job."""
    service = JobService(db)
    return await service.get_job_status(job_id)


@router.get(
    "/{job_id}/certificates",
    response_model=CertificateListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Certificates for Job",
    description=(
        "Returns a paginated list of certificate results for the specified job, "
        "including recipient details, individual statuses, download URLs, and error details."
    ),
)
async def get_job_certificates(
    job_id: Annotated[uuid.UUID, FastAPIPath(description="UUID of the bulk generation job")],
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Number of certificate results per page"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Offset index for pagination"),
    ] = 0,
    db: AsyncSession = Depends(get_db),
) -> CertificateListResponse:
    """Retrieves paginated certificate results for a specific job."""
    service = JobService(db)
    return await service.get_job_certificates(job_id, limit=limit, offset=offset)
