# Operations Runbook

> This runbook covers day-to-day operations for Super Manager institutional platform.
> Keep this document accessible to your ops team.

---

## 🔑 Secret Rotation

### Rotate JWT Secret (`SECRET_KEY`)
1. Generate new key: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
2. Update in environment variables / secret manager
3. Restart application instances
4. **All existing JWT tokens are immediately invalidated** — users must re-authenticate
5. Verify: `GET /api/health` returns `{"status": "healthy"}`

### Rotate Encryption Master Key (`ENCRYPTION_MASTER_KEY`)
> ⚠️ **Warning**: Rotating this key renders all encrypted integration tokens unreadable.
> Users must re-authorize all OAuth integrations after rotation.
1. Generate: `python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"`
2. Update in secret manager
3. Restart application
4. Notify users to re-authorize integrations

### Rotate Firebase Service Account Key
1. Go to Google Cloud Console → IAM & Admin → Service Accounts
2. Select the service account → Keys → Add Key → Create new key (JSON)
3. Base64 encode: `python -c "import base64; print(base64.b64encode(open('new-key.json','rb').read()).decode())"`
4. Update `FIREBASE_CREDENTIALS_JSON` environment variable
5. Restart application
6. **Delete the old key** from Google Cloud Console (revoke it)
7. Shred the local key file: `shred -u new-key.json` (Linux) or securely delete

---

## 🚨 Incident Response

### Application Health Check
```
GET /api/health
```
Response codes:
- `200` + `"status": "healthy"` → All good
- `200` + `"status": "degraded"` → Non-critical component down, check `components`
- `503` → Critical failure

### Check Component Status
```
GET /api/health/metrics
```
Look for circuit breaker states:
- `ai_circuit_breaker: CLOSED` → AI provider healthy
- `ai_circuit_breaker: OPEN` → AI provider failing; check provider status page
- `db_circuit_breaker: OPEN` → Database connection failing; check Supabase status

### AI Provider Failure
1. Check circuit breaker: `GET /api/health`
2. Check provider status pages (OpenAI / Moonshot AI)
3. If circuit breaker is open: system auto-routes to fallback AI model
4. Monitor telemetry for `fallback_used` events
5. Circuit breaker auto-resets after provider recovery (60s timeout)

### Database Failure
1. Check `GET /api/health` → `db_circuit_breaker` state
2. Check Supabase status: https://status.supabase.com
3. System falls back to in-memory operation — **data will not persist during outage**
4. After Supabase recovers: restart application to restore persistence

---

## 🗄️ Database Operations

### Run Migration
```bash
# From project root
python -m backend.migrations.run

# Or apply SQL directly via Supabase SQL editor:
# backend/migrations/002_governance_tables.sql
```

### Verify Schema Integrity
```sql
-- Check immutability triggers exist
SELECT tgname, tgrelid::regclass
FROM pg_trigger
WHERE tgname IN ('no_mutate_approvals', 'no_mutate_audit');

-- Check RLS enabled
SELECT tablename, rowsecurity
FROM pg_tables
WHERE tablename IN ('missions', 'approval_decisions', 'audit_events');
```

### Verify Evidence Chain Integrity
```
GET /api/governance/missions/{mission_id}/evidence/verify
```
Response:
```json
{"all_valid": true, "chain_length": 5, "artifacts": [...]}
```
If `all_valid: false` → tamper detected. Investigate immediately.

---

## 📊 Monitoring

### View Mission Telemetry
```
GET /api/analytics/telemetry          → Raw event counts
GET /api/governance/trust             → Trust metrics summary
GET /api/governance/missions/{id}/compliance → Per-mission compliance
```

### Alert Thresholds
| Metric | Warning | Critical |
|---|---|---|
| Mission success rate | < 80% | < 60% |
| Approval compliance | < 95% | < 80% |
| Trace completeness | < 70% | < 50% |
| AI circuit breaker | HALF_OPEN | OPEN |
| DB circuit breaker | any non-CLOSED | OPEN |

---

## 👥 User Management

### Provision New Institution Admin
```bash
# Generate dev JWT for testing
python -c "
from jose import jwt
import time
token = jwt.encode({
    'sub': 'admin@institution.edu',
    'tenant_id': 'institution-slug',
    'roles': ['admin'],
    'exp': int(time.time()) + 86400
}, 'your-SECRET_KEY', algorithm='HS256')
print(token)
"
```

### Reset User Rate Limits
Rate limits are IP-based and reset automatically after the window (1 minute).
For immediate reset, restart the application.

---

## 🔒 Security Incident Response

### Suspected Token Compromise
1. Immediately rotate `SECRET_KEY` (invalidates all tokens)
2. Review audit logs for suspicious activity: `GET /api/governance/missions?tenant_id=X`
3. Review approval decisions for unauthorized approvals
4. Notify affected users to re-authenticate

### Suspected Data Breach
1. Rotate all secrets (SECRET_KEY, ENCRYPTION_MASTER_KEY, Firebase)
2. Review access logs
3. Run evidence chain verification for all affected missions
4. Notify institution CISO and follow data breach procedure
5. Document incident in post-incident report

---

## 🔄 Deployment

### Standard Deploy (Development)
```bash
cd d:\projects\GOOGLE-PROJECT
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Production Deploy Checklist
1. ✅ All secrets set in environment (not defaults)
2. ✅ `APP_ENV=production` set
3. ✅ `CORS_ORIGINS` set to explicit domain (not `*`)
4. ✅ Run: `python -m pytest tests/ -v` (all tests pass)
5. ✅ Run: `gitleaks detect` (no secrets in repo)
6. Start with: `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4`

### Rollback
1. Revert to previous container/deployment
2. Do NOT roll back database migrations (they're append-only)
3. Old app versions read new schema without issues
