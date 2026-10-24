"""
Salary Slip Class Override

Overrides the HRMS Salary Slip class to handle custom attendance statuses for payroll.

Custom Statuses Treatment:
- Paid Day Offs: "Weekly Off", "Day Off", "Holiday", "Client Day Off" 
  (counted as present, do not reduce payment_days)
- Unpaid/Absent: "On Hold" 
  (counted as absent, reduces payment_days)
"""

import frappe
from frappe import _
from frappe.utils import getdate

# Import the original SalarySlip class from HRMS
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip


class CustomSalarySlip(SalarySlip):
    """
    Custom Salary Slip class that extends HRMS SalarySlip.
    Overrides methods to handle custom attendance statuses in payroll calculations.
    """
    
    def get_employee_attendance(self, start_date, end_date):
        """
        Override to include 'On Hold' status in attendance records fetched for payroll.
        
        Standard HRMS only fetches: ["Absent", "Half Day", "On Leave"]
        We add: "On Hold" (treated as unpaid/absent)
        
        Note: "Weekly Off", "Day Off", "Holiday", "Client Day Off" are NOT fetched
        because they should remain as paid days.
        """
        attendance = frappe.qb.DocType("Attendance")
        
        attendance_details = (
            frappe.qb.from_(attendance)
            .select(
                attendance.attendance_date,
                attendance.status,
                attendance.leave_type,
                attendance.half_day_status,
            )
            .where(
                # Include "On Hold" along with standard statuses that affect payroll
                (attendance.status.isin(["Absent", "Half Day", "On Leave", "On Hold"]))
                & (attendance.employee == self.employee)
                & (attendance.docstatus == 1)
                & (attendance.attendance_date.between(start_date, end_date))
            )
        ).run(as_dict=1)
        
        return attendance_details
    
    def calculate_lwp_ppl_and_absent_days_based_on_attendance(
        self, holidays, daily_wages_fraction_for_half_day, consider_marked_attendance_on_holidays
    ):
        """
        Override to treat 'On Hold' status as absent days in payroll calculations.
        
        This method calculates:
        - LWP (Leave Without Pay) days
        - Absent days (including "On Hold" status)
        
        Returns:
            tuple: (lwp, absent_days)
        """
        lwp = 0
        absent = 0
        
        leave_type_map = self.get_leave_type_map()
        
        # Uses our overridden get_employee_attendance which includes "On Hold"
        attendance_details = self.get_employee_attendance(
            start_date=self.start_date, end_date=self.actual_end_date
        )
        
        for d in attendance_details:
            if (
                d.status in ("Half Day", "On Leave")
                and d.leave_type
                and d.leave_type not in leave_type_map.keys()
            ):
                continue
            
            # Skip counting absent on holidays
            if not consider_marked_attendance_on_holidays and getdate(d.attendance_date) in holidays:
                # Include "On Hold" in the skip logic along with Absent and Half Day
                if d.status in ["Absent", "Half Day", "On Hold"] or (
                    d.leave_type
                    and d.leave_type in leave_type_map.keys()
                    and not leave_type_map[d.leave_type]["include_holiday"]
                ):
                    continue
            
            if d.leave_type:
                fraction_of_daily_salary_per_leave = leave_type_map[d.leave_type][
                    "fraction_of_daily_salary_per_leave"
                ]
            
            if d.status == "Half Day" and d.leave_type and d.leave_type in leave_type_map.keys():
                equivalent_lwp = 1 - daily_wages_fraction_for_half_day
                
                if leave_type_map[d.leave_type]["is_ppl"]:
                    equivalent_lwp *= (
                        fraction_of_daily_salary_per_leave if fraction_of_daily_salary_per_leave else 1
                    )
                lwp += equivalent_lwp
            
            elif d.status == "On Leave" and d.leave_type and d.leave_type in leave_type_map.keys():
                equivalent_lwp = 1
                if leave_type_map[d.leave_type]["is_ppl"]:
                    equivalent_lwp *= (
                        fraction_of_daily_salary_per_leave if fraction_of_daily_salary_per_leave else 1
                    )
                lwp += equivalent_lwp
            
            # Treat both "Absent" and "On Hold" as absent days
            elif d.status in ("Absent", "On Hold"):
                absent += 1
        
        return lwp, absent
