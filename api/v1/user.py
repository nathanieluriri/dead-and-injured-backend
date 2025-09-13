
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
    authenticate_user,
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



@router.post("/signup", response_model=APIResponse[UserOut])
async def signup_new_user(user_data:UserBase):
    new_user = UserCreate(**user_data.model_dump())
    items = await add_user(user_data=new_user)
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")


@router.post("/login", response_model=APIResponse[UserOut])
async def login_user(user_data:UserBase):
    items = await authenticate_user(user_data=user_data)
    return APIResponse(status_code=200, data=items, detail="Fetched successfully")
