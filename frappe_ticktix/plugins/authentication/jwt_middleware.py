# Module loaded - logging moved below imports to ensure 'frappe' is available
"""
JWT Authentication Middleware for Mobile/API Clients

This middleware extends Frappe's authentication system to support JWT Bearer tokens
from IdentityServer without impacting existing browser-based social login functionality.

Key Features:
- Only processes API requests (/api/*) with Authorization: Bearer headers
- Bypasses all browser requests (maintains existing Frappe session flow)  
- Validates JWT tokens against IdentityServer
- Maps JWT claims to existing Frappe users
- Creates temporary API session context (stateless)
- Coexists with existing TickTix social login for browsers
"""

import frappe
import jwt
import json
import requests
from frappe.auth import LoginManager
from frappe.utils import cstr, get_datetime

# Log module load after frappe is imported
frappe.logger().info("[JWT_MIDDLEWARE] jwt_middleware.py loaded (startup)")


def jwt_auth_middleware():
    """
    JWT authentication middleware for API requests.
    
    This function is called before each request via hooks.py.
    It only processes API requests that have Authorization: Bearer headers.
    All other requests (browser, standard Frappe auth) pass through unchanged.
    """
    frappe.logger().info("[JWT_MIDDLEWARE] jwt_auth_middleware called (entry)")
    # Skip if not a web request
    if not hasattr(frappe.local, 'request'):
        return
    
    request = frappe.local.request
    path = request.path
    
    # Only process API endpoints
    if not path.startswith('/api/'):
        return
    
    # Check for Authorization header with Bearer token
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return
    
    # Extract JWT token
    token = auth_header[7:]  # Remove 'Bearer ' prefix
    
    try:
        # Validate JWT and authenticate user
        user_info = validate_jwt_token(token)
        if user_info:
            frappe.logger().info(f"[JWT_MIDDLEWARE] setup_api_user_session called for user_info: {user_info.get('email', user_info.get('sub', 'unknown'))}")
            # Set user context for this API request
            setup_api_user_session(user_info)
        else:
            # Invalid token - return 401
            frappe.throw("Invalid or expired JWT token", frappe.AuthenticationError)
            
    except jwt.ExpiredSignatureError:
        frappe.throw("JWT token has expired", frappe.AuthenticationError)
    except jwt.InvalidTokenError as e:
        frappe.throw(f"Invalid JWT token: {str(e)}", frappe.AuthenticationError)
    except Exception as e:
        frappe.log_error(title="JWT auth error", message=f"JWT Middleware Error: {str(e)}")
        frappe.throw("Authentication failed", frappe.AuthenticationError)


def validate_jwt_token(token):
    """
    Validate JWT token against IdentityServer configuration.
    
    Args:
        token (str): JWT token string
        
    Returns:
        dict: User information from JWT claims or None if invalid
    """
    # Import here to avoid circular imports
    from .jwt_validator import validate_jwt_token as validator_validate_jwt_token
    
    try:
        return validator_validate_jwt_token(token)
    except jwt.ExpiredSignatureError:
        raise
    except jwt.InvalidTokenError:
        raise
    except Exception as e:
        frappe.log_error(title="JWT validation failed", message=f"JWT validation error: {str(e)}")
        return None


def get_jwt_config():
    """
    Get JWT configuration from site config and TickTix Settings.
    
    Returns:
        dict: JWT configuration settings
    """
    # Import here to avoid circular imports
    from .jwt_validator import get_jwt_config as validator_get_jwt_config
    
    return validator_get_jwt_config()


def setup_api_user_session(jwt_payload):
    """
    Set up Frappe user session for API request based on JWT claims.
    
    Args:
        jwt_payload (dict): Decoded JWT payload with user information
    """
    # Import here to avoid circular imports
    from .user_mapper import setup_api_user_session as mapper_setup_session
    
    return mapper_setup_session(jwt_payload)


# These functions are now handled by user_mapper module
# Keeping stubs for backward compatibility

def should_auto_provision_user(jwt_payload):
    """Stub - functionality moved to user_mapper module."""
    from .user_mapper import should_auto_provision_user as mapper_should_auto_provision
    return mapper_should_auto_provision(jwt_payload)


def auto_provision_jwt_user(jwt_payload):
    """Stub - functionality moved to user_mapper module."""
    from .user_mapper import auto_provision_jwt_user as mapper_auto_provision
    return mapper_auto_provision(jwt_payload)


def get_current_jwt_user():
    """Stub - functionality moved to user_mapper module."""
    from .user_mapper import get_current_jwt_user as mapper_get_current_user
    return mapper_get_current_user()