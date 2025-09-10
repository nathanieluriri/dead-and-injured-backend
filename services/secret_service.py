# ============================================================================
# SECRET SERVICE
# ============================================================================
# This file was auto-generated on: 2025-09-10 10:02:38 WAT
# It contains  asynchrounous functions that make use of the repo functions 
# 
# ============================================================================

from bson import ObjectId
from fastapi import HTTPException
from typing import List

from repositories.secret import (
    create_secret,
    get_secret,
    get_secrets,
    update_secret,
    delete_secret,
)
from schemas.secret import SecretCreate, SecretUpdate, SecretOut


async def add_secret(secret_data: SecretCreate) -> SecretOut:
    """adds an entry of SecretCreate to the database and returns an object

    Returns:
        _type_: SecretOut
    """
    return await create_secret(secret_data)


async def remove_secret(secret_id: str):
    """deletes a field from the database and removes SecretCreateobject 

    Raises:
        HTTPException 400: Invalid secret ID format
        HTTPException 404:  Secret not found
    """
    if not ObjectId.is_valid(secret_id):
        raise HTTPException(status_code=400, detail="Invalid secret ID format")

    filter_dict = {"_id": ObjectId(secret_id)}
    result = await delete_secret(filter_dict)

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Secret not found")


async def retrieve_secret_by_secret_id(id: str) -> SecretOut:
    """Retrieves secret object based specific Id 

    Raises:
        HTTPException 404(not found): if  Secret not found in the db
        HTTPException 400(bad request): if  Invalid secret ID format

    Returns:
        _type_: SecretOut
    """
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid secret ID format")

    filter_dict = {"_id": ObjectId(id)}
    result = await get_secret(filter_dict)

    if not result:
        raise HTTPException(status_code=404, detail="Secret not found")

    return result


async def retrieve_secrets(start=0,stop=100) -> List[SecretOut]:
    """Retrieves SecretOut Objects in a list

    Returns:
        _type_: SecretOut
    """
    return await get_secrets(start=start,stop=stop)


async def update_secret_by_id(secret_id: str, secret_data: SecretUpdate) -> SecretOut:
    """_summary_

    Raises:
        HTTPException 404(not found): if Secret not found or update failed
        HTTPException 400(not found): Invalid secret ID format

    Returns:
        _type_: SecretOut
    """
    if not ObjectId.is_valid(secret_id):
        raise HTTPException(status_code=400, detail="Invalid secret ID format")

    filter_dict = {"_id": ObjectId(secret_id)}
    result = await update_secret(filter_dict, secret_data)

    if not result:
        raise HTTPException(status_code=404, detail="Secret not found or update failed")

    return result