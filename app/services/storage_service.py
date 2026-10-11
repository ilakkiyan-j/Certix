import os
import shutil
from pathlib import Path

from app.core.config import settings
from app.core.logging import logger


class InvalidPathError(ValueError):
    """Raised when a storage path violates the storage root directory jail."""


class StorageService:
    """Manages file persistence, atomic writes, and safe path resolution."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = (root_dir or settings.CERTIFICATE_STORAGE_DIR).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def resolve_safe_path(self, relative_key: str) -> Path:
        """Resolve a relative key and ensure it stays within root_dir (no path traversal)."""
        clean_key = relative_key.lstrip("/\\")
        candidate = (self.root_dir / clean_key).resolve()

        # Path traversal guard: candidate must start with root_dir
        if not str(candidate).startswith(str(self.root_dir)):
            logger.error("Security violation: Path traversal attempt with key %r", relative_key)
            raise InvalidPathError(
                f"Invalid file key: '{relative_key}' resolves outside storage root."
            )

        return candidate

    def save_file(self, temp_path: Path, relative_key: str) -> Path:
        """Atomically move a temporary file to its final destination key."""
        target_path = self.resolve_safe_path(relative_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic replacement where supported by OS
        try:
            os.replace(temp_path, target_path)
        except OSError:
            # Fallback for cross-device filesystem moves
            shutil.move(str(temp_path), str(target_path))

        logger.debug("Safely saved file to %s", target_path)
        return target_path

    def file_exists(self, relative_key: str) -> bool:
        """Check if a file exists at the given relative key."""
        try:
            path = self.resolve_safe_path(relative_key)
            return path.is_file()
        except ValueError:
            return False

    def delete_file(self, relative_key: str) -> bool:
        """Delete a file if it exists."""
        try:
            path = self.resolve_safe_path(relative_key)
            if path.is_file():
                path.unlink()
                logger.debug("Deleted file at %s", path)
                return True
            return False
        except ValueError:
            return False
