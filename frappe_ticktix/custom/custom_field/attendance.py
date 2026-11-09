"""
Custom fields for Attendance doctype

Adds operations, tracking, and integration fields for:
- Multi-site operations tracking
- Project-based billing
- Overtime roster support
- Timesheet integration
- Reference tracking
"""


def get_attendance_custom_fields():
    """
    Returns custom field definitions for Attendance doctype
    
    Categories:
    1. Operations Fields - Site, shift, project, role tracking
    2. Roster & Overtime - Basic vs OT roster, day off OT
    3. Integration - Timesheet, references
    4. Tracking - Employment type, unscheduled flag
    5. Comments - Attendance comments and reasons
    """
    return {
        "Attendance": [
            # ================================================================
            # OPERATIONS SECTION - After shift field
            # ================================================================
            {
                "fieldname": "operations_section",
                "fieldtype": "Section Break",
                "insert_after": "shift",
                "label": "Operations Details",
                "collapsible": 1
            },
            {
                "fieldname": "operations_shift",
                "fieldtype": "Data",
                "insert_after": "operations_section",
                "label": "Operations Shift",
                "read_only": 1,
                "description": "Link to operations shift (for operations management)"
            },
            {
                "fieldname": "site",
                "fieldtype": "Data",
                "insert_after": "operations_shift",
                "label": "Site",
                "read_only": 1,
                "description": "Work site/location for this attendance"
            },
            {
                "fieldname": "column_break_operations",
                "fieldtype": "Column Break",
                "insert_after": "site"
            },
            {
                "fieldname": "project",
                "fieldtype": "Link",
                "insert_after": "column_break_operations",
                "label": "Project",
                "options": "Project",
                "read_only": 1,
                "description": "Project linked to this attendance (for billing)"
            },
            {
                "fieldname": "operations_role",
                "fieldtype": "Data",
                "insert_after": "project",
                "label": "Operations Role",
                "read_only": 1,
                "description": "Employee role at site (Guard, Supervisor, etc.)"
            },
            
            # ================================================================
            # ROSTER & OVERTIME SECTION - After working_hours
            # ================================================================
            {
                "fieldname": "roster_section",
                "fieldtype": "Section Break",
                "insert_after": "working_hours",
                "label": "Roster & Overtime",
                "collapsible": 1
            },
            {
                "fieldname": "roster_type",
                "fieldtype": "Select",
                "insert_after": "roster_section",
                "label": "Roster Type",
                "options": "Basic\nOver-Time",
                "default": "Basic",
                "in_standard_filter": 1,
                "description": "Basic = Regular shift, Over-Time = OT shift"
            },
            {
                "fieldname": "day_off_ot",
                "fieldtype": "Check",
                "insert_after": "roster_type",
                "label": "Day Off OT",
                "read_only": 1,
                "description": "Employee worked on their day off (eligible for OT pay)"
            },
            {
                "fieldname": "column_break_roster",
                "fieldtype": "Column Break",
                "insert_after": "day_off_ot"
            },
            {
                "fieldname": "post_abbrv",
                "fieldtype": "Data",
                "insert_after": "column_break_roster",
                "label": "Post Abbreviation",
                "read_only": 1,
                "description": "Short code for role (used in reports)"
            },
            {
                "fieldname": "sale_item",
                "fieldtype": "Data",
                "insert_after": "post_abbrv",
                "label": "Sale Item",
                "read_only": 1,
                "description": "Sales item for billing calculations"
            },
            
            # ================================================================
            # INTEGRATION SECTION - After attendance_request
            # ================================================================
            {
                "fieldname": "integration_section",
                "fieldtype": "Section Break",
                "insert_after": "attendance_request",
                "label": "Integration & References",
                "collapsible": 1
            },
            {
                "fieldname": "timesheet",
                "fieldtype": "Link",
                "insert_after": "integration_section",
                "label": "Timesheet",
                "options": "Timesheet",
                "read_only": 1,
                "description": "Linked timesheet (for project-based attendance)"
            },
            {
                "fieldname": "reference_doctype",
                "fieldtype": "Link",
                "insert_after": "timesheet",
                "label": "Reference Doctype",
                "options": "DocType",
                "description": "Source document type (if created from another doc)"
            },
            {
                "fieldname": "column_break_integration",
                "fieldtype": "Column Break",
                "insert_after": "reference_doctype"
            },
            {
                "fieldname": "reference_docname",
                "fieldtype": "Dynamic Link",
                "insert_after": "column_break_integration",
                "label": "Reference Document",
                "options": "reference_doctype",
                "depends_on": "eval:doc.reference_doctype",
                "description": "Source document name"
            },
            
            # ================================================================
            # TRACKING SECTION - After employee_name
            # ================================================================
            {
                "fieldname": "custom_employment_type",
                "fieldtype": "Link",
                "insert_after": "employee_name",
                "label": "Employment Type",
                "options": "Employment Type",
                "read_only": 1,
                "description": "Employee contract type (affects payroll calculation)"
            },
            {
                "fieldname": "is_unscheduled",
                "fieldtype": "Check",
                "insert_after": "custom_employment_type",
                "label": "Unscheduled Employee",
                "read_only": 1,
                "description": "Employee has no shift assignment (marked based on default rules)"
            },
            
            # ================================================================
            # COMMENTS SECTION - Replace existing comment section
            # ================================================================
            {
                "fieldname": "attendance_comments_section",
                "fieldtype": "Section Break",
                "insert_after": "amended_from",
                "label": "Attendance Comments",
                "collapsible": 1
            },
            {
                "fieldname": "comment",
                "fieldtype": "Small Text",
                "insert_after": "attendance_comments_section",
                "label": "Comment",
                "description": "Reason for attendance status or additional notes"
            }
        ]
    }


def create_custom_fields():
    """
    Create custom fields for Attendance doctype
    Called from install.py
    """
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    
    custom_fields = get_attendance_custom_fields()
    create_custom_fields(custom_fields, update=True)
    
    frappe.db.commit()
    print("✅ Created custom fields for Attendance doctype")
