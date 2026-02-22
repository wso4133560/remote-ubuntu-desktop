"""认证 API 端点"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.database import get_session
from ...database.transactions import immediate_transaction
from ...models.models import User, RefreshToken
from ...auth.password import verify_password, hash_password
from ...auth.jwt import (
    create_access_token,
    create_refresh_token,
    verify_token,
    generate_family_id,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


async def check_account_lock(user: User) -> None:
    """检查账户是否被锁定"""
    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is locked due to too many failed login attempts",
        )


async def handle_failed_login(session: AsyncSession, user: User) -> None:
    """处理登录失败"""
    async with immediate_transaction(session):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=30)
        session.add(user)


async def handle_successful_login(session: AsyncSession, user: User) -> None:
    """处理登录成功"""
    async with immediate_transaction(session):
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = datetime.utcnow()
        session.add(user)


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    """用户登录"""
    result = await session.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    await check_account_lock(user)

    if not verify_password(request.password, user.password_hash):
        await handle_failed_login(session, user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    await handle_successful_login(session, user)

    family_id = generate_family_id()
    access_token = create_access_token({"sub": str(user.id), "username": user.username})
    refresh_token_str = create_refresh_token({"sub": str(user.id)}, family_id)

    async with immediate_transaction(session):
        refresh_token = RefreshToken(
            token_hash=hash_password(refresh_token_str),
            user_id=user.id,
            family_id=family_id,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        session.add(refresh_token)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> RefreshResponse:
    """刷新访问令牌"""
    payload = verify_token(request.refresh_token, "refresh")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = int(payload["sub"])
    family_id = payload["family_id"]

    result = await session.execute(
        select(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .where(RefreshToken.family_id == family_id)
        .where(RefreshToken.revoked == False)
    )
    stored_token = result.scalar_one_or_none()

    if not stored_token or stored_token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or revoked",
        )

    if not verify_password(request.refresh_token, stored_token.token_hash):
        async with immediate_transaction(session):
            await session.execute(
                select(RefreshToken)
                .where(RefreshToken.family_id == family_id)
                .update({"revoked": True, "revoked_at": datetime.utcnow()})
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected",
        )

    async with immediate_transaction(session):
        stored_token.revoked = True
        stored_token.revoked_at = datetime.utcnow()
        session.add(stored_token)

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()

    new_family_id = generate_family_id()
    access_token = create_access_token({"sub": str(user.id), "username": user.username})
    new_refresh_token_str = create_refresh_token({"sub": str(user.id)}, new_family_id)

    async with immediate_transaction(session):
        new_refresh_token = RefreshToken(
            token_hash=hash_password(new_refresh_token_str),
            user_id=user.id,
            family_id=new_family_id,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        session.add(new_refresh_token)

    return RefreshResponse(
        access_token=access_token,
        refresh_token=new_refresh_token_str,
    )


@router.post("/logout")
async def logout(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """用户登出"""
    payload = verify_token(request.refresh_token, "refresh")
    if not payload:
        return {"message": "Logged out"}

    family_id = payload["family_id"]

    async with immediate_transaction(session):
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.family_id == family_id)
        )
        tokens = result.scalars().all()
        for token in tokens:
            token.revoked = True
            token.revoked_at = datetime.utcnow()
            session.add(token)

    return {"message": "Logged out"}
