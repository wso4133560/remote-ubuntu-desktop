"""设备分组和权限管理 API"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ...database.database import get_session
from ...models.models import DeviceGroup, GroupPermission, Device, User
from ...auth.jwt import get_current_user

router = APIRouter(prefix="/groups", tags=["groups"])


class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None


class GroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    device_count: int

    class Config:
        from_attributes = True


class PermissionCreate(BaseModel):
    user_id: int
    can_view: bool = True
    can_control: bool = False
    can_transfer_files: bool = False


class PermissionResponse(BaseModel):
    id: int
    user_id: int
    username: str
    can_view: bool
    can_control: bool
    can_transfer_files: bool

    class Config:
        from_attributes = True


@router.post("/", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_data: GroupCreate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """创建设备分组"""
    existing = db.query(DeviceGroup).filter(DeviceGroup.name == group_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Group name already exists"
        )

    group = DeviceGroup(
        name=group_data.name,
        description=group_data.description
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        device_count=0
    )


@router.get("/", response_model=List[GroupResponse])
async def list_groups(
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取分组列表"""
    groups = db.query(DeviceGroup).all()

    return [
        GroupResponse(
            id=g.id,
            name=g.name,
            description=g.description,
            device_count=len(g.devices)
        )
        for g in groups
    ]


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取分组详情"""
    group = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        device_count=len(group.devices)
    )


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """删除分组"""
    group = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    db.delete(group)
    db.commit()


@router.post("/{group_id}/permissions", response_model=PermissionResponse, status_code=status.HTTP_201_CREATED)
async def add_permission(
    group_id: int,
    perm_data: PermissionCreate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """添加分组权限"""
    group = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    user = db.query(User).filter(User.id == perm_data.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    existing = db.query(GroupPermission).filter(
        GroupPermission.group_id == group_id,
        GroupPermission.user_id == perm_data.user_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Permission already exists"
        )

    permission = GroupPermission(
        group_id=group_id,
        user_id=perm_data.user_id,
        can_view=perm_data.can_view,
        can_control=perm_data.can_control,
        can_transfer_files=perm_data.can_transfer_files
    )
    db.add(permission)
    db.commit()
    db.refresh(permission)

    return PermissionResponse(
        id=permission.id,
        user_id=permission.user_id,
        username=user.username,
        can_view=permission.can_view,
        can_control=permission.can_control,
        can_transfer_files=permission.can_transfer_files
    )


@router.get("/{group_id}/permissions", response_model=List[PermissionResponse])
async def list_permissions(
    group_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """获取分组权限列表"""
    group = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    permissions = db.query(GroupPermission).filter(
        GroupPermission.group_id == group_id
    ).all()

    result = []
    for perm in permissions:
        user = db.query(User).filter(User.id == perm.user_id).first()
        result.append(PermissionResponse(
            id=perm.id,
            user_id=perm.user_id,
            username=user.username if user else "Unknown",
            can_view=perm.can_view,
            can_control=perm.can_control,
            can_transfer_files=perm.can_transfer_files
        ))

    return result


@router.delete("/{group_id}/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_permission(
    group_id: int,
    permission_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """删除分组权限"""
    permission = db.query(GroupPermission).filter(
        GroupPermission.id == permission_id,
        GroupPermission.group_id == group_id
    ).first()
    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission not found"
        )

    db.delete(permission)
    db.commit()


@router.put("/{group_id}/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def assign_device_to_group(
    group_id: int,
    device_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """将设备分配到分组"""
    group = db.query(DeviceGroup).filter(DeviceGroup.id == group_id).first()
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Group not found"
        )

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    device.group_id = group_id
    db.commit()


@router.delete("/{group_id}/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device_from_group(
    group_id: int,
    device_id: int,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """从分组移除设备"""
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.group_id == group_id
    ).first()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found in group"
        )

    device.group_id = None
    db.commit()
