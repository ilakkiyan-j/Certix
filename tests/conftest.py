import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

# Path to shared test SQLite database
TEST_DB_PATH = Path("./test_shared.db").resolve()
_test_async_url = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
_test_sync_url = f"sqlite:///{TEST_DB_PATH}"

# Set test environment variables
os.environ["APP_ENV"] = "testing"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["DATABASE_URL"] = _test_async_url

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

# Async Engine for FastAPI Test Client & Async Tests
test_async_engine = create_async_engine(
    _test_async_url,
    echo=False,
    future=True,
)


@event.listens_for(test_async_engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


test_async_session_factory = async_sessionmaker(
    bind=test_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Synchronous Engine for RQ Worker Tests (points to same DB file)
test_sync_engine = create_engine(
    _test_sync_url,
    connect_args={"check_same_thread": False},
    echo=False,
    future=True,
)


@event.listens_for(test_sync_engine, "connect")
def set_sync_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


sync_session_factory_test = sessionmaker(
    bind=test_sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Create all tables in the test database at session start and clean up at end."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink(missing_ok=True)
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_async_engine.dispose()
    test_sync_engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an isolated test database session per test with automatic rollback."""
    async with test_async_session_factory() as session:
        yield session


@pytest.fixture
def sync_db_session() -> Generator[Session, None, None]:
    """Yield an isolated sync database session for testing synchronous workers."""
    with sync_session_factory_test() as session:
        yield session


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async test client fixture using httpx with real session dependency."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_async_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
