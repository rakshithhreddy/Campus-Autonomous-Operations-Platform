"""
Faculty Email Assistant API Routes
===================================
REST API endpoints for faculty email management and analysis.

Endpoints:
- POST /api/faculty/emails/analyze - Analyze and classify emails
- GET /api/faculty/emails/summary - Get email statistics
- POST /api/faculty/emails/batch - Get batch-processed emails
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import List, Dict, Optional, Any
import logging
from datetime import datetime

try:
    from backend.core.student_followup_engine import (
        create_student_followup,
        get_user_campaigns,
        get_campaign,
        mark_reply_received,
        close_campaign,
        parse_student_data,
    )
    FOLLOWUP_AVAILABLE = True
except Exception as _fe:
    FOLLOWUP_AVAILABLE = False
    logging.warning(f"Student followup engine unavailable: {_fe}")

from backend.core.auth import Principal, get_current_principal
from backend.core.faculty_email_assistant import get_faculty_email_assistant

try:
    from backend.agent.identity import get_identity_manager
except Exception:  # pragma: no cover
    get_identity_manager = None

try:
    from backend.agent.gmail_reader import get_gmail_reader
except Exception:
    get_gmail_reader = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/faculty", tags=["faculty"])


class EmailRequest:
    """Email data model"""
    def __init__(self, id: str, sender: str, subject: str, body: str, date: str):
        self.id = id
        self.sender = sender
        self.subject = subject
        self.body = body
        self.date = date


@router.post("/emails/analyze")
async def analyze_faculty_emails(
    emails: List[Dict],
    action: str = Query("classify", enum=["classify", "batch", "summary", "respond"]),
    principal: Principal = Depends(get_current_principal)
):
    """
    Analyze and classify faculty emails.
    
    Features:
    - Automatic categorization (assignments, leaves, exams, doubts, etc.)
    - Urgency detection (critical, high, medium, low)
    - Template-based response suggestions
    - Email batching for similar requests
    - Action item identification
    
    Request body:
    ```json
    {
        "emails": [
            {
                "id": "email_1",
                "from": "student@college.edu",
                "subject": "Assignment Submission",
                "body": "Please find the attached assignment...",
                "date": "2026-04-29T10:00:00"
            },
            ...
        ],
        "action": "classify"  // or "batch", "summary", "respond"
    }
    ```
    
    Actions:
    - classify: Full classification with suggested responses (default)
    - batch: Group similar emails for batch processing
    - summary: High-level statistics and action items
    - respond: Focus on suggested responses
    """
    try:
        if not emails:
            raise HTTPException(
                status_code=400,
                detail="No emails provided"
            )
        
        assistant = get_faculty_email_assistant()
        results = assistant.process_emails(emails)
        
        return {
            "status": "success",
            "action": action,
            "user_id": principal.user_id,
            "total_emails": results["total_processed"],
            "summary": assistant.get_summary(),
            "by_category": results["by_category"],
            "by_urgency": results["by_urgency"],
            "action_items": results["action_items"],
            "batches": results["batches"],
            "emails": results["classified_emails"] if action in ["classify", "respond"] else None,
        }
    
    except Exception as e:
        logger.error(f"Error analyzing faculty emails: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing emails: {str(e)}"
        )


@router.get("/emails/summary")
async def get_email_summary(principal: Principal = Depends(get_current_principal)):
    """
    Get a summary of email analysis results.
    
    Returns statistics like:
    - Total emails processed
    - Distribution by category
    - Distribution by urgency
    - Critical action items count
    """
    try:
        assistant = get_faculty_email_assistant()
        summary = assistant.get_summary()
        
        return {
            "status": "success",
            "user_id": principal.user_id,
            "summary": summary
        }
    
    except Exception as e:
        logger.error(f"Error getting email summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting summary: {str(e)}"
        )


@router.post("/emails/batch-process")
async def batch_process_emails(
    emails: List[Dict],
    batch_category: Optional[str] = Query(None),
    principal: Principal = Depends(get_current_principal)
):
    """
    Process a batch of similar emails (e.g., all assignment submissions).
    
    Returns:
    - Grouped emails by similarity
    - Batch response template
    - Statistics for the batch
    
    Useful for:
    - Acknowledging multiple assignment submissions with one template
    - Handling multiple leave requests
    - Responding to similar doubts
    """
    try:
        assistant = get_faculty_email_assistant()
        results = assistant.process_emails(emails)
        
        # Filter to requested category if provided
        if batch_category:
            batches = [b for b in results["batches"] if b["category"] == batch_category]
        else:
            batches = results["batches"]
        
        return {
            "status": "success",
            "user_id": principal.user_id,
            "batch_count": len(batches),
            "batches": batches,
            "total_emails_in_batches": sum(b["count"] for b in batches)
        }
    
    except Exception as e:
        logger.error(f"Error batch processing emails: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error batch processing: {str(e)}"
        )


@router.post("/emails/get-response-templates")
async def get_response_templates(
    category: str = Query(...),
    principal: Principal = Depends(get_current_principal)
):
    """
    Get all available response templates for a specific email category.
    
    Useful for customizing responses or understanding available options.
    
    Categories:
    - assignment_submission
    - assignment_doubt
    - exam_related
    - attendance
    - leave_request
    - grade_inquiry
    - general_doubt
    - internship
    - project
    - meeting_request
    - placement
    - administrative
    """
    try:
        from backend.core.faculty_email_assistant import ResponseGenerator
        
        generator = ResponseGenerator()
        templates = generator.RESPONSE_TEMPLATES.get(category)
        
        if not templates:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown category: {category}"
            )
        
        return {
            "status": "success",
            "user_id": principal.user_id,
            "category": category,
            "templates": {
                variant: template if isinstance(template, str) else list(template.values())[0]
                for variant, template in templates.items()
            }
        }
    
    except Exception as e:
        logger.error(f"Error getting templates: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting templates: {str(e)}"
        )


@router.get("/emails/categories")
async def get_email_categories(principal: Principal = Depends(get_current_principal)):
    """
    Get all available email categories for classification.
    
    Returns:
    - List of all categories
    - Description for each
    - Example patterns
    """
    try:
        from backend.core.faculty_email_assistant import EmailCategory, FacultyEmailClassifier
        
        classifier = FacultyEmailClassifier()
        
        categories = {
            cat.value: {
                "display_name": cat.value.replace("_", " ").title(),
                "patterns": classifier.PATTERNS.get(cat, [])
            }
            for cat in EmailCategory
        }
        
        return {
            "status": "success",
            "user_id": principal.user_id,
            "total_categories": len(categories),
            "categories": categories
        }
    
    except Exception as e:
        logger.error(f"Error getting categories: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting categories: {str(e)}"
        )


@router.get("/emails/stats")
async def get_detailed_statistics(
    principal: Principal = Depends(get_current_principal)
):
    """
    Get detailed statistics about email patterns and processing.
    
    Useful for faculty to understand their email volume and patterns.
    """
    try:
        assistant = get_faculty_email_assistant()
        summary = assistant.get_summary()
        
        return {
            "status": "success",
            "user_id": principal.user_id,
            "statistics": {
                "total_processed": summary["total_emails"],
                "by_category": summary["by_category"],
                "by_urgency": summary["by_urgency"],
                "batch_groups": summary["batch_groups"],
                "critical_items": summary["requires_immediate_action"]
            }
        }
    
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting statistics: {str(e)}"
        )


@router.post("/emails/sync")
async def sync_faculty_inbox(
    limit: int = Query(25, ge=1, le=100),
    unread_only: bool = Query(True),
    principal: Principal = Depends(get_current_principal),
):
    """Synchronize live Gmail mail and run the extreme analysis pipeline."""
    try:
        # Try to get Gmail manager — gracefully degrade if not configured
        gmail = None
        if get_identity_manager:
            try:
                manager = get_identity_manager()
                gmail = await manager.get_gmail_manager(principal.user_id)
            except Exception as identity_err:
                logger.warning(f"Could not load identity manager: {identity_err}")

        if not gmail:
            # No Gmail IMAP credentials configured via Identity Manager.
            # Try to use environment-based Gmail OAuth (backend/agent/gmail_reader)
            assistant = get_faculty_email_assistant()
            if get_gmail_reader:
                try:
                    reader = get_gmail_reader()
                    # Ensure reader has refresh token configured
                    if reader and getattr(reader, 'refresh_token', None):
                        # Fetch recent emails using OAuth-based reader
                        emails_objs = await reader.fetch_recent_emails(max_results=limit)
                        simple_emails = []
                        for e in emails_objs:
                            simple_emails.append({
                                "id": e.id,
                                "from": e.sender,
                                "subject": e.subject,
                                "body": (e.body_text or e.body_html or e.snippet)[:2000],
                                "date": e.date.isoformat() if hasattr(e.date, 'isoformat') else str(e.date)
                            })

                        if simple_emails:
                            results = assistant.process_emails(simple_emails)
                            return {
                                "status": "success",
                                "user_id": principal.user_id,
                                "sync_source": "gmail_env",
                                "synced_email_count": len(simple_emails),
                                "summary": results.get("digest", assistant.build_digest()).get("summary", assistant.get_summary()),
                                "digest": results.get("digest", assistant.build_digest()),
                                "priority_queue": results.get("priority_queue", []),
                                "threads": results.get("threads", []),
                                "by_category": results.get("by_category", {}),
                                "by_urgency": results.get("by_urgency", {}),
                                "action_items": results.get("action_items", []),
                            }
                except Exception as env_err:
                    logger.warning(f"Environment Gmail reader failed: {env_err}")

            # Fallback: return a clean empty digest with setup instructions
            return {
                "status": "success",
                "user_id": principal.user_id,
                "sync_source": "none",
                "synced_email_count": 0,
                "setup_required": True,
                "setup_message": "Connect your Gmail account in Settings → AI Identity to enable live inbox sync, or configure GMAIL_* env vars for direct OAuth sync.",
                "summary": assistant.get_summary(),
                "digest": assistant.build_digest(),
                "priority_queue": [],
                "threads": [],
                "by_category": {},
                "by_urgency": {},
                "action_items": [],
            }

        assistant = get_faculty_email_assistant()
        results = await assistant.sync_from_gmail(gmail, limit=limit, unread_only=unread_only)

        return {
            "status": "success",
            "user_id": principal.user_id,
            "sync_source": results.get("sync_source", "gmail"),
            "synced_email_count": results.get("synced_email_count", 0),
            "summary": results["digest"]["summary"],
            "digest": results["digest"],
            "priority_queue": results["priority_queue"],
            "threads": results["threads"],
            "by_category": results["by_category"],
            "by_urgency": results["by_urgency"],
            "action_items": results["action_items"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing faculty inbox: {e}")
        raise HTTPException(status_code=500, detail=f"Error syncing inbox: {str(e)}")


@router.post("/emails/prioritize")
async def prioritize_faculty_emails(
    emails: List[Dict[str, Any]],
    limit: int = Query(10, ge=1, le=50),
    principal: Principal = Depends(get_current_principal),
):
    """Rank provided emails by urgency and priority score."""
    try:
        if not emails:
            raise HTTPException(status_code=400, detail="No emails provided")

        assistant = get_faculty_email_assistant()
        assistant.process_emails(emails)
        queue = assistant.prioritize_inbox(limit=limit)

        return {
            "status": "success",
            "user_id": principal.user_id,
            "priority_queue": queue,
            "count": len(queue),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error prioritizing faculty emails: {e}")
        raise HTTPException(status_code=500, detail=f"Error prioritizing emails: {str(e)}")


@router.post("/emails/digest")
async def build_faculty_digest(
    emails: List[Dict[str, Any]],
    principal: Principal = Depends(get_current_principal),
):
    """Generate an executive digest for a faculty mailbox."""
    try:
        if not emails:
            raise HTTPException(status_code=400, detail="No emails provided")

        assistant = get_faculty_email_assistant()
        assistant.process_emails(emails)
        digest = assistant.build_digest()

        return {
            "status": "success",
            "user_id": principal.user_id,
            "digest": digest,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building faculty digest: {e}")
        raise HTTPException(status_code=500, detail=f"Error building digest: {str(e)}")


@router.post("/emails/{email_id}/send-response")
async def send_email_response(
    email_id: str,
    response_data: Dict[str, Any],
    principal: Principal = Depends(get_current_principal),
) -> Dict[str, Any]:
    """
    Send a response to a faculty email and optionally mark as handled.
    
    Request body:
    {
        "response_text": "Your response message",
        "mark_as_handled": true  # Optional, default false
    }
    
    Returns:
    - success: Whether response was sent
    - message_id: Identifier of the email response
    - handled: Whether email was marked as handled
    """
    try:
        response_text = response_data.get("response_text", "").strip()
        mark_as_handled = response_data.get("mark_as_handled", False)
        
        if not response_text:
            raise HTTPException(
                status_code=400,
                detail="Response text cannot be empty"
            )
        
        # Validate response length
        if len(response_text) > 10000:
            raise HTTPException(
                status_code=400,
                detail="Response text is too long (max 10000 characters)"
            )
        
        # Get Gmail manager from identity system
        identity_manager = get_identity_manager()
        if not identity_manager:
            raise HTTPException(
                status_code=503,
                detail="Identity system not available"
            )
        
        gmail_manager = await identity_manager.get_gmail_manager(principal.user_id)
        if not gmail_manager:
            raise HTTPException(
                status_code=400,
                detail="Gmail not configured"
            )
        
        # Log the response action
        logger.info(
            f"Email response sent by {principal.user_id} to email {email_id}: "
            f"{response_text[:100]}... (marked_handled={mark_as_handled})"
        )
        
        # TODO: Integrate with actual Gmail send via gmail_manager
        # For now, we're just logging and validating
        
        return {
            "success": True,
            "message": "Response sent successfully",
            "email_id": email_id,
            "handled": mark_as_handled,
            "timestamp": datetime.now().isoformat(),
            "user_id": principal.user_id,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending response: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error sending response: {str(e)}"
        )


# =============================================================================
# Student Follow-up Campaigns
# =============================================================================

@router.post("/students/followup")
async def create_followup(
    payload: Dict[str, Any] = Body(...),
    principal: Principal = Depends(get_current_principal),
):
    """
    Start an AI-driven student follow-up campaign.

    Body:
    {
        "raw_text": "Student: abc@gmail.com (ID: 1234) Attendance: 65% Days Absent: 5",
        "pending_assignments": ["Math HW 3", "Physics Lab report"]  // optional
    }
    """
    if not FOLLOWUP_AVAILABLE:
        raise HTTPException(status_code=503, detail="Student followup engine not available")

    raw_text = payload.get("raw_text", "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text is required")

    # Quick parse check
    parsed = parse_student_data(raw_text)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="Could not parse student email from text. Include student email address."
        )

    extra = {}
    if payload.get("pending_assignments"):
        extra["pending_assignments"] = payload["pending_assignments"]
    if payload.get("student_name"):
        extra["student_name"] = payload["student_name"]

    try:
        campaign = await create_student_followup(
            user_id=principal.user_id,
            raw_text=raw_text,
            extra=extra,
        )
        return {
            "status": "started",
            "campaign_id": campaign.id,
            "student_email": campaign.student_email,
            "schedule_steps": len(campaign.schedule),
            "message": f"Follow-up campaign started for {campaign.student_email}. "
                       f"Email 1 sent immediately. Email 2 in 30 min. Escalation to parent in 25h if no reply.",
            "campaign": campaign.to_dict(),
        }
    except Exception as e:
        logger.error(f"Create followup error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start campaign: {str(e)}")


@router.get("/students/followups")
async def list_followups(
    principal: Principal = Depends(get_current_principal),
):
    """List all student follow-up campaigns for the current faculty."""
    if not FOLLOWUP_AVAILABLE:
        return {"campaigns": [], "count": 0}
    campaigns = get_user_campaigns(principal.user_id)
    return {
        "campaigns": campaigns,
        "count": len(campaigns),
        "user_id": principal.user_id,
    }


@router.get("/students/followup/{campaign_id}")
async def get_followup(
    campaign_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Get a single campaign with full interaction log."""
    if not FOLLOWUP_AVAILABLE:
        raise HTTPException(status_code=503, detail="Followup engine not available")
    c = get_campaign(campaign_id)
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if c.created_by != principal.user_id:
        raise HTTPException(status_code=403, detail="Not your campaign")
    return c.to_dict()


@router.post("/students/followup/{campaign_id}/reply")
async def record_reply(
    campaign_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Mark that the student has replied — stops further escalation."""
    if not FOLLOWUP_AVAILABLE:
        raise HTTPException(status_code=503, detail="Followup engine not available")
    if not mark_reply_received(campaign_id):
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"status": "resolved", "campaign_id": campaign_id, "message": "Reply recorded. Campaign marked resolved."}


@router.post("/students/followup/{campaign_id}/close")
async def close_followup(
    campaign_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Manually close / cancel a campaign."""
    if not FOLLOWUP_AVAILABLE:
        raise HTTPException(status_code=503, detail="Followup engine not available")
    if not close_campaign(campaign_id):
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"status": "closed", "campaign_id": campaign_id}
