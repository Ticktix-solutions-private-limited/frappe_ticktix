"""
Client Scripts for Attendance Status Override

This module provides custom client scripts that override hardcoded status options
in HRMS JavaScript files for:
1. Mark Attendance dialog (attendance_list.js)
2. Employee Attendance Tool form

These scripts are loaded via fixtures or Client Script doctype.
"""

# Mark Attendance Dialog Override
MARK_ATTENDANCE_DIALOG_SCRIPT = """
// Override Mark Attendance dialog to use dynamic status options
frappe.provide('frappe_ticktix.attendance');

frappe_ticktix.attendance.get_status_options = function() {
	let options = [];
	
	// Try to get from server (includes customizations)
	frappe.call({
		method: 'frappe_ticktix.plugins.hr.attendance.attendance_status_override.get_status_options_for_client',
		async: false,
		callback: function(r) {
			if (r.message) {
				options = r.message;
			}
		}
	});
	
	// Fallback to extended list if API call fails
	if (options.length === 0) {
		options = ['Present', 'Absent', 'On Leave', 'Half Day', 'Work From Home', 'Weekly Off', 'Client Day Off', 'Holiday', 'On Hold'];
	}
	
	return options;
};

// Override the get_indicator function to handle custom statuses
if (frappe.listview_settings['Attendance']) {
	frappe.listview_settings['Attendance'].get_indicator = function(doc) {
		// Green statuses - Present, Work From Home, Weekly Off, Holiday, Client Day Off
		if (['Present', 'Work From Home'].includes(doc.status)) {
			return [__(doc.status), 'green', 'status,=,' + doc.status];
		}
		// Blue statuses - Weekly Off, Holiday, Client Day Off (paid day offs)
		else if (['Weekly Off', 'Holiday', 'Client Day Off'].includes(doc.status)) {
			return [__(doc.status), 'blue', 'status,=,' + doc.status];
		}
		// Red statuses - Absent, On Leave
		else if (['Absent', 'On Leave'].includes(doc.status)) {
			return [__(doc.status), 'red', 'status,=,' + doc.status];
		}
		// Orange statuses - Half Day, On Hold
		else if (['Half Day', 'On Hold'].includes(doc.status)) {
			return [__(doc.status), 'orange', 'status,=,' + doc.status];
		}
		// Fallback for any other status
		else if (doc.status) {
			return [__(doc.status), 'gray', 'status,=,' + doc.status];
		}
	};
}

// Override the listview settings for Attendance
if (frappe.listview_settings['Attendance']) {
	const original_onload = frappe.listview_settings['Attendance'].onload;
	
	frappe.listview_settings['Attendance'].onload = function(list_view) {
		// Call original onload
		if (original_onload) {
			original_onload.call(this, list_view);
		}
		
		// Override the Mark Attendance button click handler
		list_view.page.clear_inner_toolbar();
		let me = this;
		
		list_view.page.add_inner_button(__("Mark Attendance"), function () {
			let first_day_of_month = moment().startOf("month");

			if (moment().toDate().getDate() === 1) {
				first_day_of_month = first_day_of_month.subtract(1, "month");
			}

			let dialog = new frappe.ui.Dialog({
				title: __("Mark Attendance"),
				fields: [
					{
						fieldname: "employee",
						label: __("For Employee"),
						fieldtype: "Link",
						options: "Employee",
						get_query: () => {
							return {
								query: "erpnext.controllers.queries.employee_query",
							};
						},
						reqd: 1,
						onchange: () => me.reset_dialog(dialog),
					},
					{
						fieldtype: "Section Break",
						fieldname: "time_period_section",
						hidden: 1,
					},
					{
						label: __("Start"),
						fieldtype: "Date",
						fieldname: "from_date",
						reqd: 1,
						default: first_day_of_month.toDate(),
						onchange: () => me.get_unmarked_days(dialog),
					},
					{
						fieldtype: "Column Break",
						fieldname: "time_period_column",
					},
					{
						label: __("End"),
						fieldtype: "Date",
						fieldname: "to_date",
						reqd: 1,
						default: moment().toDate(),
						onchange: () => me.get_unmarked_days(dialog),
					},
					{
						fieldtype: "Section Break",
						fieldname: "days_section",
						hidden: 1,
					},
					{
						label: __("Status"),
						fieldtype: "Select",
						fieldname: "status",
						options: frappe_ticktix.attendance.get_status_options(),
						reqd: 1,
					},
					{
						label: __("Exclude Holidays"),
						fieldtype: "Check",
						fieldname: "exclude_holidays",
						onchange: () => me.get_unmarked_days(dialog),
					},
					{
						label: __("Unmarked Attendance for days"),
						fieldname: "unmarked_days",
						fieldtype: "MultiCheck",
						options: [],
						columns: 2,
						select_all: true,
					},
				],
				primary_action(data) {
					if (cur_dialog.no_unmarked_days_left) {
						frappe.msgprint(
							__(
								"Attendance from {0} to {1} has already been marked for the Employee {2}",
								[data.from_date, data.to_date, data.employee],
							),
						);
					} else {
						frappe.confirm(
							__("Mark attendance as {0} for {1} on selected dates?", [
								data.status,
								data.employee,
							]),
							() => {
								frappe.call({
									method: "hrms.hr.doctype.attendance.attendance.mark_bulk_attendance",
									args: {
										data: data,
									},
									callback: function (r) {
										if (r.message === 1) {
											frappe.show_alert({
												message: __("Attendance Marked"),
												indicator: "blue",
											});
											cur_dialog.hide();
										}
									},
								});
							},
						);
					}
					dialog.hide();
					list_view.refresh();
				},
				primary_action_label: __("Mark Attendance"),
			});
			dialog.show();
		});
	};
}
"""

# Employee Attendance Tool Override
EMPLOYEE_ATTENDANCE_TOOL_SCRIPT = """
// Override Employee Attendance Tool to use dynamic status options
frappe.ui.form.on('Employee Attendance Tool', {
	onload: function(frm) {
		// Get dynamic status options
		frappe.call({
			method: 'frappe_ticktix.plugins.hr.attendance.attendance_status_override.get_status_options_for_client',
			callback: function(r) {
				if (r.message) {
					// Update status field options
					frm.set_df_property('status', 'options', r.message);
					frm.set_df_property('half_day_status', 'options', r.message);
				}
			}
		});
	},
	
	refresh: function(frm) {
		// Ensure status options are updated on refresh
		frappe.call({
			method: 'frappe_ticktix.plugins.hr.attendance.attendance_status_override.get_status_options_for_client',
			callback: function(r) {
				if (r.message) {
					frm.set_df_property('status', 'options', r.message);
					frm.set_df_property('half_day_status', 'options', r.message);
				}
			}
		});
	}
});
"""


def get_client_scripts():
	"""
	Returns list of client scripts to be installed.
	
	Returns:
		list: List of dicts with script details
	"""
	return [
		{
			"name": "Attendance Status Override - Mark Attendance Dialog",
			"dt": "Attendance",
			"view": "List",
			"enabled": 1,
			"script": MARK_ATTENDANCE_DIALOG_SCRIPT
		},
		{
			"name": "Attendance Status Override - Employee Attendance Tool",
			"dt": "Employee Attendance Tool",
			"view": "Form",
			"enabled": 1,
			"script": EMPLOYEE_ATTENDANCE_TOOL_SCRIPT
		}
	]
