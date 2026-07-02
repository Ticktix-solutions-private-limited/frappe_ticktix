"""
Helpdesk Plugin Setup Script

Run this after installing Helpdesk app to set up the integration.
"""
import frappe


def setup_helpdesk_plugin():
    """
    Initial setup for Helpdesk plugin.
    Creates default template if needed and syncs custom fields.
    """
    print("=== Helpdesk Plugin Setup ===\n")
    
    # Check if Helpdesk is installed
    if not frappe.db.exists("DocType", "HD Ticket"):
        print("❌ Helpdesk app is not installed")
        print("   Run: bench --site <site-name> install-app helpdesk")
        return
    
    print("✅ Helpdesk app is installed\n")
    
    # Check if Default template exists
    if not frappe.db.exists("HD Ticket Template", "Default"):
        print("⚠️  Default HD Ticket Template not found")
        print("   Creating default template...")
        create_default_template()
    else:
        print("✅ Default template exists\n")
    
    # Sync custom fields
    print("Syncing custom mandatory fields...")
    from frappe_ticktix.plugins.helpdesk.template_sync import sync_helpdesk_template_fields
    
    result = sync_helpdesk_template_fields()
    
    if result.get("success"):
        print(f"✅ {result.get('message')}")
        if result.get("fields"):
            print(f"   Fields: {', '.join(result.get('fields'))}")
    else:
        print(f"❌ {result.get('message')}")
    
    print("\n=== Setup Complete ===")


def create_default_template():
    """
    Create a default HD Ticket Template if it doesn't exist.
    """
    template = frappe.get_doc({
        "doctype": "HD Ticket Template",
        "template_name": "Default",
        "about": "Default ticket template for TickTix customizations"
    })
    
    template.insert(ignore_permissions=True)
    frappe.db.commit()
    
    print("✅ Created Default template\n")


if __name__ == "__main__":
    setup_helpdesk_plugin()
