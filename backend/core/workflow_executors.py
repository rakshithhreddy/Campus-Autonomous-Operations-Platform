"""
Workflow Executors for specific scenarios

Each scenario has its own executor that handles step execution and condition evaluation.
"""

from backend.core.workflow_engine import (
    WorkflowExecutor, WorkflowInstance, WorkflowStep,
    WorkflowStepType, StepStatus
)
from backend.core.erp_integration import get_erp_integration
from backend.core.faculty_email_assistant import ResponseGenerator, EmailCategory
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# ATTENDANCE SCENARIO EXECUTOR
# ============================================================================

class AttendanceScenarioExecutor(WorkflowExecutor):
    """Executor for Student Attendance Follow-up workflow"""
    
    async def execute_step(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Execute a single step in the attendance workflow"""
        
        if step.step_type == WorkflowStepType.SEND_EMAIL:
            return await self._send_email(step, instance)
        
        elif step.step_type == WorkflowStepType.WAIT:
            return await self._wait_step(step, instance)
        
        elif step.step_type == WorkflowStepType.CHECK_CONDITION:
            return await self._check_attendance(step, instance)
        
        elif step.step_type == WorkflowStepType.QUERY_ERP:
            return await self._query_attendance(step, instance)
        
        elif step.step_type == WorkflowStepType.ESCALATE:
            return await self._escalate_to_parent(step, instance)
        
        elif step.step_type == WorkflowStepType.LOG_ACTION:
            return await self._log_action(step, instance)
        
        else:
            return {
                "status": StepStatus.FAILED.value,
                "details": {"error": f"Unknown step type: {step.step_type}"}
            }
    
    async def _send_email(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Send email to student or parent"""
        recipient_type = step.config.get("recipient_type", "student")
        template_name = step.config.get("template_name", "")
        subject = step.config.get("subject", "")
        body = step.config.get("body", "")
        
        recipient_email = instance.subject_email
        if recipient_type == "parent":
            erp = get_erp_integration()
            parent_email = await erp.get_parent_email(instance.subject_id)
            recipient_email = parent_email or instance.metadata.get("parent_email", "parent@unknown.com")
        
        logger.info(f"Sending {template_name} email to {recipient_email}")
        
        # In production, integrate with faculty_email_assistant or Gmail API
        instance.metadata["emails_sent"] = instance.metadata.get("emails_sent", [])
        instance.metadata["emails_sent"].append({
            "to": recipient_email,
            "template": template_name,
            "timestamp": __import__('datetime').datetime.utcnow().isoformat()
        })
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {
                "recipient": recipient_email,
                "template": template_name,
                "message": f"Email sent to {recipient_email}"
            }
        }
    
    async def _wait_step(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Handle wait/delay step"""
        delay_hours = step.config.get("delay_hours", 0)
        logger.info(f"Workflow paused for {delay_hours} hours")
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {
                "delay_hours": delay_hours,
                "message": f"Workflow paused for {delay_hours} hours"
            }
        }
    
    async def _check_attendance(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Check attendance condition"""
        threshold = step.config.get("threshold", 70)
        
        erp = get_erp_integration()
        attendance = await erp.get_student_attendance(instance.subject_id)
        
        if attendance is None:
            return {
                "status": StepStatus.FAILED.value,
                "details": {"error": "Could not fetch attendance from ERP"}
            }
        
        instance.metadata["last_attendance_check"] = attendance
        
        is_above_threshold = attendance >= threshold
        logger.info(f"Attendance check: {attendance}% (threshold: {threshold}%) - {'PASS' if is_above_threshold else 'FAIL'}")
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {
                "attendance": attendance,
                "threshold": threshold,
                "condition_met": is_above_threshold,
                "message": f"Attendance: {attendance}%"
            }
        }
    
    async def _query_attendance(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Query attendance from ERP"""
        erp = get_erp_integration()
        attendance = await erp.get_student_attendance(instance.subject_id)
        
        result_key = step.config.get("store_result_in", "attendance_result")
        instance.metadata[result_key] = attendance or 0
        
        logger.info(f"ERP Query - Attendance: {attendance}%")
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {
                "query": "attendance_percentage",
                "result": attendance,
                "stored_in": result_key
            }
        }
    
    async def _escalate_to_parent(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Escalate by contacting parent"""
        erp = get_erp_integration()
        parent_email = await erp.get_parent_email(instance.subject_id)
        
        if not parent_email:
            return {
                "status": StepStatus.FAILED.value,
                "details": {"error": "Parent email not found in ERP"}
            }
        
        instance.metadata["parent_email"] = parent_email
        instance.metadata["escalation_level"] = "parent"
        instance.metadata["parent_contacted"] = True
        
        logger.info(f"Escalated to parent: {parent_email}")
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {
                "escalation_type": "parent_contact",
                "parent_email": parent_email,
                "message": "Escalated to parent"
            }
        }
    
    async def _log_action(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Log workflow action"""
        action_desc = step.config.get("action_description", "")
        severity = step.config.get("severity", "info")
        notify_admin = step.config.get("notify_admin", False)
        
        logger.log(
            level=logging.WARNING if severity == "high" else logging.INFO,
            msg=f"Workflow Action [{severity}]: {action_desc}"
        )
        
        instance.metadata["last_action"] = {
            "description": action_desc,
            "severity": severity,
            "timestamp": __import__('datetime').datetime.utcnow().isoformat()
        }
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {
                "action": action_desc,
                "severity": severity,
                "admin_notified": notify_admin
            }
        }


# ============================================================================
# ASSIGNMENT SCENARIO EXECUTOR
# ============================================================================

class AssignmentScenarioExecutor(WorkflowExecutor):
    """Executor for Assignment Deadline Reminder workflow"""
    
    async def execute_step(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Execute assignment scenario step"""
        
        if step.step_type == WorkflowStepType.SEND_EMAIL:
            return await self._send_email(step, instance)
        
        elif step.step_type == WorkflowStepType.WAIT:
            return await self._wait_step(step, instance)
        
        elif step.step_type == WorkflowStepType.QUERY_ERP:
            return await self._check_submission(step, instance)
        
        elif step.step_type == WorkflowStepType.ESCALATE:
            return await self._handle_non_submission(step, instance)
        
        else:
            return {
                "status": StepStatus.FAILED.value,
                "details": {"error": f"Unknown step type: {step.step_type}"}
            }
    
    async def _send_email(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Send assignment reminder email"""
        recipient_type = step.config.get("recipient_type", "student")
        template_name = step.config.get("template_name", "")
        
        recipient_email = instance.subject_email
        if recipient_type == "parent":
            erp = get_erp_integration()
            parent_email = await erp.get_parent_email(instance.subject_id)
            recipient_email = parent_email or "parent@unknown.com"
        
        instance.metadata["emails_sent"] = instance.metadata.get("emails_sent", [])
        instance.metadata["emails_sent"].append({
            "to": recipient_email,
            "template": template_name,
            "timestamp": __import__('datetime').datetime.utcnow().isoformat()
        })
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {"recipient": recipient_email, "template": template_name}
        }
    
    async def _wait_step(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Wait step"""
        delay_hours = step.config.get("delay_hours", 0)
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {"delay_hours": delay_hours}
        }
    
    async def _check_submission(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Check if assignment was submitted"""
        erp = get_erp_integration()
        assignment_id = instance.metadata.get("assignment_id", "unknown")
        submitted = await erp.check_assignment_submitted(instance.subject_id, assignment_id)
        
        result_key = step.config.get("store_result_in", "submission_status")
        instance.metadata[result_key] = submitted
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {"submitted": submitted, "assignment_id": assignment_id}
        }
    
    async def _handle_non_submission(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Handle non-submission scenario"""
        deduction_pct = step.config.get("deduction_percentage", 0)
        notify_parent = step.config.get("notify_parent", False)
        
        instance.metadata["mark_deduction"] = deduction_pct
        instance.metadata["parent_notified"] = notify_parent
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {
                "mark_deduction": deduction_pct,
                "parent_notified": notify_parent
            }
        }


# ============================================================================
# FEE COLLECTION SCENARIO EXECUTOR
# ============================================================================

class FeeCollectionScenarioExecutor(WorkflowExecutor):
    """Executor for Fee Payment Collection workflow"""
    
    async def execute_step(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Execute fee collection step"""
        
        if step.step_type == WorkflowStepType.SEND_EMAIL:
            return await self._send_fee_reminder(step, instance)
        
        elif step.step_type == WorkflowStepType.WAIT:
            return await self._wait_step(step, instance)
        
        elif step.step_type == WorkflowStepType.QUERY_ERP:
            return await self._check_payment_status(step, instance)
        
        elif step.step_type == WorkflowStepType.ESCALATE:
            return await self._escalate_fee_issue(step, instance)
        
        else:
            return {
                "status": StepStatus.FAILED.value,
                "details": {"error": f"Unknown step type: {step.step_type}"}
            }
    
    async def _send_fee_reminder(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Send fee reminder to parent"""
        erp = get_erp_integration()
        parent_email = await erp.get_parent_email(instance.subject_id)
        fee_amount = await erp.get_fee_amount(instance.subject_id)
        
        instance.metadata["fees_reminded"] = instance.metadata.get("fees_reminded", 0) + 1
        instance.metadata["fee_amount"] = fee_amount
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {
                "recipient": parent_email,
                "amount": fee_amount,
                "reminder_count": instance.metadata["fees_reminded"]
            }
        }
    
    async def _wait_step(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Wait step"""
        delay_hours = step.config.get("delay_hours", 0)
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {"delay_hours": delay_hours}
        }
    
    async def _check_payment_status(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Check if fee is paid"""
        erp = get_erp_integration()
        paid = await erp.check_fee_paid(instance.subject_id)
        
        result_key = step.config.get("store_result_in", "payment_status")
        instance.metadata[result_key] = paid
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {"paid": paid}
        }
    
    async def _escalate_fee_issue(self, step: WorkflowStep, instance: WorkflowInstance) -> Dict[str, Any]:
        """Escalate unpaid fee to principal"""
        action = step.config.get("action", "restrict_access")
        
        instance.metadata["escalation_level"] = "principal"
        instance.metadata["access_restricted"] = action == "restrict_access"
        
        return {
            "status": StepStatus.SUCCESS.value,
            "details": {
                "escalation": "principal_notification",
                "action": action
            }
        }


# ============================================================================
# SCENARIO EXECUTOR FACTORY
# ============================================================================

def get_executor_for_scenario(scenario_type: str) -> WorkflowExecutor:
    """Get appropriate executor for scenario type"""
    executors = {
        "attendance": AttendanceScenarioExecutor,
        "assignment": AssignmentScenarioExecutor,
        "fee": FeeCollectionScenarioExecutor,
        # Can add more scenario executors here
    }
    
    executor_class = executors.get(scenario_type)
    if not executor_class:
        raise ValueError(f"No executor found for scenario: {scenario_type}")
    
    # Return a dummy definition - this will be replaced with actual in routes
    from backend.core.workflow_engine import WorkflowDefinition
    dummy_definition = WorkflowDefinition(name=f"{scenario_type}_executor")
    
    return executor_class(dummy_definition)
