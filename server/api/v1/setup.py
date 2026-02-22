"""初始化向导"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.database import get_session
from ...database.transactions import immediate_transaction
from ...models.models import User
from ...auth.password import hash_password

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8)


class SetupResponse(BaseModel):
    message: str
    username: str


async def is_initialized(session: AsyncSession) -> bool:
    """检查系统是否已初始化"""
    result = await session.execute(select(User))
    return result.first() is not None


@router.get("/status")
async def setup_status(session: AsyncSession = Depends(get_session)) -> dict:
    """获取初始化状态"""
    initialized = await is_initialized(session)
    return {"initialized": initialized}


@router.post("/initialize", response_model=SetupResponse)
async def initialize(
    request: SetupRequest,
    session: AsyncSession = Depends(get_session),
) -> SetupResponse:
    """初始化系统（创建管理员账户）"""
    if await is_initialized(session):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System already initialized",
        )

    async with immediate_transaction(session):
        admin_user = User(
            username=request.username,
            password_hash=hash_password(request.password),
            is_active=True,
        )
        session.add(admin_user)

    return SetupResponse(
        message="System initialized successfully",
        username=request.username,
    )
