from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime
import uuid

from ..database import get_db
from ..auth.jwt import create_access_token, create_refresh_token, verify_token, verify_password, get_password_hash
from ..auth.dependencies import get_current_user
from ..models import User, Tenant, UserRole

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    tenant_name: str = "default"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str
    tenant_id: str


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    username_check = await db.execute(select(User).where(User.username == req.username))
    if username_check.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    tenant = Tenant(
        id=uuid.uuid4(),
        name=req.tenant_name,
        slug=req.tenant_name.lower().replace(" ", "-"),
        plan="free",
        settings={},
    )
    db.add(tenant)
    await db.flush()

    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=req.email,
        username=req.username,
        hashed_password=get_password_hash(req.password),
        role=UserRole.EDITOR,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access = create_access_token({"sub": str(user.id), "role": user.role.value, "tenant_id": str(user.tenant_id)})
    refresh = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access, refresh_token=refresh, user_id=str(user.id), role=user.role.value)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    user.last_login = datetime.utcnow()
    await db.commit()

    access = create_access_token({"sub": str(user.id), "role": user.role.value, "tenant_id": str(user.tenant_id)})
    refresh = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access, refresh_token=refresh, user_id=str(user.id), role=user.role.value)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = verify_token(req.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.type != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token type")

    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access = create_access_token({"sub": str(user.id), "role": user.role.value, "tenant_id": str(user.tenant_id)})
    refresh = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access, refresh_token=refresh, user_id=str(user.id), role=user.role.value)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        role=current_user.role.value,
        tenant_id=str(current_user.tenant_id),
    )
