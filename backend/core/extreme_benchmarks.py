from __future__ import annotations

import hashlib
import json
import os
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

from . import governance_store as governance_store_module
from .evidence_vault import EvidenceVault
from .governance_store import get_governance_store
from .performance import CircuitBreaker, CircuitBreakerConfig, LRUCache, RateLimiter, RequestTracer
from ..routes import analytics, evidence, governance, policies


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _elapsed_ms(start: float, end: float) -> float:
    return (end - start) * 1000.0


def benchmark_cache(scale: int = 25000) -> Dict[str, Any]:
    cache = LRUCache(max_size=max(256, scale // 2), default_ttl=60.0)
    keys = [f"cache-{index}" for index in range(scale)]

    start = time.perf_counter()
    for index, key in enumerate(keys):
        cache.set(key, {"index": index})
    set_end = time.perf_counter()

    hit_start = time.perf_counter()
    hit_count = 0
    for key in keys:
        if cache.get(key) is not None:
            hit_count += 1
    hit_end = time.perf_counter()

    miss_start = time.perf_counter()
    for index in range(scale):
        cache.get(f"missing-{index}")
    miss_end = time.perf_counter()

    stats = cache.get_stats()
    return {
        "name": "lru_cache",
        "operations": scale,
        "set_ops_per_sec": round(scale / max(1e-9, set_end - start), 2),
        "get_hit_ops_per_sec": round(scale / max(1e-9, hit_end - hit_start), 2),
        "get_miss_ops_per_sec": round(scale / max(1e-9, miss_end - miss_start), 2),
        "hit_count": hit_count,
        "stats": stats,
    }


def benchmark_rate_limiter(scale: int = 50000) -> Dict[str, Any]:
    allow = RateLimiter(rate=1_000_000.0, capacity=float(scale), name="allow")
    deny = RateLimiter(rate=0.0, capacity=0.0, name="deny")

    allow_start = time.perf_counter()
    allow_success = 0
    for _ in range(scale):
        if allow.acquire():
            allow_success += 1
    allow_end = time.perf_counter()

    deny_start = time.perf_counter()
    deny_rejected = 0
    for _ in range(scale):
        if not deny.acquire():
            deny_rejected += 1
    deny_end = time.perf_counter()

    return {
        "name": "rate_limiter",
        "operations": scale,
        "allow_success": allow_success,
        "allow_ops_per_sec": round(scale / max(1e-9, allow_end - allow_start), 2),
        "deny_rejected": deny_rejected,
        "deny_ops_per_sec": round(scale / max(1e-9, deny_end - deny_start), 2),
        "allow_stats": allow.get_stats(),
        "deny_stats": deny.get_stats(),
    }


def benchmark_request_tracer(scale: int = 20000) -> Dict[str, Any]:
    tracer = RequestTracer(max_traces=scale)
    wall_durations: List[float] = []
    payload = b"trace-benchmark-payload"

    start = time.perf_counter()
    for index in range(scale):
        wall_start = time.perf_counter()
        trace_id = tracer.start_trace("benchmark", {"index": index})
        hashlib.sha256(payload + index.to_bytes(4, "little")).hexdigest()
        tracer.end_trace(trace_id, "success")
        wall_durations.append(_elapsed_ms(wall_start, time.perf_counter()))
    end = time.perf_counter()

    stats = tracer.get_stats()
    return {
        "name": "request_tracer",
        "operations": scale,
        "ops_per_sec": round(scale / max(1e-9, end - start), 2),
        "avg_duration_ms": round(statistics.mean(wall_durations), 6) if wall_durations else 0.0,
        "p50_ms": round(_percentile(wall_durations, 50), 6),
        "p95_ms": round(_percentile(wall_durations, 95), 6),
        "p99_ms": round(_percentile(wall_durations, 99), 6),
        "internal_avg_duration_ms": round(stats.get("avg_duration_ms", 0.0), 6) if stats else 0.0,
        "stats": stats,
    }


def benchmark_circuit_breaker(scale: int = 20000) -> Dict[str, Any]:
    breaker = CircuitBreaker("benchmark", CircuitBreakerConfig(failure_threshold=3, success_threshold=2, timeout=0.01, half_open_max_calls=2))

    for _ in range(3):
        breaker.record_failure()

    rejected = 0
    start = time.perf_counter()
    for _ in range(scale):
        if not breaker.can_execute():
            rejected += 1
    end = time.perf_counter()

    return {
        "name": "circuit_breaker",
        "operations": scale,
        "rejected": rejected,
        "rejection_ops_per_sec": round(scale / max(1e-9, end - start), 2),
        "status": breaker.get_status(),
    }


def benchmark_governance_store(missions: int = 1000) -> Dict[str, Any]:
    governance_store_module._governance_store = None
    store = get_governance_store()
    steps = [
        {
            "title": "collect evidence",
            "description": "benchmark path",
            "action_type": "evidence_intake",
            "risk_level": "low",
            "requires_approval": False,
        },
        {
            "title": "approve release",
            "description": "benchmark path",
            "action_type": "approval",
            "risk_level": "high",
            "requires_approval": True,
            "approver_roles": ["manager"],
        },
    ]

    created: List[tuple[str, str]] = []
    create_start = time.perf_counter()
    for index in range(missions):
        mission = store.create_mission(
            user_id="bench-user",
            tenant_id="bench-tenant",
            title=f"mission-{index}",
            description="benchmark",
            steps=steps,
            policy_version="v1",
        )
        created.append((mission.mission_id, mission.steps[1].id))
    create_end = time.perf_counter()

    approve_start = time.perf_counter()
    for mission_id, step_id in created:
        store.record_approval(
            mission_id=mission_id,
            step_id=step_id,
            tenant_id="bench-tenant",
            user_id="bench-user",
            approver_id="bench-approver",
            approver_roles=["manager"],
            decision="approve",
            reason="benchmark",
            policy_version="v1",
        )
    approve_end = time.perf_counter()

    pending = store.list_pending_approvals(tenant_id="bench-tenant", user_id="bench-user")
    return {
        "name": "governance_store",
        "missions": missions,
        "create_ops_per_sec": round(missions / max(1e-9, create_end - create_start), 2),
        "approve_ops_per_sec": round(missions / max(1e-9, approve_end - approve_start), 2),
        "create_ms_per_op": round(_elapsed_ms(create_start, create_end) / missions, 6),
        "approve_ms_per_op": round(_elapsed_ms(approve_start, approve_end) / missions, 6),
        "pending_after_approval": len(pending),
    }


def benchmark_evidence_vault(artifacts: int = 1000) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="evidence-bench-") as temp_dir:
        vault = EvidenceVault(root_dir=Path(temp_dir))
        vault._client = None

        store_start = time.perf_counter()
        for index in range(artifacts):
            vault.store_artifact(
                mission_id="mission-bench",
                tenant_id="tenant-bench",
                user_id="user-bench",
                step_id="step-bench",
                name=f"artifact-{index}.txt",
                content=f"payload-{index}",
                content_type="text/plain",
                classification="internal",
                metadata={"index": index, "source": "benchmark"},
            )
        store_end = time.perf_counter()

        export_start = time.perf_counter()
        bundle = vault.export_bundle("mission-bench", include_expired=False)
        export_end = time.perf_counter()

        return {
            "name": "evidence_vault",
            "artifacts": artifacts,
            "store_ops_per_sec": round(artifacts / max(1e-9, store_end - store_start), 2),
            "store_ms_per_op": round(_elapsed_ms(store_start, store_end) / artifacts, 6),
            "export_ms": round(_elapsed_ms(export_start, export_end), 6),
            "bundle_count": len(bundle.get("artifacts", [])),
        }


def _build_api_client() -> tuple[TestClient, str]:
    try:
        from backend.main import app as full_app

        return TestClient(full_app), "full_app"
    except Exception:
        app = FastAPI()
        app.include_router(governance.router)
        app.include_router(evidence.router)
        app.include_router(analytics.router)
        app.include_router(policies.router)
        return TestClient(app), "benchmark_subset"


def benchmark_api_load(requests: int = 200, concurrency: int = 10) -> Dict[str, Any]:
    client, app_mode = _build_api_client()
    headers = {
        "X-Dev-User-Id": "bench-user",
        "X-Dev-Tenant-Id": "bench-tenant",
        "X-Dev-Roles": "admin,user",
        "Content-Type": "application/json",
    }

    def request_headers(index: int) -> Dict[str, str]:
        return {**headers, "X-Forwarded-For": f"10.10.{index // 255}.{index % 255 + 1}"}

    mission_payload = {
        "title": "benchmark mission",
        "description": "load test",
        "steps": [
            {
                "title": "collect evidence",
                "description": "load test",
                "action_type": "evidence_intake",
                "risk_level": "low",
                "requires_approval": False,
            }
        ],
    }

    create_latencies: List[float] = []
    trust_latencies: List[float] = []

    def create_request(index: int) -> float:
        start = time.perf_counter()
        response = client.post(
            "/api/governance/missions",
            json=mission_payload,
            headers={**request_headers(index), "X-Idempotency-Key": f"bench-{index}"},
        )
        duration = _elapsed_ms(start, time.perf_counter())
        if response.status_code != 200:
            raise RuntimeError(f"mission create failed: {response.status_code}")
        return duration

    def trust_request(index: int) -> float:
        start = time.perf_counter()
        response = client.get("/api/governance/trust", headers=request_headers(index))
        duration = _elapsed_ms(start, time.perf_counter())
        if response.status_code != 200:
            raise RuntimeError(f"trust failed: {response.status_code}")
        return duration

    client.get("/api/governance/trust", headers=request_headers(0))

    create_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for duration in executor.map(create_request, range(requests)):
            create_latencies.append(duration)
    create_end = time.perf_counter()

    trust_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for duration in executor.map(trust_request, range(requests)):
            trust_latencies.append(duration)
    trust_end = time.perf_counter()

    return {
        "name": "api_load",
        "app_mode": app_mode,
        "requests": requests,
        "concurrency": concurrency,
        "mission_create_rps": round(requests / max(1e-9, create_end - create_start), 2),
        "trust_rps": round(requests / max(1e-9, trust_end - trust_start), 2),
        "mission_create_p50_ms": round(_percentile(create_latencies, 50), 6),
        "mission_create_p95_ms": round(_percentile(create_latencies, 95), 6),
        "mission_create_p99_ms": round(_percentile(create_latencies, 99), 6),
        "trust_p50_ms": round(_percentile(trust_latencies, 50), 6),
        "trust_p95_ms": round(_percentile(trust_latencies, 95), 6),
        "trust_p99_ms": round(_percentile(trust_latencies, 99), 6),
    }


def run_extreme_benchmarks(scale: str = "extreme") -> Dict[str, Any]:
    profile = {
        "mini": {"cache": 5000, "rate_limiter": 10000, "tracer": 5000, "circuit": 5000, "missions": 200, "artifacts": 200, "requests": 50, "concurrency": 5},
        "default": {"cache": 15000, "rate_limiter": 25000, "tracer": 10000, "circuit": 10000, "missions": 500, "artifacts": 500, "requests": 100, "concurrency": 8},
        "extreme": {"cache": 50000, "rate_limiter": 100000, "tracer": 30000, "circuit": 30000, "missions": 1000, "artifacts": 1000, "requests": 200, "concurrency": 16},
    }.get(scale, None)

    if profile is None:
        raise ValueError(f"Unknown benchmark scale: {scale}")

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results = {
        "started_at": started_at,
        "scale": scale,
        "environment": {
            "python": os.sys.version.split()[0],
            "platform": os.name,
        },
        "benchmarks": {
            "cache": benchmark_cache(profile["cache"]),
            "rate_limiter": benchmark_rate_limiter(profile["rate_limiter"]),
            "request_tracer": benchmark_request_tracer(profile["tracer"]),
            "circuit_breaker": benchmark_circuit_breaker(profile["circuit"]),
            "governance_store": benchmark_governance_store(profile["missions"]),
            "evidence_vault": benchmark_evidence_vault(profile["artifacts"]),
            "api_load": benchmark_api_load(profile["requests"], profile["concurrency"]),
        },
    }
    return results


def write_report(report: Dict[str, Any], output_path: Optional[Path] = None) -> Path:
    target = output_path or Path("data/benchmarks/latest_extreme_benchmark.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return target


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run extreme benchmark suite")
    parser.add_argument("--scale", default=os.getenv("BENCHMARK_SCALE", "extreme"), choices=["mini", "default", "extreme"])
    parser.add_argument("--output", default=os.getenv("BENCHMARK_OUTPUT"))
    args = parser.parse_args(argv)

    report = run_extreme_benchmarks(scale=args.scale)
    output_path = write_report(report, Path(args.output) if args.output else None)
    print(json.dumps({"output": str(output_path), "scale": args.scale, "benchmarks": list(report["benchmarks"].keys())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())