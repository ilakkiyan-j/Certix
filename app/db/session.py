from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Format Database URLs for async and sync engines
# Psycopg 3 supports async out of the box via postgresql+psycopg://
_async_db_url = settings.DATABASE_URL
if _async_db_url.startswith("postgresql://"):
    _async_db_url = _async_db_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Async Engine for FastAPI Request Handlers
async_engine: AsyncEngine = create_async_engine(
    _async_db_url,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Sync Engine for Background Workers
_sync_db_url = _async_db_url
if "+aiosqlite" in _sync_db_url:
    _sync_db_url = _sync_db_url.replace("+aiosqlite", "")

sync_engine = create_engine(
    _sync_db_url,
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,
)

sync_session_factory = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an isolated async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_session() -> Generator[Session, None, None]:
    """Context / generator providing a sync database session for workers."""
    session = sync_session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
