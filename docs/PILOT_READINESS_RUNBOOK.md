# Pilot Readiness Runbook

## Purpose

This runbook defines the minimum controls and validation steps required before positioning Super Manager as a governed execution platform in institutional pilots.

## Release gate

A candidate build is pilot-ready only when all sections below are completed.

## 1. Security hardening gate

1. Confirm no secrets or credentials are committed.
2. Ensure pre-commit secret scanning is enabled and passing.
3. Verify production startup fails when required security settings are missing.
4. Verify webhook signature and replay checks are enabled for configured channels.
5. Verify CSP headers are emitted and do not include unsafe-eval.

Evidence to capture:
- command output for secret scan
- startup failure screenshot/log for missing production secrets
- sample webhook rejection for invalid signature

## 2. Access control gate

1. Verify protected routes require authenticated principal context.
2. Verify tenant isolation for mission, evidence, and analytics data paths.
3. Verify role restrictions on approval and override endpoints.
4. Verify unauthorized access attempts return 401 or 403 and are logged.

Evidence to capture:
- regression test results for auth matrix
- example 403 for cross-tenant access

## 3. Governance and evidence gate

1. Verify mission lifecycle transitions enforce allowed state changes.
2. Verify high-risk and critical actions require approvals as configured.
3. Verify rejection path captures required reason.
4. Verify evidence exports include chain-of-custody and retention metadata.
5. Verify sensitive metadata is redacted in evidence responses.

Evidence to capture:
- mission bundle export sample
- approval decision log sample
- rejection workflow sample

## 4. Benchmark and reliability gate

1. Run extreme benchmark suite from scripts/run_extreme_benchmarks.py.
2. Publish latest benchmark artifact to data/benchmarks/latest_extreme_benchmark.json.
3. Compare against previous baseline and record regressions.
4. Flag any severe regressions before pilot release.

Evidence to capture:
- benchmark JSON diff summary
- signed-off perf note

## 5. Product proof package

Prepare a pilot package with:
- mission trace sample
- approval trail sample
- evidence bundle sample
- trust dashboard snapshot
- differentiation summary against suggestion-only mode

Do not claim market superiority without independent external benchmarks.

## 6. Pre-pilot checklist

- security gate passed
- access control gate passed
- governance and evidence gate passed
- benchmark gate passed
- proof package assembled
- known risks documented with mitigation owner

## 7. Post-pilot review

After each pilot cycle, record:
- incidents and root causes
- approval latency trends
- evidence export issues
- user friction points
- top 5 backlog items for next hardening wave
