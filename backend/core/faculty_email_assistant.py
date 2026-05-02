"""
Faculty Email Assistant
========================
Intelligent email classification, categorization, and response generation
for college faculty members.

Features:
- Automatic email categorization (assignments, leaves, doubts, attendance, etc.)
- Template-based response generation
- Urgency detection and flagging
- Email batching and summarization
- Student/staff contact grouping
"""

import re
import logging
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailCategory(Enum):
    """Email categories for faculty"""
    ASSIGNMENT_SUBMISSION = "assignment_submission"
    ASSIGNMENT_DOUBT = "assignment_doubt"
    EXAM_RELATED = "exam_related"
    ATTENDANCE = "attendance"
    LEAVE_REQUEST = "leave_request"
    GRADE_INQUIRY = "grade_inquiry"
    GENERAL_DOUBT = "general_doubt"
    INTERNSHIP = "internship"
    PROJECT = "project"
    MEETING_REQUEST = "meeting_request"
    PLACEMENT = "placement"
    ADMINISTRATIVE = "administrative"
    OTHER = "other"


class EmailUrgency(Enum):
    """Urgency levels for emails"""
    CRITICAL = "critical"  # Requires immediate action
    HIGH = "high"  # Should be addressed soon
    MEDIUM = "medium"  # Normal priority
    LOW = "low"  # Can be addressed later


@dataclass
class ClassifiedEmail:
    """Classified email with metadata"""
    email_id: str
    sender: str
    subject: str
    body: str
    date: str
    category: EmailCategory
    urgency: EmailUrgency
    keywords: List[str] = field(default_factory=list)
    suggested_response: Optional[str] = None
    is_batch_candidate: bool = False
    batch_key: Optional[str] = None
    confidence: float = 0.0
    priority_score: float = 0.0
    thread_id: Optional[str] = None
    deadline: Optional[str] = None
    attachment_hints: List[str] = field(default_factory=list)


@dataclass
class ThreadInsight:
    """Grouped email thread insight"""
    thread_id: str
    subject: str
    sender_count: int = 0
    email_count: int = 0
    primary_category: EmailCategory = EmailCategory.OTHER
    highest_urgency: EmailUrgency = EmailUrgency.LOW
    latest_deadline: Optional[str] = None
    senders: List[str] = field(default_factory=list)
    summary: Optional[str] = None


@dataclass
class InboxPriorityItem:
    """Prioritized inbox item"""
    email_id: str
    subject: str
    sender: str
    category: EmailCategory
    urgency: EmailUrgency
    priority_score: float
    thread_id: Optional[str] = None
    suggested_action: Optional[str] = None


@dataclass
class EmailBatch:
    """Group of similar emails for batch processing"""
    category: EmailCategory
    subject_pattern: str
    emails: List[ClassifiedEmail] = field(default_factory=list)
    count: int = 0
    summary: Optional[str] = None


class FacultyEmailClassifier:
    """Classifies faculty emails into actionable categories"""
    
    # Patterns for email categorization
    PATTERNS = {
        EmailCategory.ASSIGNMENT_SUBMISSION: [
            r"\b(submit|submitted|assignment|hw|homework|submission)\b",
            r"\b(attached|attached:)\b.*\b(assignment|hw|homework)\b",
            r"\b(here is|here's|here are|here's the)\b.*\b(assignment|hw|homework)\b",
        ],
        EmailCategory.ASSIGNMENT_DOUBT: [
            r"\b(doubt|confused|confused about|don't understand|unclear|clarify)\b.*\b(assignment|question|problem|concept)\b",
            r"\b(what does|how do|explain|help me with)\b.*\b(assignment|question|problem)\b",
            r"\b(in assignment|in hw|regarding question)\b",
        ],
        EmailCategory.EXAM_RELATED: [
            r"\b(exam|test|midterm|final|quiz|examination)\b",
            r"\b(answer key|solution|marks|grades|results)\b.*\b(exam|test)\b",
            r"\b(recheck|regrade|revaluation)\b.*\b(exam|test|marks)\b",
        ],
        EmailCategory.ATTENDANCE: [
            r"\b(attend|attendance|absence|absent|missed class|missed lecture)\b",
            r"\b(medical leave|sick|illness|hospital)\b",
            r"\b(attendance issue|low attendance)\b",
        ],
        EmailCategory.LEAVE_REQUEST: [
            r"\b(leave|off|vacation|holiday|request for|request to)\b",
            r"\b(permission|permission to|may i|can i|could i)\b.*\b(leave|go|stay|visit)\b",
            r"\b(emergency leave|casual leave|earned leave)\b",
        ],
        EmailCategory.GRADE_INQUIRY: [
            r"\b(grade|marks|score|result|gpa)\b",
            r"\b(why|how much|how many)\b.*\b(grade|marks|score)\b",
            r"\b(evaluation|assessment)\b",
            r"\b(deduction|penalty|reduced|failed|improve|recheck|regrade|appeal)\b",
            r"\b(question about.*grade|inquir.*grade|grade.*inquir|marks received|score received)\b",
        ],
        EmailCategory.GENERAL_DOUBT: [
            r"\b(doubt|question|clarification|explain|help me understand)\b",
            r"\b(what is|how does|why is|when do)\b",
            r"\b(concept|topic|chapter|unit)\b",
        ],
        EmailCategory.INTERNSHIP: [
            r"\b(internship|intern|placement|job|company)\b",
            r"\b(offer letter|internship offer|job offer)\b",
        ],
        EmailCategory.PROJECT: [
            r"\b(project|semester project|final project|capstone)\b",
            r"\b(deadline|submission|presentation)\b.*\b(project)\b",
        ],
        EmailCategory.MEETING_REQUEST: [
            r"\b(meeting|schedule|appointment|time slot|availability)\b",
            r"\b(can we meet|when are you free|available)\b",
            r"\b(discuss|talk|meet|conference)\b",
        ],
        EmailCategory.PLACEMENT: [
            r"\b(placement|recruitment|drive|interview|campus drive)\b",
            r"\b(offer|selected|shortlisted)\b",
        ],
        EmailCategory.ADMINISTRATIVE: [
            r"\b(syllabus|course|material|resource|documentation|policy)\b",
            r"\b(change of|updated|revised)\b",
        ],
    }
    
    # Keywords that indicate urgency
    URGENCY_KEYWORDS = {
        EmailUrgency.CRITICAL: [
            "urgent", "asap", "immediate", "emergency", "critical", 
            "deadline today", "due now", "help!", "help asap"
        ],
        EmailUrgency.HIGH: [
            "soon", "quickly", "deadline", "due tomorrow", "hurry",
            "important", "please urgent"
        ],
    }
    
    def classify(self, email_id: str, sender: str, subject: str, body: str, date: str) -> ClassifiedEmail:
        """Classify a single email"""
        combined_text = f"{subject} {body}".lower()
        
        # Determine category
        category = self._determine_category(combined_text)
        
        # Determine urgency
        urgency = self._determine_urgency(combined_text, subject)
        
        # Extract keywords
        keywords = self._extract_keywords(combined_text, category)

        # Additional structured signals for extreme-mode analysis
        confidence = self._calculate_confidence(category, combined_text)
        thread_id = self._generate_thread_id(sender, subject)
        deadline = self._extract_deadline(combined_text)
        attachment_hints = self._detect_attachment_hints(body)
        
        # Check if suitable for batching
        is_batch_candidate = category in [
            EmailCategory.ASSIGNMENT_SUBMISSION,
            EmailCategory.GRADE_INQUIRY,
            EmailCategory.GENERAL_DOUBT
        ]
        
        # Generate batch key for grouping
        batch_key = self._generate_batch_key(category, subject, body) if is_batch_candidate else None
        priority_score = self._calculate_priority_score(category, urgency, confidence, deadline)
        
        return ClassifiedEmail(
            email_id=email_id,
            sender=sender,
            subject=subject,
            body=body,
            date=date,
            category=category,
            urgency=urgency,
            keywords=keywords,
            is_batch_candidate=is_batch_candidate,
            batch_key=batch_key
            ,confidence=confidence,
            priority_score=priority_score,
            thread_id=thread_id,
            deadline=deadline,
            attachment_hints=attachment_hints,
        )
    
    def _determine_category(self, text: str) -> EmailCategory:
        """Determine email category based on patterns"""
        scores = {}
        
        for category, patterns in self.PATTERNS.items():
            match_count = 0
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    match_count += 1
            scores[category] = match_count
        
        # Get category with highest score
        best_category = max(scores, key=scores.get)
        
        # If no clear match, return OTHER
        if scores[best_category] == 0:
            return EmailCategory.OTHER
        
        return best_category
    
    def _determine_urgency(self, text: str, subject: str) -> EmailUrgency:
        """Determine urgency level"""
        combined = f"{subject} {text}".lower()
        
        # Check for critical indicators
        for keyword in self.URGENCY_KEYWORDS[EmailUrgency.CRITICAL]:
            if keyword in combined:
                return EmailUrgency.CRITICAL
        
        # Check for high priority indicators
        for keyword in self.URGENCY_KEYWORDS[EmailUrgency.HIGH]:
            if keyword in combined:
                return EmailUrgency.HIGH
        
        # Check for deadline patterns
        if re.search(r"\b(deadline|due|submission|by|before)\b.*\b(today|tonight|now)\b", combined):
            return EmailUrgency.CRITICAL
        if re.search(r"\b(deadline|due|submission|by|before)\b.*\b(tomorrow|next|soon)\b", combined):
            return EmailUrgency.HIGH
        
        return EmailUrgency.MEDIUM
    
    def _extract_keywords(self, text: str, category: EmailCategory) -> List[str]:
        """Extract relevant keywords from email"""
        keywords = []
        
        # Extract assignment names
        assignment_match = re.search(r"\b(assignment|hw|homework|project)\s+([a-z0-9]+)?", text)
        if assignment_match:
            keywords.append(f"assignment:{assignment_match.group(2) or 'general'}")
        
        # Extract exam type
        exam_match = re.search(r"\b(midterm|final|unit\s+test|quiz)\b", text)
        if exam_match:
            keywords.append(f"exam_type:{exam_match.group(1)}")
        
        # Extract dates
        date_match = re.search(r"\b(today|tomorrow|next\s+week|by\s+\d{1,2}/\d{1,2})\b", text)
        if date_match:
            keywords.append(f"timeframe:{date_match.group(1)}")
        
        return keywords
    
    def _generate_batch_key(self, category: EmailCategory, subject: str, body: str) -> str:
        """Generate a key for batching similar emails"""
        # Extract topic/assignment from subject/body
        if category == EmailCategory.ASSIGNMENT_SUBMISSION:
            match = re.search(r"(?:assignment|hw|homework)\s+([^:\n]+)", subject + " " + body, re.IGNORECASE)
            if match:
                return f"assignment:{match.group(1).strip()[:30]}"
        
        elif category == EmailCategory.GENERAL_DOUBT:
            match = re.search(r"(?:about|regarding|on|in)\s+([^:\n]+)", subject + " " + body, re.IGNORECASE)
            if match:
                return f"doubt:{match.group(1).strip()[:30]}"
        
        # Default batch key
        return f"{category.value}:general"

    def _normalize_subject(self, subject: str) -> str:
        normalized = re.sub(r"^(re|fw|fwd)\s*:\s*", "", subject.strip(), flags=re.IGNORECASE)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized[:120].lower()

    def _generate_thread_id(self, sender: str, subject: str) -> str:
        normalized = self._normalize_subject(subject)
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]

    def _calculate_confidence(self, category: EmailCategory, text: str) -> float:
        patterns = self.PATTERNS.get(category, [])
        score = 0.2 if category == EmailCategory.OTHER else 0.45
        hits = 0
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                hits += 1
        score += min(0.45, hits * 0.12)
        if category != EmailCategory.OTHER and hits:
            score += 0.1
        return round(min(score, 0.98), 2)

    def _calculate_priority_score(self, category: EmailCategory, urgency: EmailUrgency, confidence: float, deadline: Optional[str]) -> float:
        base = {
            EmailUrgency.CRITICAL: 95,
            EmailUrgency.HIGH: 80,
            EmailUrgency.MEDIUM: 55,
            EmailUrgency.LOW: 30,
        }[urgency]
        category_bonus = {
            EmailCategory.LEAVE_REQUEST: 10,
            EmailCategory.GRADE_INQUIRY: 12,
            EmailCategory.MEETING_REQUEST: 8,
            EmailCategory.ASSIGNMENT_DOUBT: 15,
            EmailCategory.EXAM_RELATED: 15,
        }.get(category, 0)
        deadline_bonus = 8 if deadline else 0
        return round(min(100.0, base + category_bonus + deadline_bonus + confidence * 10), 2)

    def _extract_deadline(self, text: str) -> Optional[str]:
        patterns = [
            r"\b(?:deadline|due|before|by)\b.{0,24}\b(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            r"\b(?:deadline|due|before|by)\b.{0,24}\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)[:120]
        return None

    def _detect_attachment_hints(self, body: str) -> List[str]:
        hints = []
        lowered = body.lower()
        if any(token in lowered for token in ["attached", "attachment", "see attached", "enclosed"]):
            hints.append("attachment_present")
        if any(token in lowered for token in ["pdf", "doc", "docx", "xlsx", "zip", "image"]):
            hints.append("file_reference")
        if any(token in lowered for token in ["ssn", "aadhaar", "passport", "otp", "bank"]):
            hints.append("sensitive_content")
        return hints


class ResponseGenerator:
    """Generates contextual responses for faculty emails"""
    
    RESPONSE_TEMPLATES = {
        EmailCategory.ASSIGNMENT_SUBMISSION: {
            "acknowledged": "Thank you for submitting your assignment. I have received it and will review it soon.",
            "late": "Thank you for your submission. Please note that this was submitted after the deadline. It will be graded with a late penalty as per course policy.",
            "batch": "Thank you all for your submissions. I have received {count} submissions for {assignment}. I will review them and provide feedback within 2-3 days.",
        },
        EmailCategory.ASSIGNMENT_DOUBT: {
            "general": "Thank you for reaching out with your question. I'll help clarify this for you:\n\n{clarification}\n\nPlease let me know if you have further questions.",
            "office_hours": "This is a great question! Please attend office hours on {day} at {time} where I can explain this in detail with examples.",
            "group": "I see several students have the same question. I'll hold an online session to clarify this topic for the group.",
        },
        EmailCategory.EXAM_RELATED: {
            "marks_inquiry": "Regarding your marks for {exam}:\n{marks_info}\n\nIf you believe there's an error, please request a recheck within 3 days.",
            "answer_key": "The answer key for {exam} has been uploaded to the course portal. You can compare with the provided solutions.",
            "reschedule": "I have noted your request for exam rescheduling. Please provide a valid reason and supporting documentation.",
        },
        EmailCategory.ATTENDANCE: {
            "low_attendance": "I have noticed that your attendance is below the required threshold. Please attend the upcoming classes regularly. Talk to me if you have any issues.",
            "absence_noted": "Your absence has been noted. Please ensure to maintain attendance and inform in advance if you need to miss a class.",
            "medical": "Thank you for informing about your medical emergency. Please submit a medical certificate and we can adjust your attendance accordingly.",
        },
        EmailCategory.LEAVE_REQUEST: {
            "approved": "Your leave request for {dates} is approved. Please inform me if the dates change. Ensure you catch up on the missed content.",
            "pending": "I have received your leave request. I will review and get back to you within 24 hours.",
            "denied": "I cannot approve this leave as it conflicts with {reason}. Please discuss alternative dates.",
        },
        EmailCategory.GRADE_INQUIRY: {
            "explanation": "Your grade for {assessment} is based on:\n{criteria}\n\nYou can appeal if you believe there's an error.",
            "recheck_approved": "I will recheck your {assessment}. I'll get back to you with the results within a week.",
        },
        EmailCategory.GENERAL_DOUBT: {
            "office_hours": "Thank you for your question on {topic}. Please visit office hours on {day} at {time} for a detailed discussion.",
            "resource": "Here's a resource that explains {topic}: {link}. Please go through it and let me know if you have further questions.",
        },
        EmailCategory.MEETING_REQUEST: {
            "slot_offered": "I can meet you on {date} at {time} in {location}. Please confirm if this works for you.",
            "office_hours": "Please attend my office hours on {day} from {start_time} to {end_time}. No need to schedule an appointment.",
        },
        EmailCategory.ADMINISTRATIVE: {
            "syllabus": "The updated syllabus has been shared. Please check the course portal for the latest version.",
            "material": "Course materials have been uploaded to the portal. You can access them anytime.",
        },
        EmailCategory.INTERNSHIP: {
            "share": "Thank you for sharing this opportunity with the class. I will forward it to interested students.",
            "forward": "This internship opportunity is suitable for students in {sem} semester. Interested students can apply directly.",
        },
        EmailCategory.PROJECT: {
            "team_formation": "I'll help coordinate team formation. Please check the portal for available team slots.",
            "guidance": "Great choice of topic! I can guide you through the project. Please schedule office hours to discuss the implementation plan.",
        },
        EmailCategory.PLACEMENT: {
            "opportunity": "Thank you for sharing this placement drive. I will inform eligible students.",
            "placement_info": "This company will be conducting interviews on {date}. Students interested in {profile} role, please register.",
        },
        EmailCategory.OTHER: {
            "acknowledge": "Thank you for reaching out. I will review this and get back to you.",
            "generic": "I have received your message and will respond shortly.",
        },
    }
    
    def generate_response(
        self, 
        classified_email: ClassifiedEmail,
        context: Optional[Dict] = None
    ) -> str:
        """Generate a response for a classified email"""
        context = context or {}
        category = classified_email.category
        
        # Get template category
        templates = self.RESPONSE_TEMPLATES.get(category, {})
        
        if not templates:
            return self._default_response(classified_email)
        
        # Determine which template variant to use
        variant = self._determine_template_variant(classified_email, context)
        template = templates.get(variant, list(templates.values())[0] if templates else "")
        
        if isinstance(template, dict):
            template = list(template.values())[0]
        
        # Format template with context
        try:
            response = template.format(**context) if context else template
        except KeyError:
            response = template
        
        # Add closing
        response += "\n\nBest regards,\nProf. [Your Name]"
        
        return response
    
    def _determine_template_variant(
        self, 
        email: ClassifiedEmail,
        context: Dict
    ) -> str:
        """Determine which template variant to use"""
        body_lower = email.body.lower()
        subject_lower = email.subject.lower()
        
        if email.category == EmailCategory.ASSIGNMENT_SUBMISSION:
            if "late" in body_lower or "after deadline" in body_lower:
                return "late"
            return "acknowledged"
        
        elif email.category == EmailCategory.EXAM_RELATED:
            if "answer" in subject_lower or "solution" in body_lower:
                return "answer_key"
            elif "marks" in subject_lower or "grade" in body_lower:
                return "marks_inquiry"
            return "reschedule"
        
        elif email.category == EmailCategory.LEAVE_REQUEST:
            return "approved"  # Default to approved
        
        elif email.category == EmailCategory.GENERAL_DOUBT:
            if "office hours" in body_lower:
                return "office_hours"
            return "resource"
        
        elif email.category == EmailCategory.MEETING_REQUEST:
            if "office hours" in body_lower:
                return "office_hours"
            return "slot_offered"
        
        # Try to find in templates dict
        templates = self.RESPONSE_TEMPLATES.get(email.category, {})
        if templates:
            return list(templates.keys())[0]
        
        return "general"
    
    def _default_response(self, email: ClassifiedEmail) -> str:
        """Generate a default response"""
        category_name = email.category.value.replace("_", " ").title()
        response = f"""Thank you for your email regarding {category_name}.

I will review your message and get back to you shortly.

Best regards,
Prof. [Your Name]"""
        return response


class FacultyEmailAssistant:
    """Main assistant for managing faculty emails"""
    
    def __init__(self):
        self.classifier = FacultyEmailClassifier()
        self.response_generator = ResponseGenerator()
        self.classified_emails: List[ClassifiedEmail] = []
        self.email_batches: Dict[str, EmailBatch] = {}
    
    def process_emails(self, emails: List[Dict]) -> Dict:
        """Process a list of raw emails"""
        results = {
            "total_processed": len(emails),
            "by_category": {},
            "by_urgency": {},
            "classified_emails": [],
            "batches": [],
            "action_items": []
        }
        
        self.classified_emails = []
        self.email_batches = {}
        
        # Classify each email
        for email in emails:
            classified = self.classifier.classify(
                email_id=email.get("id", ""),
                sender=email.get("from", ""),
                subject=email.get("subject", ""),
                body=email.get("body", ""),
                date=email.get("date", "")
            )
            
            self.classified_emails.append(classified)
            
            # Track categories and urgency
            cat_name = classified.category.value
            urg_name = classified.urgency.value
            
            results["by_category"][cat_name] = results["by_category"].get(cat_name, 0) + 1
            results["by_urgency"][urg_name] = results["by_urgency"].get(urg_name, 0) + 1
            
            # Generate suggested response
            classified.suggested_response = self.response_generator.generate_response(
                classified
            )
            
            results["classified_emails"].append({
                "id": classified.email_id,
                "from": classified.sender,
                "subject": classified.subject,
                "category": classified.category.value,
                "urgency": classified.urgency.value,
                "keywords": classified.keywords,
                "suggested_response": classified.suggested_response[:200] + "..." if len(classified.suggested_response) > 200 else classified.suggested_response,
            })
        
        # Create batches for similar emails
        self._create_batches()
        
        for batch_key, batch in self.email_batches.items():
            if len(batch.emails) > 1:
                results["batches"].append({
                    "key": batch_key,
                    "category": batch.category.value,
                    "count": len(batch.emails),
                    "subject_pattern": batch.subject_pattern,
                    "senders": [e.sender for e in batch.emails]
                })
        
        # Extract action items (urgent and critical)
        action_items = [
            e for e in self.classified_emails
            if e.urgency in [EmailUrgency.CRITICAL, EmailUrgency.HIGH]
        ]
        
        results["action_items"] = [
            {
                "from": e.sender,
                "subject": e.subject,
                "category": e.category.value,
                "urgency": e.urgency.value,
                "suggested_response": e.suggested_response[:150] + "..."
            }
            for e in action_items
        ]

        results["threads"] = self.build_thread_insights()
        results["priority_queue"] = self.prioritize_inbox(limit=10)
        results["digest"] = self.build_digest()
        
        return results
    
    def _create_batches(self):
        """Group similar emails into batches"""
        batch_map: Dict[str, EmailBatch] = {}
        
        for email in self.classified_emails:
            if email.is_batch_candidate and email.batch_key:
                if email.batch_key not in batch_map:
                    batch_map[email.batch_key] = EmailBatch(
                        category=email.category,
                        subject_pattern=email.subject[:50]
                    )
                batch_map[email.batch_key].emails.append(email)
                batch_map[email.batch_key].count = len(batch_map[email.batch_key].emails)
        
        self.email_batches = batch_map

    def _urgency_rank(self, urgency: EmailUrgency) -> int:
        return {
            EmailUrgency.CRITICAL: 4,
            EmailUrgency.HIGH: 3,
            EmailUrgency.MEDIUM: 2,
            EmailUrgency.LOW: 1,
        }[urgency]

    def build_thread_insights(self) -> List[Dict[str, Any]]:
        """Group the current inbox into conversation threads and summarize them."""
        threads: Dict[str, ThreadInsight] = {}

        for email in self.classified_emails:
            thread_id = email.thread_id or self.classifier._generate_thread_id(email.sender, email.subject)
            subject = self.classifier._normalize_subject(email.subject) or email.subject.lower().strip()

            if thread_id not in threads:
                threads[thread_id] = ThreadInsight(thread_id=thread_id, subject=subject)

            thread = threads[thread_id]
            thread.email_count += 1
            if email.sender not in thread.senders:
                thread.senders.append(email.sender)
                thread.sender_count = len(thread.senders)
            if thread.primary_category == EmailCategory.OTHER or email.priority_score > 0:
                thread.primary_category = email.category if email.category != EmailCategory.OTHER else thread.primary_category
            if self._urgency_rank(email.urgency) > self._urgency_rank(thread.highest_urgency):
                thread.highest_urgency = email.urgency
            if email.deadline:
                thread.latest_deadline = email.deadline

        results: List[Dict[str, Any]] = []
        for thread in threads.values():
            summary_bits = [f"{thread.email_count} email(s)", thread.primary_category.value.replace("_", " ").title()]
            if thread.latest_deadline:
                summary_bits.append(f"deadline {thread.latest_deadline}")
            if thread.highest_urgency == EmailUrgency.CRITICAL:
                summary_bits.append("critical urgency")
            thread.summary = ", ".join(summary_bits)
            results.append({
                "thread_id": thread.thread_id,
                "subject": thread.subject,
                "sender_count": thread.sender_count,
                "email_count": thread.email_count,
                "primary_category": thread.primary_category.value,
                "highest_urgency": thread.highest_urgency.value,
                "latest_deadline": thread.latest_deadline,
                "senders": thread.senders,
                "summary": thread.summary,
            })

        return sorted(results, key=lambda item: (item["email_count"], self._urgency_rank(EmailUrgency(item["highest_urgency"]))), reverse=True)

    def prioritize_inbox(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most important emails first."""
        prioritized = sorted(
            self.classified_emails,
            key=lambda email: (email.priority_score, self._urgency_rank(email.urgency), email.email_id),
            reverse=True,
        )[:limit]

        return [
            {
                "email_id": email.email_id,
                "subject": email.subject,
                "sender": email.sender,
                "category": email.category.value,
                "urgency": email.urgency.value,
                "priority_score": email.priority_score,
                "thread_id": email.thread_id,
                "deadline": email.deadline,
                "attachment_hints": email.attachment_hints,
                "suggested_action": email.suggested_response,
            }
            for email in prioritized
        ]

    def build_digest(self) -> Dict[str, Any]:
        """Create an executive-style digest for faculty inbox triage."""
        summary = self.get_summary()
        threads = self.build_thread_insights()
        top_items = self.prioritize_inbox(limit=5)

        return {
            "headline": f"{summary['requires_immediate_action']} urgent item(s), {summary['total_emails']} total email(s)",
            "summary": summary,
            "top_priorities": top_items,
            "threads": threads[:10],
            "recommended_focus": [
                "Handle critical and high urgency mail first",
                "Batch assignment submissions and repeated student doubts",
                "Use suggested responses for routine confirmations",
            ],
        }

    async def sync_from_gmail(self, gmail_manager, limit: int = 25, unread_only: bool = True) -> Dict[str, Any]:
        """Fetch live emails from Gmail and run the full analysis pipeline."""
        emails = await gmail_manager.read_emails(limit=limit, unread_only=unread_only)
        results = self.process_emails(emails)
        results["sync_source"] = "gmail"
        results["synced_email_count"] = len(emails)
        results["digest"] = self.build_digest()
        results["priority_queue"] = self.prioritize_inbox(limit=10)
        results["threads"] = self.build_thread_insights()
        return results
    
    def get_summary(self) -> Dict:
        """Get a summary of all processed emails"""
        categories = {}
        urgencies = {}
        
        for email in self.classified_emails:
            cat = email.category.value
            urg = email.urgency.value
            
            categories[cat] = categories.get(cat, 0) + 1
            urgencies[urg] = urgencies.get(urg, 0) + 1
        
        return {
            "total_emails": len(self.classified_emails),
            "by_category": categories,
            "by_urgency": urgencies,
            "batch_groups": len(self.email_batches),
            "requires_immediate_action": sum(1 for e in self.classified_emails if e.urgency == EmailUrgency.CRITICAL)
        }


def get_faculty_email_assistant() -> FacultyEmailAssistant:
    """Get or create faculty email assistant instance"""
    return FacultyEmailAssistant()
