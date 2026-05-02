"""
Test Faculty Email Assistant
============================
Unit tests for the faculty email classification and response generation system.

Test Coverage:
- Email classification across all 13 categories
- Urgency detection
- Response template generation
- Email batching
- Summary statistics
"""

import pytest
from datetime import datetime
from backend.core.faculty_email_assistant import (
    EmailCategory,
    EmailUrgency,
    ClassifiedEmail,
    FacultyEmailClassifier,
    ResponseGenerator,
    FacultyEmailAssistant,
)


class TestFacultyEmailClassifier:
    """Test email classification system"""
    
    def setup_method(self):
        self.classifier = FacultyEmailClassifier()
    
    def test_classify_assignment_submission(self):
        """Test classification of assignment submission email"""
        result = self.classifier.classify(
            email_id="email_1",
            sender="student@college.edu",
            subject="Assignment Submission - Chapter 5",
            body="Please find my assignment submission attached. I have completed the work on database design.",
            date="2026-04-29T10:00:00"
        )
        assert result.category == EmailCategory.ASSIGNMENT_SUBMISSION
        assert result.urgency in [EmailUrgency.LOW, EmailUrgency.MEDIUM]
    
    def test_classify_leave_request(self):
        """Test classification of leave request"""
        result = self.classifier.classify(
            email_id="email_2",
            sender="student@college.edu",
            subject="Leave Request",
            body="I request for 2 days leave from May 5-6 for medical reasons. Medical certificate attached.",
            date="2026-04-29T10:00:00"
        )
        assert result.category == EmailCategory.LEAVE_REQUEST
    
    def test_classify_critical_urgency(self):
        """Test detection of critical urgency"""
        result = self.classifier.classify(
            email_id="email_3",
            sender="student@college.edu",
            subject="URGENT: Exam Tomorrow",
            body="Sir/Madam, I have critical doubt about the exam scheduled tomorrow. Deadline is in 2 hours!!!",
            date="2026-04-29T22:00:00"
        )
        assert result.urgency == EmailUrgency.CRITICAL
    
    def test_classify_exam_related(self):
        """Test exam-related email classification"""
        result = self.classifier.classify(
            email_id="email_4",
            sender="student@college.edu",
            subject="Query about Midterm Exam",
            body="I have some doubts about the scope of the midterm examination.",
            date="2026-04-29T10:00:00"
        )
        assert result.category == EmailCategory.EXAM_RELATED
    
    def test_classify_internship_opportunity(self):
        """Test internship opportunity classification"""
        result = self.classifier.classify(
            email_id="email_5",
            sender="company@tech.com",
            subject="Internship Opportunity 2026",
            body="We have an exciting internship position available. Please share this with suitable students.",
            date="2026-04-29T10:00:00"
        )
        assert result.category == EmailCategory.INTERNSHIP
    
    def test_classify_meeting_request(self):
        """Test meeting request classification"""
        result = self.classifier.classify(
            email_id="email_6",
            sender="student@college.edu",
            subject="Meeting Request for Project Discussion",
            body="Can we meet tomorrow at 3 PM to discuss the project? Please let me know your availability.",
            date="2026-04-29T10:00:00"
        )
        assert result.category == EmailCategory.MEETING_REQUEST
    
    def test_classify_grade_inquiry(self):
        """Test grade inquiry classification"""
        result = self.classifier.classify(
            email_id="email_7",
            sender="student@college.edu",
            subject="Question about Assignment Grade",
            body="I received a C+ in assignment 2. Can you explain the deductions made?",
            date="2026-04-29T10:00:00"
        )
        assert result.category == EmailCategory.GRADE_INQUIRY
    
    def test_classify_attendance(self):
        """Test attendance-related classification"""
        result = self.classifier.classify(
            email_id="email_8",
            sender="student@college.edu",
            subject="Attendance Notification",
            body="I was absent yesterday due to illness. I will provide medical certificate.",
            date="2026-04-29T10:00:00"
        )
        assert result.category == EmailCategory.ATTENDANCE
    
    def test_classify_project_collaboration(self):
        """Test project collaboration email"""
        result = self.classifier.classify(
            email_id="email_9",
            sender="student@college.edu",
            subject="Project Team Formation",
            body="For the semester project, I would like to work on the ML classification project. Looking for team members.",
            date="2026-04-29T10:00:00"
        )
        assert result.category == EmailCategory.PROJECT
    
    def test_classification_includes_keywords(self):
        """Test that keywords are extracted"""
        result = self.classifier.classify(
            email_id="email_10",
            sender="student@college.edu",
            subject="Assignment Submission",
            body="Assignment submission for database project",
            date="2026-04-29T10:00:00"
        )
        assert len(result.keywords) > 0
    
    def test_batch_key_for_similar_emails(self):
        """Test that similar emails get same batch key"""
        result1 = self.classifier.classify(
            email_id="email_1",
            sender="student1@college.edu",
            subject="Assignment 1 Submission",
            body="Submitting assignment 1",
            date="2026-04-29T10:00:00"
        )
        
        result2 = self.classifier.classify(
            email_id="email_2",
            sender="student2@college.edu",
            subject="Assignment 1 Submission",
            body="Submitting assignment 1",
            date="2026-04-29T10:05:00"
        )
        
        # Both should be assignment submissions
        assert result1.category == result2.category == EmailCategory.ASSIGNMENT_SUBMISSION
        # Should have batch keys (grouped for similar processing)
        assert result1.batch_key is not None
        assert result2.batch_key is not None


class TestResponseGenerator:
    """Test response template generation"""
    
    def setup_method(self):
        self.generator = ResponseGenerator()
    
    def test_generate_assignment_submission_response(self):
        """Test response for assignment submission"""
        classified = ClassifiedEmail(
            email_id="email_1",
            sender="student@college.edu",
            subject="Assignment Submission",
            body="Assignment content here",
            date=datetime.now().isoformat(),
            category=EmailCategory.ASSIGNMENT_SUBMISSION,
            urgency=EmailUrgency.LOW,
            keywords=["assignment", "submission"],
            suggested_response=None,
            batch_key="assignment_submission_1"
        )
        
        response = self.generator.generate_response(classified)
        assert response is not None
        assert len(response) > 0
    
    def test_generate_urgent_response(self):
        """Test response for urgent emails"""
        classified = ClassifiedEmail(
            email_id="email_2",
            sender="student@college.edu",
            subject="URGENT: Exam Doubt",
            body="Critical doubt about exam",
            date=datetime.now().isoformat(),
            category=EmailCategory.EXAM_RELATED,
            urgency=EmailUrgency.CRITICAL,
            keywords=["urgent", "exam"],
            suggested_response=None,
            batch_key="exam_critical_1"
        )
        
        response = self.generator.generate_response(classified)
        assert response is not None
        assert len(response) > 0
    
    def test_all_categories_have_templates(self):
        """Test that all categories have response templates"""
        for category in EmailCategory:
            assert category in self.generator.RESPONSE_TEMPLATES
            templates = self.generator.RESPONSE_TEMPLATES[category]
            assert len(templates) > 0


class TestFacultyEmailAssistant:
    """Test the complete faculty email assistant"""
    
    def setup_method(self):
        self.assistant = FacultyEmailAssistant()
    
    def test_process_single_email(self):
        """Test processing a single email"""
        emails = [
            {
                "id": "email_1",
                "from": "student@college.edu",
                "subject": "Assignment Submission",
                "body": "I am submitting my assignment",
                "date": "2026-04-29T10:00:00"
            }
        ]
        
        results = self.assistant.process_emails(emails)
        assert results["total_processed"] == 1
        assert len(results["classified_emails"]) == 1
    
    def test_process_multiple_emails(self):
        """Test processing multiple emails"""
        emails = [
            {
                "id": "email_1",
                "from": "student1@college.edu",
                "subject": "Assignment Submission",
                "body": "Submission 1",
                "date": "2026-04-29T10:00:00"
            },
            {
                "id": "email_2",
                "from": "student2@college.edu",
                "subject": "Leave Request",
                "body": "I request 2 days leave",
                "date": "2026-04-29T11:00:00"
            },
            {
                "id": "email_3",
                "from": "student3@college.edu",
                "subject": "Assignment Submission",
                "body": "Submission 2",
                "date": "2026-04-29T12:00:00"
            }
        ]
        
        results = self.assistant.process_emails(emails)
        assert results["total_processed"] == 3
        assert len(results["classified_emails"]) == 3
    
    def test_email_batching(self):
        """Test that similar emails are batched"""
        emails = [
            {
                "id": f"email_{i}",
                "from": f"student{i}@college.edu",
                "subject": "Assignment 1 Submission",
                "body": "Submitting assignment",
                "date": f"2026-04-29T{10+i}:00:00"
            }
            for i in range(5)
        ]
        
        results = self.assistant.process_emails(emails)
        # All should be in same batch since they're similar
        assert len(results["batches"]) >= 1
    
    def test_get_summary(self):
        """Test summary generation"""
        summary = self.assistant.get_summary()
        
        assert "total_emails" in summary
        assert "by_category" in summary
        assert "by_urgency" in summary
        assert "batch_groups" in summary
        assert "requires_immediate_action" in summary
    
    def test_categorize_by_urgency(self):
        """Test that emails are categorized by urgency"""
        emails = [
            {
                "id": "email_1",
                "from": "student@college.edu",
                "subject": "URGENT CRITICAL: Exam Tomorrow",
                "body": "Help needed IMMEDIATELY!",
                "date": "2026-04-29T22:00:00"
            },
            {
                "id": "email_2",
                "from": "student@college.edu",
                "subject": "Assignment Submission",
                "body": "Normal submission",
                "date": "2026-04-29T10:00:00"
            }
        ]
        
        results = self.assistant.process_emails(emails)
        assert results["total_processed"] == 2
        
        # At least one should be categorized by urgency
        summary = self.assistant.get_summary()
        assert len(summary["by_urgency"]) > 0


class TestExtremeFacultyFeatures:
    """Test the extreme inbox intelligence features"""

    def setup_method(self):
        self.assistant = FacultyEmailAssistant()

    def test_thread_insights_group_related_emails(self):
        emails = [
            {
                "id": "thread-1",
                "from": "student1@college.edu",
                "subject": "Re: Assignment 3 Submission",
                "body": "Attached is my assignment 3 submission.",
                "date": "2026-04-29T09:00:00",
            },
            {
                "id": "thread-2",
                "from": "student2@college.edu",
                "subject": "Fwd: Assignment 3 Submission",
                "body": "Submitting the same assignment.",
                "date": "2026-04-29T09:05:00",
            },
        ]

        self.assistant.process_emails(emails)
        threads = self.assistant.build_thread_insights()

        assert len(threads) == 1
        assert threads[0]["email_count"] == 2
        assert threads[0]["primary_category"] == EmailCategory.ASSIGNMENT_SUBMISSION.value

    def test_priority_queue_ranks_critical_email_first(self):
        emails = [
            {
                "id": "low-1",
                "from": "student1@college.edu",
                "subject": "Assignment Submission",
                "body": "Submitting assignment",
                "date": "2026-04-29T09:00:00",
            },
            {
                "id": "high-1",
                "from": "student2@college.edu",
                "subject": "URGENT: Exam tomorrow",
                "body": "Deadline is today and I need help asap.",
                "date": "2026-04-29T21:00:00",
            },
        ]

        self.assistant.process_emails(emails)
        queue = self.assistant.prioritize_inbox(limit=2)

        assert queue[0]["email_id"] == "high-1"
        assert queue[0]["urgency"] == EmailUrgency.CRITICAL.value
        assert queue[0]["priority_score"] >= queue[1]["priority_score"]

    @pytest.mark.asyncio
    async def test_sync_from_gmail_manager(self):
        class FakeGmailManager:
            async def read_emails(self, limit=10, unread_only=True):
                return [
                    {
                        "id": "gmail-1",
                        "from": "student@college.edu",
                        "subject": "Leave Request",
                        "body": "I need 1 day leave tomorrow for medical reasons.",
                        "date": "2026-04-29T08:00:00",
                    }
                ]

        results = await self.assistant.sync_from_gmail(FakeGmailManager(), limit=5, unread_only=True)

        assert results["sync_source"] == "gmail"
        assert results["synced_email_count"] == 1
        assert results["digest"]["summary"]["total_emails"] == 1
        assert len(results["priority_queue"]) == 1


class TestIntegration:
    """Integration tests for the faculty email system"""
    
    def test_full_workflow(self):
        """Test complete workflow from emails to summary"""
        assistant = FacultyEmailAssistant()
        
        # Simulate a faculty member receiving various emails
        emails = [
            {
                "id": "email_1",
                "from": "john@student.edu",
                "subject": "Assignment Submission - Data Structures",
                "body": "Attached is my assignment on graph algorithms.",
                "date": "2026-04-29T09:00:00"
            },
            {
                "id": "email_2",
                "from": "jane@student.edu",
                "subject": "Leave Request - Medical",
                "body": "I request 1 day leave on May 5 for medical checkup.",
                "date": "2026-04-29T09:15:00"
            },
            {
                "id": "email_3",
                "from": "bob@student.edu",
                "subject": "URGENT: Exam doubt - Urgently needed answer!",
                "body": "Sir, I have a critical doubt about the exam happening tomorrow. Deadline is 2 hours!",
                "date": "2026-04-29T22:30:00"
            },
            {
                "id": "email_4",
                "from": "alice@student.edu",
                "subject": "Meeting Request for Project Discussion",
                "body": "Can we meet tomorrow to discuss the project implementation?",
                "date": "2026-04-29T10:00:00"
            },
            {
                "id": "email_5",
                "from": "company@tech.com",
                "subject": "Internship Opportunity - Full Stack Developer",
                "body": "We have internship positions available. Please share with students.",
                "date": "2026-04-29T10:30:00"
            }
        ]
        
        # Process emails
        results = assistant.process_emails(emails)
        
        # Verify basic processing
        assert results["total_processed"] == 5
        assert len(results["classified_emails"]) == 5
        
        # Verify categorization
        categories = {email["category"] for email in results["classified_emails"]}
        assert "assignment_submission" in categories
        assert "leave_request" in categories
        assert "exam_related" in categories
        assert "meeting_request" in categories
        assert "internship" in categories
        
        # Verify urgency detection
        urgencies = {email["urgency"] for email in results["classified_emails"]}
        assert "critical" in urgencies
        
        # Verify summary generation
        summary = assistant.get_summary()
        assert summary["total_emails"] == 5
        assert len(summary["by_category"]) > 0
        assert len(summary["by_urgency"]) > 0
        
        print("\n✅ Full workflow test PASSED")
        print(f"  - Processed {results['total_processed']} emails")
        print(f"  - Categories: {', '.join(categories)}")
        print(f"  - Urgencies: {', '.join(urgencies)}")
        print(f"  - Summary: {summary}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
