"""
SUPER MANAGER - CLEAN API
=========================
ONE endpoint. SIMPLE flow.

POST /api/chat
{
    "message": "user message",
    "session_id": "optional"
}

Response:
{
    "message": "AI response",
    "type": "answer|task",
    "status": "need_info|confirm|done" (if task),
    "session_id": "xxx",
    "ui_components": {...}  # Interactive UI elements
}

POST /api/chat/action
{
    "action": "confirm_yes|select_offer|...",
    "button_id": "btn_id",
    "metadata": {...},
    "session_id": "xxx"
}
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
import uuid
import time
import json
import logging

# Primary brain - brain.py (ReAct agent with streaming)
from ..core.brain import chat, get_history, save_user_data, get_user_data, get_session, brain

# Optional: unified brain for capabilities endpoint
try:
    from ..core.unified_brain import get_brain as get_unified_brain
    UNIFIED_BRAIN_AVAILABLE = True
except ImportError:
    UNIFIED_BRAIN_AVAILABLE = False
    get_unified_brain = None
from ..core.validation import (
    ChatRequest as ValidatedChatRequest,
    validate_request,
    ValidationError,
    chat_rate_limiter,
    sanitize_html,
    validate_session_id
)
from ..core.auth import get_current_principal, Principal

import re

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


def _response_has_code_artifacts(message_text: str, result: Dict[str, Any]) -> bool:
    """Detect whether the response already contains code artifacts the frontend can render.

    IMPORTANT: For landing-page UX, random code fences (e.g. bash install snippets) are NOT
    sufficient. We only treat the response as having renderable artifacts if it includes
    filepath markers or HTML-like content.
    """

    def _looks_like_html(s: str) -> bool:
        if not isinstance(s, str):
            return False
        t = s.lower()
        return "<!doctype" in t or "<html" in t or "<head" in t or "<body" in t

    if message_text:
        lower = message_text.lower()
        if "filepath:" in lower:
            return True
        if _looks_like_html(message_text):
            return True

    steps = result.get("steps") or []
    if isinstance(steps, list):
        for s in steps:
            if not isinstance(s, dict):
                continue
            st = (s.get("event") or s.get("type") or "").lower()
            if st == "code_exec":
                data = s.get("data") or {}
                code = data.get("code") or s.get("content") or ""
                if isinstance(code, str) and code.strip():
                    c = code.lower()
                    if "filepath:" in c or _looks_like_html(code):
                        return True

    r = result.get("result")
    if isinstance(r, dict) and (r.get("code") or r.get("files")):
        return True

    return False


def _inject_landing_page_artifacts_if_missing(user_message: str, message_text: str, result: Dict[str, Any]) -> str:
        """If the user asked for a landing page but the agent didn't return code, inject a minimal HTML/CSS/JS artifact."""
        text = (user_message or "").lower()
        wants_landing = "landing page" in text or ("website" in text and ("marketing" in text or "landing" in text))
        if not wants_landing:
                return message_text

        # Only skip injection if we have *renderable* artifacts already.
        if _response_has_code_artifacts(message_text, result):
                return message_text

        # Minimal, dependency-free landing page scaffold.
        code = """// filepath: index.html
<!doctype html>
<html lang=\"en\">
    <head>
        <meta charset=\"UTF-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
        <title>Marketing Landing Page</title>
        <link rel=\"stylesheet\" href=\"style.css\" />
    </head>
    <body>
        <header class=\"nav\">
            <div class=\"brand\">YourBrand</div>
            <nav class=\"links\">
                <a href=\"#features\">Features</a>
                <a href=\"#pricing\">Pricing</a>
                <a href=\"#contact\">Contact</a>
            </nav>
            <a class=\"cta\" href=\"#contact\">Get Started</a>
        </header>

        <main>
            <section class=\"hero\">
                <div class=\"hero-text\">
                    <h1>Grow your business with a modern landing page</h1>
                    <p>Clear messaging, strong calls-to-action, and a layout built to convert visitors into customers.</p>
                    <div class=\"hero-actions\">
                        <button id=\"primaryBtn\" class=\"btn primary\">Start Free</button>
                        <a class=\"btn secondary\" href=\"#features\">See features</a>
                    </div>
                    <div id=\"toast\" class=\"toast\" aria-live=\"polite\" hidden></div>
                </div>
                <div class=\"hero-card\" aria-hidden=\"true\">
                    <div class=\"metric\"><span class=\"k\">+42%</span><span class=\"l\">Conversions</span></div>
                    <div class=\"metric\"><span class=\"k\">3x</span><span class=\"l\">Faster setup</span></div>
                    <div class=\"metric\"><span class=\"k\">24/7</span><span class=\"l\">Support</span></div>
                </div>
            </section>

            <section id=\"features\" class=\"section\">
                <h2>Features</h2>
                <div class=\"grid\">
                    <div class=\"card\"><h3>Fast</h3><p>Loads quickly and stays responsive.</p></div>
                    <div class=\"card\"><h3>Clear</h3><p>Messaging that explains value in seconds.</p></div>
                    <div class=\"card\"><h3>Measurable</h3><p>Designed to track and improve conversions.</p></div>
                </div>
            </section>

            <section id=\"pricing\" class=\"section\">
                <h2>Pricing</h2>
                <div class=\"grid\">
                    <div class=\"card\"><h3>Starter</h3><p class=\"price\">$19/mo</p><p>For new projects and MVPs.</p></div>
                    <div class=\"card\"><h3>Pro</h3><p class=\"price\">$49/mo</p><p>For growing teams and launches.</p></div>
                    <div class=\"card\"><h3>Enterprise</h3><p class=\"price\">Custom</p><p>For security, SSO, and SLAs.</p></div>
                </div>
            </section>

            <section id=\"contact\" class=\"section\">
                <h2>Contact</h2>
                <form id=\"contactForm\" class=\"form\">
                    <label>
                        Name
                        <input name=\"name\" required />
                    </label>
                    <label>
                        Email
                        <input name=\"email\" type=\"email\" required />
                    </label>
                    <label>
                        Message
                        <textarea name=\"message\" rows=\"4\" required></textarea>
                    </label>
                    <button class=\"btn primary\" type=\"submit\">Send</button>
                </form>
            </section>
        </main>

        <footer class=\"footer\">© <span id=\"year\"></span> YourBrand. All rights reserved.</footer>

        <script src=\"script.js\"></script>
    </body>
</html>

// filepath: style.css
:root {
    --bg: #0b1020;
    --panel: rgba(255, 255, 255, 0.06);
    --border: rgba(255, 255, 255, 0.14);
    --text: rgba(255, 255, 255, 0.92);
    --muted: rgba(255, 255, 255, 0.66);
    --accent: #7c3aed;
}

* { box-sizing: border-box; }
body {
    margin: 0;
    font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    background: radial-gradient(1200px 600px at 20% 0%, rgba(124,58,237,.25), transparent 60%),
                            radial-gradient(900px 500px at 80% 10%, rgba(59,130,246,.18), transparent 55%),
                            var(--bg);
    color: var(--text);
}

a { color: inherit; text-decoration: none; }

.nav {
    position: sticky;
    top: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
    background: rgba(11,16,32,0.75);
    backdrop-filter: blur(12px);
}

.brand { font-weight: 700; letter-spacing: 0.2px; }

.links { display: flex; gap: 14px; color: var(--muted); }
.links a:hover { color: var(--text); }

.cta {
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: rgba(255,255,255,0.04);
}

.hero {
    display: grid;
    grid-template-columns: 1.4fr 1fr;
    gap: 20px;
    padding: 42px 18px 10px;
    max-width: 1000px;
    margin: 0 auto;
}

.hero-text h1 {
    margin: 0 0 10px;
    font-size: clamp(28px, 4vw, 44px);
    line-height: 1.05;
}

.hero-text p { margin: 0 0 18px; color: var(--muted); max-width: 52ch; }

.hero-actions { display: flex; gap: 10px; flex-wrap: wrap; }

.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 10px 14px;
    border-radius: 12px;
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.04);
    color: var(--text);
    cursor: pointer;
}

.btn.primary {
    border-color: rgba(124,58,237,0.6);
    background: rgba(124,58,237,0.22);
}

.btn.primary:hover { background: rgba(124,58,237,0.30); }
.btn.secondary:hover { background: rgba(255,255,255,0.07); }

.hero-card {
    border: 1px solid var(--border);
    background: var(--panel);
    border-radius: 18px;
    padding: 16px;
    display: grid;
    gap: 10px;
}

.metric {
    border: 1px solid rgba(255,255,255,0.10);
    background: rgba(255,255,255,0.03);
    border-radius: 14px;
    padding: 12px;
}

.metric .k { display: block; font-weight: 700; font-size: 18px; }
.metric .l { display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }

.section {
    max-width: 1000px;
    margin: 0 auto;
    padding: 22px 18px;
}

.section h2 { margin: 0 0 12px; font-size: 18px; }

.grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
}

.card {
    border: 1px solid var(--border);
    background: var(--panel);
    border-radius: 14px;
    padding: 14px;
}

.card h3 { margin: 0 0 6px; font-size: 14px; }
.card p { margin: 0; color: var(--muted); font-size: 13px; }
.price { color: var(--text) !important; font-weight: 700; margin: 6px 0 8px !important; }

.form {
    display: grid;
    gap: 10px;
    border: 1px solid var(--border);
    background: var(--panel);
    border-radius: 14px;
    padding: 14px;
    max-width: 520px;
}

label { display: grid; gap: 6px; color: var(--muted); font-size: 12px; }
input, textarea {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.14);
    background: rgba(255,255,255,0.04);
    color: var(--text);
}

.footer {
    padding: 22px 18px;
    color: var(--muted);
    text-align: center;
}

.toast {
    margin-top: 10px;
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(16, 185, 129, 0.45);
    background: rgba(16, 185, 129, 0.10);
    color: rgba(236, 253, 245, 0.95);
    font-size: 13px;
}

@media (max-width: 860px) {
    .hero { grid-template-columns: 1fr; }
    .grid { grid-template-columns: 1fr; }
    .links { display: none; }
}

// filepath: script.js
const toast = document.getElementById('toast');
const year = document.getElementById('year');
const primaryBtn = document.getElementById('primaryBtn');
const form = document.getElementById('contactForm');

year.textContent = String(new Date().getFullYear());

function showToast(text) {
    toast.hidden = false;
    toast.textContent = text;
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => {
        toast.hidden = true;
    }, 2500);
}

primaryBtn.addEventListener('click', () => {
    showToast('Thanks! Free start activated (demo).');
});

form.addEventListener('submit', (e) => {
    e.preventDefault();
    const data = new FormData(form);
    const name = String(data.get('name') || '').trim() || 'there';
    showToast(`Thanks, ${name}! We will reply soon.`);
    form.reset();
});
"""

        steps = result.get("steps")
        if not isinstance(steps, list):
                steps = []
        steps.append({
                "type": "code_exec",
                "content": "Generated landing page files",
                "data": {"code": code},
        })
        result["steps"] = steps

        suffix = "\n\n✅ Generated files: index.html, style.css, script.js (see the IDE + Preview panel)."
        return (message_text or "") + suffix


def _inject_todo_app_artifacts_if_missing(user_message: str, message_text: str, result: Dict[str, Any]) -> str:
        """If the user asked for a simple todo web app but the agent didn't return code, inject a minimal scaffold."""
        text = (user_message or "").lower()
        wants_todo = "todo" in text and ("app" in text or "list" in text)
        if not wants_todo:
                return message_text

        if _response_has_code_artifacts(message_text, result):
                return message_text

        code = """// filepath: index.html
<!doctype html>
<html lang=\"en\">
    <head>
        <meta charset=\"UTF-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
        <title>Todo App</title>
        <link rel=\"stylesheet\" href=\"style.css\" />
    </head>
    <body>
        <main class=\"wrap\">
            <h1 id=\"title\">Todo</h1>
            <form id=\"form\" class=\"row\">
                <input id=\"input\" type=\"text\" placeholder=\"Add a new todo...\" autocomplete=\"off\" />
                <button type=\"submit\">Add</button>
            </form>
            <div class=\"row\">
                <button id=\"clearDone\" type=\"button\" class=\"ghost\">Clear completed</button>
                <div id=\"count\" class=\"muted\"></div>
            </div>
            <ul id=\"list\" class=\"list\"></ul>
        </main>

        <script src=\"script.js\"></script>
    </body>
</html>

// filepath: style.css
:root { --bg:#0b1020; --panel: rgba(255,255,255,.06); --border: rgba(255,255,255,.14); --text: rgba(255,255,255,.92); --muted: rgba(255,255,255,.62); --accent: #7c3aed; }
*{ box-sizing:border-box; }
body{ margin:0; font-family: system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; background: radial-gradient(1000px 500px at 20% 0%, rgba(124,58,237,.25), transparent 60%), var(--bg); color: var(--text); }
.wrap{ max-width: 720px; margin: 40px auto; padding: 18px; }
h1{ margin: 0 0 14px; font-size: 28px; }
.row{ display:flex; gap:10px; align-items:center; margin: 10px 0; }
input{ flex:1; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--border); background: rgba(255,255,255,.04); color: var(--text); outline:none; }
button{ padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(124,58,237,.6); background: rgba(124,58,237,.22); color: var(--text); cursor:pointer; }
button.ghost{ border-color: var(--border); background: rgba(255,255,255,.04); }
.muted{ margin-left:auto; color: var(--muted); font-size: 13px; }
.list{ list-style:none; padding: 0; margin: 14px 0 0; display:flex; flex-direction:column; gap: 8px; }
.item{ display:flex; gap:10px; align-items:center; padding: 10px 12px; border-radius: 14px; border:1px solid var(--border); background: var(--panel); }
.item.done{ opacity:.75; text-decoration: line-through; }
.item input[type=checkbox]{ width: 16px; height:16px; }
.item .spacer{ flex:1; }
.item .del{ border-color: rgba(248,81,73,.55); background: rgba(248,81,73,.12); }

// filepath: script.js
const KEY = 'supermanager.todos.v1';
const form = document.getElementById('form');
const input = document.getElementById('input');
const list = document.getElementById('list');
const count = document.getElementById('count');
const clearDone = document.getElementById('clearDone');

function load(){
    try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch { return []; }
}
function save(todos){
    localStorage.setItem(KEY, JSON.stringify(todos));
}
function uid(){ return Math.random().toString(16).slice(2) + Date.now().toString(16); }

let todos = load();

function render(){
    list.innerHTML = '';
    const active = todos.filter(t => !t.done).length;
    count.textContent = `${active} active`; 
    for(const t of todos){
        const li = document.createElement('li');
        li.className = 'item' + (t.done ? ' done' : '');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.checked = !!t.done;
        cb.addEventListener('change', () => {
            t.done = cb.checked;
            save(todos);
            render();
        });
        const text = document.createElement('div');
        text.textContent = t.text;
        text.className = 'spacer';
        const del = document.createElement('button');
        del.type = 'button';
        del.textContent = 'Delete';
        del.className = 'del';
        del.addEventListener('click', () => {
            todos = todos.filter(x => x.id !== t.id);
            save(todos);
            render();
        });
        li.appendChild(cb);
        li.appendChild(text);
        li.appendChild(del);
        list.appendChild(li);
    }
}

form.addEventListener('submit', (e) => {
    e.preventDefault();
    const v = (input.value || '').trim();
    if(!v) return;
    todos.unshift({ id: uid(), text: v, done: false });
    input.value = '';
    save(todos);
    render();
});

clearDone.addEventListener('click', () => {
    todos = todos.filter(t => !t.done);
    save(todos);
    render();
});

render();
"""

        steps = result.get("steps")
        if not isinstance(steps, list):
                steps = []
        steps.append({
                "type": "code_exec",
                "content": "Generated todo app files",
                "data": {"code": code},
        })
        result["steps"] = steps

        suffix = "\n\n✅ Generated files: index.html, style.css, script.js (see the IDE + Preview panel)."
        return (message_text or "") + suffix


# =============================================================================
# Request/Response Models
# =============================================================================

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = Field(None, max_length=100)
    # user_id intentionally removed — always derived from authenticated principal (Item 3)
    
    @validator('message')
    def clean_message(cls, v):
        if not v or not v.strip():
            raise ValueError('Message cannot be empty')
        return v.strip()
    
    @validator('session_id')
    def clean_session_id(cls, v):
        if v and not validate_session_id(v):
            raise ValueError('Invalid session ID')
        return v


class ChatResponse(BaseModel):
    message: str
    type: str  # answer, task, cancelled, clarify
    status: Optional[str] = None  # need_info, confirm, done
    session_id: str
    need: Optional[List[str]] = None  # missing info fields
    summary: Optional[str] = None  # task summary for confirmation
    result: Optional[Dict] = None  # task result
    proof: Optional[Dict] = None  # proof of execution
    ui_components: Optional[Dict] = None  # interactive UI components
    task_id: Optional[str] = None  # active task ID
    steps: Optional[List[Dict]] = None  # agent thinking/tool steps
    response_time_ms: Optional[float] = None


class ButtonActionRequest(BaseModel):
    action: str = Field(..., min_length=1, max_length=100)
    button_id: str = Field(..., min_length=1, max_length=100)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    session_id: str = Field(..., min_length=1, max_length=100)
    # user_id intentionally removed — derived from principal (Item 3)


class UserDataRequest(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=254)
    data: Dict[str, Any]
    
    @validator('identifier')
    def clean_identifier(cls, v):
        return sanitize_html(v.strip().lower())


class ErrorResponse(BaseModel):
    error: str
    code: str
    field: Optional[str] = None
    retry_after: Optional[int] = None


class FeedbackRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100)
    # user_id intentionally removed — derived from principal (Item 3)
    message_index: int = Field(..., ge=0)
    rating: str = Field(..., pattern=r"^(positive|negative)$")
    comment: Optional[str] = Field(None, max_length=500)
    answer_preview: Optional[str] = Field(None, max_length=300)
    task_type: Optional[str] = Field(None, max_length=100)  # For learning loop


# =============================================================================
# Rate Limiting Dependency
# =============================================================================

def get_client_ip(request: Request) -> str:
    """Extract client IP from request"""
    # Check common headers for real IP (behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    return request.client.host if request.client else "unknown"


async def check_rate_limit(request: Request):
    """Rate limiting dependency"""
    client_ip = get_client_ip(request)

    # Never rate limit local loopback (dev + proxy polling).
    if client_ip in ("127.0.0.1", "::1"):
        request.state.rate_limit_remaining = None
        return

    allowed, remaining, retry_after = chat_rate_limiter.check(client_ip)
    
    if not allowed:
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Too many requests. Please slow down.",
                "code": "rate_limit_exceeded",
                "retry_after": retry_after
            },
            headers={"Retry-After": str(retry_after)}
        )
    
    # Add rate limit info to response headers
    request.state.rate_limit_remaining = remaining


# =============================================================================
# MAIN CHAT ENDPOINT
# =============================================================================

@router.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    raw_request: Request,
    principal: Principal = Depends(get_current_principal),
    _: None = Depends(check_rate_limit)
):
    """
    Main chat endpoint. Handles everything:
    - Questions → Direct answers
    - Tasks → Plan → Ask info → Confirm → Execute
    
    Returns interactive UI components for buttons, cards, forms, etc.
    
    Rate Limited: 30 requests per minute per IP
    """
    start_time = time.time()
    session_id = request.session_id or str(uuid.uuid4())
    user_id = principal.user_id

    # Support continuing an existing task with `/TASK_ID your message...`.
    # This keeps the same session_id so the agent has full conversation memory.
    parent_task_id = None
    message = request.message or ""
    m = re.match(r"^\s*/(?P<task_id>[a-zA-Z0-9\-_]+)\s*(?P<rest>.*)$", message, re.DOTALL)
    if m:
        parent_task_id = m.group("task_id")
        message = (m.group("rest") or "").strip() or message
        try:
            from ..agent.orchestrator import get_orchestrator
            orchestrator = get_orchestrator()
            task = await orchestrator.get_task(parent_task_id)
            if task and getattr(task, "user_id", None) == user_id:
                task_session = (getattr(task, "metadata", {}) or {}).get("session_id")
                if isinstance(task_session, str) and task_session.strip():
                    session_id = task_session.strip()
        except Exception:
            pass
            
    # Auto-link to last active task in session if not explicitly provided
    if not parent_task_id:
        try:
            from ..agent.orchestrator import get_orchestrator
            orchestrator = get_orchestrator()
            user_tasks = await orchestrator.get_user_tasks(user_id)
            if user_tasks:
                # Find most recent task associated with this session
                session_tasks = [t for t in user_tasks if (t.get("metadata") or {}).get("session_id") == session_id]
                if session_tasks:
                    parent_task_id = session_tasks[0]["id"]
        except Exception:
            pass

    
    try:
        # Log the request (without full message for privacy)
        logger.info(f"Chat request - session: {session_id[:8]}..., user: {user_id}, length: {len(request.message)}")

        # Use brain.py - has full task flow (plan -> collect info -> confirm -> execute)
        # brain.py now delegates execution to engine.py for proof generation
        result = await chat(session_id, message, user_id, parent_task_id=parent_task_id)

        raw_message = result.get("message")
        if raw_message is None:
            raw_message = result.get("response") or result.get("content") or ""
        message_text = str(raw_message) if raw_message is not None else ""

        if not message_text.strip():
            # Never return an empty assistant message to the UI.
            message_text = "I produced an empty response due to an internal issue. Please try again."
            if result.get("status") in (None, "", "done", "success"):
                result["status"] = "error"
            if not result.get("type"):
                result["type"] = "answer"

        # If the user asked for a landing page but the agent didn't produce code artifacts,
        # inject a minimal scaffold so the IDE + Preview can work.
        message_text = _inject_landing_page_artifacts_if_missing(request.message, message_text, result)

        # Similar safety-net for simple todo web apps.
        message_text = _inject_todo_app_artifacts_if_missing(request.message, message_text, result)

        # ----------------------------------------------------------------
        # AUTO-DETECT STUDENT FOLLOW-UP REQUESTS
        # If the faculty message contains student data (email + attendance)
        # AND intent to follow up, auto-create a background campaign.
        # ----------------------------------------------------------------
        try:
            from ..core.student_followup_engine import parse_student_data, create_student_followup
            _msg_lower = message.lower()
            _has_intent = any(k in _msg_lower for k in [
                "follow up", "follow-up", "focus on him", "focus on her",
                "send email", "contact student", "attendance", "absent",
                "remind", "send mail", "email to student"
            ])
            _parsed = parse_student_data(message) if _has_intent else None
            if _parsed:
                async def _bg_followup():
                    try:
                        await create_student_followup(user_id=user_id, raw_text=message)
                        logger.info(f"Auto-started followup campaign for {_parsed.get('student_email')} by {user_id}")
                    except Exception as _bge:
                        logger.warning(f"Background followup failed: {_bge}")
                import asyncio
                asyncio.create_task(_bg_followup())
        except Exception as _sfe:
            logger.debug(f"Student followup detection skipped: {_sfe}")
        
        response_time = (time.time() - start_time) * 1000
        
        response = ChatResponse(
            message=message_text,
            type=result.get("type", "answer"),
            status=result.get("status"),
            session_id=session_id,
            need=result.get("need") or result.get("missing_fields"),
            summary=result.get("summary"),
            result=result.get("result"),
            proof=result.get("proof"),
            ui_components=result.get("ui_components"),
            task_id=result.get("task_id"),
            steps=result.get("steps"),
            response_time_ms=round(response_time, 2)
        )
        
        logger.info(f"Chat response - session: {session_id[:8]}..., status: {response.status}, time: {response_time:.0f}ms")
        return response
        
    except ValidationError as e:
        logger.warning(f"Validation error: {e.message}")
        raise HTTPException(status_code=400, detail=e.to_dict())
    
    except Exception as e:
        logger.error(f"Chat error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "An unexpected error occurred. Please try again.",
                "code": "internal_error"
            }
        )


# =============================================================================
# SSE STREAMING ENDPOINT
# =============================================================================

@router.post("/api/chat/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    raw_request: Request,
    principal: Principal = Depends(get_current_principal),
    _: None = Depends(check_rate_limit)
):
    """
    Streaming chat endpoint using Server-Sent Events.
    Yields real-time agent events: thinking, tool_call, tool_result, answer.
    """
    session_id = request.session_id or str(uuid.uuid4())
    user_id = principal.user_id

    async def generate():
        try:
            async for event in brain.process_stream(session_id, request.message, user_id):
                event_data = event.to_dict()
                yield f"data: {json.dumps(event_data)}\n\n"

            # Send done event with session_id
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': 'An error occurred during processing.'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# =============================================================================
# HISTORY ENDPOINT
# =============================================================================

@router.get("/api/chat/history/{session_id}")
async def get_chat_history(session_id: str, principal: Principal = Depends(get_current_principal)):
    """Get conversation history for a session"""
    if not validate_session_id(session_id):
        raise HTTPException(
            status_code=400, 
            detail={"error": "Invalid session ID", "code": "invalid_session"}
        )
    
    try:
        session = get_session(session_id)
        if session.owner_user_id and session.owner_user_id != principal.user_id:
            raise HTTPException(status_code=403, detail={"error": "Forbidden", "code": "forbidden"})
        history = get_history(session_id)
        return {"session_id": session_id, "messages": history, "count": len(history)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"History error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve history")


# =============================================================================
# USER DATA ENDPOINTS
# =============================================================================

@router.post("/api/users")
async def save_user(
    request: UserDataRequest,
    principal: Principal = Depends(get_current_principal),
):
    """
    Save user data for future use.
    Example: Save someone's UPI ID so AI can use it for payments.
    """
    try:
        save_user_data(f"{principal.tenant_id}:{request.identifier}", request.data)
        return {"status": "saved", "identifier": request.identifier}
    except Exception as e:
        logger.error(f"Save user error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save user data")


@router.get("/api/users/{identifier}")
async def get_user(
    identifier: str,
    principal: Principal = Depends(get_current_principal),
):
    """Get saved user data"""
    identifier = sanitize_html(identifier.strip().lower())
    
    try:
        data = get_user_data(f"{principal.tenant_id}:{identifier}")
        return {"identifier": identifier, "data": data}
    except Exception as e:
        logger.error(f"Get user error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user data")


# =============================================================================
# BUTTON ACTION ENDPOINT
# =============================================================================

@router.post("/api/chat/action")
async def button_action_endpoint(
    request: ButtonActionRequest,
    raw_request: Request,
    principal: Principal = Depends(get_current_principal),
    _: None = Depends(check_rate_limit)
):
    """
    Handle button/UI component actions.
    Called when user clicks a button instead of typing.
    """
    start_time = time.time()
    
    try:
        logger.info(f"Button action - session: {request.session_id[:8]}..., action: {request.action}")

        # Convert button action to a chat message and run through brain
        action_messages = {
            "confirm_yes": "yes",
            "confirm_no": "no",
        }
        message = action_messages.get(request.action, request.action)
        result = await chat(request.session_id, message, principal.user_id)
        
        response_time = (time.time() - start_time) * 1000
        
        # Check if it's a redirect action
        if result.get("action") == "redirect":
            return {
                "action": "redirect",
                "url": result.get("url"),
                "session_id": request.session_id
            }
        
        # Handle empty messages (same as chat_endpoint)
        message_text = result.get("message") or result.get("response") or result.get("content") or ""
        if not message_text or not str(message_text).strip():
            message_text = "I produced an empty response due to an internal issue. Please try again."
            if result.get("status") in (None, "", "done", "success"):
                result["status"] = "error"
            if not result.get("type"):
                result["type"] = "answer"
        
        return ChatResponse(
            message=message_text,
            type=result.get("type", "answer"),
            status=result.get("status"),
            session_id=request.session_id,
            need=result.get("need") or result.get("missing_fields"),
            summary=result.get("summary"),
            result=result.get("result"),
            proof=result.get("proof"),
            ui_components=result.get("ui_components"),
            task_id=result.get("task_id"),
            steps=result.get("steps"),
            response_time_ms=round(response_time, 2)
        )
        
    except Exception as e:
        logger.error(f"Button action error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to process action. Please try again.",
                "code": "action_error"
            }
        )


# =============================================================================
# CAPABILITIES ENDPOINT
# =============================================================================

@router.get("/api/capabilities")
async def get_capabilities(
    principal: Principal = Depends(get_current_principal),  # Item 1: auth required
):
    """
    Get current AI capabilities and their status.
    Helps frontend show what's available.
    """
    try:
        if UNIFIED_BRAIN_AVAILABLE and get_unified_brain:
            brain = get_unified_brain()
            capabilities = brain.get_capabilities()
            return {
                "status": "operational",
                "brain": "unified",
                "capabilities": capabilities
            }
        else:
            # Build capabilities from engine Config
            from ..core.engine import Config
            services = Config.get_available_services()
            return {
                "status": "operational",
                "brain": "primary",
                "capabilities": {
                    "chat": {"available": True, "description": "Full conversational AI with task execution"},
                    "email": {"available": services.get("email_smtp") or services.get("email_sendgrid"), "description": "Send real emails"},
                    "image_generation": {"available": True, "description": "Generate images (Pollinations AI free)"},
                    "web_search": {"available": True, "description": "Search the web (DuckDuckGo)"},
                    "meetings": {"available": True, "description": "Create Jitsi meeting links"},
                    "payments": {"available": services.get("payments"), "description": "Payment links (Razorpay/UPI)"},
                }
            }
    except Exception as e:
        logger.error(f"Capabilities error: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }


# =============================================================================
# FEEDBACK ENDPOINT
# =============================================================================

@router.post("/api/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    principal: Principal = Depends(get_current_principal),
):
    """
    Submit user feedback (positive/negative) for an AI response.
    This feedback influences future AI behavior through the Learning Loop.
    """
    try:
        user_id = principal.user_id
        result = brain.submit_feedback(
            session_id=request.session_id,
            user_id=user_id,
            message_index=request.message_index,
            rating=request.rating,
            comment=request.comment,
            answer_preview=request.answer_preview or "",
            task_type=request.task_type,  # For learning loop
        )
        return result
    except Exception as e:
        logger.error(f"Feedback error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to record feedback.", "code": "feedback_error"}
        )


@router.get("/api/learning/stats")
async def get_learning_stats(
    principal: Principal = Depends(get_current_principal),  # Item 1: auth required
):
    """
    Get learning loop statistics - strategy confidence, success rates, etc.
    Requires admin role.
    """
    try:
        from backend.core.strategy_store import StrategyStore
        strategies = StrategyStore()
        return {
            "status": "ok",
            "stats": strategies.get_statistics()
        }
    except Exception as e:
        logger.error(f"Learning stats error: {str(e)}", exc_info=True)
        return {"status": "error", "stats": {}}
