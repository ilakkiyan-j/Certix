import uuid

from pydantic import BaseModel, ConfigDict

from app.schemas.error import ErrorDetail


class CertificateResultItem(BaseModel):
    """Result schema for an individual certificate within a job."""

    model_config = ConfigDict(from_attributes=True)

    certificate_id: uuid.UUID
    recipient_name: str | None
    recipient_email: str | None
    status: str
    download_url: str | None = None
    error: ErrorDetail | None = None


class CertificateListResponse(BaseModel):
    """Paginated list of certificate results for a job."""

    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    total: int
    limit: int
    offset: int
    results: list[CertificateResultItem]
