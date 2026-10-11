import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    """Configure structured, clean application logging."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    # Silence overly verbose external loggers if needed
    logging.getLogger("uvicorn.access").setLevel(level)


logger = logging.getLogger("certix")
