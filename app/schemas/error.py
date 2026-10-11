from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """Detailed error object for structured API responses."""

    model_config = ConfigDict(extra="ignore")

    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    """Standard API error response wrapper."""

    model_config = ConfigDict(extra="ignore")

    error: ErrorDetail
