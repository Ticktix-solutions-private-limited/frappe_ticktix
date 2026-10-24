"""
Custom fields for Address doctype

Adds Residence Type field shown when an Address is opened from the
Customer > Address & Contact > Primary Address link.
"""


def get_address_custom_fields():
    """Returns custom field definitions for Address doctype"""
    return {
        "Address": [
            {
                "fieldname": "custom_residence_type",
                "fieldtype": "Data",
                "insert_after": "address_type",
                "label": "Residence Type"
            }
        ]
    }


def create_custom_fields():
    """
    Create custom fields for Address doctype
    Called from install.py
    """
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    custom_fields = get_address_custom_fields()
    create_custom_fields(custom_fields, update=True)

    frappe.db.commit()
    print("✅ Created custom fields for Address doctype")
