"""
Memory API Routes

FIX: All endpoints now require JWT authentication (Depends(get_current_principal)).
     user_id is no longer accepted as a free query param — it comes from the authenticated principal.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Any, Optional, Dict

from ..core.auth import get_current_principal, Principal
from ..core.memory import MemoryManager

router = APIRouter()


class MemoryRequest(BaseModel):
    key: str
    value: Any
    context: Optional[Dict] = None


class MemoryResponse(BaseModel):
    key: str
    value: Any
    context: Dict
    updated_at: str


@router.post("/", response_model=MemoryResponse)
async def set_memory(
    request: MemoryRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Store memory. user_id is taken from JWT principal, not request body."""
    memory_manager = MemoryManager()
    await memory_manager.set_memory(principal.user_id, request.key, request.value, request.context or {})
    memory = await memory_manager.get_memory(principal.user_id, request.key)
    return MemoryResponse(
        key=request.key,
        value=memory,
        context=request.context or {},
        updated_at="now"
    )


@router.get("/{key}")
async def get_memory(
    key: str,
    principal: Principal = Depends(get_current_principal),
):
    """Get memory by key. user_id is from JWT principal."""
    memory_manager = MemoryManager()
    memory = await memory_manager.get_memory(principal.user_id, key)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"key": key, "value": memory}


@router.get("/")
async def get_all_memories(
    principal: Principal = Depends(get_current_principal),
):
    """Get all user memories. user_id is from JWT principal."""
    memory_manager = MemoryManager()
    preferences = await memory_manager.get_user_preferences(principal.user_id)
    return preferences


@router.get("/search/{query}")
async def search_memories(
    query: str,
    principal: Principal = Depends(get_current_principal),
):
    """Search memories. user_id is from JWT principal."""
    memory_manager = MemoryManager()
    results = await memory_manager.search_memories(principal.user_id, query)
    return results
