"""
Helpdesk Template Field Sync Manager

Automatically syncs custom mandatory fields from HD Ticket doctype customization
to HD Ticket Template, ensuring they appear in the Helpdesk ticket creation form.

This follows the plugin architecture pattern used in frappe_ticktix.
"""
import frappe
from frappe import _


class HelpdeskTemplateSyncManager:
    """
    Manages synchronization of custom fields between ERPNext customization
    and Helpdesk templates.
    """
    
    DOCTYPE_TICKET = "HD Ticket"
    DOCTYPE_TEMPLATE = "HD Ticket Template"
    DOCTYPE_CUSTOM_FIELD = "Custom Field"
    
    def __init__(self, template_name="Default"):
        """
        Initialize the sync manager for a specific template.
        
        Args:
            template_name: Name of the HD Ticket Template to sync (default: "Default")
        """
        self.template_name = template_name
        self.template = None
    
    def sync_custom_fields(self):
        """
        Main method to sync all custom mandatory fields to the template.
        
        Returns:
            dict: Summary of sync operation with added/skipped counts
        """
        # Check if Helpdesk app is installed
        if not frappe.db.exists("DocType", self.DOCTYPE_TICKET):
            return {
                "success": False,
                "message": "Helpdesk app is not installed"
            }
        
        # Check if template exists
        if not frappe.db.exists(self.DOCTYPE_TEMPLATE, self.template_name):
            return {
                "success": False,
                "message": f"Template '{self.template_name}' not found"
            }
        
        # Get custom fields
        custom_fields = self._get_custom_mandatory_fields()
        
        if not custom_fields:
            return {
                "success": True,
                "message": "No custom mandatory fields found",
                "added": 0,
                "skipped": 0
            }
        
        # Load template
        self.template = frappe.get_doc(self.DOCTYPE_TEMPLATE, self.template_name)
        
        # Get existing field names
        existing_fields = {field.fieldname for field in self.template.fields}
        
        # Add missing fields
        added_count = 0
        skipped_count = 0
        
        for cf in custom_fields:
            if cf.fieldname in existing_fields:
                skipped_count += 1
                frappe.log_error(
                    title="Template field already exists",
                    message=f"Field '{cf.fieldname}' already exists in template '{self.template_name}'"
                )
                continue
            
            # Add field to template
            self._add_field_to_template(cf)
            added_count += 1
        
        # Save template if fields were added
        if added_count > 0:
            self.template.save(ignore_permissions=True)
            frappe.db.commit()
        
        return {
            "success": True,
            "message": f"Sync completed: {added_count} field(s) added, {skipped_count} skipped",
            "added": added_count,
            "skipped": skipped_count,
            "fields": [cf.fieldname for cf in custom_fields]
        }
    
    def _get_custom_mandatory_fields(self):
        """
        Fetch all custom mandatory fields from HD Ticket.
        
        Returns:
            list: List of custom field dictionaries
        """
        return frappe.get_all(
            self.DOCTYPE_CUSTOM_FIELD,
            filters={
                "dt": self.DOCTYPE_TICKET,
                "reqd": 1  # Only mandatory fields
            },
            fields=[
                "fieldname",
                "label",
                "fieldtype",
                "options",
                "idx",
                "insert_after",
                "description"
            ],
            order_by="idx"
        )
    
    def _add_field_to_template(self, custom_field):
        """
        Add a custom field to the template.
        
        Args:
            custom_field: Custom field document/dict
        """
        self.template.append("fields", {
            "fieldname": custom_field.fieldname,
            "required": 1,  # Make it required in template
            "hide_from_customer": 0,  # Show to customers by default
            "idx": custom_field.idx or 0,
            # Note: label, fieldtype, options come from the actual Custom Field
            # via the API join query in hd_ticket_template/api.py
        })
        
        frappe.logger().info(f"Added field '{custom_field.fieldname}' to template '{self.template_name}'")
    
    def remove_field_from_template(self, fieldname):
        """
        Remove a specific field from the template.
        
        Args:
            fieldname: Field name to remove
            
        Returns:
            dict: Operation result
        """
        if not self.template:
            self.template = frappe.get_doc(self.DOCTYPE_TEMPLATE, self.template_name)
        
        # Find and remove the field
        for field in self.template.fields:
            if field.fieldname == fieldname:
                self.template.remove(field)
                self.template.save(ignore_permissions=True)
                frappe.db.commit()
                
                return {
                    "success": True,
                    "message": f"Removed field '{fieldname}' from template"
                }
        
        return {
            "success": False,
            "message": f"Field '{fieldname}' not found in template"
        }
    
    def get_template_fields_info(self):
        """
        Get information about all fields in the template.
        
        Returns:
            dict: Template field information
        """
        if not self.template:
            self.template = frappe.get_doc(self.DOCTYPE_TEMPLATE, self.template_name)
        
        return {
            "template_name": self.template_name,
            "total_fields": len(self.template.fields),
            "fields": [
                {
                    "fieldname": f.fieldname,
                    "required": f.required,
                    "hide_from_customer": f.hide_from_customer,
                    "idx": f.idx
                }
                for f in self.template.fields
            ]
        }


@frappe.whitelist()
def sync_helpdesk_template_fields(template_name="Default"):
    """
    API endpoint to manually trigger field synchronization.
    
    Args:
        template_name: Name of the template to sync (default: "Default")
        
    Returns:
        dict: Sync operation result
    """
    manager = HelpdeskTemplateSyncManager(template_name)
    return manager.sync_custom_fields()


@frappe.whitelist()
def get_helpdesk_template_info(template_name="Default"):
    """
    API endpoint to get template field information.
    
    Args:
        template_name: Name of the template (default: "Default")
        
    Returns:
        dict: Template field information
    """
    manager = HelpdeskTemplateSyncManager(template_name)
    return manager.get_template_fields_info()


def auto_sync_on_custom_field_change(doc, method):
    """
    Hook function to automatically sync when custom fields are added/modified.
    Should be called via doc_events hook on Custom Field doctype.
    
    Args:
        doc: Custom Field document
        method: Method name (after_insert, after_save, etc.)
    """
    # Only sync if it's a mandatory field for HD Ticket
    if doc.dt == "HD Ticket" and doc.reqd == 1:
        manager = HelpdeskTemplateSyncManager()
        result = manager.sync_custom_fields()
        
        frappe.logger().info(f"Auto-sync triggered for field '{doc.fieldname}': {result.get('message')}")
