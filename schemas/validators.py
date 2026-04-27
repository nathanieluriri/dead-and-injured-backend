from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator


SECRET_LENGTH = 4


def validate_code(value: str) -> str:
    if not value.isdigit():
        raise ValueError("Code must contain only digits")
    if len(value) != SECRET_LENGTH:
        raise ValueError(f"Code must be exactly {SECRET_LENGTH} digits")
    if len(set(value)) != SECRET_LENGTH:
        raise ValueError("Code digits must be unique")
    return value


CodeStr = Annotated[str, AfterValidator(validate_code)]
