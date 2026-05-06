"""

Async database engine and session management.

Uses SQLAlchemy 2.0 async API.

"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from sqlalchemy.orm import DeclarativeBase

from typing import AsyncGenerator



from core.config import get_settings





class Base(DeclarativeBase):

    pass





settings = get_settings()



engine = create_async_engine(

    settings.database_url,

    echo=settings.debug,

    pool_size=20,

    max_overflow=10,

    pool_pre_ping=True,

    pool_recycle=300,

)



async_session_factory = async_sessionmaker(

    engine,

    class_=AsyncSession,

    expire_on_commit=False,

)





async def get_db() -> AsyncGenerator[AsyncSession, None]:

    """FastAPI dependency — yields an async session."""

    async with async_session_factory() as session:

        try:

            yield session

        except Exception:

            await session.rollback()

            raise

        finally:

            await session.close()
