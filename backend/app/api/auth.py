from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import app.storage as storage
from app.auth.handlers import AuthedUser
from app.auth.settings import AuthType, settings
from app.schema import User

router = APIRouter()


class LoginRequest(BaseModel):
    username: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("username is required")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    sub: str


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    if settings.auth_type != AuthType.JWT_LOCAL:
        raise HTTPException(
            status_code=400, detail="AUTH_TYPE must be jwt_local to use /login."
        )

    sub = payload.username
    user, _ = await storage.get_or_create_user(sub)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": sub,
            "iss": settings.jwt_local.iss,
            "aud": settings.jwt_local.aud,
            "exp": now + timedelta(days=7),
        },
        settings.jwt_local.decode_key,
        algorithm=settings.jwt_local.alg.upper(),
    )
    return TokenResponse(access_token=token, user_id=user.user_id, sub=sub)


@router.get("/me", response_model=User)
async def me(user: AuthedUser) -> User:
    return user
