import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi import Path as FastAPIPath
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.job_service import JobService
from app.services.storage_service import StorageService

router = APIRouter(prefix="/certificates", tags=["Certificates"])


@router.get(
    "/{certificate_id}/download",
    response_class=FileResponse,
    status_code=status.HTTP_200_OK,
    summary="Download Certificate PDF",
    description=(
        "Downloads the generated PDF certificate file for a completed certificate record. "
        "Returns HTTP 409 if the certificate is pending/processing or failed, "
        "and HTTP 404 if the certificate record or physical file is not found."
    ),
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "The binary PDF certificate file.",
        },
        404: {"description": "Certificate record or physical file not found."},
        409: {"description": "Certificate is not ready or generation failed."},
    },
)
async def download_certificate(
    certificate_id: Annotated[
        uuid.UUID, FastAPIPath(description="UUID of the individual certificate")
    ],
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Streams the generated PDF certificate as an attachment."""
    service = JobService(db)
    storage = StorageService()
    safe_path, filename = await service.get_certificate_download(certificate_id, storage)

    return FileResponse(
        path=safe_path,
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
