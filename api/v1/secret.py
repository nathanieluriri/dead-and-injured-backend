
from fastapi import APIRouter, HTTPException, Query, status, Path
from typing import List
from schemas.response_schema import APIResponse
from schemas.secret import (
    SecretCreate,
    SecretOut,
    SecretBase,
    SecretUpdate,
)
from services.secret_service import (
    add_secret,
    remove_secret,
    retrieve_secrets,
    retrieve_secret_by_secret_id,
    update_secret,
)

router = APIRouter(prefix="/secrets", tags=["Secrets"])

@router.get("/", response_model=APIResponse[List[SecretOut]])
async def list_secrets():
    items = await retrieve_secrets()
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")

@router.get("/me", response_model=APIResponse[SecretOut])
async def get_my_secrets(id: str = Query(..., description="secret ID to fetch specific item")):
    items = await retrieve_secret_by_secret_id(id=id)
    return APIResponse(status_code=200, data=items, detail="secrets items fetched")
