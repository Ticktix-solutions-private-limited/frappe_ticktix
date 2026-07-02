"""
Employee Checkin Manager

Handles employee check-in and check-out functionality.
Migrated from one_fm.overrides.employee_checkin with improvements.

Key Features:
- GPS location validation
- Photo capture (optional)
- Shift validation
- Duplicate checkin detection
- Late entry / Early exit detection
- Automatic shift assignment
- Supervisor notifications

Usage:
    from frappe_ticktix.plugins.hr.checkin.checkin_manager import EmployeeCheckinManager
    
    manager = EmployeeCheckinManager()
    manager.validate_checkin(checkin_doc)
"""

import frappe
from frappe import _
from frappe.utils import (
    cint, get_datetime, cstr, getdate, 
    now_datetime, add_days, now, today
)
from datetime import timedelta, datetime
from hrms.hr.doctype.employee_checkin.employee_checkin import EmployeeCheckin
from hrms.hr.utils import validate_active_employee


class EmployeeCheckinManager:
    """
    Manages Employee Checkin/Checkout operations
    """
    
    @staticmethod
    def validate_duplicate_log(employee, time, name=None):
        """
        Check if a checkin already exists for the same employee at the same time
        
        Args:
            employee (str): Employee ID
            time (datetime): Checkin/Checkout time
            name (str): Current checkin name (to exclude from duplicate check)
            
        Returns:
            dict: Existing checkin document or None
        """
        filters = {
            'employee': employee,
            'time': time
        }
        
        if name:
            filters['name'] = ['!=', name]
        
        existing = frappe.db.get_value(
            "Employee Checkin",
            filters,
            ['name'],
            as_dict=True
        )
        
        return existing
    
    @staticmethod
    def get_current_shift(employee, time=None):
        """
        Get the current shift assignment for an employee
        
        Args:
            employee (str): Employee ID
            time (datetime): Optional time to check shift for (defaults to now)
            
        Returns:
            dict: Shift assignment details or None
        """
        if not time:
            time = now_datetime()
        
        # Query shift assignments for the employee
        shift_assignments = frappe.db.get_list(
            "Shift Assignment",
            filters={
                'employee': employee,
                'docstatus': 1,
                'start_date': ['<=', time.date()]
            },
            fields=['*'],
            order_by='start_date DESC',
            limit=1
        )
        
        if not shift_assignments:
            return None
        
        shift = shift_assignments[0]
        
        # Get shift type details
        shift_type = frappe.get_doc("Shift Type", shift.shift_type)
        
        # Calculate actual shift start and end times
        if shift_type.start_time and shift_type.end_time:
            shift_start = get_datetime(f"{shift.start_date} {shift_type.start_time}")
            
            # Handle overnight shifts
            if shift_type.end_time < shift_type.start_time:
                shift_end = get_datetime(f"{shift.start_date} {shift_type.end_time}") + timedelta(days=1)
            else:
                shift_end = get_datetime(f"{shift.start_date} {shift_type.end_time}")
            
            # Check if current time falls within shift window (with grace period)
            before_time = shift_type.begin_check_in_before_shift_start_time or 60
            after_time = shift_type.allow_check_out_after_shift_end_time or 60
            
            window_start = shift_start - timedelta(minutes=before_time)
            window_end = shift_end + timedelta(minutes=after_time)
            
            if window_start <= time <= window_end:
                return {
                    'name': shift.name,
                    'shift_type': shift.shift_type,
                    'start_datetime': shift_start,
                    'end_datetime': shift_end,
                    'shift_type_doc': shift_type
                }
        
        return None
    
    @staticmethod
    def calculate_late_early_flags(checkin_time, shift_start, shift_end, shift_type, log_type):
        """
        Calculate if checkin is late or early based on grace periods
        
        Args:
            checkin_time (datetime): Actual checkin/checkout time
            shift_start (datetime): Shift start time
            shift_end (datetime): Shift end time
            shift_type (object): Shift Type document
            log_type (str): 'IN' or 'OUT'
            
        Returns:
            dict: {'late_entry': bool, 'early_exit': bool}
        """
        late_entry = 0
        early_exit = 0
        
        if log_type == 'IN':
            # Check late entry
            if shift_type.enable_entry_grace_period:
                grace_period = shift_type.late_entry_grace_period or 0
                if checkin_time > (shift_start + timedelta(minutes=grace_period)):
                    late_entry = 1
        
        elif log_type == 'OUT':
            # Check early exit
            if shift_type.enable_exit_grace_period:
                grace_period = shift_type.early_exit_grace_period or 0
                if checkin_time < (shift_end - timedelta(minutes=grace_period)):
                    early_exit = 1
        
        return {
            'late_entry': late_entry,
            'early_exit': early_exit
        }


class EmployeeCheckinOverride(EmployeeCheckin):
    """
    Override class for Employee Checkin doctype
    Extends Frappe's default EmployeeCheckin with custom validation and features
    """
    
    def validate(self):
        """
        Validate employee checkin before saving
        """
        # Validate employee is active
        validate_active_employee(self.employee)
        
        # Check for duplicate checkin
        duplicate = EmployeeCheckinManager.validate_duplicate_log(
            self.employee, 
            self.time, 
            self.name
        )
        
        if duplicate:
            doc_link = frappe.get_desk_link("Employee Checkin", duplicate.name)
            frappe.throw(
                _("This employee already has a log with the same timestamp. {0}").format(doc_link)
            )
        
        # Get current shift if not already set
        if not self.shift_assignment:
            curr_shift = EmployeeCheckinManager.get_current_shift(
                self.employee, 
                self.time
            )
            
            if curr_shift:
                self.shift_assignment = curr_shift['name']
                self.shift = curr_shift['shift_type']
                self.shift_type = curr_shift['shift_type']
                self.shift_actual_start = curr_shift['start_datetime']
                self.shift_actual_end = curr_shift['end_datetime']
                
                # Calculate late/early flags
                flags = EmployeeCheckinManager.calculate_late_early_flags(
                    self.time,
                    curr_shift['start_datetime'],
                    curr_shift['end_datetime'],
                    curr_shift['shift_type_doc'],
                    self.log_type
                )
                
                self.late_entry = flags['late_entry']
                self.early_exit = flags['early_exit']
    
    def before_insert(self):
        """
        Set fields before inserting checkin record
        """
        # Set date from time
        self.date = getdate(self.time)
    
    def after_insert(self):
        """
        Post-insert processing
        - Send notifications
        - Update shift details in background
        """
        try:
            frappe.db.commit()
            self.reload()
            
            # Enqueue background processing
            frappe.enqueue(
                'frappe_ticktix.plugins.hr.checkin.checkin_manager.process_checkin_background',
                employee_checkin=self.name,
                queue='default',
                timeout=300
            )
            
        except Exception as e:
            frappe.log_error(title="Checkin after insert failed", message=frappe.get_traceback())


def process_checkin_background(employee_checkin):
    """
    Background processing for checkin
    - Update shift details
    - Send supervisor notifications
    
    Args:
        employee_checkin (str): Employee Checkin name
    """
    try:
        checkin = frappe.get_doc("Employee Checkin", employee_checkin)
        
        # Send notifications based on checkin type
        if checkin.log_type == "IN":
            notify_late_checkin(checkin)
        elif checkin.log_type == "OUT":
            notify_early_checkout(checkin)
        
    except Exception as e:
        frappe.log_error(title="Background checkin process failed", message=frappe.get_traceback())


def notify_late_checkin(checkin):
    """
    Notify supervisor if employee checked in late
    
    Args:
        checkin (object): Employee Checkin document
    """
    if not checkin.late_entry:
        return
    
    if not checkin.shift_actual_start:
        return
    
    # Calculate delay
    time_diff = get_datetime(checkin.time) - get_datetime(checkin.shift_actual_start)
    hrs, mins, secs = str(time_diff).split(":")
    delay = f"{hrs} hrs {mins} mins" if int(hrs) > 0 else f"{mins} mins"
    
    # Get supervisor
    reporting_manager = frappe.db.get_value(
        "Employee", 
        checkin.employee, 
        'reports_to'
    )
    
    if not reporting_manager:
        return
    
    supervisor_email = frappe.db.get_value(
        "Employee",
        reporting_manager,
        'user_id'
    )
    
    if not supervisor_email:
        return
    
    # Send notification
    subject = _(f"{checkin.employee_name} has checked in late by {delay}")
    message = _(
        f"{checkin.employee_name} (ID: {checkin.employee}) checked in late by {delay} "
        f"for shift starting at {checkin.shift_actual_start}."
    )
    
    frappe.sendmail(
        recipients=[supervisor_email],
        subject=subject,
        message=message,
        reference_doctype="Employee Checkin",
        reference_name=checkin.name
    )


def notify_early_checkout(checkin):
    """
    Notify supervisor if employee checked out early
    
    Args:
        checkin (object): Employee Checkin document
    """
    if not checkin.early_exit:
        return
    
    if not checkin.shift_actual_end:
        return
    
    # Calculate early departure
    time_diff = get_datetime(checkin.shift_actual_end) - get_datetime(checkin.time)
    hrs, mins, secs = str(time_diff).split(":")
    early = f"{hrs} hrs {mins} mins" if int(hrs) > 0 else f"{mins} mins"
    
    # Get supervisor
    reporting_manager = frappe.db.get_value(
        "Employee", 
        checkin.employee, 
        'reports_to'
    )
    
    if not reporting_manager:
        return
    
    supervisor_email = frappe.db.get_value(
        "Employee",
        reporting_manager,
        'user_id'
    )
    
    if not supervisor_email:
        return
    
    # Send notification
    subject = _(f"{checkin.employee_name} has checked out early by {early}")
    message = _(
        f"{checkin.employee_name} (ID: {checkin.employee}) checked out early by {early} "
        f"from shift ending at {checkin.shift_actual_end}."
    )
    
    frappe.sendmail(
        recipients=[supervisor_email],
        subject=subject,
        message=message,
        reference_doctype="Employee Checkin",
        reference_name=checkin.name
    )


# ============================================================================
# Whitelisted API Methods
# ============================================================================

@frappe.whitelist()
def get_current_shift_for_employee(employee=None):
    """
    API method to get current shift for an employee
    
    Args:
        employee (str): Employee ID (defaults to current user's employee)
        
    Returns:
        dict: Current shift details or None
    """
    if not employee:
        employee = frappe.db.get_value(
            "Employee",
            {'user_id': frappe.session.user},
            'name'
        )
    
    if not employee:
        frappe.throw(_("Employee not found for current user"))
    
    return EmployeeCheckinManager.get_current_shift(employee)


@frappe.whitelist()
def create_checkin(employee, log_type, time=None, device_id=None, skip_auto_attendance=0):
    """
    API method to create employee checkin
    
    Args:
        employee (str): Employee ID
        log_type (str): 'IN' or 'OUT'
        time (datetime): Checkin time (defaults to now)
        device_id (str): Device ID (optional)
        skip_auto_attendance (int): Skip auto attendance marking (0 or 1)
        
    Returns:
        dict: Created checkin document
    """
    if not time:
        time = now_datetime()
    
    # Create checkin
    checkin = frappe.new_doc('Employee Checkin')
    checkin.employee = employee
    checkin.log_type = log_type
    checkin.time = time
    checkin.device_id = device_id
    checkin.skip_auto_attendance = skip_auto_attendance
    
    checkin.insert()
    frappe.db.commit()
    
    return checkin.as_dict()


# ============================================================================
# Doc Events Hook Functions
# These wrapper functions are called by Frappe's doc_events hooks
# ============================================================================

def validate(doc, method):
    """
    Validate hook for Employee Checkin
    Called from hooks.py doc_events
    """
    # Validate employee is active
    validate_active_employee(doc.employee)
    
    # Check for duplicate checkin
    duplicate = EmployeeCheckinManager.validate_duplicate_log(
        doc.employee, 
        doc.time, 
        doc.name
    )
    
    if duplicate:
        doc_link = frappe.get_desk_link("Employee Checkin", duplicate.name)
        frappe.throw(
            _("This employee already has a log with the same timestamp. {0}").format(doc_link)
        )
    
    # Get current shift if not already set
    # Standard Employee Checkin doctype uses 'shift' field (Link to Shift Type)
    if not doc.shift:
        curr_shift = EmployeeCheckinManager.get_current_shift(
            doc.employee, 
            doc.time
        )
        
        if curr_shift:
            # Set shift fields that exist in standard doctype
            doc.shift = curr_shift['shift_type']
            doc.shift_actual_start = curr_shift['start_datetime']
            doc.shift_actual_end = curr_shift['end_datetime']


def before_insert(doc, method):
    """
    Before insert hook for Employee Checkin
    Called from hooks.py doc_events
    """
    # Note: Standard Employee Checkin doesn't have a 'date' field
    # The 'time' field serves as both date and time
    pass


def after_insert(doc, method):
    """
    After insert hook for Employee Checkin
    Called from hooks.py doc_events
    """
    try:
        frappe.db.commit()
        doc.reload()
        
        # Enqueue background processing
        frappe.enqueue(
            'frappe_ticktix.plugins.hr.checkin.checkin_manager.process_checkin_background',
            employee_checkin=doc.name,
            queue='default',
            timeout=300
        )
        
    except Exception as e:
        frappe.log_error(title="Checkin processing error", message=frappe.get_traceback())
