"""
Attendance Status Override Plugin

This module extends Frappe HRMS Attendance to support additional status options:
- Day Off
- Holiday  
- Weekly Off

It overrides hardcoded status validations in the core HRMS module.
"""

import frappe
from frappe import _


def get_attendance_status_options():
	"""
	Get complete list of attendance status options.
	Reads from Property Setter if customized, otherwise returns extended list.
	
	Based on one_fm status options with name change:
	- Weekly Off (renamed from one_fm's "Day Off" - company-assigned weekly off)
	- Client Day Off (client-requested day off, billable)
	- Holiday (from Holiday List)
	- On Hold (pending client approval for billing)
	
	Returns:
		list: List of valid attendance status options
	"""
	# Try to get from Property Setter first (if customized via Customize Form)
	property_setter = frappe.db.get_value(
		"Property Setter",
		{
			"doc_type": "Attendance",
			"field_name": "status",
			"property": "options"
		},
		"value"
	)
	
	if property_setter:
		# Property Setter exists, use its options
		options = [opt.strip() for opt in property_setter.split('\n') if opt.strip()]
		return options
	
	# Fallback to extended default list (based on one_fm)
	return [
		"Present",
		"Absent", 
		"On Leave",
		"Half Day",
		"Work From Home",
		"Weekly Off",        # Company-assigned weekly off (one_fm's "Day Off")
		"Client Day Off",    # Client-requested day off (billable)
		"Holiday",           # From Holiday List
		"On Hold"            # Pending client approval
	]


def validate_attendance_status(status):
	"""
	Validate if the given status is in the list of allowed attendance statuses.
	
	Args:
		status (str): The attendance status to validate
		
	Raises:
		frappe.ValidationError: If status is not in allowed list
	"""
	allowed_statuses = get_attendance_status_options()
	
	if status not in allowed_statuses:
		frappe.throw(
			_("Invalid Attendance Status: {0}. Must be one of: {1}").format(
				frappe.bold(status),
				", ".join(allowed_statuses)
			),
			title=_("Invalid Status")
		)


def override_attendance_validate(doc, method=None):
	"""
	Override validate method for Attendance doctype.
	Replaces hardcoded status validation with dynamic validation.
	
	This is called via doc_events hook in hooks.py:
	doc_events = {
		"Attendance": {
			"validate": "frappe_ticktix.plugins.hr.attendance.attendance_status_override.override_attendance_validate"
		}
	}
	
	Args:
		doc: Attendance document
		method: Method name (from hook)
	"""
	# Validate status using our extended list
	validate_attendance_status(doc.status)
	
	frappe.logger().debug(f"Attendance status validated: {doc.status}")


@frappe.whitelist()
def get_status_options_for_client():
	"""
	API endpoint to get attendance status options for client-side JavaScript.
	Used by custom scripts to populate status dropdowns dynamically.
	
	Returns:
		list: List of attendance status options
	"""
	return get_attendance_status_options()


def get_status_options_string():
	"""
	Get attendance status options as newline-separated string.
	Useful for Select field options format.
	
	Returns:
		str: Newline-separated status options
	"""
	return '\n'.join(get_attendance_status_options())


def apply_attendance_overrides():
	"""
	Apply monkey-patch overrides to HRMS Attendance class.
	This overrides the validate method to use our custom status list
	instead of the hardcoded HRMS status list.
	
	Called from hooks.py via after_install or boot session.
	"""
	try:
		from hrms.hr.doctype.attendance.attendance import Attendance
		from erpnext.controllers.status_updater import validate_status
		
		# Store original validate method if not already stored
		if not hasattr(Attendance, '_original_validate'):
			Attendance._original_validate = Attendance.validate
		
		def custom_validate(self):
			"""
			Custom validate method that uses extended status options.
			Replaces the hardcoded status validation in HRMS.
			"""
			# Use our extended status list instead of hardcoded list
			allowed_statuses = get_attendance_status_options()
			validate_status(self.status, allowed_statuses)
			
			# Call the rest of the original validate logic EXCEPT the status validation
			# We need to replicate the other validation checks from HRMS
			from frappe.utils import getdate, get_link_to_form
			from hrms.hr.doctype.attendance.attendance import (
				get_duplicate_attendance_record,
				get_overlapping_shift_attendance,
			)
			
			# Duplicate attendance check
			duplicate = get_duplicate_attendance_record(
				self.employee, self.attendance_date, self.shift, self.name
			)
			if duplicate:
				frappe.throw(
					_("Attendance for employee {0} is already marked for the date {1}: {2}").format(
						frappe.bold(self.employee),
						frappe.bold(self.attendance_date),
						get_link_to_form("Attendance", duplicate[0].name),
					),
					title=_("Duplicate Attendance"),
				)
			
			# Overlapping shift attendance check
			overlapping = get_overlapping_shift_attendance(
				self.employee, self.attendance_date, self.shift, self.name
			)
			if overlapping:
				frappe.throw(
					_("Attendance for employee {0} is already marked for an overlapping shift {1}: {2}").format(
						frappe.bold(self.employee),
						frappe.bold(overlapping.shift),
						get_link_to_form("Attendance", overlapping.name),
					),
					title=_("Overlapping Shift Attendance"),
				)
			
			# Validate attendance date
			if getdate(self.attendance_date) > getdate():
				frappe.throw(
					_("Attendance cannot be marked for future dates"),
					title=_("Invalid Attendance Date"),
				)
			
			# Validate leave type if status is On Leave
			if self.status == "On Leave" and not self.leave_type:
				frappe.throw(
					_("Leave Type is mandatory for On Leave status"),
					title=_("Missing Leave Type"),
				)
		
		# Apply the monkey-patch
		Attendance.validate = custom_validate
		
		frappe.logger().info("Applied Attendance class overrides for custom status options")
		
	except ImportError as e:
		frappe.logger().error(f"Could not apply Attendance overrides: {e}")
	except Exception as e:
		frappe.logger().error(f"Error applying Attendance overrides: {e}")
