import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_empty_recipients_list_returns_422(async_client: AsyncClient) -> None:
    """Verify an empty recipient array is rejected with 422."""
    payload = {
        "event_name": "Test Event",
        "completion_date": "2026-10-10",
        "recipients": [],
    }
    response = await async_client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_missing_event_name_returns_422(async_client: AsyncClient) -> None:
    """Verify missing event_name returns 422."""
    payload = {
        "completion_date": "2026-10-10",
        "recipients": [
            {"name": "Alice", "email": "alice@example.com"},
        ],
    }
    response = await async_client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_whitespace_only_event_name_returns_422(async_client: AsyncClient) -> None:
    """Verify whitespace-only event_name returns 422."""
    payload = {
        "event_name": "   ",
        "completion_date": "2026-10-10",
        "recipients": [
            {"name": "Alice", "email": "alice@example.com"},
        ],
    }
    response = await async_client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_invalid_date_format_returns_422(async_client: AsyncClient) -> None:
    """Verify invalid calendar date format returns 422."""
    payload = {
        "event_name": "Test Event",
        "completion_date": "2026-99-99",
        "recipients": [
            {"name": "Alice", "email": "alice@example.com"},
        ],
    }
    response = await async_client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_malformed_json_body_returns_422(async_client: AsyncClient) -> None:
    """Verify non-JSON or malformed payload returns 422."""
    response = await async_client.post(
        "/api/v1/jobs",
        content="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
