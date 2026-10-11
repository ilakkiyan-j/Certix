import uuid
from datetime import date
from pathlib import Path

import pytest

from app.services.certificate_generator import (
    CertificateGeneratorService,
)
from app.services.storage_service import StorageService


@pytest.fixture
def temp_storage(tmp_path: Path) -> StorageService:
    """Provides an isolated StorageService rooted in a pytest tmp_path directory."""
    return StorageService(root_dir=tmp_path / "storage" / "generated")


def test_generate_certificate_creates_valid_pdf(temp_storage: StorageService) -> None:
    """Verify certificate generation creates an actual PDF file with valid header signature."""
    generator = CertificateGeneratorService(storage_service=temp_storage)
    cert_id = uuid.uuid4()
    recipient_name = "Sarah Connor"
    event_name = "Cybersecurity Leadership Summit 2026"
    completion_date = date(2026, 10, 10)

    file_key = generator.generate_certificate(
        recipient_name=recipient_name,
        event_name=event_name,
        completion_date=completion_date,
        certificate_id=cert_id,
    )

    assert file_key == f"certificates/{cert_id}.pdf"
    assert temp_storage.file_exists(file_key) is True

    full_path = temp_storage.resolve_safe_path(file_key)
    assert full_path.exists()
    assert full_path.stat().st_size > 1000  # ReportLab PDF is typically ~2-4 KB

    # Validate PDF signature (starts with %PDF-)
    with open(full_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_generate_certificate_with_long_and_unicode_name(temp_storage: StorageService) -> None:
    """Verify handling of long names and Unicode characters."""
    generator = CertificateGeneratorService(storage_service=temp_storage)
    cert_id = uuid.uuid4()
    long_unicode_name = "Dr. María-José Hernández-Hernández de la Vega III"

    file_key = generator.generate_certificate(
        recipient_name=long_unicode_name,
        event_name="Advanced Neural Architecture & Distributed Systems",
        completion_date=date(2026, 10, 10),
        certificate_id=cert_id,
    )

    assert temp_storage.file_exists(file_key) is True
    full_path = temp_storage.resolve_safe_path(file_key)
    with open(full_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_storage_service_prevents_path_traversal(temp_storage: StorageService) -> None:
    """Verify StorageService rejects path traversal keys attempting to escape root directory."""
    with pytest.raises(ValueError, match="resolves outside storage root"):
        temp_storage.resolve_safe_path("../../etc/passwd")

    with pytest.raises(ValueError, match="resolves outside storage root"):
        temp_storage.resolve_safe_path("../secret.key")


def test_storage_service_file_exists_and_deletion(
    temp_storage: StorageService, tmp_path: Path
) -> None:
    """Verify file existence check and deletion operations."""
    dummy_temp = tmp_path / "dummy.txt"
    dummy_temp.write_text("sample content")

    rel_key = "subfolder/test_file.txt"
    saved_path = temp_storage.save_file(dummy_temp, rel_key)
    assert saved_path.exists()
    assert temp_storage.file_exists(rel_key) is True

    # Delete
    deleted = temp_storage.delete_file(rel_key)
    assert deleted is True
    assert temp_storage.file_exists(rel_key) is False
    assert not saved_path.exists()

    # Deleting non-existent file returns False safely
    assert temp_storage.delete_file("nonexistent.pdf") is False
