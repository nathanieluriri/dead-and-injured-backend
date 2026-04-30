from __future__ import annotations

from pydantic import BaseModel, Field


class GoogleAuthStartOut(BaseModel):
    authorize_url: str
    state: str
    target: str


class GoogleAuthExchangeIn(BaseModel):
    code: str = Field(..., min_length=16, max_length=256, pattern=r"^[A-Za-z0-9_\-]+$")
