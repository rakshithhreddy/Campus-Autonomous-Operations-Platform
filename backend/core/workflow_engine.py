"""
Workflow Engine for Follow-up Pipeline System

Handles workflow definition, execution, state persistence, and conditional branching.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timedelta
import json
import uuid
from abc import ABC, abstractmethod
import asyncio
from supabase import create_client
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class WorkflowStepType(str, Enum):
    """Types of workflow steps"""
    SEND_EMAIL = "send_email"
    CHECK_CONDITION = "check_condition"
    WAIT = "wait"
    LOG_ACTION = "log_action"
    ESCALATE = "escalate"
    QUERY_ERP = "query_erp"
    SEND_SMS = "send_sms"


class WorkflowState(str, Enum):
    """Workflow execution states"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PARENT_CONTACTED = "parent_contacted"
    ADMIN_ESCALATED = "admin_escalated"
    RESOLVED = "resolved"
    FAILED = "failed"
    ARCHIVED = "archived"


class StepStatus(str, Enum):
    """Individual step execution status"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class WorkflowStep:
    """Definition of a single workflow step"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    step_type: WorkflowStepType = WorkflowStepType.SEND_EMAIL
    order: int = 0
    config: Dict[str, Any] = field(default_factory=dict)  # Step-specific config
    next_step_id: Optional[str] = None  # Linear flow for now
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "step_type": self.step_type.value,
            "order": self.order,
            "config": self.config,
            "next_step_id": self.next_step_id,
        }


@dataclass
class WorkflowCondition:
    """Conditional logic for branching"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""  # 'attendance_check', 'fee_status', 'submission_status', etc.
    operator: str = ""  # '>=', '<=', '==', 'contains', etc.
    value: Any = None
    true_step_id: Optional[str] = None  # Go to this step if condition is true
    false_step_id: Optional[str] = None  # Go to this step if condition is false
    
    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "operator": self.operator,
            "value": self.value,
            "true_step_id": self.true_step_id,
            "false_step_id": self.false_step_id,
        }


@dataclass
class WorkflowDefinition:
    """Template/definition of a workflow"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    scenario_type: str = ""  # 'attendance', 'assignment', 'fee', etc.
    steps: List[WorkflowStep] = field(default_factory=list)
    conditions: List[WorkflowCondition] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    enabled: bool = True
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "scenario_type": self.scenario_type,
            "steps": [s.to_dict() for s in self.steps],
            "conditions": [c.to_dict() for c in self.conditions],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "enabled": self.enabled,
        }


@dataclass
class WorkflowInstance:
    """Running instance of a workflow"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_definition_id: str = ""
    subject_email: str = ""  # Student/parent email
    subject_id: str = ""  # Student ID or other identifier
    current_step: int = 0
    current_state: WorkflowState = WorkflowState.IN_PROGRESS
    metadata: Dict[str, Any] = field(default_factory=dict)  # Custom data
    next_scheduled_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    execution_log: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self):
        return {
            "id": self.id,
            "workflow_definition_id": self.workflow_definition_id,
            "subject_email": self.subject_email,
            "subject_id": self.subject_id,
            "current_step": self.current_step,
            "current_state": self.current_state.value,
            "metadata": self.metadata,
            "next_scheduled_at": self.next_scheduled_at.isoformat() if self.next_scheduled_at else None,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "execution_log": self.execution_log,
        }


# ============================================================================
# WORKFLOW EXECUTOR
# ============================================================================

class WorkflowExecutor(ABC):
    """Base executor for workflow execution"""
    
    def __init__(self, definition: WorkflowDefinition):
        self.definition = definition
        self.instance: Optional[WorkflowInstance] = None
    
    @abstractmethod
    async def execute_step(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Execute a single workflow step"""
        pass
    
    async def evaluate_condition(self, condition: WorkflowCondition, instance: WorkflowInstance) -> bool:
        """Evaluate a condition and return True/False"""
        # This will be overridden by specific scenario implementations
        return True
    
    async def run_workflow_instance(self, instance: WorkflowInstance) -> WorkflowInstance:
        """Execute a complete workflow instance"""
        logger.info(f"Starting workflow execution for instance {instance.id}")
        
        instance.current_state = WorkflowState.IN_PROGRESS
        current_step_order = instance.current_step
        
        try:
            while current_step_order < len(self.definition.steps):
                step = self.definition.steps[current_step_order]
                
                logger.info(f"Executing step {current_step_order}: {step.name}")
                
                # Execute the step
                result = await self.execute_step(step, instance)
                
                # Log execution
                instance.execution_log.append({
                    "step_id": step.id,
                    "step_name": step.name,
                    "status": result.get("status", StepStatus.SUCCESS.value),
                    "timestamp": datetime.utcnow().isoformat(),
                    "details": result.get("details", {}),
                })
                
                # Handle step result
                if result.get("status") == StepStatus.FAILED.value:
                    instance.current_state = WorkflowState.FAILED
                    logger.error(f"Step failed: {step.name}")
                    break
                
                # Handle wait steps (schedule next execution)
                if step.step_type == WorkflowStepType.WAIT:
                    delay_hours = step.config.get("delay_hours", 0)
                    instance.next_scheduled_at = datetime.utcnow() + timedelta(hours=delay_hours)
                    instance.current_step = current_step_order + 1
                    logger.info(f"Workflow paused. Next execution at {instance.next_scheduled_at}")
                    break
                
                # Move to next step
                current_step_order += 1
                instance.current_step = current_step_order
            
            # If all steps completed
            if current_step_order >= len(self.definition.steps):
                instance.current_state = WorkflowState.RESOLVED
                instance.completed_at = datetime.utcnow()
                logger.info(f"Workflow completed successfully: {instance.id}")
        
        except Exception as e:
            logger.error(f"Workflow execution error: {str(e)}")
            instance.current_state = WorkflowState.FAILED
            instance.execution_log.append({
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            })
        
        return instance


# ============================================================================
# WORKFLOW MANAGER (Persistence & Orchestration)
# ============================================================================

class WorkflowManager:
    """Manages workflow definitions and instances"""
    
    def __init__(self, supabase_url: str, supabase_key: str):
        self.supabase = create_client(supabase_url, supabase_key)
    
    async def save_workflow_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Save workflow definition to Supabase"""
        data = definition.to_dict()
        response = self.supabase.table("workflow_definitions").upsert(data).execute()
        logger.info(f"Saved workflow definition: {definition.id}")
        return definition
    
    async def get_workflow_definition(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Retrieve workflow definition"""
        response = self.supabase.table("workflow_definitions").select("*").eq("id", workflow_id).execute()
        if response.data:
            data = response.data[0]
            # Reconstruct objects from JSON
            steps = [WorkflowStep(**step) for step in data.get("steps", [])]
            conditions = [WorkflowCondition(**cond) for cond in data.get("conditions", [])]
            
            return WorkflowDefinition(
                id=data["id"],
                name=data["name"],
                description=data.get("description", ""),
                scenario_type=data.get("scenario_type", ""),
                steps=steps,
                conditions=conditions,
                created_by=data.get("created_by"),
                enabled=data.get("enabled", True),
            )
        return None
    
    async def list_workflow_definitions(self, scenario_type: Optional[str] = None) -> List[WorkflowDefinition]:
        """List all workflow definitions, optionally filtered by scenario"""
        query = self.supabase.table("workflow_definitions").select("*")
        if scenario_type:
            query = query.eq("scenario_type", scenario_type)
        response = query.execute()
        
        definitions = []
        for data in response.data:
            steps = [WorkflowStep(**step) for step in data.get("steps", [])]
            conditions = [WorkflowCondition(**cond) for cond in data.get("conditions", [])]
            definitions.append(WorkflowDefinition(
                id=data["id"],
                name=data["name"],
                description=data.get("description", ""),
                scenario_type=data.get("scenario_type", ""),
                steps=steps,
                conditions=conditions,
                created_by=data.get("created_by"),
                enabled=data.get("enabled", True),
            ))
        return definitions
    
    async def save_workflow_instance(self, instance: WorkflowInstance) -> WorkflowInstance:
        """Save workflow instance to Supabase"""
        data = instance.to_dict()
        response = self.supabase.table("workflow_instances").upsert(data).execute()
        logger.info(f"Saved workflow instance: {instance.id}")
        return instance
    
    async def get_workflow_instance(self, instance_id: str) -> Optional[WorkflowInstance]:
        """Retrieve workflow instance"""
        response = self.supabase.table("workflow_instances").select("*").eq("id", instance_id).execute()
        if response.data:
            data = response.data[0]
            return WorkflowInstance(
                id=data["id"],
                workflow_definition_id=data["workflow_definition_id"],
                subject_email=data["subject_email"],
                subject_id=data["subject_id"],
                current_step=data.get("current_step", 0),
                current_state=WorkflowState(data.get("current_state", "in_progress")),
                metadata=data.get("metadata", {}),
                next_scheduled_at=datetime.fromisoformat(data["next_scheduled_at"]) if data.get("next_scheduled_at") else None,
                created_at=datetime.fromisoformat(data["created_at"]),
                completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
                execution_log=data.get("execution_log", []),
            )
        return None
    
    async def list_active_instances(self, workflow_id: Optional[str] = None) -> List[WorkflowInstance]:
        """List active workflow instances"""
        query = self.supabase.table("workflow_instances").select("*").neq("current_state", "resolved")
        if workflow_id:
            query = query.eq("workflow_definition_id", workflow_id)
        response = query.execute()
        
        instances = []
        for data in response.data:
            instances.append(WorkflowInstance(
                id=data["id"],
                workflow_definition_id=data["workflow_definition_id"],
                subject_email=data["subject_email"],
                subject_id=data["subject_id"],
                current_step=data.get("current_step", 0),
                current_state=WorkflowState(data.get("current_state", "in_progress")),
                metadata=data.get("metadata", {}),
            ))
        return instances
