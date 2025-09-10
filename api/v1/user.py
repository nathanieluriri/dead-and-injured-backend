
from fastapi import APIRouter, HTTPException, Query, status, Path
from typing import List
from schemas.response_schema import APIResponse
from schemas.user import (
    UserCreate,
    UserOut,
    UserBase,
    UserUpdate,
)
from services.user_service import (
    add_user,
    remove_user,
    retrieve_users,
    retrieve_user_by_user_id,
    update_user,
)

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/", response_model=APIResponse[List[UserOut]])
async def list_users():
    items = await retrieve_users()
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")

@router.get("/me", response_model=APIResponse[UserOut])
async def get_my_users(id: str = Query(..., description="user ID to fetch specific item")):
    items = await retrieve_user_by_user_id(id=id)
    return APIResponse(status_code=200, data=items, detail="users items fetched")
