"""
User Mapping for JWT Authentication

This module handles mapping between JWT claims from IdentityServer and Frappe users,
including auto-provisioning and session management for API requests.
"""

import frappe
from frappe.utils import cstr, get_datetime, now
from frappe.auth import LoginManager


def setup_api_user_session(jwt_payload):
    """
    Set up Frappe user session for API request based on JWT claims.
    
    This function:
    1. Maps JWT claims to existing Frappe user
    2. Creates temporary API session context (stateless)  
    3. Handles auto-provisioning if enabled
    4. Sets proper user context for API request
    
    Args:
        jwt_payload (dict): Decoded JWT payload with user information
    """
    # Extract user identifiers from JWT
    user_email = jwt_payload.get('email')
    user_sub = jwt_payload.get('sub')
    user_username = jwt_payload.get('preferred_username') or jwt_payload.get('username')
    
    if not user_email and not user_sub:
        frappe.throw("JWT token missing user identifier (email or sub)", frappe.AuthenticationError)
    
    # Find existing Frappe user
    frappe_user = find_existing_frappe_user(jwt_payload)
    
    if not frappe_user:
        # User not found - check if we should auto-provision
        if should_auto_provision_user(jwt_payload):
            frappe_user = auto_provision_jwt_user(jwt_payload)
        else:
            user_email = jwt_payload.get('email', 'Unknown')
            user_sub = jwt_payload.get('sub', 'Unknown')
            frappe.logger().warning(f"JWT authentication failed - user not found in system: email={user_email}, sub={user_sub}")
            frappe.throw("User not found. Please contact administrator to create your account.", frappe.AuthenticationError)
    
    # Validate user is enabled
    user_doc = frappe.get_doc("User", frappe_user)
    if not user_doc.enabled:
        frappe.throw("User account is disabled", frappe.PermissionError)
    
    # Set user session for this request
    # Use Frappe's LoginManager to create a proper session context for this request
    try:
        login_manager = LoginManager()
        # login_as will create session_obj and set frappe.local.session appropriately
        login_manager.login_as(frappe_user)
    except Exception:
        # Fallback to minimal session setup if LoginManager cannot be used in this context
        frappe.set_user(frappe_user)
        if not hasattr(frappe.local, 'session') or not frappe.local.session:
            frappe.local.session = frappe._dict()
        if not hasattr(frappe.local.session, 'data') or not frappe.local.session.data:
            frappe.local.session.data = frappe._dict()
        frappe.local.session.user = frappe_user
        frappe.local.session.sid = frappe_user
        if not hasattr(frappe.local, 'login_manager') or not frappe.local.login_manager:
            frappe.local.login_manager = frappe._dict()
        frappe.local.login_manager.user = frappe_user
        frappe.local.user_perms = None
        frappe.local.role_permissions = {}
        frappe.get_user()
    
    # Store JWT info for potential use by API endpoints
    frappe.local.jwt_user_info = jwt_payload
    frappe.local.jwt_authenticated = True
    
    # Log successful API authentication with role info
    user_roles = frappe.get_roles(frappe_user)
    frappe.logger().info(f"[JWT_USER_MAPPER] JWT API auth successful for user: {frappe_user}, roles: {user_roles}")


def find_existing_frappe_user(jwt_payload):
    """
    Find existing Frappe user based on JWT claims.
    
    Search order:
    1. By TickTix social login mapping (sub claim)
    2. By email address
    3. By username (if configured)
    
    Args:
        jwt_payload (dict): Decoded JWT payload
        
    Returns:
        str: Frappe user name/email or None if not found
    """
    user_email = jwt_payload.get('email')
    user_sub = jwt_payload.get('sub')
    user_username = jwt_payload.get('preferred_username') or jwt_payload.get('username')
    
    # Method 1: Try to find by TickTix social login mapping first (most reliable)
    if user_sub:
        social_login_user = frappe.db.get_value("User Social Login",
                                               {"provider": "ticktix", "userid": user_sub},
                                               "parent")
        if social_login_user and frappe.db.exists("User", {"name": social_login_user, "enabled": 1}):
            frappe.logger().debug(f"Found user by TickTix mapping: {social_login_user} (sub: {user_sub})")
            return social_login_user
    # Method 2: Try to find by email
    if user_email:
        email_user = frappe.db.get_value("User", {"email": user_email, "enabled": 1}, "name")
        if email_user:
            frappe.logger().debug(f"Found user by email: {email_user}")
            # Update social login mapping if we have sub claim
            if user_sub:
                try:
                    update_social_login_mapping(email_user, user_sub, user_email)
                except Exception as e:
                    frappe.log_error(title="Social login mapping failed", message=f"Failed to update mapping for {email_user}: {str(e)}")
            return email_user
    
    # Method 3: Try to find by username (if enabled in configuration)
    config = get_jwt_config()
    if config.get('allow_username_mapping', False) and user_username:
        username_user = frappe.db.get_value("User", {"username": user_username, "enabled": 1}, "name")
        if username_user:
            frappe.logger().debug(f"Found user by username: {username_user}")
            # Update social login mapping if we have sub claim
            if user_sub:
                try:
                    update_social_login_mapping(username_user, user_sub, user_email or user_username)
                except Exception as e:
                    frappe.log_error(title="Social login mapping failed", message=f"Failed to update mapping for {username_user}: {str(e)}")
            return username_user
    
    frappe.logger().debug(f"No existing user found for JWT claims: email={user_email}, sub={user_sub}, username={user_username}")
    return None


def update_social_login_mapping(frappe_user, ticktix_user_id, username):
    """
    Create or update TickTix social login mapping for a user.
    
    Args:
        frappe_user (str): Frappe user name/email
        ticktix_user_id (str): TickTix user ID (sub claim)
        username (str): Username for the mapping
    """
    try:
        user_doc = frappe.get_doc("User", frappe_user)
        
        # Check if mapping already exists
        existing_mapping = user_doc.get_social_login_userid('ticktix')
        
        if existing_mapping and existing_mapping == ticktix_user_id:
            # Mapping already correct
            return
        
        if existing_mapping and existing_mapping != ticktix_user_id:
            # Update existing mapping
            for social_login in user_doc.social_logins:
                if social_login.provider == 'ticktix':
                    social_login.userid = ticktix_user_id
                    social_login.username = username
                    break
            frappe.logger().info(f"Updated TickTix mapping for {frappe_user}: {existing_mapping} -> {ticktix_user_id}")
        else:
            # Create new mapping
            user_doc.set_social_login_userid('ticktix', userid=ticktix_user_id, username=username)
            frappe.logger().info(f"Created TickTix mapping for {frappe_user}: {ticktix_user_id}")
        
        # Save the mapping
        user_doc.flags.ignore_permissions = True
        user_doc.save()
        frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(title="Social login sync failed", message=f"Error mapping {frappe_user} to {ticktix_user_id}: {str(e)}")
        raise


def should_auto_provision_user(jwt_payload):
    """
    Check if user should be auto-provisioned based on JWT claims and configuration.
    
    Note: Auto-provisioning is disabled for security. Only existing Frappe users 
    created by administrators can authenticate via JWT.
    
    Args:
        jwt_payload (dict): Decoded JWT payload
        
    Returns:
        bool: Always False - auto-provisioning disabled
    """
    config = get_jwt_config()
    
    # Auto-provisioning is disabled for security - only existing users allowed
    if not config.get('auto_provision_users', False):
        frappe.logger().debug("Auto-provisioning disabled - user must exist in Frappe system")
        return False
    
    # Must have valid email
    user_email = jwt_payload.get('email')
    if not user_email or '@' not in user_email:
        frappe.logger().debug("Auto-provision rejected: no valid email in JWT")
        return False
    
    # Email domain restrictions removed - allow any email provider
    # Users must still exist in Frappe system (auto-provisioning disabled)
    
    # Check required claims
    required_claims = config.get('required_claims_for_provisioning', [])
    for claim in required_claims:
        if not jwt_payload.get(claim):
            frappe.logger().debug(f"Auto-provision rejected: missing required claim {claim}")
            return False
    
    # Check role/scope requirements
    required_roles = config.get('required_roles_for_provisioning', [])
    if required_roles:
        user_roles = jwt_payload.get('role', []) or jwt_payload.get('roles', [])
        if isinstance(user_roles, str):
            user_roles = [user_roles]
        
        if not any(role in user_roles for role in required_roles):
            frappe.logger().debug(f"Auto-provision rejected: user roles {user_roles} don't match required {required_roles}")
            return False
    
    frappe.logger().debug(f"Auto-provision approved for {user_email}")
    return True


def auto_provision_jwt_user(jwt_payload):
    """
    Auto-provision a new Frappe user based on JWT claims.
    
    Args:
        jwt_payload (dict): Decoded JWT payload
        
    Returns:
        str: Frappe user name/email
    """
    user_email = jwt_payload.get('email')
    user_sub = jwt_payload.get('sub')
    
    if not user_email:
        frappe.throw("Cannot auto-provision user without email", frappe.ValidationError)
    
    # Check if user was created by another concurrent request
    existing_user = frappe.db.get_value("User", {"email": user_email}, "name")
    if existing_user:
        frappe.logger().info(f"User {user_email} was created by another process during auto-provision")
        if user_sub:
            update_social_login_mapping(existing_user, user_sub, user_email)
        return existing_user
    
    try:
        # Extract user information from JWT
        first_name = (jwt_payload.get('given_name') or 
                     jwt_payload.get('first_name') or 
                     jwt_payload.get('name', '').split()[0] if jwt_payload.get('name') else '' or
                     user_email.split('@')[0])
        
        last_name = (jwt_payload.get('family_name') or 
                    jwt_payload.get('last_name') or
                    ' '.join(jwt_payload.get('name', '').split()[1:]) if jwt_payload.get('name') else '')
        
        full_name = (jwt_payload.get('name') or 
                    f"{first_name} {last_name}".strip() or 
                    user_email)
        
        # Determine user type based on configuration and JWT claims
        config = get_jwt_config()
        default_user_type = config.get('default_user_type', 'System User')
        
        # Check if JWT has role information to determine user type
        user_roles = jwt_payload.get('role', []) or jwt_payload.get('roles', [])
        if isinstance(user_roles, str):
            user_roles = [user_roles]
        
        # Map JWT roles to Frappe user types (configurable)
        role_to_user_type = config.get('role_to_user_type_mapping', {})
        user_type = default_user_type
        for jwt_role in user_roles:
            if jwt_role in role_to_user_type:
                user_type = role_to_user_type[jwt_role]
                break
        
        # Create new user document
        user_doc = frappe.get_doc({
            "doctype": "User",
            "email": user_email,
            "first_name": first_name,
            "last_name": last_name, 
            "full_name": full_name,
            "user_type": user_type,
            "enabled": 1,
            "send_welcome_email": 0,  # Don't send welcome email for API users
            "new_password": frappe.generate_hash()  # Generate random password
        })
        
        # Add username if provided
        username = jwt_payload.get('preferred_username') or jwt_payload.get('username')
        if username:
            user_doc.username = username
        
        # Insert user (this will trigger existing auto_provision_user hook for TickTix IDP)
        user_doc.insert(ignore_permissions=True)
        
        # Create TickTix social login mapping if we have sub claim
        if user_sub:
            user_doc.set_social_login_userid('ticktix', userid=user_sub, username=user_email)
            user_doc.save(ignore_permissions=True)
        
        # Assign roles based on JWT claims
        assign_roles_from_jwt(user_doc, jwt_payload)
        
        frappe.db.commit()
        
        frappe.logger().info(f"Auto-provisioned JWT user: {user_email} (Type: {user_type})")
        return user_email
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="User provisioning failed", message=f"Error provisioning {user_email}: {str(e)}")
        frappe.throw(f"Failed to create user account: {str(e)}", frappe.ValidationError)


def assign_roles_from_jwt(user_doc, jwt_payload):
    """
    Assign Frappe roles to user based on JWT claims.
    
    Args:
        user_doc: Frappe User document
        jwt_payload (dict): Decoded JWT payload
    """
    config = get_jwt_config()
    
    # Default roles for auto-provisioned users
    default_roles = config.get('default_roles', ['Desk User'])
    
    # JWT role to Frappe role mapping
    jwt_role_mapping = config.get('jwt_role_mapping', {})
    
    # Extract roles from JWT
    jwt_roles = jwt_payload.get('role', []) or jwt_payload.get('roles', [])
    if isinstance(jwt_roles, str):
        jwt_roles = [jwt_roles]
    
    # Determine Frappe roles to assign
    roles_to_assign = set(default_roles)
    
    for jwt_role in jwt_roles:
        if jwt_role in jwt_role_mapping:
            mapped_roles = jwt_role_mapping[jwt_role]
            if isinstance(mapped_roles, str):
                mapped_roles = [mapped_roles]
            roles_to_assign.update(mapped_roles)
    
    # Assign roles
    for role in roles_to_assign:
        if frappe.db.exists("Role", role):
            user_doc.add_roles(role)
        else:
            frappe.log_error(title="Role not found", message=f"Role '{role}' does not exist for user {user_doc.email}")


def get_jwt_config():
    """Get JWT configuration (imports from jwt_validator to avoid circular imports)."""
    from .jwt_validator import get_jwt_config as validator_get_jwt_config
    return validator_get_jwt_config()


def get_current_jwt_user():
    """
    Get current user information if authenticated via JWT.
    
    Returns:
        dict: User information or None if not JWT authenticated
    """
    return getattr(frappe.local, 'jwt_user_info', None)


def is_jwt_authenticated():
    """
    Check if current request was authenticated via JWT.
    
    Returns:
        bool: True if authenticated via JWT
    """
    return getattr(frappe.local, 'jwt_authenticated', False)


@frappe.whitelist()
def get_jwt_user_info():
    """
    API endpoint to get current JWT user information.
    
    Returns:
        dict: JWT user information if available
    """
    if not is_jwt_authenticated():
        frappe.throw("Not authenticated via JWT", frappe.PermissionError)
    
    jwt_info = get_current_jwt_user()
    
    # Return safe subset of JWT claims
    safe_claims = [
        'sub', 'email', 'name', 'given_name', 'family_name', 
        'preferred_username', 'roles', 'scope'
    ]
    
    return {claim: jwt_info.get(claim) for claim in safe_claims if claim in jwt_info}


@frappe.whitelist()
def sync_jwt_user_data():
    """
    API endpoint to sync current user data from JWT claims.
    This can be called to update user information based on latest JWT token.
    """
    if not is_jwt_authenticated():
        frappe.throw("Not authenticated via JWT", frappe.PermissionError)
    
    jwt_info = get_current_jwt_user()
    current_user = frappe.session.user
    
    try:
        user_doc = frappe.get_doc("User", current_user)
        
        # Update basic user information
        updated_fields = []
        
        if jwt_info.get('given_name') and jwt_info['given_name'] != user_doc.first_name:
            user_doc.first_name = jwt_info['given_name']
            updated_fields.append('first_name')
        
        if jwt_info.get('family_name') and jwt_info['family_name'] != user_doc.last_name:
            user_doc.last_name = jwt_info['family_name']
            updated_fields.append('last_name')
            
        if jwt_info.get('name') and jwt_info['name'] != user_doc.full_name:
            user_doc.full_name = jwt_info['name']
            updated_fields.append('full_name')
        
        if updated_fields:
            user_doc.save(ignore_permissions=True)
            frappe.db.commit()
            return {"status": "updated", "fields": updated_fields}
        else:
            return {"status": "no_changes"}
            
    except Exception as e:
        frappe.log_error(title="User sync failed", message=f"Error syncing {current_user}: {str(e)}")
        frappe.throw(f"Failed to sync user data: {str(e)}")


def cleanup_expired_sessions():
    """
    Cleanup function for expired JWT sessions (if needed).
    This is a placeholder for future session management features.
    """
    # JWT authentication is stateless, so no cleanup needed currently
    pass