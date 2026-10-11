import uuid
from datetime import date

from app.core.logging import logger
from app.services.storage_service import StorageService
from app.templates.certificate_template import CertificateTemplate


class CertificateGenerationError(Exception):
    """Raised when PDF certificate rendering or persistence fails."""


class CertificateGeneratorService:
    """Service to render and persist personalized certificate PDFs."""

    def __init__(self, storage_service: StorageService | None = None) -> None:
        self.storage = storage_service or StorageService()

    def generate_certificate(
        self,
        recipient_name: str,
        event_name: str,
        completion_date: date,
        certificate_id: uuid.UUID,
    ) -> str:
        """Render a certificate PDF and store it atomically.

        Returns:
            str: The relative storage key (e.g., "certificates/<uuid>.pdf").
        """
        relative_key = f"certificates/{certificate_id}.pdf"

        # Create a temporary file for rendering
        temp_dir = self.storage.root_dir.parent / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        temp_file = temp_dir / f"tmp_{certificate_id}.pdf"

        try:
            # Render using ReportLab template
            CertificateTemplate.render(
                output=temp_file,
                recipient_name=recipient_name,
                event_name=event_name,
                completion_date=completion_date,
                certificate_id=certificate_id,
            )

            if not temp_file.exists() or temp_file.stat().st_size == 0:
                raise CertificateGenerationError("Generated PDF file is missing or empty.")

            # Atomically move to final destination in storage
            self.storage.save_file(temp_path=temp_file, relative_key=relative_key)

            logger.info(
                "Successfully generated certificate for %r (cert_id=%s, file_key=%s)",
                recipient_name,
                certificate_id,
                relative_key,
            )
            return relative_key

        except Exception as e:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            logger.error(
                "Failed to generate certificate for cert_id=%s: %s",
                certificate_id,
                e,
                exc_info=True,
            )
            raise CertificateGenerationError(f"Certificate generation failed: {e}") from e
