"""
Tasks API Routes
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional

from ..database_supabase import get_task, get_tasks_by_user, Task
from ..core.auth import get_current_principal, Principal

router = APIRouter()

class TaskResponse(BaseModel):
    id: str
    user_id: str
    intent: str
    status: str
    result: Optional[str]
    steps: List[dict]
    created_at: str
    updated_at: str

@router.get("/", response_model=List[TaskResponse])
async def get_tasks(
    principal: Principal = Depends(get_current_principal),
    limit: int = 20
):
    """Get user tasks"""
    user_id = principal.user_id
    tasks = await get_tasks_by_user(user_id, limit)
    
    return [
        TaskResponse(
            id=task.id,
            user_id=task.user_id,
            intent=task.intent,
            status=task.status,
            result=task.result,
            steps=task.steps or [],
            created_at=task.created_at.isoformat(),
            updated_at=task.updated_at.isoformat()
        )
        for task in tasks
    ]

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_by_id(
    task_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Get specific task"""
    task = await get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    return TaskResponse(
        id=task.id,
        user_id=task.user_id,
        intent=task.intent,
        status=task.status,
        result=task.result,
        steps=task.steps or [],
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat()
    )
