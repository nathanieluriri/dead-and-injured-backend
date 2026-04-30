from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import boto3
from bson import ObjectId
from fastapi import HTTPException, UploadFile
from pymongo import ReturnDocument

from core.config import get_settings
from core.database import db
from schemas.user import UserOut

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(frozen=True)
class AllowedProfileMedia:
    kind: str
    canonical_content_type: str
    allowed_content_types: tuple[str, ...]
    max_bytes: int


_IMAGE_MAX_BYTES = settings.profile_media_max_bytes
_VIDEO_MAX_BYTES = settings.profile_video_max_bytes

_ALLOWED_PROFILE_MEDIA: dict[str, AllowedProfileMedia] = {
    ".png": AllowedProfileMedia("image", "image/png", ("image/png",), _IMAGE_MAX_BYTES),
    ".jpg": AllowedProfileMedia("image", "image/jpeg", ("image/jpeg",), _IMAGE_MAX_BYTES),
    ".jpeg": AllowedProfileMedia("image", "image/jpeg", ("image/jpeg",), _IMAGE_MAX_BYTES),
    ".gif": AllowedProfileMedia("image", "image/gif", ("image/gif",), _IMAGE_MAX_BYTES),
    ".webp": AllowedProfileMedia("image", "image/webp", ("image/webp",), _IMAGE_MAX_BYTES),
    ".avif": AllowedProfileMedia("image", "image/avif", ("image/avif",), _IMAGE_MAX_BYTES),
    ".bmp": AllowedProfileMedia("image", "image/bmp", ("image/bmp",), _IMAGE_MAX_BYTES),
    ".json": AllowedProfileMedia(
        "lottie",
        "application/json",
        ("application/json", "application/vnd.lottie+json", "text/plain"),
        _IMAGE_MAX_BYTES,
    ),
    ".lottie": AllowedProfileMedia(
        "lottie",
        "application/zip",
        ("application/zip", "application/octet-stream", "application/vnd.lottie+zip"),
        _IMAGE_MAX_BYTES,
    ),
    ".mp4": AllowedProfileMedia("video", "video/mp4", ("video/mp4",), _VIDEO_MAX_BYTES),
    ".m4v": AllowedProfileMedia("video", "video/mp4", ("video/mp4", "video/x-m4v"), _VIDEO_MAX_BYTES),
    ".mov": AllowedProfileMedia("video", "video/quicktime", ("video/quicktime",), _VIDEO_MAX_BYTES),
    ".webm": AllowedProfileMedia("video", "video/webm", ("video/webm",), _VIDEO_MAX_BYTES),
    ".mkv": AllowedProfileMedia("video", "video/x-matroska", ("video/x-matroska", "application/octet-stream"), _VIDEO_MAX_BYTES),
}

_GENERIC_ALLOWED_CONTENT_TYPES = {"application/octet-stream", ""}


def _require_storage_settings() -> None:
    missing = [
        name
        for name, value in (
            ("R2_ACCESS_KEY_ID", settings.r2_access_key_id),
            ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
            ("R2_ENDPOINT_URL", settings.r2_endpoint_url),
            ("R2_BUCKET", settings.r2_bucket),
            ("PUBLIC_BASE_URL", settings.public_base_url),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing R2 configuration: {', '.join(missing)}")


def _r2_client():
    _require_storage_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def _normalize_extension(filename: str | None) -> str:
    extension = Path(filename or "").suffix.lower()
    if not extension:
        raise HTTPException(status_code=400, detail="Profile media file must include an extension")
    return extension


def _resolve_media_rule(filename: str | None, content_type: str | None) -> AllowedProfileMedia:
    extension = _normalize_extension(filename)
    rule = _ALLOWED_PROFILE_MEDIA.get(extension)
    if rule is None:
        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported profile media type. Allowed extensions: "
                f"{', '.join(sorted(_ALLOWED_PROFILE_MEDIA))}"
            ),
        )

    normalized_content_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_content_type not in rule.allowed_content_types and normalized_content_type not in _GENERIC_ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type for {extension}: {normalized_content_type or 'unknown'}",
        )
    return rule


def _build_storage_key(user_id: str, extension: str) -> str:
    timestamp = int(time.time())
    token = secrets.token_urlsafe(12)
    return f"profile-media/{user_id}/{timestamp}-{token}{extension}"


def _public_url_for_key(storage_key: str) -> str:
    base_url = settings.public_base_url.rstrip("/")
    return f"{base_url}/{quote(storage_key, safe='/')}"


async def _read_upload_bytes(upload: UploadFile, max_bytes: int) -> bytes:
    payload = await upload.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Profile media exceeds the {max_bytes // (1024 * 1024)} MB limit for this file type",
        )
    if not payload:
        raise HTTPException(status_code=400, detail="Profile media file is empty")
    return payload


def _put_object(storage_key: str, content_type: str, payload: bytes) -> None:
    client = _r2_client()
    client.put_object(
        Bucket=settings.r2_bucket,
        Key=storage_key,
        Body=payload,
        ContentType=content_type,
        CacheControl="public, max-age=31536000, immutable",
        ContentDisposition="inline",
    )


def _delete_object(storage_key: str) -> None:
    if not storage_key:
        return
    client = _r2_client()
    client.delete_object(Bucket=settings.r2_bucket, Key=storage_key)


async def upload_profile_media(user_id: str, upload: UploadFile) -> UserOut:
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID format")

    rule = _resolve_media_rule(upload.filename, upload.content_type)
    extension = _normalize_extension(upload.filename)
    payload = await _read_upload_bytes(upload, rule.max_bytes)
    storage_key = _build_storage_key(user_id, extension)
    public_url = _public_url_for_key(storage_key)
    content_type = rule.canonical_content_type

    existing_user = await db.users.find_one({"_id": ObjectId(user_id)})
    if existing_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    previous_storage_key = str(existing_user.get("profile_media_storage_key") or "")

    try:
        await asyncio.to_thread(_put_object, storage_key, content_type, payload)
    except Exception as err:
        logger.exception("Failed to upload profile media for user_id=%s", user_id)
        raise HTTPException(status_code=502, detail="Profile media upload failed") from err
    finally:
        await upload.close()

    update_payload = {
        "profile_media_url": public_url,
        "profile_media_type": content_type,
        "profile_media_kind": rule.kind,
        "profile_media_filename": upload.filename,
        "profile_media_size_bytes": len(payload),
        "profile_media_storage_key": storage_key,
        "avatar_url": public_url,
        "last_updated": int(time.time()),
    }

    updated_user = await db.users.find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": update_payload},
        return_document=ReturnDocument.AFTER,
    )
    if updated_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if previous_storage_key and previous_storage_key != storage_key:
        try:
            await asyncio.to_thread(_delete_object, previous_storage_key)
        except Exception:
            logger.warning("Failed to delete previous profile media key=%s", previous_storage_key, exc_info=True)

    return UserOut(**updated_user)
