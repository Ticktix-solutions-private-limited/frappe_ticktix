import frappe


def get_social_login_providers():
    """Return TickTix provider details compatible with Frappe's social login list.

    This will be used by the frontend to show social login buttons.
    """
    from ...config.config_manager import get_auth_config, get_config_manager, require_org_id, ensure_org_scope

    auth_config = get_auth_config()
    is_zitadel = auth_config.get('ticktix_identity_provider', 'zitadel') == 'zitadel'
    org_id = require_org_id(auth_config) if is_zitadel else None
    config_manager = get_config_manager()

    client_id = auth_config.get('ticktix_client_id', 'ticktix')
    base_url = auth_config.get('ticktix_base_url', 'https://login.ticktix.com')
    authorize_path = auth_config.get('ticktix_authorize_url', '/oauth/v2/authorize')
    token_path = auth_config.get('ticktix_token_url', '/oauth/v2/token')
    
    # Get tenant param from OAuth config
    ticktix_config = config_manager.get_config_value('ticktix', {})
    tenant_param = ticktix_config.get('oauth', {}).get('tenant_param', 'tenant') if isinstance(ticktix_config, dict) else 'tenant'

    # Build full URLs by combining base URL with relative paths
    def build_full_url(base, path):
        if path.startswith('http'):
            return path  # Already a full URL
        else:
            return base.rstrip('/') + path
    
    authorize_url = build_full_url(base_url, authorize_path)
    token_url = build_full_url(base_url, token_path)

    # Use relative redirect URL - Frappe will automatically convert to absolute URL using site's base URL
    redirect_url = auth_config.get('ticktix_redirect_url_template', '/api/method/frappe.integrations.oauth2_logins.custom/ticktix')
    
    # Get auth params from OAuth config - a site may override ticktix.oauth.auth_params
    # for unrelated reasons (e.g. a custom prompt param), so the org-enforcement scope
    # is merged in unconditionally below rather than only applied to the default.
    # Only applies on Zitadel - IdentityServer4 doesn't understand the
    # urn:zitadel:iam:... scope tokens ensure_org_scope adds.
    default_auth_params = {"response_type": "code", "scope": "openid profile email"}
    auth_params = ticktix_config.get('oauth', {}).get('auth_params', default_auth_params) if isinstance(ticktix_config, dict) else default_auth_params
    if is_zitadel:
        auth_params = ensure_org_scope(auth_params, org_id)

    provider = {
        'name': 'ticktix',
        'label': 'TickTix',
        'client_id': client_id,
        'authorize_url': authorize_url,
        'token_url': token_url,
        'tenant_param': tenant_param,
        'auth_params': auth_params,
        'redirect_url': redirect_url
    }

    return [provider]
