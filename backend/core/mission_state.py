"""
Mission state and event model for governed execution.

This module provides a canonical lifecycle for a mission so approvals,
evidence,
and trust metrics can derive from the same state transitions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class MissionState(str, Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    WAITING_INPUT = "waiting_input"
    WAITING_APPROVAL = "waiting_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


MISSION_STATE_TRANSITIONS: Dict[MissionState, set[MissionState]] = {
    MissionState.DRAFT: {MissionState.PLANNED, MissionState.CANCELLED},
    MissionState.PLANNED: {MissionState.WAITING_INPUT, MissionState.WAITING_APPROVAL, MissionState.RUNNING, MissionState.CANCELLED},
    MissionState.WAITING_INPUT: {MissionState.PLANNED, MissionState.WAITING_APPROVAL, MissionState.CANCELLED},
    MissionState.WAITING_APPROVAL: {MissionState.PLANNED, MissionState.RUNNING, MissionState.CANCELLED},
    MissionState.RUNNING: {MissionState.COMPLETED, MissionState.FAILED, MissionState.ROLLED_BACK, MissionState.CANCELLED},
    MissionState.COMPLETED: set(),
    MissionState.FAILED: {MissionState.ROLLED_BACK, MissionState.CANCELLED},
    MissionState.ROLLED_BACK: {MissionState.CANCELLED},
    MissionState.CANCELLED: set(),
}


@dataclass
class MissionStep:
    id: str
    title: str
    description: str = ""
    action_type: str = ""
    risk_level: str = "low"
    requires_approval: bool = False
    approver_roles: List[str] = field(default_factory=list)
    state: str = "pending"
    owner_role: Optional[str] = None
    approval_decision_id: Optional[str] = None
    evidence_artifact_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MissionEvent:
    id: str
    mission_id: str
    actor_id: str
    event_type: str
    previous_state: Optional[str]
    next_state: Optional[str]
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MissionRecord:
    mission_id: str
    user_id: str
    tenant_id: str
    title: str
    description: str = ""
    state: MissionState = MissionState.DRAFT
    policy_version: str = "v1"
    steps: List[MissionStep] = field(default_factory=list)
    approvals: List[Dict[str, Any]] = field(default_factory=list)
    evidence_artifact_ids: List[str] = field(default_factory=list)
    trace_events: List[MissionEvent] = field(default_factory=list)
    trace_completeness: float = 0.0
    policy_compliance: float = 0.0
    version: int = 0  # Item 9: optimistic lock counter, incremented on each state transition
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None

    def add_event(self, event: MissionEvent) -> None:
        self.trace_events.append(event)
        self.updated_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "title": self.title,
            "description": self.description,
            "state": self.state.value,
            "policy_version": self.policy_version,
            "steps": [step.to_dict() for step in self.steps],
            "approvals": self.approvals,
            "evidence_artifact_ids": self.evidence_artifact_ids,
            "trace_events": [event.to_dict() for event in self.trace_events],
            "trace_completeness": self.trace_completeness,
            "policy_compliance": self.policy_compliance,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }


def is_transition_allowed(current_state: MissionState, next_state: MissionState) -> bool:
    return next_state in MISSION_STATE_TRANSITIONS.get(current_state, set())


def advance_mission_state(
    mission: MissionRecord,
    next_state: MissionState,
    actor_id: str,
    reason: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> MissionEvent:
    if not is_transition_allowed(mission.state, next_state):
        raise ValueError(f"Invalid transition from {mission.state.value} to {next_state.value}")

    previous_state = mission.state
    mission.state = next_state
    mission.version += 1  # Item 9: increment optimistic lock version
    mission.updated_at = datetime.utcnow().isoformat()
    if next_state in {MissionState.COMPLETED, MissionState.ROLLED_BACK, MissionState.CANCELLED}:
        mission.completed_at = mission.completed_at or mission.updated_at

    event = MissionEvent(
        id=str(uuid.uuid4()),
        mission_id=mission.mission_id,
        actor_id=actor_id,
        event_type="mission_state_changed",
        previous_state=previous_state.value,
        next_state=next_state.value,
        reason=reason,
        metadata=metadata or {},
    )
    mission.add_event(event)
    return event


def calculate_trace_completeness(mission: MissionRecord) -> float:
    """Item 11: Multi-dimension trace completeness per step.

    Each step contributes 1.0 to the total score, broken into:
    - 0.4 — state recorded (not pending)
    - 0.3 — evidence artifacts attached
    - 0.2 — approval handled (approved or not required)
    - 0.1 — timing metadata captured (started_at + completed_at)
    """
    if not mission.steps:
        return 0.0

    total_score = 0.0
    for step in mission.steps:
        step_score = 0.0
        if step.state and step.state != "pending":
            step_score += 0.4
        if step.evidence_artifact_ids:
            step_score += 0.3
        if step.approval_decision_id or not step.requires_approval:
            step_score += 0.2
        if step.metadata.get("started_at") and step.metadata.get("completed_at"):
            step_score += 0.1
        total_score += min(step_score, 1.0)

    return round((total_score / len(mission.steps)) * 100, 2)


def calculate_policy_compliance(mission: MissionRecord) -> float:
    """Item 10: Risk-weighted compliance score.
    Higher-risk unapproved steps penalise the score more than low-risk ones.
    """
    if not mission.steps:
        return 100.0

    risk_weights = {"low": 1, "medium": 2, "high": 3, "critical": 5}
    total_weight = 0
    compliant_weight = 0

    for step in mission.steps:
        w = risk_weights.get(step.risk_level, 1)
        total_weight += w
        if step.requires_approval and not step.approval_decision_id:
            continue  # Non-compliant: unapproved high-risk step
        compliant_weight += w

    return round((compliant_weight / total_weight) * 100, 2) if total_weight else 100.0