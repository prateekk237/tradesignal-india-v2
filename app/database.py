"""Async SQLAlchemy database engine — graceful when DB not available."""

import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Railway gives postgres:// but SQLAlchemy needs postgresql+asyncpg://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Only create engine if we have a valid URL
engine = None
AsyncSessionLocal = None

if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    engine = create_async_engine(
        DATABASE_URL,
        echo=os.environ.get("DEBUG", "false").lower() == "true",
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={"timeout": 5},
    )
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


class Base(DeclarativeBase):
    pass


async def get_db():
    if AsyncSessionLocal is None:
        raise Exception("Database not configured")
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
