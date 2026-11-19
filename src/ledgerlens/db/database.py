"""Database connection and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from .models import Base


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self, database_url: str, echo: bool = False):
        # SQLite doesn't support pool_size/max_overflow, use NullPool for SQLite
        is_sqlite = database_url.startswith("sqlite")
        # Check if using shared in-memory SQLite (requires keeping a connection open)
        is_shared_memory = is_sqlite and ("cache=shared" in database_url)

        engine_kwargs: dict[str, object] = {"echo": echo, "pool_pre_ping": True}

        if is_sqlite:
            if is_shared_memory:
                # For shared in-memory, we need a persistent connection pool
                # Use StaticPool (single connection) to keep the database alive
                from sqlalchemy.pool import StaticPool

                engine_kwargs["poolclass"] = StaticPool
                engine_kwargs["connect_args"] = {"uri": True, "check_same_thread": False}
            else:
                engine_kwargs["poolclass"] = NullPool
                if "?uri=true" in database_url or "&uri=true" in database_url:
                    engine_kwargs["connect_args"] = {"uri": True}
        else:
            engine_kwargs["pool_size"] = 10
            engine_kwargs["max_overflow"] = 20

        self.engine: AsyncEngine = create_async_engine(database_url, **engine_kwargs)
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

    async def init_db(self) -> None:
        """Create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_db(self) -> None:
        """Drop all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self) -> None:
        """Close the engine."""
        await self.engine.dispose()


# Global database manager instance
_db_manager: DatabaseManager | None = None


def get_db_manager() -> DatabaseManager:
    """Get the global database manager."""
    global _db_manager
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call init_db_manager() first.")
    return _db_manager


async def init_db_manager(database_url: str, echo: bool = False) -> DatabaseManager:
    """Initialize the global database manager."""
    global _db_manager
    _db_manager = DatabaseManager(database_url, echo)
    return _db_manager


async def close_db_manager() -> None:
    """Close the global database manager."""
    global _db_manager
    if _db_manager is not None:
        await _db_manager.close()
        _db_manager = None


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session from the global manager."""
    manager = get_db_manager()
    async with manager.session() as session:
        yield session


async def init_db(database_url: str | None = None, echo: bool = False) -> None:
    """Initialize database - create all tables."""
    import os

    if database_url is None:
        database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    manager = await init_db_manager(database_url, echo)
    await manager.init_db()


async def drop_db(database_url: str | None = None) -> None:
    """Drop all tables."""
    import os

    if database_url is None:
        database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    manager = await init_db_manager(database_url, False)
    await manager.drop_db()
