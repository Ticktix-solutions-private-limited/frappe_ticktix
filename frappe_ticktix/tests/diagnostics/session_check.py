"""
Simple diagnostic endpoint to check session state
"""

import frappe
from frappe import _


@frappe.whitelist()
def check_session_state():
    """
    Check the current session state and initialization.
    Returns detailed information about session, roles, and permissions.
    """
    user = frappe.session.user
    
    # Check session attributes
    session_info = {
        "has_session": hasattr(frappe.local, 'session'),
        "session_type": str(type(frappe.local.session)) if hasattr(frappe.local, 'session') else None,
        "has_session_data": hasattr(frappe.local.session, 'data') if hasattr(frappe.local, 'session') else False,
        "session_user": getattr(frappe.local.session, 'user', None) if hasattr(frappe.local, 'session') else None,
        "session_sid": getattr(frappe.local.session, 'sid', None) if hasattr(frappe.local, 'session') else None,
    }
    
    # Check login_manager
    login_manager_info = {
        "has_login_manager": hasattr(frappe.local, 'login_manager'),
        "login_manager_type": str(type(frappe.local.login_manager)) if hasattr(frappe.local, 'login_manager') else None,
        "login_manager_user": getattr(frappe.local.login_manager, 'user', None) if hasattr(frappe.local, 'login_manager') else None,
    }
    
    # Check permissions
    permission_info = {
        "has_user_perms": hasattr(frappe.local, 'user_perms'),
        "user_perms_value": frappe.local.user_perms if hasattr(frappe.local, 'user_perms') else None,
        "has_role_permissions": hasattr(frappe.local, 'role_permissions'),
        "role_permissions_count": len(frappe.local.role_permissions) if hasattr(frappe.local, 'role_permissions') else 0,
    }
    
    # Get user roles
    try:
        roles = frappe.get_roles(user)
    except Exception as e:
        roles = f"Error getting roles: {str(e)}"
    
    # Check JWT authentication
    jwt_info = {
        "jwt_authenticated": getattr(frappe.local, 'jwt_authenticated', False),
        "has_jwt_user_info": hasattr(frappe.local, 'jwt_user_info'),
    }
    
    # Check Attendance permissions
    attendance_perms = {
        "has_read": frappe.has_permission("Attendance", "read"),
        "has_select": frappe.has_permission("Attendance", "select"),
        "only_select": frappe.only_has_select_perm("Attendance"),
    }
    
    # Get permitted fields for Attendance
    try:
        from frappe.model import get_permitted_fields
        permitted_fields = get_permitted_fields("Attendance", permission_type="read")
    except Exception as e:
        permitted_fields = f"Error: {str(e)}"
    
    return {
        "user": user,
        "session_info": session_info,
        "login_manager_info": login_manager_info,
        "permission_info": permission_info,
        "jwt_info": jwt_info,
        "roles": roles,
        "roles_count": len(roles) if isinstance(roles, list) else 0,
        "attendance_permissions": attendance_perms,
        "permitted_fields_for_attendance": {
            "count": len(permitted_fields) if isinstance(permitted_fields, list) else 0,
            "fields": permitted_fields[:10] if isinstance(permitted_fields, list) else permitted_fields
        }
    }
