"""
Student Follow-Up Engine
========================
AI-powered student engagement system for faculty:

1.  Parses student data from chat (email, ID, attendance, absences)
2.  Sends immediate + scheduled follow-up emails (drip sequence)
3.  Tracks reply status
4.  Escalates to parents via email/phone if no response
5.  Logs every interaction to the Faculty Email Assistant panel
6.  Connects to ERP for live student/parent data (when configured)

Architecture:
 - StudentFollowupCampaign  → one per student engagement
 - FollowupScheduler        → in-memory async scheduler (Celery-ready)
 - ERPConnector             → fetches parent contacts from UMS
 - InteractionLog           → audit trail for Faculty panel
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

FOLLOWUP_STATUS = [
    "pending",         # campaign created, not started
    "email_sent",      # first email sent
    "waiting_reply",   # waiting for student reply
    "reminder_sent",   # 2nd or 3rd email sent
    "escalated",       # no reply → parent contacted
    "parent_called",   # AI phone call placed to parent
    "resolved",        # student/parent replied
    "closed",          # faculty closed manually
]


@dataclass
class Interaction:
    """Single interaction event in the campaign log."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    type: str = ""          # email_sent, reply_received, call_placed, erp_fetch
    target: str = ""        # student | parent
    channel: str = ""       # email | sms | phone | erp
    content: str = ""       # brief summary
    status: str = ""        # success | failed | pending
    error: Optional[str] = None


@dataclass
class StudentFollowupCampaign:
    """
    One campaign = one student engagement thread.
    Tracks all outreach attempts and replies.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = ""          # faculty user_id

    # Student info
    student_email: str = ""
    student_id: str = ""
    student_name: str = ""
    attendance_pct: float = 0.0
    days_absent: int = 0
    pending_assignments: List[str] = field(default_factory=list)
    raw_input: str = ""           # original faculty chat text

    # Parent / ERP data (fetched when available)
    parent_email: str = ""
    parent_phone: str = ""
    parent_name: str = ""
    erp_fetched: bool = False

    # Campaign state
    status: str = "pending"
    schedule: List[Dict] = field(default_factory=list)   # planned outreach steps
    interactions: List[Interaction] = field(default_factory=list)

    # Scheduling handles
    next_action_at: Optional[str] = None
    reply_received: bool = False
    reply_received_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "student_email": self.student_email,
            "student_id": self.student_id,
            "student_name": self.student_name,
            "attendance_pct": self.attendance_pct,
            "days_absent": self.days_absent,
            "pending_assignments": self.pending_assignments,
            "raw_input": self.raw_input,
            "parent_email": self.parent_email,
            "parent_phone": self.parent_phone,
            "parent_name": self.parent_name,
            "erp_fetched": self.erp_fetched,
            "status": self.status,
            "schedule": self.schedule,
            "interactions": [
                {
                    "id": i.id,
                    "timestamp": i.timestamp,
                    "type": i.type,
                    "target": i.target,
                    "channel": i.channel,
                    "content": i.content,
                    "status": i.status,
                    "error": i.error,
                }
                for i in self.interactions
            ],
            "next_action_at": self.next_action_at,
            "reply_received": self.reply_received,
            "reply_received_at": self.reply_received_at,
        }


# ---------------------------------------------------------------------------
# In-Memory Store (Redis/DB-ready in production)
# ---------------------------------------------------------------------------

_campaigns: Dict[str, StudentFollowupCampaign] = {}     # id → campaign
_user_campaigns: Dict[str, List[str]] = {}              # user_id → [campaign_id]


# ---------------------------------------------------------------------------
# ERP Connector
# ---------------------------------------------------------------------------

class ERPConnector:
    """
    Fetches parent/student data from the university ERP (UMS).
    Uses ERP_URL, ERP_USERNAME, ERP_PASSWORD from .env.
    Gracefully degrades when ERP is unavailable.
    """

    def __init__(self):
        self.url = os.getenv("ERP_URL", "")
        self.username = os.getenv("ERP_USERNAME", "")
        self.password = os.getenv("ERP_PASSWORD", "")

    async def fetch_student_info(self, student_id: str) -> Dict[str, Any]:
        """
        Attempt to fetch student/parent info from ERP by student ID.
        Returns a dict with parent_email, parent_phone, parent_name, etc.
        """
        if not self.url:
            return {"error": "ERP not configured", "available": False}

        try:
            import httpx
            # ERP login + student lookup — adapter pattern for UMS
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Step 1: login
                login_resp = await client.post(
                    f"{self.url.rstrip('/')}/api/auth/login",
                    json={"username": self.username, "password": self.password},
                )
                if login_resp.status_code != 200:
                    return {"error": f"ERP login failed ({login_resp.status_code})", "available": False}

                token = login_resp.json().get("token") or login_resp.json().get("access_token")
                headers = {"Authorization": f"Bearer {token}"} if token else {}

                # Step 2: fetch student
                student_resp = await client.get(
                    f"{self.url.rstrip('/')}/api/students/{student_id}",
                    headers=headers,
                )
                if student_resp.status_code == 200:
                    data = student_resp.json()
                    return {
                        "available": True,
                        "parent_name": data.get("parent_name", ""),
                        "parent_email": data.get("parent_email", ""),
                        "parent_phone": data.get("parent_phone", ""),
                        "student_name": data.get("name", ""),
                        "department": data.get("department", ""),
                        "raw": data,
                    }
                return {"error": f"Student {student_id} not found in ERP", "available": False}

        except Exception as e:
            logger.warning(f"ERP fetch failed: {e}")
            return {"error": str(e), "available": False}


_erp = ERPConnector()


# ---------------------------------------------------------------------------
# Email Sender
# ---------------------------------------------------------------------------

async def _send_email(to: str, subject: str, body: str, html: str = "") -> Dict:
    """Send via identity_email_service (uses SMTP/OAuth from .env)."""
    try:
        from .identity_email_service import get_identity_email_service
        svc = get_identity_email_service()
        result = await svc.send_email_for_user(
            user_id="system",
            to=to,
            subject=subject,
            body=body,
            html_body=html or None,
        )
        return result
    except Exception as e:
        logger.error(f"Email send error → {to}: {e}")
        return {"status": "failed", "error": str(e)}


# ---------------------------------------------------------------------------
# Email Templates
# ---------------------------------------------------------------------------

def _student_email_1(campaign: StudentFollowupCampaign) -> tuple[str, str, str]:
    """First email: attendance + assignments reminder."""
    name = campaign.student_name or "Student"
    assignments = "\n".join(f"  • {a}" for a in campaign.pending_assignments) if campaign.pending_assignments else "  • Please check with your faculty."
    subject = f"Important: Attendance Alert & Pending Assignments – Action Required"
    body = f"""Dear {name},

I hope you're doing well. I'm writing to bring some important academic matters to your attention.

📊 ATTENDANCE STATUS
Your current attendance is {campaign.attendance_pct:.0f}%, which is below the required 75% threshold.
You have been absent for {campaign.days_absent} day(s).

Minimum required attendance is 75%. Falling below this may affect your eligibility for examinations.

📝 PENDING ASSIGNMENTS
{assignments}

Please take immediate steps to:
1. Make up your missed attendance (medical certificate if applicable)
2. Submit pending assignments before the deadline
3. Reply to this email to let me know your situation

This is a friendly reminder. I'm here to help — please reach out if you're facing any difficulties.

Warm regards,
Faculty – CAOP Platform

---
This is an automated follow-up. Please reply directly to this email.
"""
    html = f"""<div style="font-family:sans-serif;max-width:600px;margin:auto;padding:24px;background:#f8fafc;border-radius:12px;">
  <div style="background:linear-gradient(135deg,#667eea,#764ba2);border-radius:10px;padding:20px;text-align:center;margin-bottom:20px;">
    <h2 style="color:white;margin:0;">📢 Academic Alert</h2>
    <p style="color:rgba(255,255,255,.85);margin:4px 0 0;font-size:13px;">CAOP Faculty Email Assistant</p>
  </div>
  <div style="background:white;border-radius:10px;padding:24px;box-shadow:0 2px 10px rgba(0,0,0,.08);">
    <p style="font-size:16px;color:#1e293b;">Dear <strong>{name}</strong>,</p>
    <div style="background:#fef2f2;border-left:4px solid #ef4444;border-radius:6px;padding:14px;margin:16px 0;">
      <strong style="color:#dc2626;">📊 Attendance: {campaign.attendance_pct:.0f}%</strong><br>
      <span style="color:#64748b;font-size:14px;">Days absent: {campaign.days_absent} | Required minimum: 75%</span>
    </div>
    <div style="background:#fffbeb;border-left:4px solid #f59e0b;border-radius:6px;padding:14px;margin:16px 0;">
      <strong style="color:#d97706;">📝 Pending Assignments</strong><br>
      <span style="color:#64748b;font-size:14px;">{', '.join(campaign.pending_assignments) if campaign.pending_assignments else 'Check with faculty'}</span>
    </div>
    <p style="color:#475569;">Please reply to this email and update your faculty about your situation. We're here to help!</p>
    <a href="mailto:{campaign.student_email}?subject=Re: {subject}" style="display:inline-block;background:#667eea;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;margin-top:8px;">Reply to Faculty</a>
  </div>
</div>"""
    return subject, body, html


def _student_email_2(campaign: StudentFollowupCampaign) -> tuple[str, str, str]:
    """Second email: urgent reminder."""
    name = campaign.student_name or "Student"
    subject = "REMINDER: Please respond – Attendance & Assignment Follow-up"
    body = f"""Dear {name},

This is a follow-up to my previous email regarding your attendance ({campaign.attendance_pct:.0f}%) and pending assignments.

I haven't received a reply yet. Please respond as soon as possible.

If you are facing any challenges, I urge you to reach out — we can work together on a solution.

Continued non-response may require us to escalate this matter.

Warm regards,
Faculty – CAOP Platform
"""
    return subject, body, ""


def _parent_email(campaign: StudentFollowupCampaign) -> tuple[str, str, str]:
    """Parent escalation email."""
    parent = campaign.parent_name or "Parent/Guardian"
    student = campaign.student_name or campaign.student_email
    subject = f"Urgent: Academic Concern – {student}"
    body = f"""Dear {parent},

We are reaching out regarding your ward, {student} (ID: {campaign.student_id}).

We have noticed a concerning pattern in their academic engagement:
• Attendance: {campaign.attendance_pct:.0f}% (below the required 75%)
• Days absent: {campaign.days_absent}
• Pending assignments: {len(campaign.pending_assignments)}

Despite multiple attempts to contact your ward via email, we have not received a response.

We kindly request you to:
1. Speak with your ward about their attendance
2. Encourage them to communicate with their faculty
3. Reach out to us if there is any situation we should be aware of

Please reply to this email or contact the department directly.

Regards,
Faculty – CAOP Platform
"""
    return subject, body, ""


# ---------------------------------------------------------------------------
# Follow-up Scheduler
# ---------------------------------------------------------------------------

class FollowupScheduler:
    """
    Manages the drip sequence for each campaign:
    - T+0 min  : Email 1 to student
    - T+30 min : Email 2 to student (if no reply)
    - T+1 day  : Email 3 to student (if no reply)
    - T+1 day  : Parent email (if still no reply)
    - Optionally: AI phone call to parent

    Uses asyncio tasks (production: replace with Celery/APScheduler).
    """

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}

    async def start_campaign(self, campaign: StudentFollowupCampaign) -> None:
        """Start the drip sequence for a campaign."""
        logger.info(f"Starting followup campaign {campaign.id} for {campaign.student_email}")

        # Build schedule plan
        now = datetime.utcnow()
        campaign.schedule = [
            {"step": 1, "type": "email", "target": "student", "at": now.isoformat(), "status": "pending"},
            {"step": 2, "type": "email", "target": "student", "at": (now + timedelta(minutes=30)).isoformat(), "status": "pending"},
            {"step": 3, "type": "email", "target": "student", "at": (now + timedelta(hours=24)).isoformat(), "status": "pending"},
            {"step": 4, "type": "email", "target": "parent",  "at": (now + timedelta(hours=25)).isoformat(), "status": "pending"},
        ]
        campaign.status = "email_sent"
        campaign.next_action_at = campaign.schedule[1]["at"]

        # Start async drip
        task = asyncio.create_task(self._drip(campaign))
        self._tasks[campaign.id] = task

    async def _drip(self, campaign: StudentFollowupCampaign) -> None:
        """Execute the drip sequence."""
        try:
            # Step 1 – immediate email to student
            await self._execute_step(campaign, 0)

            # Step 2 – 30 min reminder to student
            await asyncio.sleep(30 * 60)
            if not campaign.reply_received:
                await self._execute_step(campaign, 1)
                campaign.status = "reminder_sent"
            else:
                _mark_step(campaign, 1, "skipped_reply_received")

            # Step 3 – next day reminder to student
            await asyncio.sleep(23.5 * 3600)  # total ~24h from start
            if not campaign.reply_received:
                await self._execute_step(campaign, 2)
            else:
                _mark_step(campaign, 2, "skipped_reply_received")

            # Step 4 – parent email (if still no reply)
            await asyncio.sleep(1 * 3600)
            if not campaign.reply_received:
                await self._escalate_to_parent(campaign)
            else:
                _mark_step(campaign, 3, "skipped_reply_received")
                campaign.status = "resolved"

        except asyncio.CancelledError:
            logger.info(f"Campaign {campaign.id} drip cancelled")
        except Exception as e:
            logger.error(f"Drip error for campaign {campaign.id}: {e}")

    async def _execute_step(self, campaign: StudentFollowupCampaign, step_idx: int) -> None:
        step = campaign.schedule[step_idx]
        _mark_step(campaign, step_idx, "running")

        if step["target"] == "student":
            if step_idx == 0:
                subject, body, html = _student_email_1(campaign)
            else:
                subject, body, html = _student_email_2(campaign)

            result = await _send_email(campaign.student_email, subject, body, html)
            ok = result.get("status") in ("completed", "simulated")
            _log(campaign, "email_sent", "student", "email",
                 f"Step {step_idx+1}: {subject[:60]}",
                 "success" if ok else "failed",
                 result.get("error"))
            _mark_step(campaign, step_idx, "sent" if ok else "failed")
        else:
            # parent – handled by _escalate_to_parent
            pass

        campaign.next_action_at = (
            campaign.schedule[step_idx + 1]["at"]
            if step_idx + 1 < len(campaign.schedule)
            else None
        )

    async def _escalate_to_parent(self, campaign: StudentFollowupCampaign) -> None:
        """Try to fetch parent info from ERP and email them."""
        campaign.status = "escalated"

        # Attempt ERP fetch if not done yet
        if not campaign.erp_fetched and campaign.student_id:
            erp_data = await _erp.fetch_student_info(campaign.student_id)
            if erp_data.get("available"):
                campaign.parent_email = erp_data.get("parent_email", "")
                campaign.parent_phone = erp_data.get("parent_phone", "")
                campaign.parent_name  = erp_data.get("parent_name", "")
                if not campaign.student_name:
                    campaign.student_name = erp_data.get("student_name", "")
                campaign.erp_fetched = True
                _log(campaign, "erp_fetch", "student", "erp",
                     f"Fetched parent data: {campaign.parent_email}", "success")
            else:
                _log(campaign, "erp_fetch", "student", "erp",
                     f"ERP unavailable: {erp_data.get('error', 'unknown')}", "failed")

        _mark_step(campaign, 3, "running")

        # Send parent email
        if campaign.parent_email:
            subject, body, html = _parent_email(campaign)
            result = await _send_email(campaign.parent_email, subject, body, html)
            ok = result.get("status") in ("completed", "simulated")
            _log(campaign, "email_sent", "parent", "email",
                 f"Parent escalation: {subject[:60]}",
                 "success" if ok else "failed",
                 result.get("error"))
            _mark_step(campaign, 3, "sent" if ok else "failed")
            campaign.status = "parent_called"  # in UI context means "escalated to parent"
        else:
            _log(campaign, "email_sent", "parent", "email",
                 "Parent email not available (ERP not connected or no data)",
                 "failed", "No parent email found")
            _mark_step(campaign, 3, "no_parent_email")

    def cancel_campaign(self, campaign_id: str) -> None:
        task = self._tasks.get(campaign_id)
        if task and not task.done():
            task.cancel()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(c: StudentFollowupCampaign, type_: str, target: str,
         channel: str, content: str, status: str, error: str = None):
    c.interactions.append(Interaction(
        type=type_, target=target, channel=channel,
        content=content, status=status, error=error
    ))


def _mark_step(c: StudentFollowupCampaign, idx: int, status: str):
    if idx < len(c.schedule):
        c.schedule[idx]["status"] = status


# ---------------------------------------------------------------------------
# Student Data Parser
# ---------------------------------------------------------------------------

def parse_student_data(text: str) -> Optional[Dict]:
    """
    Parse faculty chat text like:
    "Student: abc@gmail.com (ID: 1234554321) Attendance: 65% Days Absent: 5"
    Returns structured dict or None if not student data.
    """
    import re

    result = {}

    # Email
    email_m = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    if email_m:
        result["student_email"] = email_m.group(0)
    else:
        return None  # Must have email

    # Student ID
    id_m = re.search(r"(?:ID[:\s]+|student[_\s]?id[:\s]+|id[:\s]+)([0-9A-Za-z\-]+)", text, re.IGNORECASE)
    if id_m:
        result["student_id"] = id_m.group(1)

    # Attendance percentage
    att_m = re.search(r"attendance[:\s]+([0-9.]+)%", text, re.IGNORECASE)
    if att_m:
        result["attendance_pct"] = float(att_m.group(1))

    # Days absent
    abs_m = re.search(r"days?\s+absent[:\s]+([0-9]+)", text, re.IGNORECASE)
    if abs_m:
        result["days_absent"] = int(abs_m.group(1))

    # Student name (optional)
    name_m = re.search(r"student[:\s]+([A-Za-z ]+?)(?:\s*[\(\,]|$)", text, re.IGNORECASE)
    if name_m:
        name = name_m.group(1).strip()
        # Don't capture the email as name
        if "@" not in name:
            result["student_name"] = name

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_scheduler = FollowupScheduler()


async def create_student_followup(
    user_id: str,
    raw_text: str,
    extra: Optional[Dict] = None,
) -> StudentFollowupCampaign:
    """
    Parse student data from raw_text, create campaign, and start drip.
    extra can override any parsed field.
    """
    parsed = parse_student_data(raw_text) or {}
    if extra:
        parsed.update(extra)

    campaign = StudentFollowupCampaign(
        created_by=user_id,
        raw_input=raw_text,
        student_email=parsed.get("student_email", ""),
        student_id=parsed.get("student_id", ""),
        student_name=parsed.get("student_name", ""),
        attendance_pct=parsed.get("attendance_pct", 0.0),
        days_absent=parsed.get("days_absent", 0),
        pending_assignments=parsed.get("pending_assignments", []),
    )

    # Store
    _campaigns[campaign.id] = campaign
    _user_campaigns.setdefault(user_id, []).append(campaign.id)

    # Begin drip
    await _scheduler.start_campaign(campaign)

    return campaign


def get_user_campaigns(user_id: str) -> List[Dict]:
    ids = _user_campaigns.get(user_id, [])
    return [_campaigns[cid].to_dict() for cid in ids if cid in _campaigns]


def get_campaign(campaign_id: str) -> Optional[StudentFollowupCampaign]:
    return _campaigns.get(campaign_id)


def mark_reply_received(campaign_id: str) -> bool:
    c = _campaigns.get(campaign_id)
    if not c:
        return False
    c.reply_received = True
    c.reply_received_at = datetime.utcnow().isoformat()
    c.status = "resolved"
    _log(c, "reply_received", "student", "email", "Student replied", "success")
    return True


def close_campaign(campaign_id: str) -> bool:
    c = _campaigns.get(campaign_id)
    if not c:
        return False
    c.status = "closed"
    _scheduler.cancel_campaign(campaign_id)
    return True
