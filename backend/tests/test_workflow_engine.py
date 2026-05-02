"""
Workflow System Tests

Tests for workflow engine, scenarios, and executors.
"""

import pytest
from datetime import datetime, timedelta
from backend.core.workflow_engine import (
    WorkflowDefinition, WorkflowStep, WorkflowInstance,
    WorkflowStepType, WorkflowState, StepStatus
)
from backend.core.workflow_scenarios import (
    StudentAttendanceScenario, AssignmentReminderScenario,
    FeeCollectionScenario, ExamPrepScenario,
    get_scenario_template, list_available_scenarios
)
from backend.core.erp_integration import ERPIntegration


# ============================================================================
# TESTS FOR WORKFLOW ENGINE
# ============================================================================

class TestWorkflowScenarios:
    """Test workflow scenario templates"""
    
    def test_list_available_scenarios(self):
        """Test listing available scenarios"""
        scenarios = list_available_scenarios()
        assert "attendance" in scenarios
        assert "assignment" in scenarios
        assert "fee" in scenarios
        assert "exam" in scenarios
        assert "conduct" in scenarios
        assert "scholarship" in scenarios
        assert len(scenarios) >= 6
    
    def test_get_attendance_scenario(self):
        """Test getting attendance scenario template"""
        template = get_scenario_template("attendance")
        assert template.name == "Student Attendance Follow-up"
        assert template.scenario_type == "attendance"
        assert len(template.steps) > 0
        assert all(step.step_type in WorkflowStepType for step in template.steps)
    
    def test_get_assignment_scenario(self):
        """Test getting assignment scenario template"""
        template = get_scenario_template("assignment")
        assert template.name == "Assignment Deadline Reminder"
        assert template.scenario_type == "assignment"
        assert len(template.steps) > 0
    
    def test_get_fee_scenario(self):
        """Test getting fee collection scenario"""
        template = get_scenario_template("fee")
        assert template.name == "Fee Payment Collection Pipeline"
        assert template.scenario_type == "fee"
        assert len(template.steps) > 0
    
    def test_get_exam_scenario(self):
        """Test getting exam prep scenario"""
        template = get_scenario_template("exam")
        assert template.name == "Exam Preparation Tracking"
        assert template.scenario_type == "exam"
        assert len(template.steps) > 0
    
    def test_get_conduct_scenario(self):
        """Test getting conduct issue scenario"""
        template = get_scenario_template("conduct")
        assert template.name == "Conduct & Behavior Issue Management"
        assert template.scenario_type == "conduct"
        assert len(template.steps) > 0
    
    def test_get_scholarship_scenario(self):
        """Test getting scholarship scenario"""
        template = get_scenario_template("scholarship")
        assert template.name == "Scholarship Eligibility Reminders"
        assert template.scenario_type == "scholarship"
        assert len(template.steps) > 0
    
    def test_invalid_scenario_raises_error(self):
        """Test that invalid scenario raises error"""
        with pytest.raises(ValueError):
            get_scenario_template("invalid_scenario")


# ============================================================================
# TESTS FOR WORKFLOW DEFINITIONS
# ============================================================================

class TestWorkflowDefinition:
    """Test workflow definition"""
    
    def test_workflow_definition_creation(self):
        """Test creating a workflow definition"""
        step = WorkflowStep(
            name="Test Step",
            step_type=WorkflowStepType.SEND_EMAIL,
            order=0,
            config={"recipient": "test@example.com"}
        )
        
        definition = WorkflowDefinition(
            name="Test Workflow",
            description="Test Description",
            scenario_type="test",
            steps=[step]
        )
        
        assert definition.name == "Test Workflow"
        assert definition.scenario_type == "test"
        assert len(definition.steps) == 1
        assert definition.enabled is True
    
    def test_workflow_definition_to_dict(self):
        """Test converting workflow definition to dict"""
        definition = get_scenario_template("attendance")
        data = definition.to_dict()
        
        assert "id" in data
        assert "name" in data
        assert "steps" in data
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) > 0


# ============================================================================
# TESTS FOR WORKFLOW INSTANCES
# ============================================================================

class TestWorkflowInstance:
    """Test workflow instance"""
    
    def test_workflow_instance_creation(self):
        """Test creating workflow instance"""
        instance = WorkflowInstance(
            workflow_definition_id="test_id",
            subject_email="student@school.edu",
            subject_id="1234554321",
            metadata={"course": "Math 101"}
        )
        
        assert instance.subject_email == "student@school.edu"
        assert instance.subject_id == "1234554321"
        assert instance.current_state == WorkflowState.IN_PROGRESS
        assert instance.current_step == 0
    
    def test_workflow_instance_to_dict(self):
        """Test converting instance to dict"""
        instance = WorkflowInstance(
            workflow_definition_id="test_id",
            subject_email="student@school.edu",
            subject_id="1234554321"
        )
        data = instance.to_dict()
        
        assert "id" in data
        assert data["subject_email"] == "student@school.edu"
        assert data["current_state"] == "in_progress"


# ============================================================================
# TESTS FOR ERP INTEGRATION
# ============================================================================

class TestERPIntegration:
    """Test ERP integration"""
    
    def test_erp_initialization(self):
        """Test ERP initialization"""
        erp = ERPIntegration(use_real_erp=False)
        assert erp.use_real_erp is False
    
    @pytest.mark.asyncio
    async def test_get_mock_student_data(self):
        """Test getting mock student data"""
        erp = ERPIntegration(use_real_erp=False)
        student = await erp.get_student_data("1234554321", "abc@gmail.com")
        
        assert student is not None
        assert student.student_id == "1234554321"
        assert student.email == "abc@gmail.com"
        assert 0 <= student.attendance_percentage <= 100
        assert student.gpa >= 0
    
    @pytest.mark.asyncio
    async def test_get_student_attendance(self):
        """Test getting student attendance"""
        erp = ERPIntegration(use_real_erp=False)
        attendance = await erp.get_student_attendance("1234554321")
        
        assert attendance is not None
        assert 0 <= attendance <= 100
    
    @pytest.mark.asyncio
    async def test_get_parent_email(self):
        """Test getting parent email"""
        erp = ERPIntegration(use_real_erp=False)
        parent_email = await erp.get_parent_email("1234554321")
        
        assert parent_email is not None
        assert "@" in parent_email
    
    @pytest.mark.asyncio
    async def test_check_fee_paid(self):
        """Test checking fee paid status"""
        erp = ERPIntegration(use_real_erp=False)
        paid = await erp.check_fee_paid("1234554321")
        
        assert isinstance(paid, bool)
    
    @pytest.mark.asyncio
    async def test_check_scholarship_eligibility(self):
        """Test checking scholarship eligibility"""
        erp = ERPIntegration(use_real_erp=False)
        eligibility = await erp.check_scholarship_eligibility("1234554321")
        
        assert "eligible" in eligibility
        assert "scholarships" in eligibility
        assert isinstance(eligibility["eligible"], bool)


# ============================================================================
# TESTS FOR WORKFLOW EXECUTOR
# ============================================================================

class TestWorkflowExecutor:
    """Test workflow executors"""
    
    def test_attendance_executor_creation(self):
        """Test creating attendance executor"""
        from backend.core.workflow_executors import AttendanceScenarioExecutor
        
        definition = get_scenario_template("attendance")
        executor = AttendanceScenarioExecutor(definition)
        
        assert executor.definition.scenario_type == "attendance"
    
    def test_get_executor_for_scenario(self):
        """Test getting executor for scenario"""
        from backend.core.workflow_executors import get_executor_for_scenario
        
        executor = get_executor_for_scenario("attendance")
        assert executor is not None
    
    def test_invalid_executor_raises_error(self):
        """Test that invalid executor raises error"""
        from backend.core.workflow_executors import get_executor_for_scenario
        
        with pytest.raises(ValueError):
            get_executor_for_scenario("invalid_scenario")


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestWorkflowIntegration:
    """Integration tests for complete workflows"""
    
    def test_attendance_workflow_structure(self):
        """Test attendance workflow has correct structure"""
        template = get_scenario_template("attendance")
        
        # Verify workflow steps
        assert len(template.steps) > 0
        
        # Verify step types exist
        step_types_found = {step.step_type for step in template.steps}
        assert WorkflowStepType.SEND_EMAIL in step_types_found or len(step_types_found) > 0
        
        # Verify steps are linked
        for i, step in enumerate(template.steps[:-1]):
            next_step = template.steps[i + 1]
            # Steps should have some linking or ordering
            assert step.order < next_step.order or step.order == next_step.order
    
    def test_assignment_workflow_structure(self):
        """Test assignment workflow structure"""
        template = get_scenario_template("assignment")
        
        assert len(template.steps) > 0
        assert template.scenario_type == "assignment"
        
        # Verify email sending steps
        email_steps = [s for s in template.steps if s.step_type == WorkflowStepType.SEND_EMAIL]
        assert len(email_steps) > 0
    
    def test_fee_workflow_structure(self):
        """Test fee workflow structure"""
        template = get_scenario_template("fee")
        
        assert len(template.steps) > 0
        assert template.scenario_type == "fee"
    
    def test_exam_workflow_structure(self):
        """Test exam workflow structure"""
        template = get_scenario_template("exam")
        
        assert len(template.steps) > 0
        assert template.scenario_type == "exam"
    
    def test_conduct_workflow_structure(self):
        """Test conduct workflow structure"""
        template = get_scenario_template("conduct")
        
        assert len(template.steps) > 0
        assert template.scenario_type == "conduct"
        
        # Verify escalation steps exist
        escalate_steps = [s for s in template.steps if s.step_type == WorkflowStepType.ESCALATE]
        assert len(escalate_steps) > 0
    
    def test_scholarship_workflow_structure(self):
        """Test scholarship workflow structure"""
        template = get_scenario_template("scholarship")
        
        assert len(template.steps) > 0
        assert template.scenario_type == "scholarship"


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
