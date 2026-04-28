from __future__ import annotations

import time
from typing import Optional

from pydantic import ConfigDict, Field, model_validator

from schemas.imports import BaseModel, EmailStr, ObjectId
from security.hash import hash_password


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserSignup(UserLogin):
    username: str = Field(..., min_length=3, max_length=32)

    @model_validator(mode="after")
    def password_complexity(self) -> "UserSignup":
        pwd = self.password
        has_letter = any(c.isalpha() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        if not (has_letter and has_digit):
            raise ValueError("Password must include at least one letter and one digit")
        return self


class UserRefresh(BaseModel):
    refresh_token: str | None = None


class UserUpdate(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=32)
    avatar_url: str | None = None
    bio: str | None = Field(None, max_length=280)
    last_updated: int = Field(default_factory=lambda: int(time.time()))


class UserCreate(UserSignup):
    bio: str | None = None
    avatar_url: str | None = None
    is_email_verified: bool = False
    rank: int | None = None
    date_created: int = Field(default_factory=lambda: int(time.time()))
    last_updated: int = Field(default_factory=lambda: int(time.time()))

    @model_validator(mode="after")
    def obscure_password(self) -> "UserCreate":
        self.password = hash_password(self.password)
        return self


class UserOut(BaseModel):
    id: Optional[str] = None
    username: str
    email: EmailStr
    bio: str | None = None
    avatar_url: str | None = None
    is_email_verified: bool = False
    rank: int | None = None
    date_created: Optional[int] = None
    last_updated: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def set_dynamic_values(cls, values: dict | "UserOut") -> dict | "UserOut":
        if isinstance(values, dict):
            values["id"] = str(values.get("_id"))
        return values

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


class UserRecord(UserOut):
    password: str


class EmailVerificationRequest(BaseModel):
    token: str = Field(..., min_length=16, max_length=256, pattern=r"^[A-Za-z0-9_\-]+$")


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=16, max_length=256, pattern=r"^[A-Za-z0-9_\-]+$")
    password: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="after")
    def password_complexity(self) -> "PasswordResetConfirm":
        pwd = self.password
        has_letter = any(c.isalpha() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        if not (has_letter and has_digit):
            raise ValueError("Password must include at least one letter and one digit")
        return self
