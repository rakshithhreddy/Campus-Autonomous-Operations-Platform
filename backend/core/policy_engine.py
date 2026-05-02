"""
Policy and approval engine for governed execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import uuid

from .mission_state import MissionRecord, MissionStep


RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class PolicyRule:
    rule_id: str
    name: str
    risk_level: str
    keywords: List[str] = field(default_factory=list)
    required_roles: List[str] = field(default_factory=list)
    min_approvals: int = 1
    active: bool = True
    version: str = "v1"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyDecision:
    decision_id: str
    mission_id: str
    step_id: str
    requires_approval: bool
    risk_level: str
    reason: str
    policy_rule_id: Optional[str] = None
    required_roles: List[str] = field(default_factory=list)
    min_approvals: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PolicyEngine:
    def __init__(self, rules: Optional[List[PolicyRule]] = None):
        self.rules = rules or self._default_rules()

    def _default_rules(self) -> List[PolicyRule]:
        return [
            PolicyRule(
                rule_id="policy_approval_high_risk",
                name="High-risk actions require approval",
                risk_level="high",
                keywords=["delete", "revoke", "send", "approve", "export", "publish", "pay", "invite"],
                required_roles=["admin", "manager", "reviewer"],
                min_approvals=1,
            ),
            PolicyRule(
                rule_id="policy_approval_critical_risk",
                name="Critical actions require multi-approval",
                risk_level="critical",
                keywords=["payment", "credential", "identity", "secret", "bulk", "mass"],
                required_roles=["admin", "security", "manager"],
                min_approvals=2,
            ),
        ]

    def classify_risk(self, step: MissionStep) -> str:
        candidate_text = " ".join(
            part for part in [step.title, step.description, step.action_type, step.metadata.get("category", "")] if part
        ).lower()
        for rule in sorted(self.rules, key=lambda item: RISK_ORDER.get(item.risk_level, 0), reverse=True):
            if any(keyword in candidate_text for keyword in rule.keywords):
                return rule.risk_level

        if step.requires_approval:
            return step.risk_level if step.risk_level in RISK_ORDER else "medium"

        return step.risk_level if step.risk_level in RISK_ORDER else "low"

    def evaluate_step(self, mission: MissionRecord, step: MissionStep) -> PolicyDecision:
        risk_level = self.classify_risk(step)
        matching_rule = next(
            (
                rule
                for rule in sorted(self.rules, key=lambda item: RISK_ORDER.get(item.risk_level, 0), reverse=True)
                if rule.active
                and rule.risk_level == risk_level
                and any(keyword in f"{step.title} {step.description} {step.action_type}".lower() for keyword in rule.keywords)
            ),
            None,
        )

        requires_approval = RISK_ORDER.get(risk_level, 1) >= RISK_ORDER["high"] or step.requires_approval
        required_roles = matching_rule.required_roles if matching_rule else (step.approver_roles or ["manager"])
        rule_min_approvals = matching_rule.min_approvals if matching_rule else 1
        min_approvals = max(rule_min_approvals, 2 if risk_level == "critical" else 1)

        return PolicyDecision(
            decision_id=str(uuid.uuid4()),
            mission_id=mission.mission_id,
            step_id=step.id,
            requires_approval=requires_approval,
            risk_level=risk_level,
            reason="Approval required by policy" if requires_approval else "No approval required",
            policy_rule_id=matching_rule.rule_id if matching_rule else None,
            required_roles=required_roles,
            min_approvals=min_approvals,
        )

    def evaluate_mission(self, mission: MissionRecord) -> Dict[str, Any]:
        decisions = [self.evaluate_step(mission, step) for step in mission.steps]
        approval_required = [decision for decision in decisions if decision.requires_approval]
        compliance_target = 100 if not approval_required else 100 - min(25, len(approval_required) * 5)
        return {
            "mission_id": mission.mission_id,
            "policy_version": mission.policy_version,
            "decisions": [decision.to_dict() for decision in decisions],
            "requires_approval": bool(approval_required),
            "approval_count": len(approval_required),
            "policy_compliance_target": compliance_target,
            "trace_completeness_target": 100,
        }

    def upsert_rule(self, rule: PolicyRule) -> PolicyRule:
        for index, existing in enumerate(self.rules):
            if existing.rule_id == rule.rule_id:
                self.rules[index] = rule
                return rule
        self.rules.append(rule)
        return rule

    def list_rules(self) -> List[Dict[str, Any]]:
        return [rule.to_dict() for rule in self.rules]