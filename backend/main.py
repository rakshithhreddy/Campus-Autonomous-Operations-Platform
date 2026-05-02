"""
Super Manager - Main FastAPI Application
A next-generation AI agent system for intent-to-action execution

Features:
- Multi-provider AI routing (Ollama, OpenAI, Groq, Zuki)
- Dynamic workflow planning
- Real-time WebSocket updates
- Plugin architecture for extensibility
- Enterprise-grade performance optimizations
- Security hardening
- Structured logging
"""
from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

try:
    from .config import validate_settings
except ImportError:  # pragma: no cover
    from backend.config import validate_settings

BACKEND_ENV_FILE = Path(__file__).resolve().parent / ".env"

# Load environment early from the backend config file, not the repo root.
load_dotenv(dotenv_path=BACKEND_ENV_FILE, override=True)

# Fail fast for unsafe production settings.
validate_settings()

# If this module is imported as a top-level module (e.g. `cd backend && uvicorn main:app`),
# relative imports (from .core/ .routes) will fail in submodules. Ensure the repository root
# is on sys.path so we can import the `backend` package consistently.
if __package__ in (None, ""):  # pragma: no cover
    try:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if repo_root and repo_root not in sys.path:
            sys.path.insert(0, repo_root)
    except Exception:
        pass

# Import and setup structured logging FIRST
# Support both:
# - `uvicorn backend.main:app` (package import)
# - `cd backend && uvicorn main:app` (module import)
try:
    from .core.logging_config import (
        setup_logging, LogConfig, get_logger,
        perf_logger, audit_logger, LogContext, timed
    )
except ImportError:  # pragma: no cover
    from backend.core.logging_config import (
        setup_logging, LogConfig, get_logger,
        perf_logger, audit_logger, LogContext, timed
    )

# Configure logging based on environment
log_config = LogConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_format=os.getenv("LOG_FORMAT", "").lower() == "json",
    log_file=os.getenv("LOG_FILE")
)
setup_logging(log_config)
logger = get_logger(__name__)

# Import performance and security modules
try:
    from .core.performance import (
        ai_circuit_breaker, db_circuit_breaker, email_circuit_breaker,
        response_cache, api_rate_limiter, health_monitor,
        RequestTracer
    )
    from .core.security import setup_security_middleware
    from .core.auth_middleware import AuthMiddleware
except ImportError:  # pragma: no cover
    from backend.core.performance import (
        ai_circuit_breaker, db_circuit_breaker, email_circuit_breaker,
        response_cache, api_rate_limiter, health_monitor,
        RequestTracer
    )
    from backend.core.security import setup_security_middleware
    from backend.core.auth_middleware import AuthMiddleware

# Force UTF-8 encoding for stdout/stderr on Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

# Import database - use Supabase (production)
try:
    from .database_supabase import init_db, get_db
except ImportError:  # pragma: no cover
    from backend.database_supabase import init_db, get_db
logger.info("[DB] Using Supabase PostgreSQL")

# Import routes with error handling to prevent one failed import from crashing the app
try:
    from .routes import api, streaming, users
except ImportError:  # pragma: no cover
    from backend.routes import api, streaming, users

# Legacy routes - loaded conditionally
try:
    try:
        from .routes import agent, plugins, task_agent, tasks, memory
    except ImportError:  # pragma: no cover
        from backend.routes import agent, plugins, task_agent, tasks, memory
    LEGACY_ROUTES_AVAILABLE = True
except Exception as e:
    LEGACY_ROUTES_AVAILABLE = False
    logger.warning(f"[IMPORT] Legacy routes partially unavailable: {e}")

# Try to import new routers - they may fail due to dependencies
try:
    try:
        from .routes import agent_v2
    except ImportError:  # pragma: no cover
        from backend.routes import agent_v2
    AGENT_V2_AVAILABLE = True
    logger.info("[IMPORT] ✅ agent_v2 loaded")
except Exception as e:
    AGENT_V2_AVAILABLE = False
    agent_v2 = None
    logger.error(f"[IMPORT] ❌ agent_v2 failed: {e}")

try:
    try:
        from .routes import tasks_v2
    except ImportError:  # pragma: no cover
        from backend.routes import tasks_v2
    TASKS_V2_AVAILABLE = True
    logger.info("[IMPORT] ✅ tasks_v2 loaded")
except Exception as e:
    TASKS_V2_AVAILABLE = False
    tasks_v2 = None
    logger.error(f"[IMPORT] ❌ tasks_v2 failed: {e}")

try:
    try:
        from .routes import governance
    except ImportError:  # pragma: no cover
        from backend.routes import governance
    GOVERNANCE_AVAILABLE = True
    logger.info("[IMPORT] ✅ governance loaded")
except Exception as e:
    GOVERNANCE_AVAILABLE = False
    governance = None
    logger.error(f"[IMPORT] ❌ governance failed: {e}")

try:
    try:
        from .routes import evidence
    except ImportError:  # pragma: no cover
        from backend.routes import evidence
    EVIDENCE_AVAILABLE = True
    logger.info("[IMPORT] ✅ evidence loaded")
except Exception as e:
    EVIDENCE_AVAILABLE = False
    evidence = None
    logger.error(f"[IMPORT] ❌ evidence failed: {e}")

try:
    try:
        from .routes import policies
    except ImportError:  # pragma: no cover
        from backend.routes import policies
    POLICIES_AVAILABLE = True
    logger.info("[IMPORT] ✅ policies loaded")
except Exception as e:
    POLICIES_AVAILABLE = False
    policies = None
    logger.error(f"[IMPORT] ❌ policies failed: {e}")

try:
    try:
        from .routes import analytics
    except ImportError:  # pragma: no cover
        from backend.routes import analytics
    ANALYTICS_AVAILABLE = True
    logger.info("[IMPORT] ✅ analytics loaded")
except Exception as e:
    ANALYTICS_AVAILABLE = False
    analytics = None
    logger.error(f"[IMPORT] ❌ analytics failed: {e}")

try:
    try:
        from .routes import identity
    except ImportError:  # pragma: no cover
        from backend.routes import identity
    IDENTITY_AVAILABLE = True
    logger.info("[IMPORT] ✅ identity loaded")
except Exception as e:
    IDENTITY_AVAILABLE = False
    identity = None
    logger.error(f"[IMPORT] ❌ identity failed: {e}")

try:
    try:
        from .routes import oauth
    except ImportError:  # pragma: no cover
        from backend.routes import oauth
    OAUTH_AVAILABLE = True
    logger.info("[IMPORT] ✅ oauth loaded")
except Exception as e:
    OAUTH_AVAILABLE = False
    oauth = None
    logger.error(f"[IMPORT] ❌ oauth failed: {e}")

try:
    try:
        from .routes import automation
    except ImportError:  # pragma: no cover
        from backend.routes import automation
    AUTOMATION_AVAILABLE = True
    logger.info("[IMPORT] ✅ automation loaded")
except Exception as e:
    AUTOMATION_AVAILABLE = False
    automation = None
    logger.error(f"[IMPORT] ❌ automation failed: {e}")

try:
    try:
        from .routes import integrations
    except ImportError:  # pragma: no cover
        from backend.routes import integrations
    INTEGRATIONS_AVAILABLE = True
    logger.info("[IMPORT] ✅ integrations loaded")
except Exception as e:
    INTEGRATIONS_AVAILABLE = False
    integrations = None
    logger.error(f"[IMPORT] ❌ integrations failed: {e}")

# Faculty email management and assistance
try:
    try:
        from .routes import faculty
    except ImportError:  # pragma: no cover
        from backend.routes import faculty
    FACULTY_AVAILABLE = True
    logger.info("[IMPORT] ✅ faculty loaded")
except Exception as e:
    FACULTY_AVAILABLE = False
    faculty = None
    logger.error(f"[IMPORT] ❌ faculty failed: {e}")

# Follow-up Pipeline System - Automated workflow orchestration
try:
    try:
        from .routes import workflows
    except ImportError:  # pragma: no cover
        from backend.routes import workflows
    WORKFLOWS_AVAILABLE = True
    logger.info("[IMPORT] ✅ workflows loaded")
except Exception as e:
    WORKFLOWS_AVAILABLE = False
    workflows = None
    logger.error(f"[IMPORT] ❌ workflows failed: {e}")

# Messaging webhooks (Telegram, WhatsApp, Voice)

# Messaging webhooks (Telegram, WhatsApp, Voice)
try:
    try:
        from .routes import messaging
    except ImportError:  # pragma: no cover
        from backend.routes import messaging
    MESSAGING_AVAILABLE = True
    logger.info("[IMPORT] ✅ messaging loaded")
except Exception as e:
    MESSAGING_AVAILABLE = False
    messaging = None
    logger.error(f"[IMPORT] ❌ messaging failed: {e}")

# Teaching mode (workflow learning)
try:
    try:
        from .routes import teaching
    except ImportError:  # pragma: no cover
        from backend.routes import teaching
    TEACHING_AVAILABLE = True
    logger.info("[IMPORT] ✅ teaching loaded")
except Exception as e:
    TEACHING_AVAILABLE = False
    teaching = None
    logger.error(f"[IMPORT] ❌ teaching failed: {e}")

try:
    from .core.agent import AgentManager
    from .core.ai_providers import get_ai_router
    from .core.realtime import get_connection_manager, websocket_endpoint
except ImportError:  # pragma: no cover
    from backend.core.agent import AgentManager
    from backend.core.ai_providers import get_ai_router
    from backend.core.realtime import get_connection_manager, websocket_endpoint

# Import scheduler
try:
    from .agent.scheduler import start_scheduler, stop_scheduler
except ImportError:  # pragma: no cover
    from backend.agent.scheduler import start_scheduler, stop_scheduler

# Initialize request tracer
request_tracer = RequestTracer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup on startup/shutdown"""
    startup_start = time.time()
    logger.info("=" * 60)
    logger.info("  SUPER MANAGER - Starting up...")
    logger.info("=" * 60)
    
    # Register health monitor components
    health_monitor.register_component("database")
    health_monitor.register_component("ai_router")
    health_monitor.register_component("websocket")
    
    # Initialize database
    try:
        db_ready = await init_db()
        health_monitor.update_health("database", bool(db_ready))
        if db_ready:
            logger.info("[DB] ✅ Database initialized")
        else:
            logger.info("[DB] Running in memory-only mode")
    except Exception as e:
        health_monitor.update_health("database", False, str(e))
        logger.warning(f"[DB] ⚠️ Database initialization warning: {e}")
        logger.info("[DB] System will run in memory-only mode")
    
    # Initialize AI Router (with all providers)
    try:
        ai_router = get_ai_router()
        await ai_router.initialize()
        app.state.ai_router = ai_router
        available = ai_router.get_available_providers()
        health_monitor.update_health("ai_router", True, metadata={"providers": available})
        logger.info(f"[AI] ✅ AI Router initialized. Available: {available}")
    except Exception as e:
        health_monitor.update_health("ai_router", False, str(e))
        logger.warning(f"[AI] ⚠️ AI Router warning: {e}")
    
    # Initialize Agent Manager
    app.state.agent_manager = AgentManager()
    logger.info("[AGENT] ✅ Agent Manager initialized")
    
    # Initialize WebSocket Connection Manager
    app.state.ws_manager = get_connection_manager()
    health_monitor.update_health("websocket", True)
    logger.info("[WS] ✅ WebSocket Manager initialized")
    
    # Start the job scheduler for reminders and scheduled tasks
    try:
        start_scheduler()
        logger.info("[SCHEDULER] ✅ Job scheduler started")
    except Exception as e:
        logger.warning(f"[SCHEDULER] ⚠️ Scheduler warning: {e}")
    
    # Store performance utilities in app state
    app.state.request_tracer = request_tracer
    app.state.health_monitor = health_monitor
    
    startup_duration = (time.time() - startup_start) * 1000
    perf_logger.log_duration("startup", startup_duration)
    
    logger.info("=" * 60)
    logger.info(f"  SUPER MANAGER - Ready in {startup_duration:.0f}ms!")
    logger.info("=" * 60)
    
    yield
    
    # Cleanup
    logger.info("[SHUTDOWN] Cleaning up resources...")
    audit_logger.log_security_event("shutdown", "low", "Application shutting down")

app = FastAPI(
    title="Super Manager API",
    description="""
    ## AI Agent System for Intent-to-Action Execution
    
    Super Manager is an intelligent AI assistant that:
    - Understands natural language requests
    - Plans multi-step workflows dynamically
    - Executes real-world actions (email, meetings, bookings)
    - Provides real-time progress updates
    
    ### AI Providers
    - **Ollama** (Local, Free) - Primary provider for privacy
    - **Groq** (Fast, Free tier) - Secondary fallback
    - **Zuki** (Free API) - Alternative fallback
    - **OpenAI** (Paid) - High-capability fallback
    
    ### Security Features
    - Rate limiting (1000 requests/minute)
    - Input validation and sanitization
    - Security headers (CSP, HSTS, X-Frame-Options)
    - Request ID tracking
    
    ### Performance Features
    - Circuit breaker for external services
    - Response caching (5 minute TTL)
    - Request tracing with percentiles (p50, p90, p95, p99)
    """,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Setup security middleware (headers, rate limiting, logging)
setup_security_middleware(app)

# Auth middleware: enforces JWT on all non-public paths (Item 1)
app.add_middleware(AuthMiddleware)

# Register standardized error handlers (Item 68)
try:
    from .core.error_response import register_exception_handlers
except ImportError:
    from backend.core.error_response import register_exception_handlers
register_exception_handlers(app)

# Performance tracking middleware
@app.middleware("http")
async def performance_tracking_middleware(request: Request, call_next):
    """Track request performance metrics"""
    start_time = time.time()
    operation = f"{request.method} {request.url.path}"
    
    response = await call_next(request)
    
    duration_ms = (time.time() - start_time) * 1000
    request_tracer.record_duration(operation, duration_ms)
    
    # Add performance header
    response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
    
    return response

# Global exception handler
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        import traceback
        error_msg = f"[CRITICAL] Uncaught exception: {e}\n{traceback.format_exc()}"
        logger.error(error_msg, exc_info=True)
        audit_logger.log_security_event(
            "error", "high", 
            f"Unhandled exception: {type(e).__name__}",
            path=str(request.url.path)
        )
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

# CORS middleware
_cors_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:5173",
]
_frontend_url = os.getenv("FRONTEND_URL", "")
if _frontend_url and _frontend_url != "*":
    _cors_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # Allow preview deploys + any local Vite port during development
    allow_origin_regex=r"(https://(.*\.vercel\.app|.*\.pages\.dev)|https?://(localhost|127\.0\.0\.1)(:\d+)?)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
# /api/chat is THE MAIN ENDPOINT - clean, simple flow
app.include_router(api.router)  # MAIN: /api/chat - brain.py with engine integration
app.include_router(streaming.router)  # /api/stream/* - streaming version
app.include_router(users.router)  # /api/users/* - user profile and preferences

# Conditionally include new routers
if AGENT_V2_AVAILABLE and agent_v2:
    app.include_router(agent_v2.router)  # /api/v2/* - TRUE AI Agent
    logger.info("[ROUTER] agent_v2 router added")

if TASKS_V2_AVAILABLE and tasks_v2:
    app.include_router(tasks_v2.router)  # /api/v2/tasks/* - Task Orchestration
    logger.info("[ROUTER] tasks_v2 router added")

if GOVERNANCE_AVAILABLE and governance:
    app.include_router(governance.router)  # /api/governance/* - approvals, missions, trust
    logger.info("[ROUTER] governance router added")

if EVIDENCE_AVAILABLE and evidence:
    app.include_router(evidence.router)  # /api/evidence/* - evidence vault
    logger.info("[ROUTER] evidence router added")

if POLICIES_AVAILABLE and policies:
    app.include_router(policies.router)  # /api/policies/* - policy studio
    logger.info("[ROUTER] policies router added")

if ANALYTICS_AVAILABLE and analytics:
    app.include_router(analytics.router)  # /api/analytics/* - trust analytics
    logger.info("[ROUTER] analytics router added")

if IDENTITY_AVAILABLE and identity:
    app.include_router(identity.router)  # /api/identity/* - AI Identity Management
    logger.info("[ROUTER] identity router added")

if OAUTH_AVAILABLE and oauth:
    app.include_router(oauth.router)  # /api/oauth/* - OAuth Flow Management
    logger.info("[ROUTER] oauth router added")

if AUTOMATION_AVAILABLE and automation:
    app.include_router(automation.router)  # /api/automation/* - Automation Flows
    logger.info("[ROUTER] automation router added")

if INTEGRATIONS_AVAILABLE and integrations:
    app.include_router(integrations.router)  # /api/integrations/* - Integration Manager
    logger.info("[ROUTER] integrations router added")
if FACULTY_AVAILABLE and faculty:
    app.include_router(faculty.router)  # /api/faculty/* - Faculty Email Assistant
    logger.info("[ROUTER] faculty router added")

if WORKFLOWS_AVAILABLE and workflows:
    app.include_router(workflows.router)  # /api/workflows/* - Follow-up Pipeline System
    logger.info("[ROUTER] workflows router added")


if MESSAGING_AVAILABLE and messaging:
    app.include_router(messaging.router)  # /webhook/* - Telegram, WhatsApp, Voice
    logger.info("[ROUTER] messaging router added")

if TEACHING_AVAILABLE and teaching:
    app.include_router(teaching.router)  # /api/teach/* - Workflow Learning
    logger.info("[ROUTER] teaching router added")

# Legacy routes (only if available)
if LEGACY_ROUTES_AVAILABLE:
    app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
    app.include_router(task_agent.router, prefix="/api/task", tags=["task_agent"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(plugins.router, prefix="/api/plugins", tags=["plugins"])


# =============================================================================
# WebSocket Endpoint for Real-time Updates
# =============================================================================
@app.websocket("/ws/{user_id}")
async def websocket_route(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for real-time task progress updates"""
    await websocket_endpoint(websocket, user_id)


# =============================================================================
# Root & Health Endpoints
# =============================================================================
@app.get("/")
async def root():
    return {
        "message": "Super Manager API",
        "status": "operational",
        "version": "2.0.0",
        "docs": "/api/docs"
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint for monitoring"""
    ai_router = getattr(app.state, 'ai_router', None)
    tracer = getattr(app.state, 'request_tracer', None)
    monitor = getattr(app.state, 'health_monitor', None)
    
    # Get circuit breaker states
    circuit_status = {
        "ai": ai_circuit_breaker.state.name if ai_circuit_breaker else "unknown",
        "database": db_circuit_breaker.state.name if db_circuit_breaker else "unknown",
        "email": email_circuit_breaker.state.name if email_circuit_breaker else "unknown"
    }
    
    # Get performance metrics
    perf_metrics = tracer.get_stats() if tracer else {}
    
    # Get cache stats
    cache_stats = response_cache.get_stats() if response_cache else {}
    
    # Check overall health
    component_health = monitor.get_overall_health() if monitor else {}
    all_healthy = component_health.get("healthy", False) if isinstance(component_health, dict) else True
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "ai_providers": ai_router.get_available_providers() if ai_router else [],
        "websocket_connections": app.state.ws_manager.get_stats() if hasattr(app.state, 'ws_manager') else {},
        "circuit_breakers": circuit_status,
        "performance": perf_metrics,
        "cache": cache_stats,
        "components": component_health
    }


@app.get("/api/health/ready")
async def readiness_check():
    """
    Readiness probe endpoint.
    
    Returns 200 if the service is ready to accept traffic.
    Returns 503 if critical dependencies are unavailable.
    """
    monitor = getattr(app.state, 'health_monitor', None)
    ai_router = getattr(app.state, 'ai_router', None)
    
    # Check critical components
    checks = {
        "ai_router": ai_router is not None and len(ai_router.get_available_providers()) > 0,
        "websocket_manager": hasattr(app.state, 'ws_manager'),
        "agent_manager": hasattr(app.state, 'agent_manager'),
    }
    
    # Database is optional (can run in memory mode)
    if monitor:
        component_health = monitor.get_overall_health()
        if isinstance(component_health, dict):
            checks["database"] = component_health.get("components", {}).get("database", {}).get("healthy", True)
    
    all_ready = all(checks.values())
    
    if not all_ready:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "checks": checks,
                "message": "Service not ready"
            }
        )
    
    return {
        "ready": True,
        "checks": checks,
        "message": "Service is ready"
    }


@app.get("/api/health/metrics")
async def health_metrics():
    """
    Prometheus-compatible metrics endpoint.
    
    Returns detailed performance metrics for monitoring.
    """
    tracer = getattr(app.state, 'request_tracer', None)
    
    metrics = {
        "cache": response_cache.get_stats() if response_cache else {},
        "rate_limiter": api_rate_limiter.get_stats() if api_rate_limiter else {},
        "circuit_breakers": {
            "ai": {
                "state": ai_circuit_breaker.state.name,
                "failures": ai_circuit_breaker._failure_count
            } if ai_circuit_breaker else {},
            "database": {
                "state": db_circuit_breaker.state.name,
                "failures": db_circuit_breaker._failure_count
            } if db_circuit_breaker else {},
            "email": {
                "state": email_circuit_breaker.state.name,
                "failures": email_circuit_breaker._failure_count
            } if email_circuit_breaker else {}
        },
        "request_traces": tracer.get_stats() if tracer else {}
    }
    
    return metrics

@app.get("/api/status")
async def system_status():
    """Detailed system status with setup requirements"""
    import os
    ai_router = getattr(app.state, 'ai_router', None)
    monitor = getattr(app.state, 'health_monitor', None)
    
    # Check OAuth setup
    gmail_configured = bool(os.getenv("GMAIL_CLIENT_ID") and os.getenv("GMAIL_CLIENT_SECRET"))
    gmail_token_valid = bool(os.getenv("GMAIL_REFRESH_TOKEN"))
    
    # Check Firebase
    firebase_configured = bool(os.getenv("FIREBASE_PROJECT_ID") or os.getenv("FIREBASE_CREDENTIALS_PATH"))
    
    # Check AI providers
    ai_configured = bool(os.getenv("KIMI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY"))
    
    # Get AI provider status
    ai_providers = ai_router.get_available_providers() if ai_router else []
    
    # Setup requirements
    setup_requirements = []
    if not ai_configured:
        setup_requirements.append({
            "item": "AI Provider",
            "status": "missing",
            "action": "Add KIMI_API_KEY (recommended) or OPENAI_API_KEY or GROQ_API_KEY to .env"
        })
    if not gmail_configured:
        setup_requirements.append({
            "item": "Gmail OAuth",
            "status": "missing", 
            "action": "Add GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET to .env"
        })
    elif not gmail_token_valid:
        setup_requirements.append({
            "item": "Gmail Token",
            "status": "expired",
            "action": "Open the integrations panel to authorize Gmail with your signed-in account"
        })
    
    return {
        "status": "operational",
        "version": "2.0.0",
        "ai": {
            "providers": ai_providers,
            "configured": ai_configured,
            "primary": ai_providers[0] if ai_providers else None,
        },
        "services": {
            "oauth": OAUTH_AVAILABLE,
            "automation": AUTOMATION_AVAILABLE,
            "identity": IDENTITY_AVAILABLE,
            "firebase": firebase_configured,
        },
        "features": {
            "email_sending": gmail_configured and gmail_token_valid,
            "meeting_booking": AUTOMATION_AVAILABLE,
            "service_signup": AUTOMATION_AVAILABLE,
            "real_time_updates": True,
            "multi_provider_ai": len(ai_providers) > 1,
            "plugin_system": True,
            "structured_logging": True
        },
        "setup_required": setup_requirements,
        "quick_start": {
            "1_authorize_gmail": "Use /api/oauth/authorize/gmail with an authenticated user context.",
            "2_check_status": "Use /api/oauth/token/gmail with an authenticated user context.",
            "3_test_email": "Use /api/automation/quick/email with authenticated user context and explicit recipient parameters.",
            "4_chat": "/api/chat (POST with message)"
        },
        "health": monitor.get_overall_health() if monitor else {}
    }

@app.get("/api/metrics")
async def get_metrics():
    """Get detailed performance metrics"""
    tracer = getattr(app.state, 'request_tracer', None)
    
    metrics = {
        "cache": response_cache.get_stats() if response_cache else {},
        "rate_limiter": api_rate_limiter.get_stats() if api_rate_limiter else {},
        "circuit_breakers": {
            "ai": {
                "state": ai_circuit_breaker.state.name,
                "failures": ai_circuit_breaker._failure_count
            } if ai_circuit_breaker else {},
            "database": {
                "state": db_circuit_breaker.state.name,
                "failures": db_circuit_breaker._failure_count
            } if db_circuit_breaker else {},
            "email": {
                "state": email_circuit_breaker.state.name,
                "failures": email_circuit_breaker._failure_count
            } if email_circuit_breaker else {}
        },
        "request_traces": tracer.get_stats() if tracer else {}
    }
    
    return metrics

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
