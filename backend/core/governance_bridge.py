"""
Governance Bridge - Linking AI Agent actions to the Institutional Governance Store.
This ensures all agent-executed tasks are recorded as verifiable missions.
"""

import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from .governance_store import get_governance_store
from .mission_state import MissionRecord, MissionStep, MissionState
from .policy_engine import PolicyEngine

logger = logging.getLogger(__name__)

class GovernanceBridge:
    def __init__(self):
        self.store = get_governance_store()
        self.engine = PolicyEngine()

    def start_mission_from_agent(
        self,
        user_id: str,
        tenant_id: str,
        title: str,
        message: str,
        classification: Any
    ) -> str:
        """
        Create a new mission when the agent starts a task.
        """
        try:
            # Evaluate institutional policies
            policy_result = self.engine.evaluate_task(message, classification.category.value if hasattr(classification, 'category') else "unknown")
            risk_level = policy_result.get("risk_level", "low")
            requires_approval = policy_result.get("requires_approval", False)

            # Map complexity to initial steps
            initial_steps = [
                {
                    "title": "Institutional Risk Analysis",
                    "description": f"Policy check: {policy_result.get('reason', 'Standard task evaluation')}",
                    "action_type": "governance",
                    "risk_level": risk_level,
                    "requires_approval": requires_approval,
                    "approver_roles": policy_result.get("approver_roles", ["manager"]),
                },
                {
                    "title": "Analyze Request",
                    "description": message[:200],
                    "action_type": "analysis",
                    "risk_level": "low",
                    "requires_approval": False,
                }
            ]

            mission = self.store.create_mission(
                user_id=user_id,
                tenant_id=tenant_id,
                title=title,
                description=message,
                steps=initial_steps,
            )
            
            # If policy requires approval, transition mission to WAITING_APPROVAL
            if requires_approval:
                self.store.transition_mission(
                    mission_id=mission.mission_id,
                    next_state=MissionState.WAITING_APPROVAL,
                    actor_id="system",
                    reason="Institutional policy requires approval for this task category."
                )

            logger.info(f"[GovernanceBridge] Mission created: {mission.mission_id} (Risk: {risk_level}, Approval: {requires_approval})")
            return mission.mission_id
        except Exception as e:
            logger.error(f"[GovernanceBridge] Failed to create mission: {e}")
            return ""

    def record_step_execution(
        self,
        mission_id: str,
        step_title: str,
        action_type: str,
        risk_level: str,
        params: Dict[str, Any],
        result: Any,
        success: bool = True
    ):
        """
        Record a tool/primitive execution in the mission trace.
        """
        if not mission_id:
            return

        try:
            mission = self.store.get_mission(mission_id)
            if not mission:
                return

            # Add a new step for this action
            step = MissionStep(
                id=str(uuid.uuid4()),
                title=step_title,
                description=f"Executed {action_type}",
                action_type=action_type,
                risk_level=risk_level,
                requires_approval=False,  # If we reached here, it was either safe or approved
                state="completed" if success else "failed",
                metadata={"params": params, "result_preview": str(result)[:500]},
                updated_at=datetime.utcnow().isoformat()
            )
            
            mission.steps.append(step)
            
            # Record audit event
            self.store._persist("mission_steps", {
                "id": step.id,
                "mission_id": mission_id,
                "title": step.title,
                "action_type": step.action_type,
                "state": step.state,
                "metadata": step.metadata
            })
            
            logger.info(f"[GovernanceBridge] Step recorded for mission {mission_id}: {step_title}")
        except Exception as e:
            logger.error(f"[GovernanceBridge] Failed to record step: {e}")

    def complete_mission(self, mission_id: str, final_answer: str):
        """
        Mark the mission as completed.
        """
        if not mission_id:
            return

        try:
            mission = self.store.get_mission(mission_id)
            if not mission:
                return

            self.store.transition_mission(
                mission_id=mission_id,
                next_state=MissionState.COMPLETED,
                actor_id="system",
                reason="Agent completed the task",
                metadata={"final_answer": final_answer[:1000]}
            )
            logger.info(f"[GovernanceBridge] Mission completed: {mission_id}")
        except Exception as e:
            logger.error(f"[GovernanceBridge] Failed to complete mission: {e}")

_bridge = None

def get_governance_bridge() -> GovernanceBridge:
    global _bridge
    if _bridge is None:
        _bridge = GovernanceBridge()
    return _bridge
