# Pilot Readiness Checklist

> Run this checklist before deploying to any institutional pilot environment.
> **All items in the Security and Auth Gates must be checked before go-live.**

---

## 🔐 Security Gates (Blocking)

### Secrets & Credentials
- [ ] All secrets rotated from git history (`git filter-repo` completed)
- [ ] `ENCRYPTION_MASTER_KEY` set (not default, 32+ bytes base64)
- [ ] `SECRET_KEY` set (not `change-me-in-production`)
- [ ] `ENCRYPTION_SECRET` set (not `change-this-secret-key...`)
- [ ] Firebase credentials loaded via `FIREBASE_CREDENTIALS_JSON` env var (not file)
- [ ] Old Firebase service account key revoked in Google Cloud Console
- [ ] `.env` removed from git index (`git rm --cached .env`)
- [ ] `.env` not in git history (verify with `git log --all -- .env`)

### Headers & CORS
- [ ] CSP headers present and verified (no `unsafe-eval`)
- [ ] CORS restricted to explicit production origins (no wildcard `*`)
- [ ] HSTS enabled (`max-age=31536000; includeSubDomains`)
- [ ] `X-Content-Type-Options: nosniff` present
- [ ] `X-Frame-Options: DENY` present

### Pre-commit & CI
- [ ] Pre-commit hooks installed (`pre-commit install`)
- [ ] `gitleaks` secret scan passing on all commits
- [ ] CI security gate passes (auth tests + secret scan)

---

## 🛂 Auth & Authorization Gates (Blocking)

- [ ] JWT authentication enforced on all business endpoints (verified by test)
- [ ] All 50 auth tests passing (`pytest tests/test_governance_comprehensive.py`)
- [ ] No endpoint accepts freely-supplied `user_id` in request body
- [ ] `X-Dev-User-Id` bypass disabled in non-dev environments
- [ ] Role-based access enforced (admin/operator/reviewer/auditor matrix tested)
- [ ] Cross-tenant mission access returns 404 (verified by test)
- [ ] Approval decisions require min_length=10 on reason (verified by test)

---

## 📋 Governance Gates (Blocking)

- [ ] Policy engine configured with at least one active rule for this tenant
- [ ] At least one workflow pack available (accreditation/faculty/it_incident)
- [ ] Approval queue functional (create → approve → execute cycle tested)
- [ ] Approval decisions have content_hash (verified: `len(hash) == 64`)
- [ ] Rejection captures `rejection_reason`, `rejected_by`, `rejected_at`
- [ ] Replan endpoint functional (rejected → replan → re-queue)
- [ ] Mission version counter increments on each state transition
- [ ] Evidence vault storing artifacts with chain verification passing

---

## 📊 Monitoring Gates (Recommended)

- [ ] Health endpoint returns accurate component status
- [ ] Telemetry events being recorded (`mission_created`, `approval_completed`)
- [ ] Structured logging enabled (no `print()` in production code)
- [ ] Error responses never include stack traces (verified via test client)
- [ ] KPI report endpoint accessible (`/api/analytics/kpi-report`)
- [ ] Trust metrics accessible (`/api/governance/trust`)

---

## 🗄️ Database Gates (Recommended)

- [ ] Supabase Row Level Security enabled on `missions` table
- [ ] `approval_decisions` table has immutability trigger deployed
- [ ] `audit_events` table has immutability trigger deployed
- [ ] Migration `002_governance_tables.sql` executed successfully
- [ ] Database backup policy in place

---

## 📝 Documentation Gates (Recommended)

- [ ] ADR-001 (Security Model) documented
- [ ] ADR-002 (Approval Model) documented
- [ ] ADR-003 (Tenant Isolation) documented
- [ ] Operations Runbook accessible to ops team
- [ ] Onboarding wizard functional for new institution setup

---

## ✅ Sign-Off

| Gate | Verified By | Date |
|---|---|---|
| Security Gates | | |
| Auth & Authorization | | |
| Governance | | |
| Monitoring | | |
| Database | | |
