# JWT API module for frappe_ticktix

import frappe
from urllib.parse import urlencode
from ...config.config_manager import get_config_manager

@frappe.whitelist(allow_guest=True)
def ticktix_login(redirect_to=None, tenant=None, mobile=None):
    """Override /login to force redirect to TickTix IdentityServer."""
    
    # Check for pending logout cookie
    if frappe.request.cookies.get('ticktix_logout_pending'):
        frappe.local.cookie_manager.delete_cookie('ticktix_logout_pending')
        return ticktix_logout(redirect_to_idp=True)

    # Get TickTix settings using ConfigManager
    config_manager = get_config_manager()
    auth_config = config_manager.get_auth_config()

    client_id = auth_config.get('ticktix_client_id') or 'ticktix'
    base_url = auth_config.get('ticktix_base_url') or 'https://login.ticktix.com'
    authorize_path = auth_config.get('ticktix_authorize_url') or '/connect/authorize'
    tenant_param = 'tenant'  # Standard tenant parameter
    auth_params = {"response_type": "code", "scope": "openid profile email"}  # Standard OAuth params
    
    # Build full authorize URL
    if authorize_path.startswith('http'):
        # Already a full URL
        authorize_url = authorize_path
    else:
        # Relative path, combine with base URL
        authorize_url = base_url.rstrip('/') + authorize_path

    # Build redirect URI using Frappe's standard URL construction
    # This matches the same method used by Frappe's OAuth system
    redirect_uri_template = auth_config.get('ticktix_redirect_url_template') or '/api/method/frappe.integrations.oauth2_logins.custom/ticktix'
    redirect_uri = frappe.utils.get_url(redirect_uri_template)

    # Generate state and nonce for CSRF protection
    state_data = {
        'token': frappe.generate_hash(),
        'redirect_to': redirect_to,
        'mobile': mobile
    }
    
    import base64
    import json
    state = base64.b64encode(json.dumps(state_data).encode()).decode()

    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'state': state,
        'nonce': frappe.generate_hash(),
    }
    params.update(auth_params)

    # Add tenant parameter only if explicitly provided (for mobile apps)
    if tenant:
        params[tenant_param] = tenant

    url = authorize_url + ('?' + urlencode(params))

    if mobile:
        # For mobile app, return the URL instead of redirecting
        return {'login_url': url, 'tenant': tenant if tenant else 'default'}
    else:
        # For web, redirect directly
        frappe.local.response['type'] = 'redirect'
        frappe.local.response['location'] = url
        return ''


@frappe.whitelist(allow_guest=True)
def mobile_login(tenant_domain):
    """Mobile app login endpoint that returns TickTix login URL with tenant."""
    return ticktix_login(mobile=True, tenant=tenant_domain)


@frappe.whitelist()
def mobile_logout():
    """Mobile app logout endpoint that clears session and returns logout info."""
    # For mobile apps using JWT, logout is client-side (delete token from storage)
    # But we can provide useful logout info and clear any server-side session if exists
    
    try:
        current_user = frappe.session.user
        
        # Clear server-side session if exists (for hybrid auth scenarios)
        if hasattr(frappe.local, 'session'):
            frappe.local.session.user = 'Guest'
            
        return {
            'status': 'success',
            'message': 'Logout successful',
            'user_logged_out': current_user,
            'instructions': {
                'mobile_apps': 'Delete JWT token from secure storage',
                'next_steps': 'User must authenticate again to access protected resources'
            }
        }
    except Exception as e:
        frappe.log_error(f"Mobile logout error: {str(e)}", "Mobile Logout")
        return {
            'status': 'error',
            'message': 'Logout failed',
            'error': str(e)
        }


def force_ticktix_login():
    """Before-request hook to redirect authentication-related paths to TickTix for website requests."""
    try:
        path = frappe.local.request.path
    except Exception:
        path = None

    if path:
        # Handle both login and logout paths
        clean_path = path.rstrip('/')
        if clean_path == '/login':
            return ticktix_login()
        elif clean_path == '/logout':
            return ticktix_logout()


@frappe.whitelist(allow_guest=True)
def ticktix_logout(redirect_to_idp=False):
    """
    Override /logout to clear Frappe session and redirect to TickTix IdentityServer logout.
    """
    # Clear Frappe session
    if frappe.session.user != "Guest":
        frappe.local.login_manager.logout()
        frappe.db.commit()
    
    # Get TickTix settings
    config_manager = get_config_manager()
    auth_config = config_manager.get_auth_config()
    
    base_url = auth_config.get('ticktix_base_url') or 'https://login.ticktix.com'
    endsession_path = auth_config.get('ticktix_endsession_url') or '/connect/endsession'
    
    # Build full endsession URL
    if endsession_path.startswith('http'):
        endsession_url = endsession_path
    else:
        endsession_url = base_url.rstrip('/') + endsession_path
        
    # Add post_logout_redirect_uri to return to the app after logout
    # We redirect back to the base URL of the app
    post_logout_redirect_uri = frappe.utils.get_url()
    
    # IdentityServer usually expects 'post_logout_redirect_uri'
    params = {
        'post_logout_redirect_uri': post_logout_redirect_uri
    }
    
    url = endsession_url + ('?' + urlencode(params))
    
    # Handle AJAX requests (e.g. from Desk)
    # If we redirect an AJAX request, the browser follows it in the background (CORS issue)
    # Instead, we set a cookie and let the client reload. The reload will hit /login,
    # which will see the cookie and redirect to the IdP logout URL.
    is_ajax = frappe.request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if not redirect_to_idp and is_ajax:
        frappe.local.cookie_manager.set_cookie('ticktix_logout_pending', '1')
        return {'message': 'Logged out'}

    frappe.local.response['type'] = 'redirect'
    frappe.local.response['location'] = url
    return ''