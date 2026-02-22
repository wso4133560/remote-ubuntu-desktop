"""数据库初始化和连接管理"""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from ..models.models import Base


class Database:
    """数据库管理类"""

    def __init__(self, database_url: str):
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def init_db(self) -> None:
        """初始化数据库表"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def drop_db(self) -> None:
        """删除所有数据库表"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def close(self) -> None:
        """关闭数据库连接"""
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """获取数据库会话"""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


# 全局数据库实例
_db: Database | None = None


def init_database(database_url: str) -> Database:
    """初始化全局数据库实例"""
    global _db
    _db = Database(database_url)
    return _db


def get_database() -> Database:
    """获取全局数据库实例"""
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """依赖注入：获取数据库会话"""
    db = get_database()
    async with db.session() as session:
        yield session
