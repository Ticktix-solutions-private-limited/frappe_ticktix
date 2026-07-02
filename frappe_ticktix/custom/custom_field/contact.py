"""
Custom fields for Contact doctype

Adds identity/KYC fields shown when a Contact is opened from the
Customer > Address & Contact > Primary Contact link:
- Date of Birth
- PAN
- Marital Status
"""


def get_contact_custom_fields():
    """Returns custom field definitions for Contact doctype"""
    return {
        "Contact": [
            {
                "fieldname": "custom_kyc_details_section",
                "fieldtype": "Section Break",
                "insert_after": "unsubscribed",
                "label": "KYC Details",
                "collapsible": 1
            },
            {
                "fieldname": "custom_date_of_birth",
                "fieldtype": "Date",
                "insert_after": "custom_kyc_details_section",
                "label": "Date of Birth"
            },
            {
                "fieldname": "custom_pan",
                "fieldtype": "Data",
                "insert_after": "custom_date_of_birth",
                "label": "PAN"
            },
            {
                "fieldname": "custom_column_break_kyc",
                "fieldtype": "Column Break",
                "insert_after": "custom_pan"
            },
            {
                "fieldname": "custom_marital_status",
                "fieldtype": "Select",
                "insert_after": "custom_column_break_kyc",
                "label": "Marital Status",
                "options": "\nSingle\nMarried\nDivorced\nWidowed"
            }
        ]
    }


def create_custom_fields():
    """
    Create custom fields for Contact doctype
    Called from install.py
    """
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    custom_fields = get_contact_custom_fields()
    create_custom_fields(custom_fields, update=True)

    frappe.db.commit()
    print("✅ Created custom fields for Contact doctype")
