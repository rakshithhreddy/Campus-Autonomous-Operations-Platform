-- =============================================================================
-- Migration 002: Governance Tables with Immutability (Item 69)
-- =============================================================================

-- Audit events table (canonical schema from Item 32)
CREATE TABLE IF NOT EXISTS audit_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    tenant_id VARCHAR(100) NOT NULL,
    actor_id VARCHAR(100) NOT NULL,
    actor_roles TEXT[] DEFAULT '{}',
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL DEFAULT 'mission',
    resource_id VARCHAR(100),
    previous_state VARCHAR(50),
    next_state VARCHAR(50),
    reason TEXT DEFAULT '',
    policy_version VARCHAR(20),
    request_id VARCHAR(100),
    ip_address VARCHAR(45),
    metadata JSONB DEFAULT '{}',
    retention_days INTEGER DEFAULT 365,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_events(resource_id) WHERE resource_type = 'mission';
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action);

-- Policy rules table (versioned, tenant-scoped)
CREATE TABLE IF NOT EXISTS policy_rules (
    rule_id VARCHAR(100) PRIMARY KEY,
    tenant_id VARCHAR(100),
    name VARCHAR(200) NOT NULL,
    risk_level VARCHAR(20) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    keywords TEXT[] DEFAULT '{}',
    required_roles TEXT[] DEFAULT '{}',
    min_approvals INTEGER DEFAULT 1 CHECK (min_approvals >= 0),
    active BOOLEAN DEFAULT TRUE,
    version VARCHAR(20) DEFAULT 'v1',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policy_rules_tenant ON policy_rules(tenant_id);
CREATE INDEX IF NOT EXISTS idx_policy_rules_active ON policy_rules(active) WHERE active = TRUE;

-- Policy evaluation records (versioned snapshots, Item 70)
CREATE TABLE IF NOT EXISTS policy_evaluations (
    evaluation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id UUID NOT NULL,
    step_id VARCHAR(100) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    policy_rule_id VARCHAR(100),
    policy_version VARCHAR(20),
    risk_level VARCHAR(20),
    requires_approval BOOLEAN DEFAULT FALSE,
    min_approvals INTEGER DEFAULT 1,
    required_roles TEXT[] DEFAULT '{}',
    decision_snapshot JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policy_eval_mission ON policy_evaluations(mission_id);
CREATE INDEX IF NOT EXISTS idx_policy_eval_tenant ON policy_evaluations(tenant_id);

-- Approval decisions table (immutable)
CREATE TABLE IF NOT EXISTS approval_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id UUID NOT NULL,
    step_id VARCHAR(100) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    approver_id VARCHAR(100) NOT NULL,
    approver_roles TEXT[] DEFAULT '{}',
    decision VARCHAR(30) NOT NULL CHECK (decision IN ('approve', 'approved', 'reject', 'rejected', 'request_changes')),
    reason TEXT NOT NULL DEFAULT '',
    policy_version VARCHAR(20),
    policy_rule_id VARCHAR(100),
    content_hash VARCHAR(64) NOT NULL,  -- SHA-256 tamper seal (Item 7)
    policy_rule_snapshot JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approvals_mission ON approval_decisions(mission_id);
CREATE INDEX IF NOT EXISTS idx_approvals_step ON approval_decisions(mission_id, step_id);
CREATE INDEX IF NOT EXISTS idx_approvals_tenant ON approval_decisions(tenant_id);

-- Missions table with optimistic locking (Item 9)
CREATE TABLE IF NOT EXISTS missions (
    mission_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT DEFAULT '',
    state VARCHAR(50) NOT NULL DEFAULT 'draft',
    policy_version VARCHAR(20) DEFAULT 'v1',
    trace_completeness FLOAT DEFAULT 0.0,
    policy_compliance FLOAT DEFAULT 0.0,
    version INTEGER DEFAULT 0,  -- Item 9: optimistic lock
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_missions_tenant_user ON missions(tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_missions_state ON missions(state);
CREATE INDEX IF NOT EXISTS idx_missions_created ON missions(created_at DESC);

-- Enable Row Level Security (Item 5)
ALTER TABLE missions ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

-- RLS policies (requires setting app.tenant_id via SET LOCAL)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'missions' AND policyname = 'tenant_isolation') THEN
        CREATE POLICY tenant_isolation ON missions
          USING (tenant_id = current_setting('app.tenant_id', true));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'approval_decisions' AND policyname = 'tenant_isolation') THEN
        CREATE POLICY tenant_isolation ON approval_decisions
          USING (tenant_id = current_setting('app.tenant_id', true));
    END IF;
END $$;

-- =============================================================================
-- Immutability Triggers (Item 7, Item 38)
-- =============================================================================

CREATE OR REPLACE FUNCTION prevent_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Table % is append-only and immutable', TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

-- Approval decisions are immutable
DROP TRIGGER IF EXISTS no_mutate_approvals ON approval_decisions;
CREATE TRIGGER no_mutate_approvals
    BEFORE UPDATE OR DELETE ON approval_decisions
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

-- Audit events are immutable
DROP TRIGGER IF EXISTS no_mutate_audit ON audit_events;
CREATE TRIGGER no_mutate_audit
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION prevent_mutation();

-- =============================================================================
-- Data Retention (Item 33)
-- =============================================================================

-- Function to clean expired audit events
CREATE OR REPLACE FUNCTION cleanup_expired_audit_events()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM audit_events
    WHERE created_at < NOW() - (retention_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
