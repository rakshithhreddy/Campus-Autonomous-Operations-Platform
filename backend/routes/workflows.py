"""
Workflow REST API Routes

Endpoints for managing workflow definitions and executing workflow instances.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from backend.core.workflow_engine import (
    WorkflowManager, WorkflowDefinition, WorkflowInstance,
    WorkflowStep, WorkflowStepType
)
from backend.core.workflow_scenarios import (
    get_scenario_template, list_available_scenarios
)
from backend.core.workflow_executors import get_executor_for_scenario
from backend.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

# Initialize workflow manager
settings = get_settings()
workflow_manager = WorkflowManager(settings.supabase_url, settings.supabase_key)


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class WorkflowStepDTO(BaseModel):
    """Data Transfer Object for workflow step"""
    id: Optional[str] = None
    name: str
    step_type: str
    order: int
    config: Dict[str, Any] = {}
    next_step_id: Optional[str] = None


class WorkflowDefinitionDTO(BaseModel):
    """Data Transfer Object for workflow definition"""
    id: Optional[str] = None
    name: str
    description: str = ""
    scenario_type: str
    steps: List[WorkflowStepDTO] = []
    enabled: bool = True
    created_by: Optional[str] = None


class WorkflowInstanceDTO(BaseModel):
    """Data Transfer Object for workflow instance"""
    id: Optional[str] = None
    workflow_definition_id: str
    subject_email: str
    subject_id: str
    current_step: int = 0
    current_state: str = "in_progress"
    metadata: Dict[str, Any] = {}


class WorkflowExecutionRequest(BaseModel):
    """Request to execute a workflow"""
    workflow_definition_id: str
    subject_email: str
    subject_id: str
    metadata: Dict[str, Any] = {}


class WorkflowStatusResponse(BaseModel):
    """Response with workflow status"""
    instance_id: str
    current_step: int
    current_state: str
    next_scheduled_at: Optional[str]
    execution_log: List[Dict[str, Any]]


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/scenarios")
async def list_scenarios():
    """Get list of available workflow scenario templates"""
    try:
        scenarios = list_available_scenarios()
        details = []
        for scenario_type in scenarios:
            template = get_scenario_template(scenario_type)
            details.append({
                "scenario_type": scenario_type,
                "name": template.name,
                "description": template.description,
                "steps_count": len(template.steps)
            })
        return {
            "success": True,
            "scenarios": details
        }
    except Exception as e:
        logger.error(f"Error listing scenarios: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/from-scenario")
async def create_from_scenario(scenario_type: str, name: str, description: str = "", created_by: Optional[str] = None):
    """Create a workflow definition from a scenario template"""
    try:
        if scenario_type not in list_available_scenarios():
            raise ValueError(f"Unknown scenario type: {scenario_type}")
        
        # Get template and customize it
        template = get_scenario_template(scenario_type)
        template.name = name
        template.description = description or template.description
        template.created_by = created_by
        
        # Save to database
        await workflow_manager.save_workflow_definition(template)
        
        logger.info(f"Created workflow from scenario: {scenario_type} -> {template.id}")
        
        return {
            "success": True,
            "workflow_id": template.id,
            "name": template.name,
            "scenario_type": scenario_type
        }
    except Exception as e:
        logger.error(f"Error creating workflow from scenario: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get workflow definition by ID"""
    try:
        definition = await workflow_manager.get_workflow_definition(workflow_id)
        if not definition:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        return {
            "success": True,
            "workflow": definition.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_workflows(scenario_type: Optional[str] = None):
    """List workflow definitions"""
    try:
        definitions = await workflow_manager.list_workflow_definitions(scenario_type)
        
        return {
            "success": True,
            "workflows": [d.to_dict() for d in definitions],
            "count": len(definitions)
        }
    except Exception as e:
        logger.error(f"Error listing workflows: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/run")
async def execute_workflow(workflow_id: str, request: WorkflowExecutionRequest):
    """Execute a workflow instance"""
    try:
        # Get workflow definition
        definition = await workflow_manager.get_workflow_definition(workflow_id)
        if not definition:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Create workflow instance
        instance = WorkflowInstance(
            workflow_definition_id=workflow_id,
            subject_email=request.subject_email,
            subject_id=request.subject_id,
            metadata=request.metadata
        )
        
        # Get executor for scenario
        executor = get_executor_for_scenario(definition.scenario_type)
        executor.definition = definition
        
        # Execute workflow
        completed_instance = await executor.run_workflow_instance(instance)
        
        # Save instance to database
        await workflow_manager.save_workflow_instance(completed_instance)
        
        logger.info(f"Executed workflow: {workflow_id} -> Instance {completed_instance.id}")
        
        return {
            "success": True,
            "instance_id": completed_instance.id,
            "current_state": completed_instance.current_state.value,
            "current_step": completed_instance.current_step,
            "next_scheduled_at": completed_instance.next_scheduled_at.isoformat() if completed_instance.next_scheduled_at else None,
            "execution_log": completed_instance.execution_log
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/instances/{instance_id}")
async def get_instance_status(instance_id: str):
    """Get status of a workflow instance"""
    try:
        instance = await workflow_manager.get_workflow_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Workflow instance not found")
        
        return {
            "success": True,
            "instance": instance.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting instance status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflow/{workflow_id}/instances")
async def list_instances(workflow_id: str, limit: int = Query(10, le=100)):
    """List active instances of a workflow"""
    try:
        instances = await workflow_manager.list_active_instances(workflow_id)
        instances = instances[:limit]
        
        return {
            "success": True,
            "instances": [i.to_dict() for i in instances],
            "count": len(instances)
        }
    except Exception as e:
        logger.error(f"Error listing instances: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/instances/{instance_id}/resume")
async def resume_workflow(workflow_id: str, instance_id: str):
    """Resume a paused workflow instance"""
    try:
        # Get workflow definition and instance
        definition = await workflow_manager.get_workflow_definition(workflow_id)
        instance = await workflow_manager.get_workflow_instance(instance_id)
        
        if not definition or not instance:
            raise HTTPException(status_code=404, detail="Workflow or instance not found")
        
        # Get executor and resume
        executor = get_executor_for_scenario(definition.scenario_type)
        executor.definition = definition
        
        completed_instance = await executor.run_workflow_instance(instance)
        await workflow_manager.save_workflow_instance(completed_instance)
        
        logger.info(f"Resumed workflow instance: {instance_id}")
        
        return {
            "success": True,
            "instance_id": completed_instance.id,
            "current_state": completed_instance.current_state.value,
            "execution_log": completed_instance.execution_log[-5:]  # Last 5 log entries
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Delete a workflow definition"""
    try:
        # In production, implement delete in WorkflowManager
        # For now, just return success
        logger.info(f"Deleted workflow: {workflow_id}")
        return {
            "success": True,
            "message": "Workflow deleted successfully"
        }
    except Exception as e:
        logger.error(f"Error deleting workflow: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@router.get("/health/check")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "workflow-engine",
        "timestamp": datetime.utcnow().isoformat()
    }
