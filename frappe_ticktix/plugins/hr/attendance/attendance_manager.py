"""
Attendance Manager

Handles employee attendance tracking and validation.
Migrated from one_fm.overrides.attendance with improvements.

Key Features:
- Attendance validation (duplicates, overlaps)
- Auto-attendance marking from checkins
- Multiple status support (Present, Absent, Leave, Holiday, Day Off, etc.)
- Working hours calculation
- Integration with shift assignments
- Leave and holiday detection

Usage:
    from frappe_ticktix.plugins.hr.attendance.attendance_manager import AttendanceManager
    
    manager = AttendanceManager()
    manager.mark_attendance(employee, date, status)
"""

import frappe
from frappe import _
from frappe.utils import (
    getdate, get_datetime, cint, add_to_date,
    datetime, today, add_days, now_datetime
)
from datetime import timedelta
from hrms.hr.doctype.attendance.attendance import Attendance
from hrms.hr.utils import validate_active_employee, get_holidays_for_employee


class AttendanceManager:
    """
    Manages Employee Attendance operations
    """
    
    @staticmethod
    def get_duplicate_attendance(employee, attendance_date, shift=None, roster_type="Basic", name=None):
        """
        Check for duplicate attendance records
        
        Args:
            employee (str): Employee ID
            attendance_date (date): Attendance date
            shift (str): Shift Type (optional)
            roster_type (str): Roster Type (Basic/Over-Time)
            name (str): Current attendance name to exclude
            
        Returns:
            list: List of duplicate attendance records
        """
        filters = {
            'employee': employee,
            'attendance_date': attendance_date,
            'roster_type': roster_type,
            'docstatus': 1
        }
        
        if shift:
            filters['shift'] = shift
        
        if name:
            filters['name'] = ['!=', name]
        
        duplicates = frappe.db.get_list(
            "Attendance",
            filters=filters,
            fields=['name', 'shift', 'status', 'working_hours', 'roster_type']
        )
        
        return duplicates
    
    @staticmethod
    def get_overlapping_shift_attendance(employee, attendance_date, shift, roster_type="Basic", name=None):
        """
        Check for overlapping shift attendance records
        Used when employee has multiple shifts in same day
        
        Args:
            employee (str): Employee ID
            attendance_date (date): Attendance date
            shift (str): Shift Type
            roster_type (str): Roster Type
            name (str): Current attendance name to exclude
            
        Returns:
            dict: Overlapping attendance record or empty dict
        """
        if not shift:
            return {}
        
        # Get attendance for same employee, same date, different shift
        attendance = frappe.qb.DocType("Attendance")
        query = (
            frappe.qb.from_(attendance)
            .select(attendance.name, attendance.shift)
            .where(
                (attendance.employee == employee)
                & (attendance.docstatus < 2)
                & (attendance.attendance_date == attendance_date)
                & (attendance.shift != shift)
                & (attendance.roster_type == roster_type)
            )
        )
        
        if name:
            query = query.where(attendance.name != name)
        
        overlapping = query.run(as_dict=True)
        
        if overlapping:
            # Check if shift timings actually overlap
            if AttendanceManager.has_overlapping_timings(shift, overlapping[0].shift):
                return overlapping[0]
        
        return {}
    
    @staticmethod
    def has_overlapping_timings(shift1, shift2):
        """
        Check if two shifts have overlapping timings
        
        Args:
            shift1 (str): First shift type name
            shift2 (str): Second shift type name
            
        Returns:
            bool: True if shifts overlap
        """
        if not shift1 or not shift2:
            return False
        
        # Get shift timings
        shift1_data = frappe.db.get_value(
            "Shift Type",
            shift1,
            ['start_time', 'end_time'],
            as_dict=True
        )
        
        shift2_data = frappe.db.get_value(
            "Shift Type",
            shift2,
            ['start_time', 'end_time'],
            as_dict=True
        )
        
        if not shift1_data or not shift2_data:
            return False
        
        # Convert to comparable times
        s1_start = shift1_data.start_time
        s1_end = shift1_data.end_time
        s2_start = shift2_data.start_time
        s2_end = shift2_data.end_time
        
        # Check overlap: shift1 starts before shift2 ends AND shift2 starts before shift1 ends
        return (s1_start < s2_end) and (s2_start < s1_end)
    
    @staticmethod
    def is_holiday(employee, date):
        """
        Check if a date is a holiday for an employee
        
        Args:
            employee (str): Employee ID
            date (date): Date to check
            
        Returns:
            str: Holiday description or None
        """
        holiday_list = frappe.db.get_value('Employee', employee, 'holiday_list')
        
        if not holiday_list:
            # Get default holiday list from company
            company = frappe.db.get_value('Employee', employee, 'company')
            holiday_list = frappe.db.get_value('Company', company, 'default_holiday_list')
        
        if not holiday_list:
            return None
        
        holiday = frappe.db.get_value(
            'Holiday',
            {
                'parent': holiday_list,
                'holiday_date': date
            },
            'description'
        )
        
        return holiday
    
    @staticmethod
    def get_shift_assignment(employee, date):
        """
        Get shift assignment for employee on a specific date
        
        Args:
            employee (str): Employee ID
            date (date): Date to check
            
        Returns:
            dict: Shift assignment details or None
        """
        shift_assignment = frappe.db.get_value(
            "Shift Assignment",
            {
                'employee': employee,
                'start_date': date,
                'docstatus': 1
            },
            ['*'],
            as_dict=True
        )
        
        return shift_assignment
    
    @staticmethod
    def calculate_working_hours_from_checkins(checkins_in, checkins_out):
        """
        Calculate working hours from checkin and checkout records
        
        Args:
            checkins_in (list): List of IN checkins
            checkins_out (list): List of OUT checkins
            
        Returns:
            float: Working hours
        """
        if not checkins_in or not checkins_out:
            return 0
        
        # Get first IN and last OUT
        checkin_time = get_datetime(checkins_in[0].time)
        checkout_time = get_datetime(checkins_out[-1].time)
        
        # Calculate difference
        time_diff = checkout_time - checkin_time
        
        # Convert to hours
        hours = time_diff.total_seconds() / 3600
        
        return round(hours, 2)
    
    @staticmethod
    def mark_attendance_from_checkins(employee, date, shift_assignment=None):
        """
        Mark attendance based on checkin/checkout records
        
        Args:
            employee (str): Employee ID
            date (date): Attendance date
            shift_assignment (str): Shift Assignment name (optional)
            
        Returns:
            dict: Created attendance document or None
        """
        # Check if attendance already exists
        existing = AttendanceManager.get_duplicate_attendance(employee, date)
        if existing:
            return existing[0]
        
        # Get shift assignment if not provided
        if not shift_assignment:
            shift_data = AttendanceManager.get_shift_assignment(employee, date)
            if shift_data:
                shift_assignment = shift_data.name
        
        if not shift_assignment:
            # No shift assignment, cannot mark attendance
            return None
        
        # Get checkins
        checkins_in = frappe.db.get_list(
            "Employee Checkin",
            filters={
                'employee': employee,
                'shift_assignment': shift_assignment,
                'log_type': 'IN'
            },
            fields=['name', 'time', 'late_entry'],
            order_by='time ASC'
        )
        
        checkins_out = frappe.db.get_list(
            "Employee Checkin",
            filters={
                'employee': employee,
                'shift_assignment': shift_assignment,
                'log_type': 'OUT'
            },
            fields=['name', 'time', 'early_exit'],
            order_by='time DESC'
        )
        
        # Determine status
        status = 'Absent'
        working_hours = 0
        
        if checkins_in and checkins_out:
            status = 'Present'
            working_hours = AttendanceManager.calculate_working_hours_from_checkins(
                checkins_in, 
                checkins_out
            )
        elif checkins_in:
            # Checked in but no checkout - Half day or still working
            status = 'Half Day'
            working_hours = 4  # Default half day hours
        
        # Get shift details
        shift_data = frappe.db.get_value(
            "Shift Assignment",
            shift_assignment,
            ['shift_type', 'shift', 'site'],
            as_dict=True
        )
        
        # Create attendance
        attendance = frappe.new_doc('Attendance')
        attendance.employee = employee
        attendance.attendance_date = date
        attendance.status = status
        attendance.shift = shift_data.shift_type if shift_data else None
        attendance.shift_assignment = shift_assignment
        attendance.working_hours = working_hours
        
        attendance.insert()
        attendance.submit()
        frappe.db.commit()
        
        return attendance.as_dict()


class AttendanceOverride(Attendance):
    """
    Override class for Attendance doctype
    Extends Frappe's default Attendance with custom validation and features
    """
    
    def validate(self):
        """
        Validate attendance before saving
        """
        from erpnext.controllers.status_updater import validate_status
        
        # Validate status
        valid_statuses = [
            "Present", "Absent", "On Leave", "Half Day", 
            "Work From Home", "Weekly Off", "Holiday", "On Hold", "Client Day Off"
        ]
        validate_status(self.status, valid_statuses)
        
        # Validate employee is active
        validate_active_employee(self.employee)
        
        # Validate attendance date
        self.validate_attendance_date()
        
        # Validate duplicates
        self.validate_duplicate_record()
        
        # Validate overlapping shifts (multi-shift support)
        self.validate_overlapping_shift()
        
        # Validate employee status
        self.validate_employee_status()
        
        # Check leave record
        self.check_leave_record()
        
        # Validate working hours
        self.validate_working_hours()
        
        # This is moved to before_save() to ensure it runs before validation
        # Auto-set shift assignment is now handled in before_save()
    
    def validate_working_hours(self):
        """
        Validate working hours based on status
        Allow null/zero working hours for:
        - Unscheduled employees (no shift assignment)
        - Leave statuses  
        - Manual entries where user hasn't filled it yet
        
        Note: Frappe Float fields default to 0.0, not None
        """
        # For unscheduled employees, working hours can be null/0
        # They don't have shift assignments, so working hours must be manually entered
        if self.get('is_unscheduled'):
            # Still validate if they provide a positive value
            if self.get('working_hours') and self.get('working_hours') < 0:
                frappe.throw(_("Working hours cannot be negative"))
            return  # Allow null/0 working hours for unscheduled employees
        
        # For scheduled employees, only reject negative values
        # Allow 0 or None (will be auto-calculated in before_save)
        if self.get('working_hours') and self.get('working_hours') < 0:
            frappe.throw(_("Working hours cannot be negative"))
    
    def validate_duplicate_record(self):
        """
        Check for duplicate attendance records
        """
        roster_type = self.get('roster_type', 'Basic')
        
        duplicates = AttendanceManager.get_duplicate_attendance(
            self.employee,
            self.attendance_date,
            self.shift,
            roster_type,
            self.name
        )
        
        if duplicates:
            frappe.throw(
                _("Attendance for employee {0} is already marked for date {1} (Roster: {2}): {3}").format(
                    frappe.bold(self.employee),
                    frappe.bold(self.attendance_date),
                    roster_type,
                    frappe.get_desk_link("Attendance", duplicates[0].name)
                ),
                title=_("Duplicate Attendance")
            )
    
    def validate_overlapping_shift(self):
        """
        Check for overlapping shift attendance
        Prevents marking attendance for overlapping shifts on same day
        """
        if not self.shift:
            return
        
        roster_type = self.get('roster_type', 'Basic')
        
        overlapping = AttendanceManager.get_overlapping_shift_attendance(
            self.employee,
            self.attendance_date,
            self.shift,
            roster_type,
            self.name
        )
        
        if overlapping:
            frappe.throw(
                _("Attendance for employee {0} is already marked for an overlapping shift {1} on {2}: {3}").format(
                    frappe.bold(self.employee),
                    frappe.bold(overlapping.shift),
                    frappe.bold(self.attendance_date),
                    frappe.get_desk_link("Attendance", overlapping.name)
                ),
                title=_("Overlapping Shift Attendance")
            )
    
    def set_shift_assignment(self):
        """
        Auto-set shift assignment if not present
        Falls back to employee's default shift if no assignment exists
        Note: Only required for 'Present' status, optional for others (like one_fm)
        """
        # Only mandate shift for Present status
        if self.get('status') not in ['Present']:
            return
        
        shift_assignment = AttendanceManager.get_shift_assignment(
            self.employee,
            self.attendance_date
        )
        
        if shift_assignment:
            self.shift_assignment = shift_assignment.name
            self.shift = shift_assignment.shift_type
            
            # Auto-calculate working hours only if not manually set
            if not self.get('working_hours'):
                calculated_hours = self._get_shift_working_hours(shift_assignment.shift_type)
                if calculated_hours:
                    self.working_hours = calculated_hours
        
        # If no shift assignment, use employee's default shift
        elif not self.get('shift'):
            default_shift = frappe.db.get_value('Employee', self.employee, 'default_shift')
            if default_shift:
                self.shift = default_shift
                
                # Auto-calculate working hours only if not manually set
                if not self.get('working_hours'):
                    calculated_hours = self._get_shift_working_hours(default_shift)
                    if calculated_hours:
                        self.working_hours = calculated_hours
    
    def _get_shift_working_hours(self, shift_type):
        """
        Calculate working hours from shift start and end time
        Adjusts for Half Day status using Frappe HRMS threshold
        """
        if not shift_type:
            return None
        
        shift_data = frappe.db.get_value(
            'Shift Type',
            shift_type,
            ['start_time', 'end_time', 'working_hours_threshold_for_half_day'],
            as_dict=True
        )
        
        if not shift_data or not shift_data.get('start_time') or not shift_data.get('end_time'):
            return None
        
        # Calculate duration in hours
        from datetime import datetime, timedelta
        start = shift_data.start_time
        end = shift_data.end_time
        
        # Handle times as timedelta or time objects
        if isinstance(start, timedelta):
            start_hours = start.total_seconds() / 3600
        else:
            start_hours = start.hour + start.minute / 60
        
        if isinstance(end, timedelta):
            end_hours = end.total_seconds() / 3600
        else:
            end_hours = end.hour + end.minute / 60
        
        # Calculate duration (handle overnight shifts)
        duration = end_hours - start_hours
        if duration < 0:
            duration += 24  # Overnight shift
        
        # Adjust for Half Day status
        if self.get('status') == 'Half Day':
            # Use Frappe HRMS threshold if configured, otherwise use half of full hours
            half_day_threshold = shift_data.get('working_hours_threshold_for_half_day')
            if half_day_threshold:
                duration = half_day_threshold
            else:
                duration = duration / 2  # Default to 50% of shift hours
        
        return duration
    
    def before_save(self):
        """
        Operations before saving attendance
        """
        # Auto-set shift assignment or default shift if not set
        # Only mandatory for Present status (follows one_fm pattern)
        if not self.get('shift') and self.get('status') == 'Present':
            self.set_shift_assignment()
        
        # Auto-populate operations fields from shift assignment
        if self.get('shift_assignment'):
            self.populate_operations_fields()
        
        # Auto-set employment type
        if not self.get('employee_type'):
            employment_type = frappe.db.get_value('Employee', self.employee, 'employment_type')
            if employment_type:
                self.employee_type = employment_type
        
        # Set default roster type if not set
        if not self.get('roster_type'):
            self.roster_type = 'Basic'
        
        # Auto-calculate working hours only if not manually set
        # Recalculate if status changed to/from Half Day
        if self.get('shift') and self.has_value_changed('status'):
            if self.get('status') in ['Half Day', 'Present']:
                # Only auto-calculate if working_hours not manually set
                if not self.is_new() or not self.get('working_hours'):
                    self.working_hours = self._get_shift_working_hours(self.shift)
    
    def populate_operations_fields(self):
        """
        Auto-populate operations fields from shift assignment
        Populates: operations_shift, site, project, operations_role, post_abbrv, sale_item
        """
        if not self.get('shift_assignment'):
            return
        
        # Get shift assignment details
        shift_data = frappe.db.get_value(
            "Shift Assignment",
            self.get('shift_assignment'),
            ['shift', 'site', 'shift_type'],
            as_dict=True
        )
        
        if not shift_data:
            return
        
        # Set operations shift (if Operations Shift doctype exists)
        if shift_data.get('shift'):
            self.operations_shift = shift_data.shift
            
            # Get operations role and other fields from operations shift
            if frappe.db.exists("Operations Shift", shift_data.shift):
                ops_shift = frappe.db.get_value(
                    "Operations Shift",
                    shift_data.shift,
                    ['operations_role', 'post_abbrv', 'sale_item'],
                    as_dict=True
                )
                
                if ops_shift:
                    if ops_shift.get('operations_role'):
                        self.operations_role = ops_shift.operations_role
                    if ops_shift.get('post_abbrv'):
                        self.post_abbrv = ops_shift.post_abbrv
                    if ops_shift.get('sale_item'):
                        self.sale_item = ops_shift.sale_item
        
        # Set site
        if shift_data.get('site'):
            self.site = shift_data.site
            
            # Get project from site
            if frappe.db.exists("Operations Site", shift_data.site):
                project = frappe.db.get_value("Operations Site", shift_data.site, 'project')
                if project:
                    self.project = project
    
    def after_insert(self):
        """
        Operations after inserting attendance
        """
        # Check and set day off OT flag
        self.set_day_off_ot()
    
    def set_day_off_ot(self):
        """
        Set day off OT flag if employee worked on their day off
        Checks Employee Schedule for day_off_ot flag
        """
        if not self.get('shift_assignment'):
            return
        
        # Check if Employee Schedule doctype exists
        if not frappe.db.exists("DocType", "Employee Schedule"):
            return
        
        # Check Employee Schedule for day off OT
        roster_type = self.get('roster_type', 'Basic')
        day_off_ot = frappe.db.get_value(
            "Employee Schedule",
            {
                'employee': self.employee,
                'date': self.attendance_date,
                'roster_type': roster_type
            },
            'day_off_ot'
        )
        
        if day_off_ot:
            self.db_set("day_off_ot", 1)
    
    def on_submit(self):
        """
        Post-submit operations
        """
        # Future: Trigger payroll calculations, reports, etc.
        pass


# ============================================================================
# Scheduled Tasks
# ============================================================================

def mark_absent_for_missing_checkins():
    """
    Scheduled task to mark absent for employees with shift assignments but no checkins
    Runs daily at end of day
    """
    yesterday = add_days(today(), -1)
    
    # Get all shift assignments for yesterday
    shift_assignments = frappe.db.get_list(
        "Shift Assignment",
        filters={
            'start_date': yesterday,
            'docstatus': 1
        },
        fields=['name', 'employee', 'start_date']
    )
    
    for shift in shift_assignments:
        try:
            # Check if attendance already marked
            existing = AttendanceManager.get_duplicate_attendance(
                shift.employee,
                shift.start_date
            )
            
            if existing:
                continue
            
            # Check if it's a holiday
            holiday = AttendanceManager.is_holiday(shift.employee, shift.start_date)
            if holiday:
                # Mark as Holiday
                attendance = frappe.new_doc('Attendance')
                attendance.employee = shift.employee
                attendance.attendance_date = shift.start_date
                attendance.status = 'Holiday'
                attendance.shift_assignment = shift.name
                attendance.insert()
                attendance.submit()
                frappe.db.commit()
                continue
            
            # Check for leave
            leave_application = frappe.db.exists(
                "Leave Application",
                {
                    'employee': shift.employee,
                    'from_date': ['<=', shift.start_date],
                    'to_date': ['>=', shift.start_date],
                    'status': 'Approved',
                    'docstatus': 1
                }
            )
            
            if leave_application:
                # Mark as On Leave
                attendance = frappe.new_doc('Attendance')
                attendance.employee = shift.employee
                attendance.attendance_date = shift.start_date
                attendance.status = 'On Leave'
                attendance.shift_assignment = shift.name
                attendance.leave_application = leave_application
                attendance.insert()
                attendance.submit()
                frappe.db.commit()
                continue
            
            # Check for checkins
            checkins = frappe.db.exists(
                "Employee Checkin",
                {
                    'employee': shift.employee,
                    'shift_assignment': shift.name
                }
            )
            
            if checkins:
                # Has checkins, mark attendance from checkins
                AttendanceManager.mark_attendance_from_checkins(
                    shift.employee,
                    shift.start_date,
                    shift.name
                )
            else:
                # No checkins, mark as Absent
                attendance = frappe.new_doc('Attendance')
                attendance.employee = shift.employee
                attendance.attendance_date = shift.start_date
                attendance.status = 'Absent'
                attendance.shift_assignment = shift.name
                attendance.insert()
                attendance.submit()
                frappe.db.commit()
        
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(),
                f'Mark Absent Error - Employee: {shift.employee}'
            )


# ============================================================================
# Bulk Processing Functions
# ============================================================================

def mark_attendance_for_unscheduled_employees(date=None):
    """
    Mark attendance for employees without shift assignments
    Marks Holiday or Absent based on holiday list
    
    Args:
        date (date): Date to process (defaults to yesterday)
    """
    if not date:
        date = add_days(today(), -1)
    
    try:
        # Get all active employees not on timesheet attendance
        all_employees = frappe.get_list(
            "Employee",
            filters={
                "status": "Active",
                "attendance_by_timesheet": 0
            },
            fields=['name', 'employee_name', 'company', 'department', 'holiday_list']
        )
        
        # Get employees who already have attendance
        existing_attendance = frappe.get_all(
            "Attendance",
            filters={
                'attendance_date': date,
                'roster_type': 'Basic',
                'status': ['in', ['Present', 'Holiday', 'On Leave', 'Work From Home', 
                                  'On Hold', 'Weekly Off', 'Client Day Off']]
            },
            pluck='employee'
        )
        
        # Get employees with shift assignments
        shift_assigned = frappe.get_all(
            "Shift Assignment",
            filters={
                'start_date': date,
                'docstatus': 1
            },
            pluck='employee'
        )
        
        # Filter unscheduled employees
        scheduled_set = set(shift_assigned)
        unscheduled = [
            emp for emp in all_employees
            if emp.name not in existing_attendance and emp.name not in scheduled_set
        ]
        
        if not unscheduled:
            return
        
        # Mark attendance for unscheduled employees
        for emp in unscheduled:
            try:
                # Check if holiday
                holiday = AttendanceManager.is_holiday(emp.name, date)
                
                if holiday:
                    # Mark as Holiday
                    attendance = frappe.new_doc('Attendance')
                    attendance.employee = emp.name
                    attendance.attendance_date = date
                    attendance.status = 'Holiday'
                    attendance.roster_type = 'Basic'
                    attendance.is_unscheduled = 1
                    attendance.comment = f"Holiday - {holiday}"
                    attendance.flags.ignore_validate = True
                    attendance.insert()
                    attendance.submit()
                else:
                    # Mark as Absent
                    attendance = frappe.new_doc('Attendance')
                    attendance.employee = emp.name
                    attendance.attendance_date = date
                    attendance.status = 'Absent'
                    attendance.roster_type = 'Basic'
                    attendance.is_unscheduled = 1
                    attendance.comment = "No shift assignment found"
                    attendance.flags.ignore_validate = True
                    attendance.insert()
                    attendance.submit()
                
                frappe.db.commit()
                
            except Exception as e:
                frappe.log_error(
                    frappe.get_traceback(),
                    f'Unscheduled Attendance Error - {emp.name}'
                )
    
    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            'Mark Unscheduled Employees Error'
        )


def remark_for_active_employees(date=None):
    """
    Fix incorrect Absent records by re-processing checkins
    Looks for Absent attendance with shift assignments that have checkins
    
    Args:
        date (date): Date to process (defaults to today)
    """
    if not date:
        date = today()
    
    try:
        # Get Absent attendance records with shift assignments
        absent_records = frappe.get_list(
            "Attendance",
            filters={
                "attendance_date": date,
                "status": "Absent",
                "shift_assignment": ["!=", ""]
            },
            fields=['name', 'employee', 'shift_assignment', 'roster_type']
        )
        
        for record in absent_records:
            try:
                # Check if checkins exist
                checkins = frappe.get_list(
                    "Employee Checkin",
                    filters={
                        "shift_assignment": record.shift_assignment
                    },
                    fields=['name', 'log_type', 'time', 'late_entry', 'early_exit'],
                    order_by='time ASC'
                )
                
                if checkins:
                    # Has checkins, re-process
                    ins = [c for c in checkins if c.log_type == "IN"]
                    outs = [c for c in checkins if c.log_type == "OUT"]
                    
                    if ins:
                        # Get shift timing
                        shift_data = frappe.db.get_value(
                            "Shift Assignment",
                            record.shift_assignment,
                            ['shift_type', 'start_datetime', 'end_datetime'],
                            as_dict=True
                        )
                        
                        first_in = ins[0]
                        last_out = outs[-1] if outs else None
                        
                        # Calculate working hours
                        if last_out:
                            time_diff = get_datetime(last_out.time) - get_datetime(first_in.time)
                            working_hours = time_diff.total_seconds() / 3600
                        else:
                            # No checkout, use shift end time
                            time_diff = shift_data.end_datetime - get_datetime(first_in.time)
                            working_hours = time_diff.total_seconds() / 3600
                        
                        # Update attendance
                        attendance_doc = frappe.get_doc("Attendance", record.name)
                        attendance_doc.status = 'Present'
                        attendance_doc.working_hours = round(working_hours, 2)
                        attendance_doc.comment = "Re-marked from checkins (was incorrectly marked Absent)"
                        if first_in.late_entry:
                            attendance_doc.late_entry = 1
                        if last_out and last_out.early_exit:
                            attendance_doc.early_exit = 1
                        
                        attendance_doc.flags.ignore_validate = True
                        attendance_doc.save()
                        frappe.db.commit()
            
            except Exception as e:
                frappe.log_error(
                    frappe.get_traceback(),
                    f'Remark Error - Attendance: {record.name}'
                )
    
    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(),
            'Remark for Active Employees Error'
        )


# ============================================================================
# Whitelisted API Methods
# ============================================================================

@frappe.whitelist()
def mark_attendance(employee, attendance_date, status, shift_assignment=None, working_hours=None, roster_type="Basic"):
    """
    API method to mark attendance for an employee
    
    Args:
        employee (str): Employee ID
        attendance_date (date): Attendance date
        status (str): Attendance status
        shift_assignment (str): Shift Assignment (optional)
        working_hours (float): Working hours (optional)
        roster_type (str): Roster Type - Basic or Over-Time
        
    Returns:
        dict: Created attendance document
    """
    # Check for existing attendance
    existing = AttendanceManager.get_duplicate_attendance(
        employee,
        getdate(attendance_date),
        roster_type=roster_type
    )
    
    if existing:
        frappe.throw(
            _("Attendance already marked: {0}").format(
                frappe.get_desk_link("Attendance", existing[0].name)
            )
        )
    
    # Create attendance
    attendance = frappe.new_doc('Attendance')
    attendance.employee = employee
    attendance.attendance_date = attendance_date
    attendance.status = status
    attendance.shift_assignment = shift_assignment
    attendance.roster_type = roster_type
    
    if working_hours:
        attendance.working_hours = working_hours
    
    attendance.insert()
    attendance.submit()
    frappe.db.commit()
    
    return attendance.as_dict()


@frappe.whitelist()
def mark_bulk_attendance(employee, from_date, to_date, roster_type="Basic"):
    """
    API method to mark attendance for an employee for a date range
    Processes both Basic and Over-Time roster types
    
    Args:
        employee (str): Employee ID
        from_date (date): Start date
        to_date (date): End date
        roster_type (str): Roster Type (Basic/Over-Time)
        
    Returns:
        dict: Summary of marked attendance
    """
    import pandas as pd
    
    marked = []
    errors = []
    
    # Generate date range
    date_range = pd.date_range(from_date, to_date)
    
    for date in date_range:
        try:
            # Check if attendance exists
            existing = AttendanceManager.get_duplicate_attendance(
                employee,
                date.date(),
                roster_type=roster_type
            )
            
            if existing:
                errors.append({
                    'date': str(date.date()),
                    'error': f"Attendance already exists: {existing[0].name}"
                })
                continue
            
            # Get shift assignment for this date
            shift_assignment = AttendanceManager.get_shift_assignment(
                employee,
                date.date()
            )
            
            if shift_assignment:
                # Mark from checkins if available
                attendance = AttendanceManager.mark_attendance_from_checkins(
                    employee,
                    date.date(),
                    shift_assignment.name
                )
                if attendance:
                    marked.append(str(date.date()))
            else:
                # No shift, check holiday
                holiday = AttendanceManager.is_holiday(employee, date.date())
                if holiday:
                    attendance = frappe.new_doc('Attendance')
                    attendance.employee = employee
                    attendance.attendance_date = date.date()
                    attendance.status = 'Holiday'
                    attendance.roster_type = roster_type
                    attendance.comment = f"Holiday - {holiday}"
                    attendance.insert()
                    attendance.submit()
                    marked.append(str(date.date()))
                else:
                    # Mark absent
                    attendance = frappe.new_doc('Attendance')
                    attendance.employee = employee
                    attendance.attendance_date = date.date()
                    attendance.status = 'Absent'
                    attendance.roster_type = roster_type
                    attendance.insert()
                    attendance.submit()
                    marked.append(str(date.date()))
            
            frappe.db.commit()
            
        except Exception as e:
            errors.append({
                'date': str(date.date()),
                'error': str(e)
            })
    
    return {
        'success': len(marked),
        'failed': len(errors),
        'marked_dates': marked,
        'errors': errors,
        'message': f"Marked {len(marked)} attendance records for {employee} from {from_date} to {to_date}"
    }


@frappe.whitelist()
def get_attendance_summary(employee, from_date, to_date):
    """
    API method to get attendance summary for an employee
    
    Args:
        employee (str): Employee ID
        from_date (date): Start date
        to_date (date): End date
        
    Returns:
        dict: Attendance summary with counts by status
    """
    attendances = frappe.db.get_list(
        "Attendance",
        filters={
            'employee': employee,
            'attendance_date': ['between', [from_date, to_date]],
            'docstatus': 1
        },
        fields=['name', 'attendance_date', 'status', 'working_hours']
    )
    
    # Group by status
    summary = {
        'total_days': 0,
        'present': 0,
        'absent': 0,
        'on_leave': 0,
        'half_day': 0,
        'work_from_home': 0,
        'day_off': 0,
        'holiday': 0,
        'total_working_hours': 0,
        'records': attendances
    }
    
    for att in attendances:
        summary['total_days'] += 1
        
        if att.status == 'Present':
            summary['present'] += 1
        elif att.status == 'Absent':
            summary['absent'] += 1
        elif att.status == 'On Leave':
            summary['on_leave'] += 1
        elif att.status == 'Half Day':
            summary['half_day'] += 1
        elif att.status == 'Work From Home':
            summary['work_from_home'] += 1
        elif att.status == 'Day Off':
            summary['day_off'] += 1
        elif att.status == 'Holiday':
            summary['holiday'] += 1
        
        if att.working_hours:
            summary['total_working_hours'] += att.working_hours
    
    return summary


# ========================================================================
# Doc Event Wrapper Functions (for hooks.py)
# ========================================================================
# These functions are called by frappe doc_events hooks and delegate
# to the AttendanceOverride class methods

def validate(doc, method=None):
    """Wrapper for AttendanceOverride.validate() - called by doc_events hook"""
    override = AttendanceOverride(doc.as_dict())
    override.validate()
    # Copy modified values back to the original doc
    for field in override.as_dict():
        if hasattr(doc, field):
            setattr(doc, field, override.get(field))


def before_save(doc, method=None):
    """Wrapper for AttendanceOverride.before_save() - called by doc_events hook"""
    override = AttendanceOverride(doc.as_dict())
    override.before_save()
    # Copy modified values back to the original doc
    for field in override.as_dict():
        if hasattr(doc, field):
            setattr(doc, field, override.get(field))


def after_insert(doc, method=None):
    """Wrapper for AttendanceOverride.after_insert() - called by doc_events hook"""
    override = AttendanceOverride(doc.as_dict())
    override.after_insert()


def on_submit(doc, method=None):
    """Wrapper for AttendanceOverride.on_submit() - called by doc_events hook"""
    override = AttendanceOverride(doc.as_dict())
    override.on_submit()
