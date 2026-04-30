from __future__ import annotations

import time
from enum import Enum
from typing import Optional
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from schemas.imports import BaseModel, EmailStr, ObjectId
from security.hash import hash_password

PROFILE_MEDIA_URL_MAX_LENGTH = 2048
PROFILE_MEDIA_FILENAME_MAX_LENGTH = 255
PROFILE_MEDIA_SIZE_MAX_BYTES = 40 * 1024 * 1024

ProfileMediaContentType = Literal[
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/avif",
    "image/bmp",
    "application/json",
    "application/zip",
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
]


class ProfileMediaKind(str, Enum):
    image = "image"
    lottie = "lottie"
    video = "video"


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
    avatar_url: str | None = Field(None, min_length=1, max_length=PROFILE_MEDIA_URL_MAX_LENGTH, pattern=r"^https?://")
    profile_media_url: str | None = Field(
        None,
        min_length=1,
        max_length=PROFILE_MEDIA_URL_MAX_LENGTH,
        pattern=r"^https?://",
    )
    profile_media_type: ProfileMediaContentType | None = None
    profile_media_kind: ProfileMediaKind | None = None
    profile_media_filename: str | None = Field(None, min_length=1, max_length=PROFILE_MEDIA_FILENAME_MAX_LENGTH)
    profile_media_size_bytes: int | None = Field(None, ge=1, le=PROFILE_MEDIA_SIZE_MAX_BYTES)
    bio: str | None = Field(None, max_length=280)
    last_updated: int = Field(default_factory=lambda: int(time.time()))


class UserCreate(UserSignup):
    bio: str | None = None
    avatar_url: str | None = Field(None, min_length=1, max_length=PROFILE_MEDIA_URL_MAX_LENGTH, pattern=r"^https?://")
    profile_media_url: str | None = Field(
        None,
        min_length=1,
        max_length=PROFILE_MEDIA_URL_MAX_LENGTH,
        pattern=r"^https?://",
    )
    profile_media_type: ProfileMediaContentType | None = None
    profile_media_kind: ProfileMediaKind | None = None
    profile_media_filename: str | None = Field(None, min_length=1, max_length=PROFILE_MEDIA_FILENAME_MAX_LENGTH)
    profile_media_size_bytes: int | None = Field(None, ge=1, le=PROFILE_MEDIA_SIZE_MAX_BYTES)
    is_email_verified: bool = False
    is_guest: bool = False
    expires_at: int | None = None
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
    avatar_url: str | None = Field(None, min_length=1, max_length=PROFILE_MEDIA_URL_MAX_LENGTH, pattern=r"^https?://")
    profile_media_url: str | None = Field(
        None,
        min_length=1,
        max_length=PROFILE_MEDIA_URL_MAX_LENGTH,
        pattern=r"^https?://",
    )
    profile_media_type: ProfileMediaContentType | None = None
    profile_media_kind: ProfileMediaKind | None = None
    profile_media_filename: str | None = Field(None, min_length=1, max_length=PROFILE_MEDIA_FILENAME_MAX_LENGTH)
    profile_media_size_bytes: int | None = Field(None, ge=1, le=PROFILE_MEDIA_SIZE_MAX_BYTES)
    is_email_verified: bool = False
    is_guest: bool = False
    expires_at: Optional[int] = None
    rank: int | None = None
    date_created: Optional[int] = None
    last_updated: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def set_dynamic_values(cls, values: dict | "UserOut") -> dict | "UserOut":
        if isinstance(values, dict):
            if values.get("_id") is not None:
                values["id"] = str(values["_id"])
            if not values.get("profile_media_url") and values.get("avatar_url"):
                values["profile_media_url"] = values["avatar_url"]
            if not values.get("avatar_url") and values.get("profile_media_url"):
                values["avatar_url"] = values["profile_media_url"]
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


class GuestUpgradeRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    username: str | None = Field(None, min_length=3, max_length=32)

    @model_validator(mode="after")
    def password_complexity(self) -> "GuestUpgradeRequest":
        pwd = self.password
        has_letter = any(c.isalpha() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        if not (has_letter and has_digit):
            raise ValueError("Password must include at least one letter and one digit")
        return self
