"""审计日志服务"""
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import AuditLog
from ..database.transactions import immediate_transaction


async def log_audit(
    session: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[int] = None,
    device_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """记录审计日志"""
    try:
        async with immediate_transaction(session):
            audit_log = AuditLog(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                user_id=user_id,
                device_id=device_id,
                details=details,
                ip_address=ip_address,
            )
            session.add(audit_log)
    except Exception as e:
        print(f"Failed to log audit: {e}")
