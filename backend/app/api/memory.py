from typing import Annotated, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.auth.handlers import AuthedUser
from app.memory import clear_user_memory, delete_user_memory, list_user_memory

router = APIRouter()


class MemoryItem(BaseModel):
    id: str
    content: str
    role: Optional[str] = None
    created_at: Optional[str] = None
    thread_id: Optional[str] = None
    assistant_id: Optional[str] = None


@router.get("")
async def get_memory(
    user: AuthedUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MemoryItem]:
    items = await list_user_memory(user_id=user.user_id, limit=limit, offset=offset)
    return [MemoryItem(**item) for item in items]


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    user: AuthedUser,
) -> dict:
    deleted = await delete_user_memory(user_id=user.user_id, memory_id=memory_id)
    return {"deleted": deleted}


@router.delete("")
async def clear_memory(user: AuthedUser) -> dict:
    deleted = await clear_user_memory(user_id=user.user_id)
    return {"deleted": deleted}
