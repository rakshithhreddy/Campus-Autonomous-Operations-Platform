-- =============================================================================
-- Migration: Add user_integrations table for persistent OAuth token storage
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_integrations (
    -- Use (user_id, provider) as a composite unique key for upserts
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    provider VARCHAR(100) NOT NULL,

    -- Encrypted token payload (AES-256-GCM via crypto_vault)
    encrypted_tokens TEXT,

    -- OAuth scopes granted
    scopes JSONB DEFAULT '[]'::jsonb,

    -- Extra metadata (email, account name, etc.)
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Connection status: 'connected' | 'revoked' | 'expired'
    status VARCHAR(50) DEFAULT 'connected',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Composite unique constraint for upsert
    UNIQUE(user_id, provider)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_user_integrations_user_id ON user_integrations(user_id);
CREATE INDEX IF NOT EXISTS idx_user_integrations_provider ON user_integrations(provider);
CREATE INDEX IF NOT EXISTS idx_user_integrations_status ON user_integrations(status);
CREATE INDEX IF NOT EXISTS idx_user_integrations_user_provider ON user_integrations(user_id, provider);

-- Auto-update updated_at
CREATE OR REPLACE TRIGGER update_user_integrations_updated_at
    BEFORE UPDATE ON user_integrations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- RLS (Row Level Security) - users can only see their own integrations
ALTER TABLE user_integrations ENABLE ROW LEVEL SECURITY;

-- Allow service_role full access (backend uses service_role key)
CREATE POLICY user_integrations_service_role ON user_integrations
    FOR ALL
    USING (true)
    WITH CHECK (true);
