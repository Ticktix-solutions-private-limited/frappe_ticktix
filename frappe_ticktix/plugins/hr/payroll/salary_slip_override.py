"""
Salary Slip Override Plugin

Extends Salary Slip to handle custom attendance statuses for payroll calculations.

Custom Statuses Treatment:
- Paid Day Offs: "Weekly Off", "Day Off", "Holiday", "Client Day Off" 
  (counted as present, do not reduce payment_days)
- Unpaid/Absent: "On Hold" 
  (counted as absent, reduces payment_days)

This ensures payroll correctly calculates payment days based on attendance status.
"""

import frappe
from frappe import _
from frappe.utils import getdate


def override_get_employee_attendance(doc, method=None):
	"""
	Override the get_employee_attendance method to include 'On Hold' status
	in the attendance records fetched for payroll calculations.
	
	This is a monkey-patch style override that will be applied via hooks.
	
	Args:
		doc: Salary Slip document
		method: Method name (from hook)
	"""
	# This will be handled by monkey-patching the method in hooks
	# The actual implementation is in the calculate_lwp_based_on_attendance override
	pass


def calculate_lwp_ppl_and_absent_days_with_custom_statuses(doc, holidays, daily_wages_fraction_for_half_day, consider_marked_attendance_on_holidays):
	"""
	Calculate Leave Without Pay (LWP) and absent days including custom attendance statuses.
	
	Treatment:
	- "On Hold" is treated as Absent (reduces payment days)
	- "Weekly Off", "Day Off", "Holiday", "Client Day Off" are NOT fetched 
	  (they remain as paid days)
	
	Args:
		doc: Salary Slip document
		holidays: List of holiday dates
		daily_wages_fraction_for_half_day: Fraction for half day (0.5 default)
		consider_marked_attendance_on_holidays: Whether to consider attendance on holidays
		
	Returns:
		tuple: (lwp, absent_days)
	"""
	lwp = 0
	absent = 0
	
	# Get the original leave type map from HRMS
	leave_type_map = doc.get_leave_type_map()
	
	# Fetch attendance details including "On Hold" status
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
			& (attendance.employee == doc.employee)
			& (attendance.docstatus == 1)
			& (attendance.attendance_date.between(doc.start_date, doc.actual_end_date))
		)
	).run(as_dict=1)
	
	for d in attendance_details:
		if (
			d.status in ("Half Day", "On Leave")
			and d.leave_type
			and d.leave_type not in leave_type_map.keys()
		):
			continue
		
		# Skip counting absent on holidays
		if not consider_marked_attendance_on_holidays and getdate(d.attendance_date) in holidays:
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


def override_salary_slip_validate(doc, method=None):
	"""
	Hook for Salary Slip validate event.
	Currently just logs the validation for monitoring.
	
	Args:
		doc: Salary Slip document
		method: Method name (from hook)
	"""
	frappe.logger().debug(f"Salary Slip validation with custom attendance statuses: {doc.name}")


# Monkey-patch the Salary Slip class to use custom LWP calculation
def apply_salary_slip_overrides():
	"""
	Apply monkey-patch overrides to Salary Slip class.
	Called from hooks.py after_install or on server start.
	"""
	from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
	
	# Store original method
	if not hasattr(SalarySlip, '_original_calculate_lwp_ppl_and_absent_days_based_on_attendance'):
		SalarySlip._original_calculate_lwp_ppl_and_absent_days_based_on_attendance = \
			SalarySlip.calculate_lwp_ppl_and_absent_days_based_on_attendance
	
	# Override with custom method
	def custom_calculate_lwp_ppl_and_absent_days_based_on_attendance(
		self, holidays, daily_wages_fraction_for_half_day, consider_marked_attendance_on_holidays
	):
		"""Custom implementation that includes 'On Hold' as absent"""
		return calculate_lwp_ppl_and_absent_days_with_custom_statuses(
			self, holidays, daily_wages_fraction_for_half_day, consider_marked_attendance_on_holidays
		)
	
	SalarySlip.calculate_lwp_ppl_and_absent_days_based_on_attendance = \
		custom_calculate_lwp_ppl_and_absent_days_based_on_attendance
	
	frappe.logger().info("Applied Salary Slip overrides for custom attendance statuses")


def validate_attendance_status_for_payroll(doc, method=None):
	"""
	Validate that attendance statuses are being correctly handled in payroll.
	This can be used to add warnings or additional validation.
	
	Args:
		doc: Salary Slip document
		method: Method name (from hook)
	"""
	# Add any additional validation logic here if needed
	pass
