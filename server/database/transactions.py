"""数据库事务管理"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """事务上下文管理器"""
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@asynccontextmanager
async def immediate_transaction(session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """立即事务上下文管理器（用于 SQLite 写操作）"""
    try:
        await session.execute(text("BEGIN IMMEDIATE"))
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


class TransactionManager:
    """事务管理器"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[AsyncSession, None]:
        """开始普通事务"""
        async with transaction(self.session) as sess:
            yield sess

    @asynccontextmanager
    async def begin_immediate(self) -> AsyncGenerator[AsyncSession, None]:
        """开始立即事务（SQLite 写操作）"""
        async with immediate_transaction(self.session) as sess:
            yield sess
