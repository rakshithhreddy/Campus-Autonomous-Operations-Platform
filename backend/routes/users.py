from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional

from ..core.auth import get_current_principal, Principal
from ..database_supabase import get_db, Memory

router = APIRouter(prefix="/api/users", tags=["Users"])

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None

@router.get("/profile/{user_id}")
async def get_user_profile(user_id: str, principal: Principal = Depends(get_current_principal)):
    # Make sure users can only access their own profile
    if principal.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    db = get_db()
    user = await db.get_or_create_user(user_id)
    
    # Also fetch manual preferences/memories
    memories = await db.get_user_memories(user_id)
    
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "preferences": user.preferences,
        "memories": [m.to_dict() for m in memories]
    }

@router.put("/profile/{user_id}")
async def update_user_profile(user_id: str, data: UserProfileUpdate, principal: Principal = Depends(get_current_principal)):
    if principal.user_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    db = get_db()
    
    updates = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.preferences is not None:
        updates["preferences"] = data.preferences
        
    if not updates:
        return {"success": True, "message": "No updates provided"}
        
    updated_user = await db.update_user(user_id, updates)
    if not updated_user:
        raise HTTPException(status_code=500, detail="Failed to update user profile")
        
    return {
        "success": True,
        "user": {
            "id": updated_user.id,
            "name": updated_user.name,
            "email": updated_user.email,
            "preferences": updated_user.preferences
        }
    }
