from backend.core.extreme_benchmarks import run_extreme_benchmarks


def test_extreme_benchmark_report_shape():
    report = run_extreme_benchmarks(scale="mini")

    assert report["scale"] == "mini"
    assert "benchmarks" in report
    assert set(report["benchmarks"].keys()) == {
        "cache",
        "rate_limiter",
        "request_tracer",
        "circuit_breaker",
        "governance_store",
        "evidence_vault",
        "api_load",
    }

    api = report["benchmarks"]["api_load"]
    assert api["requests"] > 0
    assert api["mission_create_rps"] > 0
    assert api["trust_rps"] > 0


def test_extreme_benchmark_includes_percentiles():
    report = run_extreme_benchmarks(scale="mini")
    tracer = report["benchmarks"]["request_tracer"]
    api = report["benchmarks"]["api_load"]

    assert tracer["p50_ms"] >= 0
    assert tracer["p95_ms"] >= tracer["p50_ms"]
    assert tracer["p99_ms"] >= tracer["p95_ms"]
    assert api["mission_create_p95_ms"] >= api["mission_create_p50_ms"]
    assert api["trust_p99_ms"] >= api["trust_p95_ms"]