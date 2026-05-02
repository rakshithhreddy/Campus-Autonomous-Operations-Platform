"""
Structured telemetry collector for mission and governance events.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import logging
import os
import uuid

logger = logging.getLogger(__name__)


@dataclass
class TelemetryEvent:
    event_id: str
    event_name: str
    tenant_id: str
    user_id: str
    mission_id: Optional[str]
    request_id: Optional[str]
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TelemetryCollector:
    def __init__(self) -> None:
        self._events: List[TelemetryEvent] = []
        self._log_path = os.getenv("TELEMETRY_LOG_PATH", "")

    def record_event(
        self,
        event_name: str,
        *,
        tenant_id: str,
        user_id: str,
        mission_id: Optional[str] = None,
        request_id: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> TelemetryEvent:
        event = TelemetryEvent(
            event_id=str(uuid.uuid4()),
            event_name=event_name,
            tenant_id=tenant_id,
            user_id=user_id,
            mission_id=mission_id,
            request_id=request_id,
            properties=properties or {},
        )
        self._events.append(event)
        logger.info("telemetry_event", extra={"telemetry_event": event.to_dict()})
        if self._log_path:
            try:
                with open(self._log_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event.to_dict()) + "\n")
            except Exception:
                logger.exception("Failed to persist telemetry event")
        return event

    def list_events(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        events = self._events
        if tenant_id:
            events = [event for event in events if event.tenant_id == tenant_id]
        return [event.to_dict() for event in events]

    def summarize(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        events = self.list_events(tenant_id)
        counts: Dict[str, int] = {}
        approval_latencies: List[float] = []
        fallback_events = 0
        mission_success = 0
        mission_failures = 0
        competitive_reasons: Dict[str, int] = {}

        for event in events:
            counts[event["event_name"]] = counts.get(event["event_name"], 0) + 1
            props = event.get("properties") or {}
            if "approval_latency_ms" in props:
                try:
                    approval_latencies.append(float(props["approval_latency_ms"]))
                except Exception:
                    pass
            if props.get("fallback_strategy"):
                fallback_events += 1
            if event["event_name"] in {"mission_completed", "mission_success"}:
                mission_success += 1
            if event["event_name"] in {"mission_failed", "step_failed"}:
                mission_failures += 1
            if event["event_name"] == "procurement_competitive_signal":
                reason = str(props.get("reason") or "unspecified")
                competitive_reasons[reason] = competitive_reasons.get(reason, 0) + 1

        event_count = len(events)
        average_approval_latency_ms = round(sum(approval_latencies) / len(approval_latencies), 2) if approval_latencies else 0.0
        fallback_frequency = round((fallback_events / event_count) * 100, 2) if event_count else 0.0
        mission_success_rate = round((mission_success / (mission_success + mission_failures)) * 100, 2) if (mission_success + mission_failures) else 0.0

        return {
            "event_count": event_count,
            "counts": counts,
            "average_approval_latency_ms": average_approval_latency_ms,
            "fallback_frequency": fallback_frequency,
            "mission_success_rate": mission_success_rate,
            "competitive_reasons": competitive_reasons,
        }

    def summarize_with_baseline(self, tenant_id: Optional[str] = None, baseline: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        baseline = baseline or {}
        summary = self.summarize(tenant_id)
        delta = {
            "mission_success_rate_delta": round(summary["mission_success_rate"] - float(baseline.get("mission_success_rate", 0.0)), 2),
            "fallback_frequency_delta": round(summary["fallback_frequency"] - float(baseline.get("fallback_frequency", 0.0)), 2),
            "approval_latency_delta_ms": round(summary["average_approval_latency_ms"] - float(baseline.get("average_approval_latency_ms", 0.0)), 2),
        }
        return {
            **summary,
            "baseline": {
                "mission_success_rate": float(baseline.get("mission_success_rate", 0.0)),
                "fallback_frequency": float(baseline.get("fallback_frequency", 0.0)),
                "average_approval_latency_ms": float(baseline.get("average_approval_latency_ms", 0.0)),
            },
            "delta": delta,
        }


_telemetry: Optional[TelemetryCollector] = None


def get_telemetry() -> TelemetryCollector:
    global _telemetry
    if _telemetry is None:
        _telemetry = TelemetryCollector()
    return _telemetry