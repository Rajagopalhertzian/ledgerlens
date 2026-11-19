"""Pytest configuration and fixtures."""

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Set test environment - use shared in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///file:test.db?mode=memory&cache=shared&uri=true"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["MCP_SECRET_KEY"] = "test-secret-key-for-testing-only-32bytes!!"
os.environ["LLM_API_KEY"] = "test-key"


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create test database engine using shared in-memory SQLite."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from ledgerlens.db.models import Base

    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Create test database session."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    async_session = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session
        await session.rollback()


# Initialize auth for tests
@pytest.fixture(scope="session", autouse=True)
def init_auth():
    """Initialize auth managers for tests."""
    from ledgerlens.mcp_servers.erp.approval_token import init_token_manager
    from ledgerlens.mcp_servers.erp.auth import init_auth_manager

    init_auth_manager("test-secret-key-for-testing-only-32bytes!!")
    init_token_manager("test-secret-key-for-testing-only-32bytes!!")
