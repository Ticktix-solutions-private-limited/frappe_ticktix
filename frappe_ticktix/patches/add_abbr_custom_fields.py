"""
Patch: Add Abbreviation Custom Fields

Adds custom_abbr field to Department, Branch, and Employment Type doctypes
for Employee ID generation plugin

Run: bench --site <sitename> execute frappe_ticktix.patches.add_abbr_custom_fields.execute
"""

import frappe


def execute():
    """Add custom_abbr field to Department, Branch, and Employment Type doctypes"""
    
    custom_fields = [
        {
            "doctype": "Department",
            "fieldname": "custom_abbr",
            "label": "Abbreviation",
            "fieldtype": "Data",
            "insert_after": "department_name",
            "description": "Short code for Employee ID generation (e.g., IT, HR, FIN)",
            "length": 10
        },
        {
            "doctype": "Branch",
            "fieldname": "custom_abbr",
            "label": "Abbreviation",
            "fieldtype": "Data",
            "insert_after": "branch",
            "description": "Short code for Employee ID generation (e.g., HO, BR01)",
            "length": 10
        },
        {
            "doctype": "Employment Type",
            "fieldname": "custom_abbr",
            "label": "Abbreviation",
            "fieldtype": "Data",
            "insert_after": "employee_type_name",
            "description": "Short code for Employee ID generation (e.g., FT, PT, CT)",
            "length": 10
        }
    ]
    
    for field_def in custom_fields:
        doctype = field_def.pop("doctype")
        fieldname = field_def["fieldname"]
        
        # Check if field already exists
        if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": fieldname}):
            print(f"✓ Custom field '{fieldname}' already exists in {doctype}")
            continue
        
        # Create custom field
        custom_field = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": doctype,
            **field_def
        })
        custom_field.insert(ignore_permissions=True)
        print(f"✓ Created custom field '{fieldname}' in {doctype}")
    
    frappe.db.commit()
    print("\n✅ Custom field migration complete!")


if __name__ == "__main__":
    execute()
