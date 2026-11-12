"""
Supabase Database - PostgreSQL backend for Super Manager
Replaces Firebase with Supabase for better SQL queries and real-time subscriptions
"""
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncio

try:
    from supabase import create_client, Client
    from supabase.lib.client_options import ClientOptions
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None

# Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")  # Use anon/service key
SUPABASE_DB_URL = os.getenv("DATABASE_URL", "")  # Direct PostgreSQL connection

# Global client
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    """Get or create Supabase client"""
    global _supabase_client
    
    if _supabase_client is None and SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY:
        try:
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("[DB] [OK] Supabase client initialized")
        except Exception as e:
            print(f"[DB] [ERROR] Supabase init error: {e}")
            return None
    
    return _supabase_client


async def init_db():
    """Initialize database connection and verify tables exist"""
    client = get_supabase_client()
    
    if client is None:
        print("[DB] [WARN] Supabase not configured. Set SUPABASE_URL and SUPABASE_KEY")
        print("[DB] System will run in memory-only mode")
        return False
    
    try:
        # The Supabase SDK call is synchronous; keep DNS/network failures from
        # blocking FastAPI startup and leave the app in explicit memory-only mode.
        await asyncio.wait_for(
            asyncio.to_thread(
                lambda: client.table("tasks").select("id").limit(1).execute()
            ),
            timeout=10,
        )
        print("[DB] [OK] Connected to Supabase PostgreSQL")
        return True
    except asyncio.TimeoutError:
        print("[DB] [WARN] Supabase connection timed out")
        print("[DB] System will run in memory-only mode")
        return False
    except Exception as e:
        print(f"[DB] [WARN] Connection test failed: {e}")
        print("[DB] Please run the SQL migration to create tables")
        return False


# =============================================================================
# SQL Migration (Run this in Supabase SQL Editor)
# =============================================================================
MIGRATION_SQL = """
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(255) UNIQUE,  -- For external auth (Telegram, etc.)
    email VARCHAR(255) UNIQUE,
    name VARCHAR(255),
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Conversations table (chat sessions)
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500),
    status VARCHAR(50) DEFAULT 'active',  -- active, completed, archived
    context JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,  -- user, assistant, system
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    intent VARCHAR(500) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',  -- pending, in_progress, completed, failed
    result TEXT,
    steps JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Memories table (user preferences and context)
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    key VARCHAR(255) NOT NULL,
    value JSONB NOT NULL,
    category VARCHAR(100),  -- preference, fact, context
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, key)
);

-- Workflow sessions (for multi-stage conversations)
CREATE TABLE IF NOT EXISTS workflow_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    workflow_type VARCHAR(100) NOT NULL,
    current_stage INTEGER DEFAULT 0,
    stages JSONB DEFAULT '[]',
    context JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Mission governance tables
CREATE TABLE IF NOT EXISTS policy_rules (
    rule_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    risk_level VARCHAR(50) NOT NULL,
    keywords JSONB DEFAULT '[]',
    required_roles JSONB DEFAULT '[]',
    min_approvals INTEGER DEFAULT 1,
    active BOOLEAN DEFAULT TRUE,
    version VARCHAR(50) DEFAULT 'v1',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS missions (
    mission_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
    title VARCHAR(255) NOT NULL,
    description TEXT,
    state VARCHAR(50) NOT NULL DEFAULT 'draft',
    policy_version VARCHAR(50) NOT NULL DEFAULT 'v1',
    trace_completeness NUMERIC(6,2) DEFAULT 0,
    policy_compliance NUMERIC(6,2) DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS mission_steps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mission_id UUID REFERENCES missions(mission_id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    action_type VARCHAR(255),
    risk_level VARCHAR(50) DEFAULT 'low',
    requires_approval BOOLEAN DEFAULT FALSE,
    approver_roles JSONB DEFAULT '[]',
    state VARCHAR(50) DEFAULT 'pending',
    owner_role VARCHAR(100),
    approval_decision_id UUID,
    evidence_artifact_ids JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS approval_decisions (
    decision_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mission_id UUID REFERENCES missions(mission_id) ON DELETE CASCADE,
    step_id UUID REFERENCES mission_steps(id) ON DELETE CASCADE,
    tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    approver_id UUID REFERENCES users(id) ON DELETE CASCADE,
    approver_roles JSONB DEFAULT '[]',
    decision VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    policy_version VARCHAR(50) NOT NULL DEFAULT 'v1',
    policy_rule_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS mission_state_transitions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mission_id UUID REFERENCES missions(mission_id) ON DELETE CASCADE,
    actor_id UUID REFERENCES users(id) ON DELETE CASCADE,
    previous_state VARCHAR(50),
    next_state VARCHAR(50) NOT NULL,
    reason TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS evidence_artifacts (
    artifact_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mission_id UUID REFERENCES missions(mission_id) ON DELETE CASCADE,
    step_id UUID REFERENCES mission_steps(id) ON DELETE SET NULL,
    tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    file_path TEXT NOT NULL,
    content_hash VARCHAR(255) NOT NULL,
    previous_hash VARCHAR(255),
    classification VARCHAR(50) DEFAULT 'internal',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mission_id UUID REFERENCES missions(mission_id) ON DELETE CASCADE,
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
    action VARCHAR(255) NOT NULL,
    resource_id VARCHAR(255),
    previous_state VARCHAR(255),
    next_state VARCHAR(255),
    reason TEXT,
    policy_version VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trust_metrics_daily (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
    metric_date DATE NOT NULL DEFAULT CURRENT_DATE,
    mission_count INTEGER DEFAULT 0,
    trace_completeness NUMERIC(6,2) DEFAULT 0,
    policy_compliance NUMERIC(6,2) DEFAULT 0,
    approval_backlog INTEGER DEFAULT 0,
    fallback_frequency NUMERIC(6,2) DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, metric_date)
);

-- Plugin executions log
CREATE TABLE IF NOT EXISTS plugin_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    plugin_name VARCHAR(100) NOT NULL,
    action VARCHAR(100) NOT NULL,
    parameters JSONB DEFAULT '{}',
    result JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    execution_time_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_memories_user_key ON memories(user_id, key);
CREATE INDEX IF NOT EXISTS idx_workflow_sessions_user ON workflow_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_missions_user_id ON missions(user_id);
CREATE INDEX IF NOT EXISTS idx_missions_tenant_id ON missions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_missions_state ON missions(state);
CREATE INDEX IF NOT EXISTS idx_mission_steps_mission_id ON mission_steps(mission_id);
CREATE INDEX IF NOT EXISTS idx_approval_decisions_mission_id ON approval_decisions(mission_id);
CREATE INDEX IF NOT EXISTS idx_evidence_artifacts_mission_id ON evidence_artifacts(mission_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_mission_id ON audit_events(mission_id);
CREATE INDEX IF NOT EXISTS idx_trust_metrics_daily_tenant_date ON trust_metrics_daily(tenant_id, metric_date);

-- Row Level Security (RLS) Policies
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE missions ENABLE ROW LEVEL SECURITY;
ALTER TABLE mission_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE mission_state_transitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE trust_metrics_daily ENABLE ROW LEVEL SECURITY;

-- Realtime subscriptions (enable for specific tables)
ALTER PUBLICATION supabase_realtime ADD TABLE tasks;
ALTER PUBLICATION supabase_realtime ADD TABLE messages;

-- Triggers for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_memories_updated_at BEFORE UPDATE ON memories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workflow_sessions_updated_at BEFORE UPDATE ON workflow_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_policy_rules_updated_at BEFORE UPDATE ON policy_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_missions_updated_at BEFORE UPDATE ON missions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_mission_steps_updated_at BEFORE UPDATE ON mission_steps
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
"""


# =============================================================================
# Data Models & CRUD Operations
# =============================================================================

class User:
    """User model"""
    def __init__(
        self,
        id: Optional[str] = None,
        external_id: Optional[str] = None,
        email: Optional[str] = None,
        name: Optional[str] = None,
        preferences: Dict = None
    ):
        self.id = id
        self.external_id = external_id
        self.email = email
        self.name = name
        self.preferences = preferences or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "external_id": self.external_id,
            "email": self.email,
            "name": self.name,
            "preferences": self.preferences
        }
    
    @classmethod
    def from_dict(cls, data: Dict, id: str = None) -> "User":
        return cls(
            id=id or data.get("id"),
            external_id=data.get("external_id"),
            email=data.get("email"),
            name=data.get("name"),
            preferences=data.get("preferences", {})
        )


class Task:
    """Task model"""
    def __init__(
        self,
        id: Optional[str] = None,
        user_id: str = None,
        conversation_id: Optional[str] = None,
        intent: str = "",
        status: str = "pending",
        result: Optional[str] = None,
        steps: List[Dict] = None,
        metadata: Dict = None
    ):
        self.id = id
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.intent = intent
        self.status = status
        self.result = result
        self.steps = steps or []
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "user_id": self.user_id,
            "intent": self.intent,
            "status": self.status,
            "result": self.result,
            "steps": self.steps,
            "metadata": self.metadata
        }
        if self.conversation_id:
            data["conversation_id"] = self.conversation_id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Task":
        return cls(
            id=data.get("id"),
            user_id=data.get("user_id"),
            conversation_id=data.get("conversation_id"),
            intent=data.get("intent", ""),
            status=data.get("status", "pending"),
            result=data.get("result"),
            steps=data.get("steps", []),
            metadata=data.get("metadata", {})
        )


class Memory:
    """Memory model for user context and preferences"""
    def __init__(
        self,
        id: Optional[str] = None,
        user_id: str = None,
        key: str = "",
        value: Any = None,
        category: str = "context"
    ):
        self.id = id
        self.user_id = user_id
        self.key = key
        self.value = value
        self.category = category
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "key": self.key,
            "value": self.value if isinstance(self.value, dict) else {"data": self.value},
            "category": self.category
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Memory":
        value = data.get("value", {})
        if isinstance(value, dict) and "data" in value and len(value) == 1:
            value = value["data"]
        return cls(
            id=data.get("id"),
            user_id=data.get("user_id"),
            key=data.get("key", ""),
            value=value,
            category=data.get("category", "context")
        )


# =============================================================================
# Database Operations
# =============================================================================

class DatabaseOperations:
    """Database CRUD operations using Supabase"""
    
    def __init__(self):
        self._client = None
        self._in_memory_store = {
            "users": {},
            "tasks": {},
            "memories": {},
            "conversations": {},
            "workflow_sessions": {}
        }
    
    @property
    def client(self) -> Optional[Client]:
        if self._client is None:
            self._client = get_supabase_client()
        return self._client
    
    def _use_memory(self) -> bool:
        """Check if we should use in-memory storage"""
        return self.client is None
    
    # ---- Users ----
    async def get_or_create_user(self, external_id: str, name: str = None) -> User:
        """Get user by external_id or create new one"""
        if self._use_memory():
            if external_id in self._in_memory_store["users"]:
                return User.from_dict(self._in_memory_store["users"][external_id])
            user_data = {"id": external_id, "external_id": external_id, "name": name or external_id}
            self._in_memory_store["users"][external_id] = user_data
            return User.from_dict(user_data)
        
        try:
            # Try to find existing user
            result = self.client.table("users").select("*").eq("external_id", external_id).execute()
            if result.data:
                return User.from_dict(result.data[0])
            
            # Create new user
            user = User(external_id=external_id, name=name or external_id)
            result = self.client.table("users").insert(user.to_dict()).execute()
            return User.from_dict(result.data[0])
        except Exception as e:
            print(f"[DB] User error: {e}")
            return User(id=external_id, external_id=external_id, name=name)
            
    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> Optional[User]:
        """Update user profile"""
        if self._use_memory():
            # In memory, we map external_id to user_data, but sometimes id == external_id
            for ext_id, u_data in self._in_memory_store["users"].items():
                if u_data.get("id") == user_id or ext_id == user_id:
                    self._in_memory_store["users"][ext_id].update(updates)
                    return User.from_dict(self._in_memory_store["users"][ext_id])
            
            # If user not found, create it with the updates
            # This handles the case where we're updating a user that hasn't been explicitly created yet
            user_data = {"id": user_id, "external_id": user_id}
            user_data.update(updates)
            self._in_memory_store["users"][user_id] = user_data
            return User.from_dict(user_data)
            
        try:
            result = self.client.table("users").update(updates).eq("id", user_id).execute()
            # If id is external_id, fallback to eq("external_id")
            if not result.data:
                result = self.client.table("users").update(updates).eq("external_id", user_id).execute()
            if result.data:
                return User.from_dict(result.data[0])
            # If Supabase update didn't find the user, update in memory as fallback
            user_data = {"id": user_id, "external_id": user_id}
            user_data.update(updates)
            self._in_memory_store["users"][user_id] = user_data
            return User.from_dict(user_data)
        except Exception as e:
            print(f"[DB] Update user error: {e}")
            # Fallback to memory update when Supabase fails
            user_data = {"id": user_id, "external_id": user_id}
            user_data.update(updates)
            self._in_memory_store["users"][user_id] = user_data
            return User.from_dict(user_data)
    
    # ---- Tasks ----
    async def create_task(self, task: Task) -> Task:
        """Create a new task"""
        if self._use_memory():
            import uuid
            task.id = str(uuid.uuid4())
            self._in_memory_store["tasks"][task.id] = task.to_dict()
            self._in_memory_store["tasks"][task.id]["id"] = task.id
            return task
        
        try:
            result = self.client.table("tasks").insert(task.to_dict()).execute()
            return Task.from_dict(result.data[0])
        except Exception as e:
            print(f"[DB] Create task error: {e}")
            raise
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        if self._use_memory():
            data = self._in_memory_store["tasks"].get(task_id)
            return Task.from_dict(data) if data else None
        
        try:
            result = self.client.table("tasks").select("*").eq("id", task_id).execute()
            return Task.from_dict(result.data[0]) if result.data else None
        except Exception as e:
            print(f"[DB] Get task error: {e}")
            return None
    
    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> Optional[Task]:
        """Update task fields"""
        if self._use_memory():
            if task_id in self._in_memory_store["tasks"]:
                self._in_memory_store["tasks"][task_id].update(updates)
                return Task.from_dict(self._in_memory_store["tasks"][task_id])
            return None
        
        try:
            result = self.client.table("tasks").update(updates).eq("id", task_id).execute()
            return Task.from_dict(result.data[0]) if result.data else None
        except Exception as e:
            print(f"[DB] Update task error: {e}")
            return None
    
    async def get_user_tasks(self, user_id: str, status: str = None, limit: int = 50) -> List[Task]:
        """Get tasks for a user"""
        if self._use_memory():
            tasks = [Task.from_dict(t) for t in self._in_memory_store["tasks"].values()
                     if t.get("user_id") == user_id]
            if status:
                tasks = [t for t in tasks if t.status == status]
            return tasks[:limit]
        
        try:
            query = self.client.table("tasks").select("*").eq("user_id", user_id)
            if status:
                query = query.eq("status", status)
            result = query.order("created_at", desc=True).limit(limit).execute()
            return [Task.from_dict(t) for t in result.data]
        except Exception as e:
            print(f"[DB] Get user tasks error: {e}")
            return []
    
    # ---- Memories ----
    async def set_memory(self, memory: Memory) -> Memory:
        """Set or update a memory (upsert)"""
        if self._use_memory():
            key = f"{memory.user_id}:{memory.key}"
            self._in_memory_store["memories"][key] = memory.to_dict()
            return memory
        
        try:
            result = self.client.table("memories").upsert(
                memory.to_dict(),
                on_conflict="user_id,key"
            ).execute()
            return Memory.from_dict(result.data[0]) if result.data else memory
        except Exception as e:
            print(f"[DB] Set memory error: {e}")
            return memory
    
    async def get_memory(self, user_id: str, key: str) -> Optional[Memory]:
        """Get a specific memory"""
        if self._use_memory():
            data = self._in_memory_store["memories"].get(f"{user_id}:{key}")
            return Memory.from_dict(data) if data else None
        
        try:
            result = self.client.table("memories").select("*").eq("user_id", user_id).eq("key", key).execute()
            return Memory.from_dict(result.data[0]) if result.data else None
        except Exception as e:
            print(f"[DB] Get memory error: {e}")
            return None
    
    async def get_user_memories(self, user_id: str, category: str = None) -> List[Memory]:
        """Get all memories for a user"""
        if self._use_memory():
            memories = [Memory.from_dict(m) for m in self._in_memory_store["memories"].values()
                       if m.get("user_id") == user_id]
            if category:
                memories = [m for m in memories if m.category == category]
            return memories
        
        try:
            query = self.client.table("memories").select("*").eq("user_id", user_id)
            if category:
                query = query.eq("category", category)
            result = query.execute()
            return [Memory.from_dict(m) for m in result.data]
        except Exception as e:
            print(f"[DB] Get user memories error: {e}")
            return []
    
    async def search_memories(self, user_id: str, search_term: str) -> List[Memory]:
        """Search memories by key pattern"""
        if self._use_memory():
            return [Memory.from_dict(m) for m in self._in_memory_store["memories"].values()
                   if m.get("user_id") == user_id and search_term.lower() in m.get("key", "").lower()]
        
        try:
            result = self.client.table("memories").select("*").eq("user_id", user_id).ilike("key", f"%{search_term}%").execute()
            return [Memory.from_dict(m) for m in result.data]
        except Exception as e:
            print(f"[DB] Search memories error: {e}")
            return []


# Global database operations instance
_db_ops: Optional[DatabaseOperations] = None


def get_db() -> DatabaseOperations:
    """Get database operations singleton"""
    global _db_ops
    if _db_ops is None:
        _db_ops = DatabaseOperations()
    return _db_ops


# =============================================================================
# Legacy compatibility layer (for existing code)
# =============================================================================

def get_tasks_collection():
    """Legacy compatibility - returns db operations"""
    return get_db()


def get_memories_collection():
    """Legacy compatibility - returns db operations"""
    return get_db()


def get_conversations_collection():
    """Legacy compatibility - returns db operations"""
    return get_db()


# =============================================================================
# Legacy function wrappers (for existing code compatibility)
# =============================================================================

async def get_task(task_id: str) -> Optional[Task]:
    """Get task by ID - legacy wrapper"""
    return await get_db().get_task(task_id)


async def get_tasks_by_user(user_id: str, limit: int = 50) -> List[Task]:
    """Get tasks by user - legacy wrapper"""
    return await get_db().get_user_tasks(user_id, limit=limit)


async def get_memory_by_key(user_id: str, key: str) -> Optional[Memory]:
    """Get memory by key - legacy wrapper"""
    return await get_db().get_memory(user_id, key)


async def get_memories_by_user(user_id: str, category: str = None) -> List[Memory]:
    """Get all memories for user - legacy wrapper"""
    return await get_db().get_user_memories(user_id, category)


async def create_memory(user_id: str, key: str, value: Any, context: Dict = None) -> Memory:
    """Create memory - legacy wrapper"""
    memory = Memory(user_id=user_id, key=key, value=value, category=context.get("category") if context else None)
    return await get_db().set_memory(memory)


async def update_memory(memory_id: str, updates: Dict[str, Any]) -> Optional[Memory]:
    """Update memory - legacy wrapper (limited support)"""
    # Note: This is a simplified version - Supabase uses upsert
    return None


async def search_memories(user_id: str, search_term: str) -> List[Memory]:
    """Search memories - legacy wrapper"""
    return await get_db().search_memories(user_id, search_term)


async def create_task(user_id: str = None, intent: str = None, task: Task = None) -> Task:
    """Create task - legacy wrapper supporting both old and new signatures"""
    if task is not None:
        return await get_db().create_task(task)
    else:
        new_task = Task(user_id=user_id or "default", intent=intent or "")
        return await get_db().create_task(new_task)
