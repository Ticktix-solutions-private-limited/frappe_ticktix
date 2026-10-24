"""
Attendance Class Override

Overrides the HRMS Attendance class to support custom attendance status options.
This replaces the hardcoded status validation with a dynamic list.

Custom Statuses:
- Present (standard)
- Absent (standard)
- On Leave (standard)
- Half Day (standard)
- Work From Home (standard)
- Weekly Off (custom - company-assigned weekly off)
- Client Day Off (custom - client-requested day off)
- Holiday (custom - from Holiday List)
- On Hold (custom - pending client approval)
"""

import frappe
from frappe import _
from frappe.utils import getdate, get_link_to_form
from erpnext.controllers.status_updater import validate_status

# Import the original Attendance class from HRMS
from hrms.hr.doctype.attendance.attendance import Attendance

from frappe_ticktix.plugins.hr.attendance.attendance_status_override import get_attendance_status_options


class CustomAttendance(Attendance):
    """
    Custom Attendance class that extends HRMS Attendance.
    Overrides the validate method to use custom status options.
    """
    
    def validate(self):
        """
        Override validate to use custom attendance status options.
        Replaces the hardcoded status list with our dynamic list.
        """
        from hrms.hr.utils import validate_active_employee
        
        # Use our extended status list instead of hardcoded list
        allowed_statuses = get_attendance_status_options()
        validate_status(self.status, allowed_statuses)
        
        # Call the parent class's other validation methods (these are instance methods)
        validate_active_employee(self.employee)
        self.validate_attendance_date()
        self.validate_duplicate_record()
        self.validate_overlapping_shift_attendance()
        self.validate_employee_status()
        self.check_leave_record()
