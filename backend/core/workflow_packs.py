"""
Predefined institutional workflow packs for governed mission creation.

Items 14-16: Expanded to full institutional-grade workflows for:
- Accreditation (NAAC/NBA): 7-step evidence-to-submission lifecycle
- Faculty Workload: 7-step workload coordination with escalation
- Campus IT Incident: 8-step ITIL-aligned incident response
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


WORKFLOW_PACKS: Dict[str, Dict[str, Any]] = {
    # =========================================================================
    # Item 14: NAAC/NBA Accreditation Pack (fully expanded)
    # =========================================================================
    "accreditation": {
        "id": "accreditation",
        "name": "Accreditation Workflow (NAAC/NBA)",
        "description": "Full evidence lifecycle: criteria mapping, intake, gap analysis, owner assignment, validation, compliance report, and final submission bundle.",
        "tags": ["naac", "nba", "compliance", "accreditation"],
        "default_title": "Accreditation Evidence Cycle",
        "steps": [
            {
                "title": "Define criteria mapping",
                "description": "Map institutional data sources to NAAC 7-criteria or NBA programme outcomes. Identify responsible departments per criterion.",
                "action_type": "criteria_mapping",
                "risk_level": "low",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Collect self-study evidence",
                "description": "Ingest SSR documents, faculty qualification data, student outcomes, infrastructure records, and financial statements.",
                "action_type": "evidence_intake",
                "risk_level": "medium",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Run gap analysis",
                "description": "Identify missing evidence per criterion. Flag criteria below minimum threshold. Generate gap report with severity ratings.",
                "action_type": "gap_analysis",
                "risk_level": "medium",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Assign evidence owners and set deadlines",
                "description": "Route evidence collection ownership to departments with SLA deadlines. Send automated notifications to assigned owners.",
                "action_type": "owner_assignment",
                "risk_level": "medium",
                "requires_approval": True,
                "approver_roles": ["manager"],
                "owner_role": "manager",
            },
            {
                "title": "Review and validate submissions",
                "description": "Quality-check submitted evidence for completeness, accuracy, and criterion alignment. Flag items for re-submission.",
                "action_type": "evidence_review",
                "risk_level": "high",
                "requires_approval": True,
                "approver_roles": ["reviewer"],
                "owner_role": "reviewer",
            },
            {
                "title": "Generate compliance report",
                "description": "Produce criterion-wise compliance score and readiness assessment. Include gap summary and improvement recommendations.",
                "action_type": "compliance_report",
                "risk_level": "medium",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Publish accreditation bundle",
                "description": "Export final evidence package with chain-of-custody for NAAC/NBA submission. Requires admin sign-off before release.",
                "action_type": "export_bundle",
                "risk_level": "high",
                "requires_approval": True,
                "approver_roles": ["admin", "manager"],
                "owner_role": "admin",
            },
        ],
    },

    # =========================================================================
    # Item 15: Faculty Workload Pack (fully expanded)
    # =========================================================================
    "faculty_workload": {
        "id": "faculty_workload",
        "name": "Faculty Workload Workflow",
        "description": "End-to-end workload coordination: import from ERP, calculate balance, confirm with faculty, escalate overdue, and publish report.",
        "tags": ["faculty", "operations", "ownership", "workload"],
        "default_title": "Faculty Workload Coordination",
        "steps": [
            {
                "title": "Import workload register",
                "description": "Pull teaching, research, and admin duties from HR/ERP system. Validate against policy limits (max teaching hours, research quota).",
                "action_type": "workload_import",
                "risk_level": "low",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Calculate workload balance",
                "description": "Compare assigned hours vs. policy limits. Flag overloaded or underloaded faculty. Generate imbalance report.",
                "action_type": "workload_balance",
                "risk_level": "low",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Generate ownership map",
                "description": "Create visual responsibility matrix with accountability chains. Link courses, research projects, and admin duties to faculty owners.",
                "action_type": "ownership_map",
                "risk_level": "low",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Send workload confirmations",
                "description": "Dispatch confirmation requests to each faculty member for review and sign-off on their assigned workload.",
                "action_type": "send_confirmations",
                "risk_level": "medium",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Send overdue reminders",
                "description": "Auto-remind faculty who haven't confirmed their workload within the deadline window. Escalation trigger if still unresponsive.",
                "action_type": "send_reminders",
                "risk_level": "medium",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Escalate unresolved items",
                "description": "Route overdue and disputed workload items to department heads for intervention. Requires manager approval before escalation.",
                "action_type": "escalate_overdue",
                "risk_level": "high",
                "requires_approval": True,
                "approver_roles": ["manager"],
                "owner_role": "manager",
            },
            {
                "title": "Publish workload report",
                "description": "Generate summary report with faculty distribution, overload flags, and compliance status for institutional review.",
                "action_type": "workload_report",
                "risk_level": "medium",
                "requires_approval": False,
                "owner_role": "operator",
            },
        ],
    },

    # =========================================================================
    # Item 16: Campus IT Incident Pack (ITIL-aligned, fully expanded)
    # =========================================================================
    "it_incident": {
        "id": "it_incident",
        "name": "Campus IT Incident Response (ITIL)",
        "description": "Full ITIL-aligned incident lifecycle: intake, classify, triage, investigate, approve remediation, execute, verify, and post-incident report.",
        "tags": ["incident", "it", "remediation", "itil", "security"],
        "default_title": "Campus IT Incident Response",
        "steps": [
            {
                "title": "Receive and log incident",
                "description": "Auto-capture from monitoring alerts, helpdesk tickets, or manual report. Assign unique incident ID and open timestamp.",
                "action_type": "incident_intake",
                "risk_level": "low",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Classify severity and impact",
                "description": "Assign P1-P4 severity based on affected services and user count. Determine blast radius and SLA breach risk.",
                "action_type": "incident_classify",
                "risk_level": "medium",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Triage and assign responder",
                "description": "Route to appropriate team based on incident category. Set SLA clock. Brief responder on current impact.",
                "action_type": "incident_triage",
                "risk_level": "medium",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Investigate root cause",
                "description": "Collect system logs, trace error chain, identify root cause. Propose remediation options with risk assessments.",
                "action_type": "incident_investigate",
                "risk_level": "high",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Approve remediation plan",
                "description": "Review proposed fix for risk, data integrity impact, and change scope before execution. Manager and security officer sign-off required.",
                "action_type": "incident_approve_fix",
                "risk_level": "high",
                "requires_approval": True,
                "approver_roles": ["manager", "reviewer"],
                "owner_role": "manager",
            },
            {
                "title": "Execute remediation",
                "description": "Apply approved fix with monitoring. Execute in maintenance window if possible. Document every change step.",
                "action_type": "incident_remediation",
                "risk_level": "critical",
                "requires_approval": True,
                "approver_roles": ["manager", "admin"],
                "owner_role": "operator",
            },
            {
                "title": "Verify resolution",
                "description": "Confirm service restored to full capacity. Perform smoke tests. Get affected user/team confirmation.",
                "action_type": "incident_verify",
                "risk_level": "medium",
                "requires_approval": False,
                "owner_role": "operator",
            },
            {
                "title": "Generate post-incident report",
                "description": "Produce timeline, root cause summary, remediation steps, prevention recommendations, and SLA compliance metrics.",
                "action_type": "post_incident_report",
                "risk_level": "medium",
                "requires_approval": False,
                "owner_role": "operator",
            },
        ],
    },
}


def list_workflow_packs() -> List[Dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "description": item["description"],
            "tags": item.get("tags", []),
            "default_title": item.get("default_title", item["name"]),
            "step_count": len(item.get("steps", [])),
        }
        for item in WORKFLOW_PACKS.values()
    ]


def get_workflow_pack(pack_id: str) -> Optional[Dict[str, Any]]:
    pack = WORKFLOW_PACKS.get(pack_id)
    return deepcopy(pack) if pack else None
