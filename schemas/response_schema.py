from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, model_validator
from pydantic.generics import GenericModel

T = TypeVar("T")


class APIError(BaseModel):
    code: str
    message: str
    field: str | None = None


class APIResponse(GenericModel, Generic[T]):
    success: bool
    message: str
    data: T | None = None
    meta: dict[str, Any] | None = None
    errors: list[APIError] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def support_legacy_shape(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values

        if "message" in values and "success" in values:
            return values

        status_code = int(values.get("status_code", 200))
        detail = values.get("detail") or values.get("message") or "Request completed"
        errors = values.get("errors") or []
        if not errors and status_code >= 400:
            errors = [APIError(code="http_error", message=str(detail))]

        return {
            "success": status_code < 400 and not errors,
            "message": detail,
            "data": values.get("data"),
            "meta": values.get("meta"),
            "errors": errors,
        }


def ok_response(
    data: T | None = None,
    message: str = "Request completed",
    meta: dict[str, Any] | None = None,
) -> APIResponse[T]:
    return APIResponse(success=True, message=message, data=data, meta=meta, errors=[])

