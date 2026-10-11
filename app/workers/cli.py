import sys

from rq import SimpleWorker, Worker

from app.core.config import settings
from app.core.logging import logger
from app.workers.queue import get_job_queue, get_redis_connection


def run_worker() -> None:
    """Run an RQ worker process listening to the configured Certix jobs queue."""
    logger.info("Starting Certix RQ Worker on queue '%s'...", settings.QUEUE_NAME)
    try:
        redis_conn = get_redis_connection()
        queue = get_job_queue(connection=redis_conn)

        # On Windows os.fork is unavailable, so RQ uses SimpleWorker
        worker_cls = SimpleWorker if sys.platform == "win32" else Worker
        worker = worker_cls([queue], connection=redis_conn)

        logger.info(
            "Certix Worker listening on Redis %s (Worker class: %s)",
            settings.REDIS_URL,
            worker_cls.__name__,
        )
        worker.work(with_scheduler=False)
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")
    except Exception as e:
        logger.critical("Worker encountered fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run_worker()
