"""
BACKWARD COMPATIBILITY LAYER - Manual Cleanup
Functionality moved to utils.manual_cleanup
"""

# Import everything from new location for backward compatibility
try:
    from .utils.manual_cleanup import *
    
    import frappe
    frappe.logger().info("Successfully imported manual_cleanup from utils")
    
except ImportError as e:
    import frappe
    frappe.log_error(f"Failed to import manual_cleanup from utils: {e}", "Manual Cleanup Compatibility")