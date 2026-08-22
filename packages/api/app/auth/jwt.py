from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenPayload:
    def __init__(
        self,
        sub: str,
        tenant_id: str,
        role: str,
        exp: datetime,
        iat: datetime,
        type: str = "access",
        jti: str | None = None,
    ) -> None:
        self.sub = sub
        self.tenant_id = tenant_id
        self.role = role
        self.exp = exp
        self.iat = iat
        self.type = type
        self.jti = jti


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.auth.access_token_expire_minutes)
    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "access",
    })
    return jwt.encode(
        to_encode,
        settings.auth.secret_key.get_secret_value(),
        algorithm=settings.auth.algorithm,
    )


def create_refresh_token(data: dict[str, Any]) -> str:
    settings = get_settings()
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.auth.refresh_token_expire_days)
    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": "refresh",
    })
    return jwt.encode(
        to_encode,
        settings.auth.secret_key.get_secret_value(),
        algorithm=settings.auth.algorithm,
    )


def verify_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.auth.secret_key.get_secret_value(),
            algorithms=[settings.auth.algorithm],
        )
        sub: str | None = payload.get("sub")
        tenant_id: str | None = payload.get("tenant_id")
        role: str | None = payload.get("role")
        exp: datetime | None = payload.get("exp")
        iat: datetime | None = payload.get("iat")
        token_type: str = payload.get("type", "access")
        jti: str | None = payload.get("jti")

        if sub is None or tenant_id is None or role is None or exp is None or iat is None:
            raise JWTError("Missing required claims in token")

        return TokenPayload(
            sub=sub,
            tenant_id=tenant_id,
            role=role,
            exp=exp,
            iat=iat,
            type=token_type,
            jti=jti,
        )
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
