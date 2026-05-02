"""
Faculty Email Chat Commands
============================
High-value chat primitives that surface extreme email analysis.

Commands:
- Analyze my inbox (with priority ranking)
- Show priority emails (top 10 urgent)
- List threads needing response (by topic)
"""

import logging
from typing import Dict, Any, List
from backend.core.primitives import PrimitiveResult
from backend.core.faculty_email_assistant import (
    get_faculty_email_assistant,
    EmailUrgency,
)

logger = logging.getLogger(__name__)


async def analyze_my_inbox(user_id: str = None) -> PrimitiveResult:
    """
    Sync and analyze faculty inbox with extreme features.
    
    Returns:
    - Executive digest (headline, top 5 priorities)
    - Thread insights (conversation groups)
    - Priority queue (top 10 ranked emails)
    
    Requires Gmail connected in identity system.
    """
    try:
        from backend.agent.identity import get_identity_manager
        from backend.core.faculty_email_assistant import get_faculty_email_assistant
        
        user_id = user_id or "default"
        
        # Get Gmail manager from identity system
        identity_manager = get_identity_manager()
        if not identity_manager:
            return PrimitiveResult(
                success=False,
                output="❌ Identity system not available. Cannot sync Gmail.",
                error="identity_system_unavailable"
            )
        
        gmail_manager = await identity_manager.get_gmail_manager(user_id)
        if not gmail_manager:
            return PrimitiveResult(
                success=False,
                output="📧 Gmail not connected. Please set up your email in the Identity panel first.\n\nSteps:\n1. Go to Settings → AI Identity\n2. Add Gmail account\n3. Generate and provide App Password\n4. Return here to sync",
                error="gmail_not_configured",
                data={"setup_required": True, "integration": "gmail"}
            )
        
        # Run full analysis pipeline
        assistant = get_faculty_email_assistant()
        results = await assistant.sync_from_gmail(gmail_manager, limit=25, unread_only=True)
        
        # Build executive output
        digest = results.get("digest", {})
        top_items = digest.get("top_priorities", [])[:5]
        threads = digest.get("threads", [])[:10]
        
        output_lines = [
            f"📊 **{digest.get('headline', 'Inbox Analysis')}**\n",
            "**Top Priorities:**",
        ]
        
        for i, item in enumerate(top_items, 1):
            output_lines.append(
                f"{i}. {item['subject'][:80]} (from {item['sender'].split('@')[0]})\n"
                f"   Category: {item['category']} | Urgency: {item['urgency']} | Score: {item['priority_score']}"
            )
        
        if threads:
            output_lines.append(f"\n**Conversation Threads ({len(threads)})**:")
            for thread in threads[:5]:
                output_lines.append(
                    f"• {thread['subject'][:60]} ({thread['email_count']} emails, "
                    f"{thread['sender_count']} participants, {thread['highest_urgency']} urgency)"
                )
        
        output_lines.extend([
            f"\n**Recommendations:**",
            "• Review critical/high urgency emails first",
            "• Batch similar emails for grouped responses",
            "• Use suggested responses for routine items",
        ])
        
        return PrimitiveResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "digest": digest,
                "priority_queue": results.get("priority_queue", []),
                "threads": threads,
                "synced_count": results.get("synced_email_count", 0),
            }
        )
    
    except Exception as e:
        logger.error(f"Error analyzing inbox: {e}")
        return PrimitiveResult(
            success=False,
            output=f"❌ Error analyzing inbox: {str(e)}",
            error=str(e)
        )


async def show_priority_emails(limit: int = 10) -> PrimitiveResult:
    """
    Show the highest-priority emails from inbox (ranked 0-100).
    
    Filters:
    - Highest priority_score first
    - Within same score, critical/high urgency first
    - Includes deadline and attachment hints
    
    Use for quick triage of what needs immediate attention.
    """
    try:
        from backend.agent.identity import get_identity_manager
        from backend.core.faculty_email_assistant import get_faculty_email_assistant
        
        user_id = "default"
        
        # Get Gmail manager
        identity_manager = get_identity_manager()
        gmail_manager = await identity_manager.get_gmail_manager(user_id) if identity_manager else None
        
        if not gmail_manager:
            return PrimitiveResult(
                success=False,
                output="📧 Gmail not connected",
                error="gmail_not_configured"
            )
        
        # Sync and get priority queue
        assistant = get_faculty_email_assistant()
        results = await assistant.sync_from_gmail(gmail_manager, limit=25)
        priority_queue = results.get("priority_queue", [])[:limit]
        
        if not priority_queue:
            return PrimitiveResult(
                success=True,
                output="✅ No priority emails. Your inbox is clear!",
                data={"priority_queue": []}
            )
        
        # Format output
        output_lines = [f"🔴 **Top {limit} Priority Emails** (score 0-100)\n"]
        
        for i, email in enumerate(priority_queue, 1):
            urgency_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢",
            }.get(email[" urgency"], "⚪")
            
            attachments = " 📎" if email.get("attachment_hints") else ""
            deadline = f" ⏰ {email['deadline']}" if email.get("deadline") else ""
            
            output_lines.append(
                f"{i}. [{email['priority_score']:.0f}] {email['subject'][:70]}{attachments}{deadline}\n"
                f"   {urgency_emoji} {email['urgency'].upper()} | {email['category']} | from {email['sender']}"
            )
        
        return PrimitiveResult(
            success=True,
            output="\n".join(output_lines),
            data={"priority_queue": priority_queue, "count": len(priority_queue)}
        )
    
    except Exception as e:
        logger.error(f"Error showing priority emails: {e}")
        return PrimitiveResult(
            success=False,
            output=f"❌ Error: {str(e)}",
            error=str(e)
        )


async def list_response_needed_threads() -> PrimitiveResult:
    """
    Show threads with critical/high urgency emails that need your response.
    
    Groups emails by conversation topic, sorted by urgency.
    Perfect for scanning what needs action.
    """
    try:
        from backend.agent.identity import get_identity_manager
        from backend.core.faculty_email_assistant import get_faculty_email_assistant
        
        user_id = "default"
        
        # Get Gmail manager
        identity_manager = get_identity_manager()
        gmail_manager = await identity_manager.get_gmail_manager(user_id) if identity_manager else None
        
        if not gmail_manager:
            return PrimitiveResult(
                success=False,
                output="📧 Gmail not connected",
                error="gmail_not_configured"
            )
        
        # Sync and filter threads
        assistant = get_faculty_email_assistant()
        results = await assistant.sync_from_gmail(gmail_manager, limit=25)
        threads = results.get("threads", [])
        
        # Filter to urgent threads
        urgent_threads = [
            t for t in threads
            if t["highest_urgency"] in ["critical", "high"]
        ]
        
        if not urgent_threads:
            return PrimitiveResult(
                success=True,
                output="✅ No urgent threads. All clear!",
                data={"threads": []}
            )
        
        # Format output
        output_lines = [f"⚠️ **{len(urgent_threads)} Thread(s) Needing Response**\n"]
        
        for i, thread in enumerate(urgent_threads, 1):
            urgency_emoji = "🔴" if thread["highest_urgency"] == "critical" else "🟠"
            deadline = f" (deadline: {thread['latest_deadline']})" if thread.get("latest_deadline") else ""
            
            output_lines.append(
                f"{i}. {thread['subject'][:70]}{deadline}\n"
                f"   {urgency_emoji} {thread['highest_urgency'].upper()} | "
                f"{thread['email_count']} email(s) from {thread['sender_count']} person(s) | "
                f"{thread['primary_category']}"
            )
            
            if thread.get("senders"):
                senders_str = ", ".join([s.split("@")[0] for s in thread["senders"][:3]])
                output_lines.append(f"   From: {senders_str}")
        
        return PrimitiveResult(
            success=True,
            output="\n".join(output_lines),
            data={
                "threads": urgent_threads,
                "count": len(urgent_threads),
                "total_threads": len(threads)
            }
        )
    
    except Exception as e:
        logger.error(f"Error listing threads: {e}")
        return PrimitiveResult(
            success=False,
            output=f"❌ Error: {str(e)}",
            error=str(e)
        )
