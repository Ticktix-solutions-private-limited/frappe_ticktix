"""
API endpoints for JWT authentication testing and mobile app integration.
"""

import frappe
from frappe_ticktix.plugins.authentication.user_mapper import is_jwt_authenticated, get_current_jwt_user
from ...config.config_manager import get_config_manager


@frappe.whitelist()
def test_jwt_auth():
    """
    Test endpoint to verify JWT authentication is working.
    
    Returns different information based on authentication method.
    """
    if is_jwt_authenticated():
        jwt_user = get_current_jwt_user()
        return {
            "status": "jwt_authenticated",
            "user": frappe.session.user,
            "authentication_method": "jwt",
            "jwt_claims": {
                "sub": jwt_user.get("sub"),
                "email": jwt_user.get("email"), 
                "name": jwt_user.get("name"),
                "roles": jwt_user.get("role") or jwt_user.get("roles")
            },
            "message": "Successfully authenticated via JWT token"
        }
    else:
        return {
            "status": "session_authenticated",
            "user": frappe.session.user,
            "authentication_method": "session",
            "message": "Authenticated via Frappe session (cookies)"
        }


@frappe.whitelist()
def get_user_profile():
    """
    Get current user profile information.
    Works with both JWT and session authentication.
    """
    user_doc = frappe.get_doc("User", frappe.session.user)
    
    profile = {
        "email": user_doc.email,
        "full_name": user_doc.full_name,
        "first_name": user_doc.first_name,
        "last_name": user_doc.last_name,
        "user_type": user_doc.user_type,
        "roles": [role.role for role in user_doc.roles],
        "authentication_method": "jwt" if is_jwt_authenticated() else "session"
    }
    
    # Add JWT-specific information if available
    if is_jwt_authenticated():
        jwt_user = get_current_jwt_user()
        profile["jwt_info"] = {
            "sub": jwt_user.get("sub"),
            "iss": jwt_user.get("iss"),
            "aud": jwt_user.get("aud"),
            "exp": jwt_user.get("exp"),
            "iat": jwt_user.get("iat")
        }
    
    return profile


@frappe.whitelist(allow_guest=True)
def mobile_api_info():
    """
    Get API configuration information for mobile applications.
    This endpoint helps mobile apps discover authentication endpoints.
    """
    config_manager = get_config_manager()
    auth_config = config_manager.get_auth_config()
    base_url = auth_config.get('ticktix_base_url', 'https://login.ticktix.com')
    
    return {
        "api_version": "1.0",
        "site": frappe.local.site,
        "server_info": {
            "frappe_version": frappe.__version__,
            "site_name": frappe.local.site
        },
        "authentication": {
            "jwt_enabled": auth_config.get('jwt_enabled', True),
            "methods_supported": ["jwt", "session"],
            "recommended_flow": "pkce",
            "mobile_client_id": "mobile-app"
        },
        "oauth_config": {
            "issuer": base_url,
            "audience": frappe.local.site,
            "auth_endpoint": base_url + auth_config.get('ticktix_authorize_url', '/connect/authorize'),
            "token_endpoint": base_url + auth_config.get('ticktix_token_url', '/connect/token'),
            "jwks_uri": base_url + "/.well-known/openid-configuration/jwks"
        },
        "api_endpoints": {
            "test_auth": "/api/method/frappe_ticktix.api.v1.jwt_api.test_jwt_auth",
            "user_profile": "/api/method/frappe_ticktix.api.v1.jwt_api.get_user_profile",
            "mobile_auth_url": "/api/method/frappe_ticktix.api.v1.jwt_api.get_mobile_auth_url"
        },
        "mobile_integration": {
            "redirect_uri_scheme": "com.yourapp://oauth/callback",
            "scopes": ["openid", "profile", "api"],
            "pkce_required": True
        }
    }
    

@frappe.whitelist(allow_guest=True, methods=["POST"])
def get_mobile_auth_url():
    """
    Generate mobile auth URL for PKCE flow (Alternative approach).
    
    Expects JSON payload:
    {
        "redirect_uri": "com.yourapp://oauth/callback",
        "state": "random_state_string"
    }
    """
    import base64
    import hashlib
    import os
    from urllib.parse import urlencode
    
    data = frappe.local.form_dict
    redirect_uri = data.get('redirect_uri')
    state = data.get('state')
    
    if not redirect_uri or not state:
        frappe.throw("Missing redirect_uri or state parameter")
    
    # Get configuration using ConfigManager
    config_manager = get_config_manager()
    auth_config = config_manager.get_auth_config()
    base_url = auth_config.get('ticktix_base_url', 'https://login.ticktix.com')
    
    # Generate PKCE parameters
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    
    # Store code_verifier temporarily (for token exchange if needed)
    frappe.cache().set(f"pkce_{state}", code_verifier, expires_in_sec=600)
    
    # Build auth URL parameters
    params = {
        'client_id': 'mobile-app',
        'response_type': 'code',
        'scope': 'openid profile api',
        'redirect_uri': redirect_uri,
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'audience': frappe.local.site
    }
    
    auth_url = f"{base_url}/connect/authorize?" + urlencode(params)
    
    return {
        'auth_url': auth_url,
        'code_challenge': code_challenge,
        'state': state,
        'issuer': base_url
    }


@frappe.whitelist(allow_guest=True)
def health_check():
    """
    Health check endpoint for monitoring.
    """
    return {
        "status": "ok",
        "timestamp": frappe.utils.now(),
        "version": "1.0"
    }