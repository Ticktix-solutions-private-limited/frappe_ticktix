"""
Helpdesk Customizations
Sync custom mandatory fields from HD Ticket to HD Ticket Template
"""
import frappe


def sync_custom_fields_to_helpdesk_template(template_name="Default"):
    """
    Add all custom mandatory fields from HD Ticket to the specified template.
    This ensures custom fields appear in the ticket creation form.
    
    Args:
        template_name: Name of the HD Ticket Template (default: "Default")
    """
    if not frappe.db.exists("HD Ticket Template", template_name):
        frappe.log_error(f"Template {template_name} not found", "Helpdesk Customization")
        return
    
    # Get all custom mandatory fields from HD Ticket
    custom_fields = frappe.get_all(
        "Custom Field",
        filters={
            "dt": "HD Ticket",
            "reqd": 1  # Mandatory fields only
        },
        fields=["fieldname", "label", "fieldtype", "options", "idx"]
    )
    
    if not custom_fields:
        print("No custom mandatory fields found on HD Ticket")
        return
    
    # Get the template
    template = frappe.get_doc("HD Ticket Template", template_name)
    
    # Get existing field names in template
    existing_fields = {field.fieldname for field in template.fields}
    
    # Add missing custom fields to template
    added_count = 0
    for cf in custom_fields:
        if cf.fieldname not in existing_fields:
            template.append("fields", {
                "fieldname": cf.fieldname,
                "required": 1,  # Make it required in template
                "hide_from_customer": 0,  # Show to customers
                "idx": cf.idx
            })
            added_count += 1
            print(f"Added custom field: {cf.fieldname} ({cf.label})")
    
    if added_count > 0:
        template.save(ignore_permissions=True)
        frappe.db.commit()
        print(f"✅ Successfully added {added_count} custom field(s) to template '{template_name}'")
    else:
        print(f"✅ All custom mandatory fields already exist in template '{template_name}'")


def remove_field_from_helpdesk_template(fieldname, template_name="Default"):
    """
    Remove a specific field from HD Ticket Template.
    
    Args:
        fieldname: Field name to remove
        template_name: Name of the HD Ticket Template (default: "Default")
    """
    if not frappe.db.exists("HD Ticket Template", template_name):
        frappe.log_error(f"Template {template_name} not found", "Helpdesk Customization")
        return
    
    template = frappe.get_doc("HD Ticket Template", template_name)
    
    # Find and remove the field
    for i, field in enumerate(template.fields):
        if field.fieldname == fieldname:
            template.remove(field)
            template.save(ignore_permissions=True)
            frappe.db.commit()
            print(f"✅ Removed field '{fieldname}' from template '{template_name}'")
            return
    
    print(f"⚠️  Field '{fieldname}' not found in template '{template_name}'")


@frappe.whitelist()
def get_template_fields_info(template_name="Default"):
    """
    Get information about fields in a template.
    Useful for debugging.
    """
    if not frappe.db.exists("HD Ticket Template", template_name):
        return {"error": f"Template {template_name} not found"}
    
    template = frappe.get_doc("HD Ticket Template", template_name)
    
    return {
        "template_name": template_name,
        "total_fields": len(template.fields),
        "fields": [
            {
                "fieldname": f.fieldname,
                "required": f.required,
                "hide_from_customer": f.hide_from_customer,
                "idx": f.idx
            }
            for f in template.fields
        ]
    }
