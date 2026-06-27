"""
Employee ID Generator utilities
"""

import frappe


@frappe.whitelist()
def get_ui_settings():
    """Return settings needed for client-side UI behavior."""
    ticktix_config = frappe.conf.get("ticktix", {})
    settings = ticktix_config.get("hr_employee_id_settings", {})

    return {
        "enabled": bool(settings.get("enabled", False)),
        "allow_manual_override": bool(settings.get("allow_manual_override", False)),
    }
