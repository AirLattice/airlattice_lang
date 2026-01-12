from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator, model_validator

import app.storage as storage
from app.auth.handlers import AuthedUser
from app.auth.passwords import hash_password, validate_password, verify_password
from app.auth.settings import AuthType, settings
from app.memory import clear_user_memory
from app.schema import User

router = APIRouter()


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
async def login(payload: LoginRequest) -> TokenResponse:
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


@router.post("/signup", response_model=TokenResponse)
async def signup(payload: SignupRequest) -> TokenResponse:
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


@router.post("/account/password")
async def change_password(
    payload: ChangePasswordRequest, user: AuthedUser
) -> dict:
    if settings.auth_type != AuthType.JWT_LOCAL:
        raise HTTPException(
            status_code=400, detail="AUTH_TYPE must be jwt_local to use /account/password."
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
            status_code=400, detail="AUTH_TYPE must be jwt_local to use /account/delete."
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
