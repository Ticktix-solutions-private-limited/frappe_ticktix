app_name = "frappe_ticktix"
app_title = "Frappe Ticktix"
app_publisher = "Ticktix Solutions private limited"
app_description = "Ticktix Custom app"
app_email = "facilitix@ticktix.com"
app_license = "mit"

# App Logo - Set via hooks
# ------------------
# Provide app logo URL through hooks (this will be used as fallback by get_app_logo())
app_logo_url = "frappe_ticktix.plugins.branding.logo_manager.get_company_logo_url"

# Website Context - Will be set dynamically
# ------------------
# website_context will be set dynamically from site configuration
website_context = {
	"favicon": None,  # Will be set dynamically
	"splash_image": None,  # Will be set dynamically  
	"app_name": None,  # Will be set dynamically
	"app_title": None,  # Will be set dynamically
}

# Update website context dynamically from site config
update_website_context = [
	"frappe_ticktix.plugins.branding.logo_manager.update_website_context"
]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "frappe_ticktix",
# 		"logo": "/assets/frappe_ticktix/logo.png",
# 		"title": "Frappe Ticktix",
# 		"route": "/frappe_ticktix",
# 		"has_permission": "frappe_ticktix.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/frappe_ticktix/css/frappe_ticktix.css"
app_include_js = "/assets/frappe_ticktix/js/ticktix_logout.js"

# include js, css files in header of web template
web_include_css = [
	"/assets/frappe_ticktix/css/login_custom.css",
	"/assets/frappe_ticktix/css/helpdesk_custom.css"
]
web_include_js = [
	"/assets/frappe_ticktix/js/login_custom.js",
	"/assets/frappe_ticktix/js/helpdesk_custom.js"
]

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "frappe_ticktix/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "frappe_ticktix/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "frappe_ticktix.utils.jinja_methods",
# 	"filters": "frappe_ticktix.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "frappe_ticktix.install.before_install"
after_install = "frappe_ticktix.install.after_install"

# Migration
# ---------

after_migrate = "frappe_ticktix.install.after_migrate"

# Uninstallation
# ------------

before_uninstall = "frappe_ticktix.install.before_uninstall"
# after_uninstall = "frappe_ticktix.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "frappe_ticktix.utils.before_app_install"
# after_app_install = "frappe_ticktix.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "frappe_ticktix.utils.before_app_uninstall"
# after_app_uninstall = "frappe_ticktix.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "frappe_ticktix.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Scheduler Events
# ----------------
# NOTE: Only ONE scheduler_events dict is allowed — the second definition
# below (lines ~251) has been merged here and removed to prevent silent override.

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Attendance": "frappe_ticktix.plugins.hr.attendance.attendance_class_override.CustomAttendance",
	"Salary Slip": "frappe_ticktix.plugins.hr.payroll.salary_slip_class_override.CustomSalarySlip"
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	# Zitadel provisioning - push new users to Zitadel on creation
	"User": {
		"after_insert": "frappe_ticktix.plugins.authentication.zitadel_provisioner.auto_provision_user"
	},
	# HR Plugin - Employee Checkin
	"Employee Checkin": {
		"validate": "frappe_ticktix.plugins.hr.checkin.checkin_manager.validate",
		"before_insert": "frappe_ticktix.plugins.hr.checkin.checkin_manager.before_insert",
		"after_insert": "frappe_ticktix.plugins.hr.checkin.checkin_manager.after_insert"
	},
	# HR Plugin - Attendance
	"Attendance": {
		"validate": [
			"frappe_ticktix.plugins.hr.attendance.attendance_manager.validate",
			"frappe_ticktix.plugins.hr.attendance.attendance_status_override.override_attendance_validate"
		],
		"before_save": "frappe_ticktix.plugins.hr.attendance.attendance_manager.before_save",
		"after_insert": "frappe_ticktix.plugins.hr.attendance.attendance_manager.after_insert",
		"on_submit": "frappe_ticktix.plugins.hr.attendance.attendance_manager.on_submit"
	},
	# HR Plugin - Salary Slip (Payroll)
	"Salary Slip": {
		"validate": "frappe_ticktix.plugins.hr.payroll.salary_slip_override.override_salary_slip_validate"
	},
	# Helpdesk Plugin - Auto-sync custom fields to templates
	"Custom Field": {
		"after_insert": "frappe_ticktix.plugins.helpdesk.template_sync.auto_sync_on_custom_field_change",
		"after_save": "frappe_ticktix.plugins.helpdesk.template_sync.auto_sync_on_custom_field_change"
	},
	# HR Employee ID Generator Plugin - Auto-generate employee IDs
	"Employee": {
		"before_insert": "frappe_ticktix.plugins.hr.employee_id_generator.hooks.before_insert_employee",
		"validate": "frappe_ticktix.plugins.hr.employee_id_generator.hooks.validate_employee"
	},
	# HR Plugin - Employee Checkin
	"Employee Checkin": {
		"validate": "frappe_ticktix.plugins.hr.checkin.checkin_manager.validate",
		"before_insert": "frappe_ticktix.plugins.hr.checkin.checkin_manager.before_insert",
		"after_insert": "frappe_ticktix.plugins.hr.checkin.checkin_manager.after_insert"
	},
	# HR Plugin - Attendance
	"Attendance": {
		"validate": [
			"frappe_ticktix.plugins.hr.attendance.attendance_manager.validate",
			"frappe_ticktix.plugins.hr.attendance.attendance_status_override.override_attendance_validate"
		],
		"before_save": "frappe_ticktix.plugins.hr.attendance.attendance_manager.before_save",
		"after_insert": "frappe_ticktix.plugins.hr.attendance.attendance_manager.after_insert",
		"on_submit": "frappe_ticktix.plugins.hr.attendance.attendance_manager.on_submit"
	},
	# HR Plugin - Salary Slip (Payroll)
	"Salary Slip": {
		"validate": "frappe_ticktix.plugins.hr.payroll.salary_slip_override.override_salary_slip_validate"
	}
}

# Scheduled Tasks
# ---------------
scheduler_events = {
	# Runs once per day at the system-scheduler cadence (midnight)
	"daily": [
		"frappe_ticktix.plugins.hr.attendance.attendance_manager.mark_absent_for_missing_checkins",
		"frappe_ticktix.plugins.hr.attendance.attendance_manager.mark_attendance_for_unscheduled_employees",
		"frappe_ticktix.plugins.hr.attendance.attendance_manager.remark_for_active_employees",
	],
	# Cron-based jobs for precise timing
	"cron": {
		# -----------------------------------------------------------------
		# Runs at 00:30 daily so we process the full previous day window
		# (00:00:00 to 23:59:59) after data for that day has settled.
		# then restart bench.
		# -----------------------------------------------------------------
		"30 0 * * *": [
			"frappe_ticktix.services.geo_processing.run_daily_travel_summary",
		],
	},
}

# Testing
# -------

# before_tests = "frappe_ticktix.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "frappe_ticktix.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "frappe_ticktix.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["frappe_ticktix.utils.before_request"]
# after_request = ["frappe_ticktix.utils.after_request"]

# Job Events
# ----------
# before_job = ["frappe_ticktix.utils.before_job"]
# after_job = ["frappe_ticktix.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"frappe_ticktix.auth.validate"
# ]

# Override /login to redirect to TickTix OAuth (Zitadel)
override_whitelisted_methods = {
	"login": "frappe_ticktix.api.ticktix_login",
	"logout": "frappe_ticktix.api.ticktix_logout"
}

# Expose TickTix as a social login provider
override_whitelisted_methods["frappe.integrations.oauth2_logins.get_social_login_providers"] = "frappe_ticktix.plugins.authentication.oauth_provider.get_social_login_providers"

# Override login callback path if needed (frappe uses /api/method/frappe.integrations.oauth2_logins.custom/<provider>)
# We provide a custom handler for OAuth callbacks that properly handles TickTix user ID mapping
override_whitelisted_methods["frappe.integrations.oauth2_logins.custom"] = "frappe_ticktix.plugins.authentication.login_callback.custom_oauth_handler"


# Mobile app support endpoints
override_whitelisted_methods["frappe_ticktix.api.mobile_login"] = "frappe_ticktix.api.mobile_login"
override_whitelisted_methods["frappe_ticktix.api.mobile_logout"] = "frappe_ticktix.api.mobile_logout"

# Company logo utility endpoint
override_whitelisted_methods["frappe_ticktix.plugins.branding.logo_manager.get_company_logo"] = "frappe_ticktix.plugins.branding.logo_manager.get_company_logo"

# JWT Authentication API endpoints
override_whitelisted_methods["frappe_ticktix.plugins.authentication.user_mapper.get_jwt_user_info"] = "frappe_ticktix.plugins.authentication.user_mapper.get_jwt_user_info"
override_whitelisted_methods["frappe_ticktix.plugins.authentication.user_mapper.sync_jwt_user_data"] = "frappe_ticktix.plugins.authentication.user_mapper.sync_jwt_user_data" 
override_whitelisted_methods["frappe_ticktix.plugins.authentication.jwt_validator.test_jwt_config"] = "frappe_ticktix.plugins.authentication.jwt_validator.test_jwt_config"
override_whitelisted_methods["frappe_ticktix.plugins.authentication.jwt_validator.clear_jwks_cache"] = "frappe_ticktix.plugins.authentication.jwt_validator.clear_jwks_cache"

# HR Plugin - Attendance Status API endpoint
override_whitelisted_methods["frappe_ticktix.plugins.hr.attendance.attendance_status_override.get_status_options_for_client"] = "frappe_ticktix.plugins.hr.attendance.attendance_status_override.get_status_options_for_client"

# HR Plugin - Attendance Manager API endpoints
override_whitelisted_methods["frappe_ticktix.plugins.hr.attendance.attendance_manager.mark_attendance"] = "frappe_ticktix.plugins.hr.attendance.attendance_manager.mark_attendance"
override_whitelisted_methods["frappe_ticktix.plugins.hr.attendance.attendance_manager.mark_bulk_attendance"] = "frappe_ticktix.plugins.hr.attendance.attendance_manager.mark_bulk_attendance"
override_whitelisted_methods["frappe_ticktix.plugins.hr.attendance.attendance_manager.get_attendance_summary"] = "frappe_ticktix.plugins.hr.attendance.attendance_manager.get_attendance_summary"

# JWT API test endpoints  
override_whitelisted_methods["frappe_ticktix.api.v1.jwt_api.test_jwt_auth"] = "frappe_ticktix.api.v1.jwt_api.test_jwt_auth"
override_whitelisted_methods["frappe_ticktix.api.v1.jwt_api.get_user_profile"] = "frappe_ticktix.api.v1.jwt_api.get_user_profile"
override_whitelisted_methods["frappe_ticktix.api.v1.jwt_api.mobile_api_info"] = "frappe_ticktix.api.v1.jwt_api.mobile_api_info"
override_whitelisted_methods["frappe_ticktix.api.v1.jwt_api.health_check"] = "frappe_ticktix.api.v1.jwt_api.health_check"

# Session diagnostic endpoint (moved to tests/diagnostics)
override_whitelisted_methods["frappe_ticktix.tests.diagnostics.session_check.check_session_state"] = "frappe_ticktix.tests.diagnostics.session_check.check_session_state"

# HR Plugin - Employee Checkin API
override_whitelisted_methods["frappe_ticktix.plugins.hr.checkin.checkin_manager.get_current_shift_for_employee"] = "frappe_ticktix.plugins.hr.checkin.checkin_manager.get_current_shift_for_employee"
override_whitelisted_methods["frappe_ticktix.plugins.hr.checkin.checkin_manager.create_checkin"] = "frappe_ticktix.plugins.hr.checkin.checkin_manager.create_checkin"

# Daily Travel Summary API endpoints
override_whitelisted_methods["frappe_ticktix.api.geo_tracking.get_employee_travel_summary"] = "frappe_ticktix.api.geo_tracking.get_employee_travel_summary"
override_whitelisted_methods["frappe_ticktix.api.geo_tracking.get_team_travel_summary"] = "frappe_ticktix.api.geo_tracking.get_team_travel_summary"
override_whitelisted_methods["frappe_ticktix.api.geo_tracking.reprocess_travel_summary"] = "frappe_ticktix.api.geo_tracking.reprocess_travel_summary"
override_whitelisted_methods["frappe_ticktix.api.geo_tracking.trigger_batch_processing"] = "frappe_ticktix.api.geo_tracking.trigger_batch_processing"

# Helpdesk Plugin - Template field sync API endpoints
override_whitelisted_methods["frappe_ticktix.plugins.helpdesk.template_sync.sync_helpdesk_template_fields"] = "frappe_ticktix.plugins.helpdesk.template_sync.sync_helpdesk_template_fields"
override_whitelisted_methods["frappe_ticktix.plugins.helpdesk.template_sync.get_helpdesk_template_info"] = "frappe_ticktix.plugins.helpdesk.template_sync.get_helpdesk_template_info"

# Intercept website requests so that visiting /login redirects to TickTix
# Add JWT middleware for API authentication (runs before TickTix redirect)
before_request = [
	"frappe_ticktix.plugins.authentication.jwt_middleware.jwt_auth_middleware",  # JWT auth for API requests
	"frappe_ticktix.api.force_ticktix_login"  # TickTix redirect for browser requests
]

# Add company logo to boot information  
extend_bootinfo = [
	"frappe_ticktix.plugins.branding.logo_manager.extend_bootinfo"
]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

