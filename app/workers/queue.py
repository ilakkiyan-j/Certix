import uuid

import redis
from rq import Queue

from app.core.config import settings
from app.core.logging import logger


def get_redis_connection() -> redis.Redis:
    """Create and return a Redis client connection."""
    return redis.Redis.from_url(settings.REDIS_URL)


def get_job_queue(connection: redis.Redis | None = None) -> Queue:
    """Return the Redis Queue instance configured for Certix bulk jobs."""
    conn = connection or get_redis_connection()
    return Queue(name=settings.QUEUE_NAME, connection=conn)


def enqueue_bulk_job(job_id: uuid.UUID | str) -> str | None:
    """Enqueue a bulk certificate generation job to Redis Queue.

    Args:
        job_id: The unique identifier of the GenerationJob.

    Returns:
        The RQ job identifier string if enqueued successfully, or None if bypassed.
    """
    job_id_str = str(job_id)

    # In testing environment, if Redis is unavailable or testing without queue, log and return
    if settings.APP_ENV == "testing":
        logger.info("Testing environment: Enqueue called for job_id=%s", job_id_str)
        return f"test-enqueued-{job_id_str}"

    try:
        from app.workers.certificate_worker import process_bulk_certificate_job

        redis_conn = get_redis_connection()
        queue = get_job_queue(connection=redis_conn)
        rq_job = queue.enqueue(
            process_bulk_certificate_job,
            job_id_str,
            job_timeout="1h",
            result_ttl=86400,  # Keep result in redis for 24h
            failure_ttl=86400 * 7,  # Keep failure info for 7 days
        )
        logger.info(
            "Enqueued job_id=%s to Redis Queue '%s' (rq_job_id=%s)",
            job_id_str,
            settings.QUEUE_NAME,
            rq_job.id,
        )
        return rq_job.id
    except Exception as e:
        logger.error(
            "Failed to enqueue bulk job_id=%s to Redis: %s",
            job_id_str,
            e,
            exc_info=True,
        )
        # Note: Do not raise here to prevent rolling back the already-committed HTTP response,
        # but the failure is logged and can be retried by an admin/recovery process.
        return None
