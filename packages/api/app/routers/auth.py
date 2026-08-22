from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr
from datetime import timedelta

from ..database import get_db
from ..auth.jwt import create_access_token, create_refresh_token, verify_password, get_password_hash
from ..auth.dependencies import get_current_user
from ..models import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
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


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    from ..models import Tenant
    import uuid

    existing = await db.execute(
        __import__("sqlalchemy").select(User).where(User.email == req.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    tenant = Tenant(id=uuid.uuid4(), name=req.tenant_name, plan="free", config_json={})
    db.add(tenant)
    await db.flush()

    user = User(
        id=uuid.uuid4(),
        email=req.email,
        hashed_password=get_password_hash(req.password),
        role="developer",
        tenant_id=tenant.id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": str(user.tenant_id)})
    refresh = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access, refresh_token=refresh, user_id=str(user.id), role=user.role)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(__import__("sqlalchemy").select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": str(user.tenant_id)})
    refresh = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access, refresh_token=refresh, user_id=str(user.id), role=user.role)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = verify_token(req.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.type != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token type")

    result = await db.execute(__import__("sqlalchemy").select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access = create_access_token({"sub": str(user.id), "role": user.role.value if hasattr(user.role, 'value') else user.role, "tenant_id": str(user.tenant_id)})
    refresh = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access, refresh_token=refresh, user_id=str(user.id), role=user.role.value if hasattr(user.role, 'value') else user.role)


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {"id": str(current_user.id), "email": current_user.email, "role": current_user.role, "tenant_id": str(current_user.tenant_id)}
