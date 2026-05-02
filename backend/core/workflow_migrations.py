"""
Workflow System Database Migrations

SQL migrations for creating workflow-related tables in Supabase PostgreSQL
"""

# Migration 001: Create workflow_definitions table
MIGRATION_001_CREATE_WORKFLOW_DEFINITIONS = """
CREATE TABLE IF NOT EXISTS workflow_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    scenario_type VARCHAR(100) NOT NULL,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    enabled BOOLEAN DEFAULT true,
    
    CONSTRAINT scenario_type_check CHECK (scenario_type IN (
        'attendance', 'assignment', 'fee', 'exam', 'conduct', 'scholarship'
    ))
);

CREATE INDEX idx_workflow_definitions_scenario ON workflow_definitions(scenario_type);
CREATE INDEX idx_workflow_definitions_enabled ON workflow_definitions(enabled);
"""

# Migration 002: Create workflow_instances table
MIGRATION_002_CREATE_WORKFLOW_INSTANCES = """
CREATE TABLE IF NOT EXISTS workflow_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_definition_id UUID NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    subject_email VARCHAR(255) NOT NULL,
    subject_id VARCHAR(255) NOT NULL,
    current_step INT DEFAULT 0,
    current_state VARCHAR(50) DEFAULT 'in_progress',
    metadata JSONB DEFAULT '{}'::jsonb,
    next_scheduled_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    execution_log JSONB DEFAULT '[]'::jsonb,
    
    CONSTRAINT current_state_check CHECK (current_state IN (
        'pending', 'in_progress', 'parent_contacted', 'admin_escalated', 
        'resolved', 'failed', 'archived'
    ))
);

CREATE INDEX idx_workflow_instances_definition ON workflow_instances(workflow_definition_id);
CREATE INDEX idx_workflow_instances_state ON workflow_instances(current_state);
CREATE INDEX idx_workflow_instances_scheduled ON workflow_instances(next_scheduled_at) 
    WHERE next_scheduled_at IS NOT NULL;
CREATE INDEX idx_workflow_instances_subject ON workflow_instances(subject_id, subject_email);
"""

# Migration 003: Create workflow_execution_log table
MIGRATION_003_CREATE_EXECUTION_LOG = """
CREATE TABLE IF NOT EXISTS workflow_execution_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_instance_id UUID NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
    step_number INT NOT NULL,
    action_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT status_check CHECK (status IN (
        'pending', 'running', 'success', 'failed', 'skipped'
    )),
    CONSTRAINT action_type_check CHECK (action_type IN (
        'email_sent', 'check_performed', 'escalation', 'log_action', 
        'erp_query', 'sms_sent', 'condition_check'
    ))
);

CREATE INDEX idx_execution_log_instance ON workflow_execution_log(workflow_instance_id);
CREATE INDEX idx_execution_log_timestamp ON workflow_execution_log(executed_at);
"""

# Migration 004: Create workflow_history table for audit trail
MIGRATION_004_CREATE_HISTORY = """
CREATE TABLE IF NOT EXISTS workflow_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_definition_id UUID NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by UUID,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT action_check CHECK (action IN ('created', 'updated', 'deleted', 'executed'))
);

CREATE INDEX idx_workflow_history_definition ON workflow_history(workflow_definition_id);
CREATE INDEX idx_workflow_history_timestamp ON workflow_history(changed_at);
"""

# Migration 005: Create workflow_notifications table
MIGRATION_005_CREATE_NOTIFICATIONS = """
CREATE TABLE IF NOT EXISTS workflow_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_instance_id UUID NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
    recipient_email VARCHAR(255) NOT NULL,
    recipient_type VARCHAR(50),
    notification_type VARCHAR(100) NOT NULL,
    subject VARCHAR(255),
    body TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT status_check CHECK (status IN (
        'pending', 'sent', 'failed', 'bounced'
    ))
);

CREATE INDEX idx_notifications_instance ON workflow_notifications(workflow_instance_id);
CREATE INDEX idx_notifications_recipient ON workflow_notifications(recipient_email);
CREATE INDEX idx_notifications_status ON workflow_notifications(status);
"""

# Python function to apply migrations
async def apply_migrations(supabase_client):
    """Apply all migrations to database"""
    migrations = [
        ("workflow_definitions", MIGRATION_001_CREATE_WORKFLOW_DEFINITIONS),
        ("workflow_instances", MIGRATION_002_CREATE_WORKFLOW_INSTANCES),
        ("workflow_execution_log", MIGRATION_003_CREATE_EXECUTION_LOG),
        ("workflow_history", MIGRATION_004_CREATE_HISTORY),
        ("workflow_notifications", MIGRATION_005_CREATE_NOTIFICATIONS),
    ]
    
    for name, sql in migrations:
        try:
            # Execute raw SQL through Supabase
            result = await supabase_client.rpc("execute_sql", {"sql": sql}).execute()
            print(f"✅ Migration applied: {name}")
        except Exception as e:
            print(f"⚠️ Migration {name} may have already been applied: {e}")


# Manual SQL script (for running directly in Supabase console)
MANUAL_MIGRATION_SCRIPT = """
-- Workflow System Database Schema
-- Execute this script in Supabase SQL Editor to set up workflow tables

-- 1. Workflow Definitions Table
CREATE TABLE IF NOT EXISTS workflow_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    scenario_type VARCHAR(100) NOT NULL,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    enabled BOOLEAN DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_workflow_definitions_scenario ON workflow_definitions(scenario_type);
CREATE INDEX IF NOT EXISTS idx_workflow_definitions_enabled ON workflow_definitions(enabled);

-- 2. Workflow Instances Table
CREATE TABLE IF NOT EXISTS workflow_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_definition_id UUID NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    subject_email VARCHAR(255) NOT NULL,
    subject_id VARCHAR(255) NOT NULL,
    current_step INT DEFAULT 0,
    current_state VARCHAR(50) DEFAULT 'in_progress',
    metadata JSONB DEFAULT '{}'::jsonb,
    next_scheduled_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    execution_log JSONB DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_workflow_instances_definition ON workflow_instances(workflow_definition_id);
CREATE INDEX IF NOT EXISTS idx_workflow_instances_state ON workflow_instances(current_state);
CREATE INDEX IF NOT EXISTS idx_workflow_instances_scheduled ON workflow_instances(next_scheduled_at) 
    WHERE next_scheduled_at IS NOT NULL;

-- 3. Workflow Execution Log Table
CREATE TABLE IF NOT EXISTS workflow_execution_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_instance_id UUID NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
    step_number INT NOT NULL,
    action_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_execution_log_instance ON workflow_execution_log(workflow_instance_id);
CREATE INDEX IF NOT EXISTS idx_execution_log_timestamp ON workflow_execution_log(executed_at);

-- 4. Workflow History Table
CREATE TABLE IF NOT EXISTS workflow_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_definition_id UUID NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by UUID,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_history_definition ON workflow_history(workflow_definition_id);
CREATE INDEX IF NOT EXISTS idx_workflow_history_timestamp ON workflow_history(changed_at);

-- 5. Workflow Notifications Table
CREATE TABLE IF NOT EXISTS workflow_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_instance_id UUID NOT NULL REFERENCES workflow_instances(id) ON DELETE CASCADE,
    recipient_email VARCHAR(255) NOT NULL,
    recipient_type VARCHAR(50),
    notification_type VARCHAR(100) NOT NULL,
    subject VARCHAR(255),
    body TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_instance ON workflow_notifications(workflow_instance_id);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON workflow_notifications(recipient_email);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON workflow_notifications(status);

-- Enable RLS (Row Level Security) if needed
ALTER TABLE workflow_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_execution_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_notifications ENABLE ROW LEVEL SECURITY;
"""
