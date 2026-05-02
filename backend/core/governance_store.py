"""
Append-only governance store for missions, approvals, policy rules, and trust metrics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

try:
    from ..database_supabase import get_supabase_client
except ImportError:  # pragma: no cover
    from backend.database_supabase import get_supabase_client

from .evidence_vault import get_evidence_vault
from .mission_state import MissionEvent, MissionRecord, MissionState, MissionStep, advance_mission_state, calculate_policy_compliance, calculate_trace_completeness
from .policy_engine import PolicyEngine, PolicyRule
from .telemetry import get_telemetry


@dataclass
class ApprovalDecisionRecord:
    decision_id: str
    mission_id: str
    step_id: str
    tenant_id: str
    user_id: str
    approver_id: str
    approver_roles: List[str]
    decision: str
    reason: str
    policy_version: str
    policy_rule_id: Optional[str] = None
    content_hash: str = ""  # Item 7: SHA-256 tamper seal
    policy_rule_snapshot: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        import hashlib, json
        payload = json.dumps({
            "decision_id": self.decision_id,
            "mission_id": self.mission_id,
            "step_id": self.step_id,
            "approver_id": self.approver_id,
            "decision": self.decision,
            "reason": self.reason,
            "policy_version": self.policy_version,
            "created_at": self.created_at,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ManualOverrideRecord:
    override_id: str
    mission_id: str
    step_id: str
    tenant_id: str
    actor_id: str
    reason: str
    override_action: str
    reviewer_visibility_notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _build_step(step: Dict[str, Any]) -> MissionStep:
    allowed_keys = {
        "id",
        "title",
        "description",
        "action_type",
        "risk_level",
        "requires_approval",
        "approver_roles",
        "state",
        "owner_role",
        "approval_decision_id",
        "evidence_artifact_ids",
        "metadata",
        "created_at",
        "updated_at",
    }
    clean_step = {key: value for key, value in step.items() if key in allowed_keys}
    clean_step.setdefault("id", str(uuid.uuid4()))
    clean_step.setdefault("title", clean_step["id"])
    return MissionStep(**clean_step)


class GovernanceStore:
    def __init__(self) -> None:
        self.policy_engine = PolicyEngine()
        self._client = get_supabase_client()
        self._missions: Dict[str, MissionRecord] = {}
        self._approvals: Dict[str, ApprovalDecisionRecord] = {}
        self._overrides: Dict[str, List[ManualOverrideRecord]] = {}
        self._events: List[MissionEvent] = []
        self._policy_rules: Dict[str, PolicyRule] = {rule.rule_id: rule for rule in self.policy_engine.rules}
        self._idempotency_index: Dict[str, str] = {}

    def _idempotency_scope(self, tenant_id: str, user_id: str, idempotency_key: str) -> str:
        return f"{tenant_id}:{user_id}:{idempotency_key.strip()}"

    def required_approvals_for_step(self, mission: MissionRecord, step: MissionStep) -> int:
        decision = self.policy_engine.evaluate_step(mission, step)
        return max(1, int(decision.min_approvals or 1))

    def count_step_approvals(self, mission_id: str, step_id: str) -> int:
        return len(
            [
                item
                for item in self._approvals.values()
                if item.mission_id == mission_id and item.step_id == step_id and item.decision in {"approve", "approved"}
            ]
        )

    def _persist(self, table_name: str, payload: Dict[str, Any]) -> None:
        if not self._client:
            return
        try:
            self._client.table(table_name).insert(payload).execute()
        except Exception:
            # Persistence must never block the in-memory runtime.
            return

    def create_mission(
        self,
        *,
        user_id: str,
        tenant_id: str,
        title: str,
        description: str,
        steps: List[Dict[str, Any]],
        policy_version: str = "v1",
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> MissionRecord:
        if idempotency_key and idempotency_key.strip():
            scope = self._idempotency_scope(tenant_id, user_id, idempotency_key)
            existing_mission_id = self._idempotency_index.get(scope)
            if existing_mission_id and existing_mission_id in self._missions:
                return self._missions[existing_mission_id]

        mission = MissionRecord(
            mission_id=str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            title=title,
            description=description,
            policy_version=policy_version,
            steps=[_build_step(step) for step in steps],
        )

        evaluation = self.policy_engine.evaluate_mission(mission)
        mission.trace_completeness = calculate_trace_completeness(mission)
        mission.policy_compliance = calculate_policy_compliance(mission)
        mission.state = MissionState.WAITING_APPROVAL if evaluation["requires_approval"] else MissionState.PLANNED

        creation_event = MissionEvent(
            id=str(uuid.uuid4()),
            mission_id=mission.mission_id,
            actor_id=user_id,
            event_type="mission_created",
            previous_state=None,
            next_state=mission.state.value,
            reason="mission created",
            metadata={"policy_version": policy_version, "evaluation": evaluation, "request_id": request_id},
        )
        mission.add_event(creation_event)
        self._missions[mission.mission_id] = mission
        if idempotency_key and idempotency_key.strip():
            self._idempotency_index[self._idempotency_scope(tenant_id, user_id, idempotency_key)] = mission.mission_id
        self._events.append(creation_event)
        self._persist(
            "missions",
            {
                "mission_id": mission.mission_id,
                "user_id": mission.user_id,
                "tenant_id": mission.tenant_id,
                "title": mission.title,
                "description": mission.description,
                "state": mission.state.value,
                "policy_version": mission.policy_version,
                "trace_completeness": mission.trace_completeness,
                "policy_compliance": mission.policy_compliance,
                "metadata": {"evaluation": evaluation},
            },
        )
        for step in mission.steps:
            self._persist(
                "mission_steps",
                {
                    "id": step.id,
                    "mission_id": mission.mission_id,
                    "title": step.title,
                    "description": step.description,
                    "action_type": step.action_type,
                    "risk_level": step.risk_level,
                    "requires_approval": step.requires_approval,
                    "approver_roles": step.approver_roles,
                    "state": step.state,
                    "owner_role": step.owner_role,
                    "approval_decision_id": step.approval_decision_id,
                    "evidence_artifact_ids": step.evidence_artifact_ids,
                    "metadata": step.metadata,
                },
            )
        self._persist(
            "audit_events",
            {
                "event_id": creation_event.id,
                "mission_id": mission.mission_id,
                "actor_id": mission.user_id,
                "tenant_id": mission.tenant_id,
                "action": "mission_created",
                "next_state": mission.state.value,
                "reason": "mission created",
                "policy_version": mission.policy_version,
                "metadata": {
                    **creation_event.metadata,
                    "idempotency_key": bool(idempotency_key and idempotency_key.strip()),
                },
            },
        )

        get_telemetry().record_event(
            "mission_created",
            tenant_id=tenant_id,
            user_id=user_id,
            mission_id=mission.mission_id,
            request_id=request_id,
            properties={
                "approval_required": evaluation["requires_approval"],
                "idempotency_key_present": bool(idempotency_key and idempotency_key.strip()),
            },
        )
        return mission

    def list_missions(self, user_id: str, tenant_id: str) -> List[MissionRecord]:
        """Item 5: tenant_id is mandatory — enforces cross-tenant isolation."""
        missions = [
            m for m in self._missions.values()
            if m.user_id == user_id and m.tenant_id == tenant_id
        ]
        return sorted(missions, key=lambda m: m.created_at, reverse=True)

    def get_mission(self, mission_id: str, tenant_id: Optional[str] = None) -> Optional[MissionRecord]:
        """Item 5: if tenant_id supplied, cross-tenant access returns None."""
        mission = self._missions.get(mission_id)
        if mission and tenant_id and mission.tenant_id != tenant_id:
            return None  # Cross-tenant access denied
        return mission

    def record_approval(
        self,
        *,
        mission_id: str,
        step_id: str,
        tenant_id: str,
        user_id: str,
        approver_id: str,
        approver_roles: List[str],
        decision: str,
        reason: str,
        policy_version: str,
        policy_rule_id: Optional[str] = None,
    ) -> ApprovalDecisionRecord:
        # Item 7: prevent self-approval for multi-approver steps
        if approver_id == user_id:
            target_step = next(
                (s for s in (self._missions.get(mission_id) or MissionRecord.__new__(MissionRecord)).steps
                 if getattr(s, 'id', None) == step_id), None
            ) if mission_id in self._missions else None
            required = self.required_approvals_for_step(
                self._missions[mission_id],
                next((s for s in self._missions[mission_id].steps if s.id == step_id),
                     None) or MissionStep(id=step_id, title=step_id)
            ) if mission_id in self._missions else 1
            if required > 1:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail={"error": "Self-approval not allowed for multi-approver steps", "code": "self_approval_denied"})

        existing_for_actor = next(
            (
                item
                for item in self._approvals.values()
                if item.mission_id == mission_id and item.step_id == step_id and item.approver_id == approver_id
            ),
            None,
        )
        if existing_for_actor:
            return existing_for_actor

        decision_record = ApprovalDecisionRecord(
            decision_id=str(uuid.uuid4()),
            mission_id=mission_id,
            step_id=step_id,
            tenant_id=tenant_id,
            user_id=user_id,
            approver_id=approver_id,
            approver_roles=approver_roles,
            decision=decision,
            reason=reason,
            policy_version=policy_version,
            policy_rule_id=policy_rule_id,
            # content_hash auto-computed in __post_init__ (Item 7)
        )
        # Item 7: append-only — never overwrite an existing key
        if decision_record.decision_id not in self._approvals:
            self._approvals[decision_record.decision_id] = decision_record
        self._persist(
            "approval_decisions",
            {
                "decision_id": decision_record.decision_id,
                "mission_id": mission_id,
                "step_id": step_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "approver_id": approver_id,
                "approver_roles": approver_roles,
                "decision": decision,
                "reason": reason,
                "policy_version": policy_version,
                "policy_rule_id": policy_rule_id,
                "content_hash": decision_record.content_hash,
            },
        )

        mission = self._missions.get(mission_id)
        if mission:
            mission.approvals.append(decision_record.to_dict())
            mission.trace_completeness = calculate_trace_completeness(mission)
            mission.policy_compliance = calculate_policy_compliance(mission)
            event = MissionEvent(
                id=str(uuid.uuid4()),
                mission_id=mission_id,
                actor_id=approver_id,
                event_type="approval_recorded",
                previous_state=mission.state.value,
                next_state=mission.state.value,
                reason=reason,
                metadata={"decision": decision, "step_id": step_id, "policy_rule_id": policy_rule_id},
            )
            mission.add_event(event)
            self._events.append(event)
            self._persist(
                "mission_state_transitions",
                {
                    "id": event.id,
                    "mission_id": mission_id,
                    "actor_id": approver_id,
                    "previous_state": event.previous_state,
                    "next_state": event.next_state,
                    "reason": reason,
                    "metadata": event.metadata,
                },
            )
            self._persist(
                "audit_events",
                {
                    "event_id": event.id,
                    "mission_id": mission_id,
                    "actor_id": approver_id,
                    "tenant_id": tenant_id,
                    "action": "approval_recorded",
                    "previous_state": event.previous_state,
                    "next_state": event.next_state,
                    "reason": reason,
                    "policy_version": policy_version,
                    "metadata": event.metadata,
                },
            )

        get_telemetry().record_event(
            "approval_recorded",
            tenant_id=tenant_id,
            user_id=user_id,
            mission_id=mission_id,
            properties={"decision": decision, "step_id": step_id},
        )
        return decision_record

    def record_step_failure(
        self,
        *,
        mission_id: str,
        step_id: str,
        actor_id: str,
        reason: str,
        retry_strategy: Optional[str] = None,
        fallback_strategy: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        mission = self._missions.get(mission_id)
        if not mission:
            raise KeyError(f"Mission not found: {mission_id}")

        step = next((item for item in mission.steps if item.id == step_id), None)
        if not step:
            raise KeyError(f"Step not found: {step_id}")

        failure_record = {
            "reason": reason,
            "retry_strategy": retry_strategy,
            "fallback_strategy": fallback_strategy,
            "metadata": metadata or {},
            "actor_id": actor_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        history = list(step.metadata.get("failure_history", []))
        history.append(failure_record)
        step.metadata["failure_history"] = history
        step.state = "failed"
        step.updated_at = datetime.utcnow().isoformat()

        event = MissionEvent(
            id=str(uuid.uuid4()),
            mission_id=mission_id,
            actor_id=actor_id,
            event_type="step_failed",
            previous_state=mission.state.value,
            next_state=mission.state.value,
            reason=reason,
            metadata={
                "step_id": step_id,
                "retry_strategy": retry_strategy,
                "fallback_strategy": fallback_strategy,
                "failure_metadata": metadata or {},
            },
        )
        mission.add_event(event)
        self._events.append(event)
        self._persist(
            "audit_events",
            {
                "event_id": event.id,
                "mission_id": mission_id,
                "actor_id": actor_id,
                "tenant_id": mission.tenant_id,
                "action": "step_failed",
                "previous_state": event.previous_state,
                "next_state": event.next_state,
                "reason": reason,
                "policy_version": mission.policy_version,
                "metadata": event.metadata,
            },
        )
        get_telemetry().record_event(
            "step_failed",
            tenant_id=mission.tenant_id,
            user_id=mission.user_id,
            mission_id=mission_id,
            properties={
                "step_id": step_id,
                "retry_strategy": retry_strategy,
                "fallback_strategy": fallback_strategy,
            },
        )
        return failure_record

    def record_manual_override(
        self,
        *,
        mission_id: str,
        step_id: str,
        tenant_id: str,
        actor_id: str,
        reason: str,
        override_action: str,
        reviewer_visibility_notes: Optional[str] = None,
    ) -> ManualOverrideRecord:
        mission = self._missions.get(mission_id)
        if not mission:
            raise KeyError(f"Mission not found: {mission_id}")

        override_record = ManualOverrideRecord(
            override_id=str(uuid.uuid4()),
            mission_id=mission_id,
            step_id=step_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            reason=reason,
            override_action=override_action,
            reviewer_visibility_notes=reviewer_visibility_notes,
        )
        self._overrides.setdefault(mission_id, []).append(override_record)
        self._persist(
            "audit_events",
            {
                "event_id": str(uuid.uuid4()),
                "mission_id": mission_id,
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "action": "manual_override_recorded",
                "previous_state": mission.state.value,
                "next_state": mission.state.value,
                "reason": "manual override recorded",
                "policy_version": mission.policy_version,
                "metadata": {
                    "step_id": step_id,
                    "override_action": override_action,
                    "sensitive_reason": True,
                },
            },
        )
        get_telemetry().record_event(
            "manual_override_recorded",
            tenant_id=tenant_id,
            user_id=mission.user_id,
            mission_id=mission_id,
            properties={"step_id": step_id, "override_action": override_action},
        )
        return override_record

    def list_manual_overrides(self, mission_id: str) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self._overrides.get(mission_id, [])]

    def list_pending_approvals(self, tenant_id: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pending: List[Dict[str, Any]] = []
        for mission in self._missions.values():
            if tenant_id and mission.tenant_id != tenant_id:
                continue
            if user_id and mission.user_id != user_id:
                continue
            for step in mission.steps:
                if step.requires_approval and not step.approval_decision_id:
                    required_approvals = self.required_approvals_for_step(mission, step)
                    current_approvals = self.count_step_approvals(mission.mission_id, step.id)
                    pending.append(
                        {
                            "mission_id": mission.mission_id,
                            "mission_title": mission.title,
                            "step_id": step.id,
                            "step_title": step.title,
                            "risk_level": step.risk_level,
                            "approver_roles": step.approver_roles,
                            "required_approvals": required_approvals,
                            "current_approvals": current_approvals,
                            "state": mission.state.value,
                            "created_at": mission.created_at,
                        }
                    )
        return pending

    def transition_mission(
        self,
        mission_id: str,
        next_state: MissionState,
        actor_id: str,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MissionEvent:
        mission = self._missions.get(mission_id)
        if not mission:
            raise KeyError(f"Mission not found: {mission_id}")
        event = advance_mission_state(mission, next_state, actor_id=actor_id, reason=reason, metadata=metadata)
        self._events.append(event)
        return event

    def list_policy_rules(self) -> List[Dict[str, Any]]:
        return [rule.to_dict() for rule in self._policy_rules.values()]

    def upsert_policy_rule(self, rule: PolicyRule) -> PolicyRule:
        self._policy_rules[rule.rule_id] = rule
        self.policy_engine.upsert_rule(rule)
        self._persist("policy_rules", rule.to_dict())
        return rule

    def get_trust_summary(self, tenant_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        if user_id:
            missions = self.list_missions(user_id=user_id, tenant_id=tenant_id)
        else:
            missions = [mission for mission in self._missions.values() if tenant_id is None or mission.tenant_id == tenant_id]

        if not missions:
            return {
                "mission_count": 0,
                "trace_completeness": 0.0,
                "policy_compliance": 0.0,
                "approval_backlog": 0,
                "mission_states": {},
            }

        state_counts: Dict[str, int] = {}
        trace_total = 0.0
        compliance_total = 0.0
        for mission in missions:
            state_counts[mission.state.value] = state_counts.get(mission.state.value, 0) + 1
            trace_total += mission.trace_completeness
            compliance_total += mission.policy_compliance

        return {
            "mission_count": len(missions),
            "trace_completeness": round(trace_total / len(missions), 2),
            "policy_compliance": round(compliance_total / len(missions), 2),
            "approval_backlog": len(self.list_pending_approvals(tenant_id=tenant_id, user_id=user_id)),
            "mission_states": state_counts,
        }

    def export_mission_bundle(self, mission_id: str) -> Dict[str, Any]:
        mission = self._missions.get(mission_id)
        if not mission:
            raise KeyError(f"Mission not found: {mission_id}")
        return {
            "mission": mission.to_dict(),
            "evidence": get_evidence_vault().export_bundle(mission_id),
            "approvals": [approval.to_dict() for approval in self._approvals.values() if approval.mission_id == mission_id],
        }


_governance_store: Optional[GovernanceStore] = None


def get_governance_store() -> GovernanceStore:
    global _governance_store
    if _governance_store is None:
        _governance_store = GovernanceStore()
    return _governance_store