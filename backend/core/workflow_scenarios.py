"""
Workflow Scenarios - Pre-built pipeline templates for common use cases
"""

from backend.core.workflow_engine import (
    WorkflowDefinition, WorkflowStep, WorkflowCondition,
    WorkflowExecutor, WorkflowInstance, WorkflowStepType,
    StepStatus, WorkflowState
)
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# SCENARIO 1: STUDENT ATTENDANCE FOLLOW-UP
# ============================================================================

class StudentAttendanceScenario:
    """
    Pipeline for getting non-attending students to attend classes.
    
    Flow:
    1. Send initial email to student
    2. Wait 3 days
    3. Check attendance in ERP
    4. If low → Send reminder; else → End
    5. Wait 2 days
    6. Check again
    7. If still low → Fetch parent email and escalate
    8. End with escalation logged
    """
    
    @staticmethod
    def create_template() -> WorkflowDefinition:
        steps = [
            WorkflowStep(
                name="Initial Student Contact",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=0,
                config={
                    "recipient_type": "student",
                    "template_name": "attendance_initial_contact",
                    "subject": "Class Attendance Alert",
                    "body": """Dear Student,

We noticed you have been missing classes regularly. Regular attendance is crucial for your academic success.

Please make sure to attend all upcoming classes. If you have any issues, please contact your class teacher.

Best regards,
School Administration"""
                },
                next_step_id=None  # Will be set after step creation
            ),
            WorkflowStep(
                name="Wait 3 Days",
                step_type=WorkflowStepType.WAIT,
                order=1,
                config={"delay_hours": 72},  # 3 days
                next_step_id=None
            ),
            WorkflowStep(
                name="Check Attendance Status",
                step_type=WorkflowStepType.CHECK_CONDITION,
                order=2,
                config={
                    "condition_type": "attendance_percentage",
                    "query_source": "erp",
                    "threshold": 70
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Send Reminder to Student",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=3,
                config={
                    "recipient_type": "student",
                    "template_name": "attendance_reminder",
                    "subject": "Urgent: Improve Your Attendance",
                    "body": """Dear Student,

Despite our previous warning, your attendance is still below acceptable levels. This is affecting your grades and eligibility for exams.

Please improve your attendance immediately. Attendance below 75% may lead to debarment from exams.

Contact your teacher if you need support.

Best regards,
School Administration"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 2 Days",
                step_type=WorkflowStepType.WAIT,
                order=4,
                config={"delay_hours": 48},  # 2 days
                next_step_id=None
            ),
            WorkflowStep(
                name="Re-check Attendance",
                step_type=WorkflowStepType.QUERY_ERP,
                order=5,
                config={
                    "query_type": "attendance_percentage",
                    "store_result_in": "attendance_second_check"
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Escalate to Parent",
                step_type=WorkflowStepType.ESCALATE,
                order=6,
                config={
                    "escalation_type": "parent_contact",
                    "fetch_parent_email_from": "erp",
                    "email_template": "attendance_parent_escalation",
                    "subject": "Urgent: Your Child's Poor Attendance",
                    "body": """Dear Parent,

We are writing to inform you about your child's poor attendance in school. Your child has missed several classes, which is affecting their academic performance.

We request your intervention to ensure your child attends school regularly. Please contact us if there are any issues preventing regular attendance.

Regards,
School Principal"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Log Escalation",
                step_type=WorkflowStepType.LOG_ACTION,
                order=7,
                config={
                    "action_description": "Escalated to parent due to persistent low attendance",
                    "severity": "high",
                    "notify_admin": True
                },
                next_step_id=None
            ),
        ]
        
        # Link steps
        for i in range(len(steps) - 1):
            steps[i].next_step_id = steps[i + 1].id
        
        definition = WorkflowDefinition(
            name="Student Attendance Follow-up",
            description="Automated follow-up pipeline for students with low attendance. Sends reminders and escalates to parents if necessary.",
            scenario_type="attendance",
            steps=steps,
            conditions=[],
            enabled=True
        )
        
        return definition


# ============================================================================
# SCENARIO 2: ASSIGNMENT DEADLINE REMINDERS
# ============================================================================

class AssignmentReminderScenario:
    """
    Pipeline for reminding students about assignment submissions.
    
    Flow:
    1. Send reminder (3 days before deadline)
    2. Wait until 1 day before deadline
    3. Check if submitted
    4. If no → Send urgent reminder; else → End
    5. Wait until after deadline
    6. Check final submission
    7. If not submitted → Auto-reduce marks, notify parent
    8. End
    """
    
    @staticmethod
    def create_template() -> WorkflowDefinition:
        steps = [
            WorkflowStep(
                name="Send Assignment Reminder",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=0,
                config={
                    "recipient_type": "student",
                    "template_name": "assignment_reminder",
                    "subject": "Assignment Reminder: {assignment_name} Due Soon",
                    "body": """Dear Student,

This is a reminder that Assignment "{assignment_name}" is due in 3 days.

Please submit your work on time. Late submissions will incur a penalty.

Submission link: {submission_link}

Best regards,
Your Teacher"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait Until 1 Day Before",
                step_type=WorkflowStepType.WAIT,
                order=1,
                config={"delay_hours": 48},  # 2 days, then 1 day remains
                next_step_id=None
            ),
            WorkflowStep(
                name="Check Submission Status",
                step_type=WorkflowStepType.QUERY_ERP,
                order=2,
                config={
                    "query_type": "assignment_submitted",
                    "store_result_in": "submission_status_1"
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Send Urgent Reminder",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=3,
                config={
                    "recipient_type": "student",
                    "template_name": "assignment_urgent",
                    "subject": "URGENT: {assignment_name} Due Tomorrow!",
                    "body": """Dear Student,

Your assignment "{assignment_name}" is DUE TOMORROW. Please submit it as soon as possible.

Failure to submit on time will result in:
- Late penalty of -10% for each day late
- Impact on your final grade

Submit now: {submission_link}

Best regards,
Your Teacher"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait Until After Deadline",
                step_type=WorkflowStepType.WAIT,
                order=4,
                config={"delay_hours": 24},
                next_step_id=None
            ),
            WorkflowStep(
                name="Check Final Submission",
                step_type=WorkflowStepType.QUERY_ERP,
                order=5,
                config={
                    "query_type": "assignment_submitted",
                    "store_result_in": "submission_status_final"
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="If Not Submitted: Mark Deduction & Parent Notification",
                step_type=WorkflowStepType.ESCALATE,
                order=6,
                config={
                    "escalation_type": "mark_deduction",
                    "deduction_percentage": 50,
                    "notify_parent": True,
                    "parent_email_template": "assignment_not_submitted",
                    "parent_subject": "Assignment Not Submitted - Grade Impact",
                    "parent_body": """Dear Parent,

Your child did not submit the assignment "{assignment_name}" by the deadline. As per school policy, 50% marks have been deducted from their score.

Please encourage your child to submit assignments on time.

Regards,
School Administration"""
                },
                next_step_id=None
            ),
        ]
        
        for i in range(len(steps) - 1):
            steps[i].next_step_id = steps[i + 1].id
        
        definition = WorkflowDefinition(
            name="Assignment Deadline Reminder",
            description="Automated reminders and follow-up for assignment submissions. Tracks submission status and escalates if not submitted.",
            scenario_type="assignment",
            steps=steps,
            conditions=[],
            enabled=True
        )
        
        return definition


# ============================================================================
# SCENARIO 3: FEE PAYMENT COLLECTION
# ============================================================================

class FeeCollectionScenario:
    """
    Pipeline for fee payment reminders and escalation.
    
    Flow:
    1. Send fee payment reminder to parent
    2. Wait 15 days
    3. Check if paid
    4. If no → Send 2nd reminder + partial payment option
    5. Wait 15 days more
    6. Check again
    7. If still no → Escalate to principal, restrict access
    """
    
    @staticmethod
    def create_template() -> WorkflowDefinition:
        steps = [
            WorkflowStep(
                name="Send Fee Reminder to Parent",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=0,
                config={
                    "recipient_type": "parent",
                    "template_name": "fee_reminder_1",
                    "subject": "School Fee Payment Reminder",
                    "body": """Dear Parent,

This is a friendly reminder that your child's school fees for this term are now due.

Amount Due: {amount}
Due Date: {due_date}
Payment Link: {payment_link}

Please process the payment at your earliest convenience.

Regards,
School Finance Department"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 15 Days",
                step_type=WorkflowStepType.WAIT,
                order=1,
                config={"delay_hours": 360},  # 15 days
                next_step_id=None
            ),
            WorkflowStep(
                name="Check Payment Status",
                step_type=WorkflowStepType.QUERY_ERP,
                order=2,
                config={
                    "query_type": "fee_paid",
                    "store_result_in": "payment_status_1"
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Send 2nd Reminder + Partial Payment Option",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=3,
                config={
                    "recipient_type": "parent",
                    "template_name": "fee_reminder_2",
                    "subject": "Urgent: Outstanding School Fee",
                    "body": """Dear Parent,

Your child's school fees remain unpaid. We request immediate payment to avoid any interruption to their studies.

Outstanding Amount: {amount}

We also offer an installment plan:
- 50% now + 50% in 30 days
- Please contact our office for details

Payment Link: {payment_link}
Contact: finance@school.edu

Regards,
School Finance Department"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 15 More Days",
                step_type=WorkflowStepType.WAIT,
                order=4,
                config={"delay_hours": 360},
                next_step_id=None
            ),
            WorkflowStep(
                name="Final Payment Check",
                step_type=WorkflowStepType.QUERY_ERP,
                order=5,
                config={
                    "query_type": "fee_paid",
                    "store_result_in": "payment_status_final"
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Escalate to Principal & Restrict Access",
                step_type=WorkflowStepType.ESCALATE,
                order=6,
                config={
                    "escalation_type": "principal_notification",
                    "action": "restrict_access",
                    "notify_principal": True,
                    "principal_subject": "Outstanding Fee - Student {student_name}",
                    "restrict_from": ["online_portal", "attendance_marking", "exam_registration"],
                    "parent_notification": "Fee Payment Final Notice"
                },
                next_step_id=None
            ),
        ]
        
        for i in range(len(steps) - 1):
            steps[i].next_step_id = steps[i + 1].id
        
        definition = WorkflowDefinition(
            name="Fee Payment Collection Pipeline",
            description="Tracks fee payments, sends reminders, offers installment options, and escalates to principal if unpaid.",
            scenario_type="fee",
            steps=steps,
            conditions=[],
            enabled=True
        )
        
        return definition


# ============================================================================
# SCENARIO 4: EXAM PREPARATION TRACKING
# ============================================================================

class ExamPrepScenario:
    """
    Pipeline for tracking exam preparation and supporting unprepared students.
    
    Flow:
    1. Send study materials 60 days before exam
    2. Wait 30 days
    3. Send mock test link
    4. Check if student attempted
    5. If no → Send remedial guidance
    6. Wait 23 days
    7. Send final tips 1 day before exam
    """
    
    @staticmethod
    def create_template() -> WorkflowDefinition:
        steps = [
            WorkflowStep(
                name="Send Study Materials & Plan",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=0,
                config={
                    "recipient_type": "student",
                    "template_name": "exam_study_materials",
                    "subject": "{exam_name} - Study Guide & Resources",
                    "body": """Dear Student,

Your {exam_name} is 60 days away. We have compiled comprehensive study materials to help you prepare.

Download your study guide: {study_guide_link}
Syllabus: {syllabus_link}
Previous year papers: {previous_papers_link}

Study Plan:
- Week 1-2: Topics 1-5
- Week 3-4: Topics 6-10
- Week 5-6: Revision & Mock Tests

Best of luck!

Your Academic Team"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 30 Days",
                step_type=WorkflowStepType.WAIT,
                order=1,
                config={"delay_hours": 720},  # 30 days
                next_step_id=None
            ),
            WorkflowStep(
                name="Send Mock Test Link",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=2,
                config={
                    "recipient_type": "student",
                    "template_name": "exam_mock_test",
                    "subject": "Mock Test Available: {exam_name}",
                    "body": """Dear Student,

A full-length mock test is now available to assess your preparation level.

Take Mock Test: {mock_test_link}
Time: 3 hours
Format: Same as actual exam

After completion, review the solutions and identify weak areas.

Good luck!"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Check if Mock Test Attempted",
                step_type=WorkflowStepType.QUERY_ERP,
                order=3,
                config={
                    "query_type": "mock_test_attempted",
                    "store_result_in": "mock_test_status"
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Send Remedial Guidance",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=4,
                config={
                    "recipient_type": "student",
                    "template_name": "exam_remedial",
                    "subject": "Personalized Study Recommendations",
                    "body": """Dear Student,

Based on your mock test performance, here are areas you need to focus on:

Weak Areas: {weak_areas}
Recommended Resources: {resource_links}
Suggested Study Hours: {study_hours}

Please dedicate extra time to these topics. Contact your teacher if you need clarification.

You can do it!"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 23 Days (Until 1 Day Before Exam)",
                step_type=WorkflowStepType.WAIT,
                order=5,
                config={"delay_hours": 552},  # 23 days
                next_step_id=None
            ),
            WorkflowStep(
                name="Send Final Tips & Exam Day Instructions",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=6,
                config={
                    "recipient_type": "student",
                    "template_name": "exam_final_tips",
                    "subject": "{exam_name} - Exam Tomorrow! Final Tips",
                    "body": """Dear Student,

Your {exam_name} is tomorrow! Here are final tips for success:

✓ Get good sleep tonight
✓ Keep all required documents ready
✓ Reach exam center 15 minutes early
✓ Read questions carefully before answering
✓ Manage time - don't spend too long on one question
✓ Stay calm and confident

Exam Details:
- Date: {exam_date}
- Time: {exam_time}
- Venue: {exam_venue}
- Duration: {duration}

You are prepared. Go ace it!

Best wishes,
Your School"""
                },
                next_step_id=None
            ),
        ]
        
        for i in range(len(steps) - 1):
            steps[i].next_step_id = steps[i + 1].id
        
        definition = WorkflowDefinition(
            name="Exam Preparation Tracking",
            description="Comprehensive exam preparation pipeline with study materials, mock tests, and personalized guidance.",
            scenario_type="exam",
            steps=steps,
            conditions=[],
            enabled=True
        )
        
        return definition


# ============================================================================
# SCENARIO 5: CONDUCT & BEHAVIOR ISSUES
# ============================================================================

class ConductIssueScenario:
    """
    Pipeline for managing student conduct and behavior problems.
    
    Flow:
    1. Send first warning to student
    2. Wait 7 days, check for improvement
    3. If no improvement → Schedule counselor meeting
    4. Wait 7 days, check again
    5. If still issues → Notify parents with meeting invitation
    6. Wait 7 days
    7. If unresolved → Send suspension notice to principal
    """
    
    @staticmethod
    def create_template() -> WorkflowDefinition:
        steps = [
            WorkflowStep(
                name="Send First Warning to Student",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=0,
                config={
                    "recipient_type": "student",
                    "template_name": "conduct_warning_1",
                    "subject": "Behavior Concern - Improvement Required",
                    "body": """Dear {student_name},

We have observed {behavior_issue} in your recent conduct. This is not acceptable and does not align with our school values.

We expect you to:
✓ Show respect to teachers and peers
✓ Follow school rules
✓ Demonstrate responsible behavior

This is a formal warning. Any further incidents will result in escalation.

Please meet with your class teacher to discuss this matter.

Regards,
School Administration"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 7 Days",
                step_type=WorkflowStepType.WAIT,
                order=1,
                config={"delay_hours": 168},  # 7 days
                next_step_id=None
            ),
            WorkflowStep(
                name="Check for Improvement",
                step_type=WorkflowStepType.QUERY_ERP,
                order=2,
                config={
                    "query_type": "behavior_incidents",
                    "store_result_in": "incidents_after_warning"
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Schedule Counselor Meeting",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=3,
                config={
                    "recipient_type": "student",
                    "template_name": "conduct_counselor",
                    "subject": "Mandatory Counselor Session - {date}",
                    "body": """Dear {student_name},

As your behavior has not improved, we are scheduling a mandatory session with our school counselor.

Counselor: {counselor_name}
Date & Time: {counseling_date_time}
Location: {counselor_office}

This session is to help you understand the impact of your behavior and develop better coping strategies.

It's mandatory attendance.

Regards,
School Administration"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 7 Days for Counseling Impact",
                step_type=WorkflowStepType.WAIT,
                order=4,
                config={"delay_hours": 168},
                next_step_id=None
            ),
            WorkflowStep(
                name="Check If Issues Persist",
                step_type=WorkflowStepType.QUERY_ERP,
                order=5,
                config={
                    "query_type": "behavior_incidents",
                    "store_result_in": "incidents_after_counseling"
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Notify Parents - Formal Meeting",
                step_type=WorkflowStepType.ESCALATE,
                order=6,
                config={
                    "escalation_type": "parent_meeting",
                    "notify_parent": True,
                    "parent_subject": "Formal Meeting Required - Student Conduct",
                    "meeting_type": "formal_behavior_discussion",
                    "meeting_invitees": ["principal", "counselor", "class_teacher"],
                    "parent_body": """Dear Parent,

Despite our interventions, your child continues to exhibit behavioral issues. We need to have a formal discussion to understand and resolve this matter.

Meeting Details:
Date & Time: {meeting_date_time}
Location: Principal's Office
Duration: 30 minutes
Attendees: Principal, Counselor, Class Teacher

Please confirm your attendance by {confirmation_date}.

Regards,
School Principal"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 7 Days for Resolution",
                step_type=WorkflowStepType.WAIT,
                order=7,
                config={"delay_hours": 168},
                next_step_id=None
            ),
            WorkflowStep(
                name="Final Check - Suspension If Unresolved",
                step_type=WorkflowStepType.ESCALATE,
                order=8,
                config={
                    "escalation_type": "suspension",
                    "condition_check": "behavior_incidents_count > 3",
                    "suspension_duration_days": 3,
                    "notify_parent": True,
                    "notify_admin": True,
                    "action": "suspend_student"
                },
                next_step_id=None
            ),
        ]
        
        for i in range(len(steps) - 1):
            steps[i].next_step_id = steps[i + 1].id
        
        definition = WorkflowDefinition(
            name="Conduct & Behavior Issue Management",
            description="Graduated escalation for student behavior problems: warning → counseling → parent meeting → suspension.",
            scenario_type="conduct",
            steps=steps,
            conditions=[],
            enabled=True
        )
        
        return definition


# ============================================================================
# SCENARIO 6: SCHOLARSHIP ELIGIBILITY REMINDERS
# ============================================================================

class ScholarshipScenario:
    """
    Pipeline for reminding eligible students about scholarship applications.
    
    Flow:
    1. Check eligibility in ERP
    2. If eligible → Send application form & details (30 days before deadline)
    3. Wait 15 days
    4. Send reminder (15 days before deadline)
    5. Wait 10 days
    6. Send URGENT (5 days before deadline)
    7. Wait 5 days
    8. Log final status after deadline
    """
    
    @staticmethod
    def create_template() -> WorkflowDefinition:
        steps = [
            WorkflowStep(
                name="Check Scholarship Eligibility",
                step_type=WorkflowStepType.QUERY_ERP,
                order=0,
                config={
                    "query_type": "scholarship_eligibility",
                    "store_result_in": "eligibility_status",
                    "criteria": ["minimum_gpa >= 3.0", "family_income < threshold"]
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Send Eligibility & Application Form",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=1,
                config={
                    "recipient_type": "student_and_parent",
                    "template_name": "scholarship_eligible",
                    "subject": "You Are Eligible for {scholarship_name} - Apply Now!",
                    "body": """Dear {student_name} and Parent,

Great news! Your child is eligible for the {scholarship_name} scholarship worth {amount}.

Scholarship Benefits:
✓ Full/Partial tuition fee waiver
✓ Academic support
✓ Mentorship program

Important Dates:
- Application Opens: {open_date}
- Deadline: {deadline}
- Results: {result_date}

Download Application: {application_link}
Required Documents: {documents_link}

Don't miss this opportunity!

Regards,
School Scholarships Team"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 15 Days",
                step_type=WorkflowStepType.WAIT,
                order=2,
                config={"delay_hours": 360},  # 15 days
                next_step_id=None
            ),
            WorkflowStep(
                name="Send Deadline Reminder (15 Days Left)",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=3,
                config={
                    "recipient_type": "student_and_parent",
                    "template_name": "scholarship_reminder_1",
                    "subject": "Reminder: {scholarship_name} Application Deadline - 15 Days Left",
                    "body": """Dear {student_name} and Parent,

Gentle reminder: The {scholarship_name} scholarship application deadline is in 15 days.

If you haven't submitted your application yet, please do so now.

Application Link: {application_link}
Deadline: {deadline}

We are here to help if you have any questions.

Best regards,
School Scholarships Team"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 10 Days",
                step_type=WorkflowStepType.WAIT,
                order=4,
                config={"delay_hours": 240},  # 10 days
                next_step_id=None
            ),
            WorkflowStep(
                name="Send URGENT Reminder (5 Days Left)",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=5,
                config={
                    "recipient_type": "student_and_parent",
                    "template_name": "scholarship_urgent",
                    "subject": "URGENT: {scholarship_name} Application - 5 Days Left to Apply!",
                    "body": """Dear {student_name} and Parent,

🚨 URGENT - Only 5 days left to submit your {scholarship_name} application!

This is your final reminder. Applications received after {deadline} will NOT be accepted.

Apply Now: {application_link}

Don't let this opportunity slip away!

Regards,
School Scholarships Team"""
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Wait 5 Days (Until Deadline)",
                step_type=WorkflowStepType.WAIT,
                order=6,
                config={"delay_hours": 120},  # 5 days
                next_step_id=None
            ),
            WorkflowStep(
                name="Check Final Submission & Log Status",
                step_type=WorkflowStepType.QUERY_ERP,
                order=7,
                config={
                    "query_type": "scholarship_applied",
                    "store_result_in": "final_application_status"
                },
                next_step_id=None
            ),
            WorkflowStep(
                name="Send Results Notification",
                step_type=WorkflowStepType.SEND_EMAIL,
                order=8,
                config={
                    "recipient_type": "student_and_parent",
                    "template_name": "scholarship_result",
                    "subject": "{scholarship_name} Application Status - {result}",
                    "body": """Dear {student_name} and Parent,

The {scholarship_name} application deadline has closed.

Your Application Status: {result}

{if_applied}
Your application has been received and is under review. Results will be announced on {result_date}.

{if_not_applied}
We noticed you did not submit an application. If you wish to apply next year, please keep an eye on our announcements.

Thank you,
School Scholarships Team"""
                },
                next_step_id=None
            ),
        ]
        
        for i in range(len(steps) - 1):
            steps[i].next_step_id = steps[i + 1].id
        
        definition = WorkflowDefinition(
            name="Scholarship Eligibility Reminders",
            description="Tracks scholarship deadlines and sends timely reminders to eligible students. Tracks final submission status.",
            scenario_type="scholarship",
            steps=steps,
            conditions=[],
            enabled=True
        )
        
        return definition


# ============================================================================
# SCENARIO REGISTRY
# ============================================================================

SCENARIO_TEMPLATES = {
    "attendance": StudentAttendanceScenario,
    "assignment": AssignmentReminderScenario,
    "fee": FeeCollectionScenario,
    "exam": ExamPrepScenario,
    "conduct": ConductIssueScenario,
    "scholarship": ScholarshipScenario,
}


def get_scenario_template(scenario_type: str) -> WorkflowDefinition:
    """Get a workflow template for a given scenario type"""
    scenario_class = SCENARIO_TEMPLATES.get(scenario_type)
    if not scenario_class:
        raise ValueError(f"Unknown scenario type: {scenario_type}")
    return scenario_class.create_template()


def list_available_scenarios():
    """List all available scenario templates"""
    return list(SCENARIO_TEMPLATES.keys())
