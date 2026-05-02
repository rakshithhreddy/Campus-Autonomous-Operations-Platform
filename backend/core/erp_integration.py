"""
ERP Integration - Mock implementation for querying student data

In production, this would connect to actual ERP systems (SAP, Oracle, custom, etc.)
For now, we provide mock data with a switch to use real ERP when available.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import random

logger = logging.getLogger(__name__)


@dataclass
class StudentData:
    """Student information from ERP"""
    student_id: str
    email: str
    name: str
    attendance_percentage: float
    parent_email: str
    parent_phone: str
    class_name: str
    gpa: float
    fee_status: str  # 'paid', 'pending', 'overdue'
    fee_amount: float
    fee_due_date: datetime


class ERPIntegration:
    """
    Mock ERP Integration
    
    Provides methods to query student data from ERP system.
    Replace mock_data methods with actual API calls when integrating with real ERP.
    """
    
    def __init__(self, use_real_erp: bool = False, erp_config: Optional[Dict[str, Any]] = None):
        self.use_real_erp = use_real_erp
        self.erp_config = erp_config or {}
        logger.info(f"ERP Integration initialized. Using real ERP: {use_real_erp}")
    
    async def get_student_data(self, student_id: str, email: str) -> Optional[StudentData]:
        """
        Get complete student data from ERP
        
        Args:
            student_id: Student ID in ERP
            email: Student email
        
        Returns:
            StudentData object or None if not found
        """
        if self.use_real_erp:
            return await self._get_from_real_erp(student_id, email)
        else:
            return self._get_mock_student_data(student_id, email)
    
    async def get_student_attendance(self, student_id: str) -> Optional[float]:
        """Get student attendance percentage"""
        student = await self.get_student_data(student_id, "")
        if student:
            return student.attendance_percentage
        return None
    
    async def get_parent_email(self, student_id: str) -> Optional[str]:
        """Get parent email for a student"""
        student = await self.get_student_data(student_id, "")
        if student:
            return student.parent_email
        return None
    
    async def check_assignment_submitted(self, student_id: str, assignment_id: str) -> bool:
        """Check if student has submitted an assignment"""
        # Mock: 60% chance of submission
        return random.random() < 0.6
    
    async def check_fee_paid(self, student_id: str) -> bool:
        """Check if student fee is paid"""
        student = await self.get_student_data(student_id, "")
        if student:
            return student.fee_status == "paid"
        return False
    
    async def get_fee_amount(self, student_id: str) -> Optional[float]:
        """Get outstanding fee amount"""
        student = await self.get_student_data(student_id, "")
        if student:
            return student.fee_amount if student.fee_status != "paid" else 0.0
        return None
    
    async def check_mock_test_attempted(self, student_id: str, exam_id: str) -> bool:
        """Check if student attempted mock test"""
        # Mock: 50% chance of attempting
        return random.random() < 0.5
    
    async def get_behavior_incidents(self, student_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get behavior/conduct incidents for student in last N days"""
        # Mock data
        incidents = []
        num_incidents = random.randint(0, 3)
        for i in range(num_incidents):
            incidents.append({
                "date": (datetime.utcnow() - timedelta(days=random.randint(1, days))).isoformat(),
                "type": random.choice(["classroom_disruption", "bullying", "late_arrival", "dress_code"]),
                "severity": random.choice(["low", "medium", "high"]),
                "description": "Mock incident for testing"
            })
        return incidents
    
    async def check_scholarship_eligibility(self, student_id: str) -> Dict[str, Any]:
        """Check scholarship eligibility for student"""
        student = await self.get_student_data(student_id, "")
        if student:
            return {
                "eligible": student.gpa >= 3.0 and student.fee_status != "pending",
                "scholarships": [
                    "merit_scholarship",
                    "need_based_scholarship"
                ],
                "criteria": {
                    "gpa_requirement_met": student.gpa >= 3.0,
                    "financial_requirement_met": student.fee_status != "pending",
                }
            }
        return {"eligible": False, "scholarships": [], "criteria": {}}
    
    # ======================================================================
    # MOCK DATA METHODS
    # ======================================================================
    
    def _get_mock_student_data(self, student_id: str, email: str) -> StudentData:
        """Return mock student data for testing"""
        logger.debug(f"Returning mock data for student {student_id}")
        
        return StudentData(
            student_id=student_id,
            email=email or f"{student_id}@school.edu",
            name=f"Student {student_id}",
            attendance_percentage=random.uniform(40, 95),
            parent_email=f"parent_{student_id}@gmail.com",
            parent_phone="+1234567890",
            class_name="10-A",
            gpa=random.uniform(2.0, 4.0),
            fee_status=random.choice(["paid", "pending", "overdue"]),
            fee_amount=random.uniform(0, 50000),
            fee_due_date=datetime.utcnow() + timedelta(days=30)
        )
    
    # ======================================================================
    # REAL ERP METHODS (Placeholder - implement with actual API)
    # ======================================================================
    
    async def _get_from_real_erp(self, student_id: str, email: str) -> Optional[StudentData]:
        """
        Fetch from real ERP system
        
        This is a placeholder. In production, implement actual API calls to:
        - SAP StudentInformation API
        - Oracle PeopleSoft Student Portal
        - Custom school ERP endpoints
        - etc.
        """
        logger.warning("Real ERP integration not implemented yet. Using mock data.")
        return self._get_mock_student_data(student_id, email)


# ============================================================================
# GLOBAL ERP INSTANCE
# ============================================================================

_erp_instance: Optional[ERPIntegration] = None


def init_erp_integration(use_real_erp: bool = False, config: Optional[Dict[str, Any]] = None):
    """Initialize global ERP integration instance"""
    global _erp_instance
    _erp_instance = ERPIntegration(use_real_erp=use_real_erp, erp_config=config)


def get_erp_integration() -> ERPIntegration:
    """Get global ERP integration instance"""
    global _erp_instance
    if _erp_instance is None:
        _erp_instance = ERPIntegration()
    return _erp_instance
