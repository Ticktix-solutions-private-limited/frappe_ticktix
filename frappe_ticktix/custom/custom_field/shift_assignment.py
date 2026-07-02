"""
Custom fields for Shift Assignment doctype
"""


def get_shift_assignment_custom_fields():
    return {
        "Shift Assignment": [
            {
                "fieldname": "custom_enable_live_geo_tracking",
                "fieldtype": "Check",
                "label": "Enable Live GEO Tracking",
                "insert_after": "shift_location",
                "default": "0",
            }
        ]
    }


def create_custom_fields():
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(get_shift_assignment_custom_fields(), update=True)
    frappe.db.commit()
    print("✅ Created custom fields for Shift Assignment doctype")
