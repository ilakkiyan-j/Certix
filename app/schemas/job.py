import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RecipientInput(BaseModel):
    """Input payload for a single recipient."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=200, description="Recipient full name")]
    email: Annotated[
        EmailStr | str,
        Field(max_length=320, description="Recipient email address"),
    ]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Recipient name must not be empty or whitespace only")
        return trimmed


class JobCreateRequest(BaseModel):
    """Request payload to create a bulk certificate generation job."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    event_name: Annotated[
        str,
        Field(min_length=1, max_length=200, description="Event or course name"),
    ]
    completion_date: Annotated[
        date,
        Field(description="Event completion date (YYYY-MM-DD)"),
    ]
    recipients: Annotated[
        list[RecipientInput],
        Field(min_length=1, description="List of certificate recipients"),
    ]

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Event name must not be empty or whitespace only")
        return trimmed


class JobCreateResponse(BaseModel):
    """HTTP 202 Accepted response for bulk job creation."""

    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    status: str
    total_recipients: int
    completed: int
    failed: int
    status_url: str


class JobStatusResponse(BaseModel):
    """Job status and progress response."""

    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    status: str
    total_recipients: int
    processed: int
    completed: int
    failed: int
    progress_percentage: float
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
