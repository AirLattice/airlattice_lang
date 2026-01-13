from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator, model_validator

import app.storage as storage
from app.auth.handlers import AuthedUser
from app.auth.passwords import hash_password, validate_password, verify_password
from app.auth.settings import AuthType, settings
from app.memory import clear_user_memory
from app.schema import User

router = APIRouter()

REFRESH_COOKIE_NAME = "opengpts_refresh"


def _issue_access_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": sub,
            "iss": settings.jwt_local.iss,
            "aud": settings.jwt_local.aud,
            "token_use": "access",
            "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        },
        settings.jwt_local.decode_key,
        algorithm=settings.jwt_local.alg.upper(),
    )


def _issue_refresh_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": sub,
            "iss": settings.jwt_local.iss,
            "aud": settings.jwt_local.aud,
            "token_use": "refresh",
            "exp": now + timedelta(days=settings.refresh_token_ttl_days),
        },
        settings.jwt_local.decode_key,
        algorithm=settings.jwt_local.alg.upper(),
    )


def _set_refresh_cookie(response: Response, request: Request, refresh_token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


def _clear_refresh_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("username is required")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_field(cls, value: str) -> str:
        if not value:
            raise ValueError("password is required")
        return value


class SignupRequest(BaseModel):
    username: str
    password: str
    password_confirm: str

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("username is required")
        return value

    @field_validator("password")
    @classmethod
    def validate_password_field(cls, value: str) -> str:
        if not value:
            raise ValueError("password is required")
        validate_password(value)
        return value

    @model_validator(mode="after")
    def confirm_password(self):
        if self.password != self.password_confirm:
            raise ValueError("passwords do not match")
        return self


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str

    @field_validator("current_password")
    @classmethod
    def validate_current_password(cls, value: str) -> str:
        if not value:
            raise ValueError("current password is required")
        return value

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not value:
            raise ValueError("new password is required")
        validate_password(value)
        return value

    @model_validator(mode="after")
    def confirm_new_password(self):
        if self.new_password != self.new_password_confirm:
            raise ValueError("passwords do not match")
        return self


class DeleteAccountRequest(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_field(cls, value: str) -> str:
        if not value:
            raise ValueError("password is required")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    sub: str


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> TokenResponse:
    if settings.auth_type != AuthType.JWT_LOCAL:
        raise HTTPException(
            status_code=400, detail="AUTH_TYPE must be jwt_local to use /login."
        )

    sub = payload.username
    record = await storage.get_user_by_sub(sub)
    if not record or not record.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = User(**record)
    access_token = _issue_access_token(sub)
    refresh_token = _issue_refresh_token(sub)
    _set_refresh_cookie(response, request, refresh_token)
    return TokenResponse(access_token=access_token, user_id=user.user_id, sub=sub)


@router.post("/signup", response_model=TokenResponse)
async def signup(payload: SignupRequest, request: Request, response: Response) -> TokenResponse:
    if settings.auth_type != AuthType.JWT_LOCAL:
        raise HTTPException(
            status_code=400, detail="AUTH_TYPE must be jwt_local to use /signup."
        )

    sub = payload.username
    record = await storage.get_user_by_sub(sub)
    password_hash = hash_password(payload.password)
    if record:
        if record.get("password_hash"):
            raise HTTPException(status_code=409, detail="User already exists")
        user = await storage.set_user_password(record["user_id"], password_hash)
    else:
        user = await storage.create_user_with_password(sub, password_hash)

    access_token = _issue_access_token(sub)
    refresh_token = _issue_refresh_token(sub)
    _set_refresh_cookie(response, request, refresh_token)
    return TokenResponse(access_token=access_token, user_id=user.user_id, sub=sub)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response) -> TokenResponse:
    if settings.auth_type != AuthType.JWT_LOCAL:
        raise HTTPException(
            status_code=400, detail="AUTH_TYPE must be jwt_local to use /refresh."
        )

    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    try:
        payload = jwt.decode(
            refresh_token,
            settings.jwt_local.decode_key,
            issuer=settings.jwt_local.iss,
            audience=settings.jwt_local.aud,
            algorithms=[settings.jwt_local.alg.upper()],
            options={"require": ["exp", "iss", "aud", "sub", "token_use"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if payload.get("token_use") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    sub = payload["sub"]
    record = await storage.get_user_by_sub(sub)
    if not record:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = User(**record)

    access_token = _issue_access_token(sub)
    new_refresh_token = _issue_refresh_token(sub)
    _set_refresh_cookie(response, request, new_refresh_token)
    return TokenResponse(access_token=access_token, user_id=user.user_id, sub=sub)


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    _clear_refresh_cookie(response, request)
    return {"ok": True}


@router.post("/account/password")
async def change_password(payload: ChangePasswordRequest, user: AuthedUser) -> dict:
    if settings.auth_type != AuthType.JWT_LOCAL:
        raise HTTPException(
            status_code=400,
            detail="AUTH_TYPE must be jwt_local to use /account/password.",
        )

    record = await storage.get_user_by_sub(user.sub)
    if not record or not record.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.current_password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    password_hash = hash_password(payload.new_password)
    await storage.set_user_password(record["user_id"], password_hash)
    return {"ok": True}


@router.post("/account/delete")
async def delete_account(payload: DeleteAccountRequest, user: AuthedUser) -> dict:
    if settings.auth_type != AuthType.JWT_LOCAL:
        raise HTTPException(
            status_code=400,
            detail="AUTH_TYPE must be jwt_local to use /account/delete.",
        )

    record = await storage.get_user_by_sub(user.sub)
    if not record or not record.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    await clear_user_memory(user_id=user.user_id)
    await storage.delete_user_data(user.user_id)
    return {"deleted": True}


@router.get("/me", response_model=User)
async def me(user: AuthedUser) -> User:
    return user
