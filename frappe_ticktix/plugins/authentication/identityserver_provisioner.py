"""
IdentityServer4 User Provisioning (login.ticktix.com)

Sibling backend to zitadel_provisioner.py, for sites whose
ticktix.identity_server.provider is "identityserver" instead of "zitadel".
IdentityServer4's admin API is a different product from Zitadel with a
different auth model, host, and payload shape, so it cannot share
zitadel_provisioner.py's request functions - only the dispatch in that
module and the shared _ensure_social_login_mapping() are common.

Endpoints and payload shapes below are taken from standalone_api_test.py,
the only prior working reference against this API. They have not been
re-verified against a live login.ticktix.com instance as part of this
change - confirm with one real create/search call before relying on this
in provision_existing_users bulk runs.
"""

import frappe
import requests

_TOKEN_CACHE_KEY = "ticktix_identityserver_api_token"
_TOKEN_EXPIRY_BUFFER_SEC = 60


def _get_token(config):
    """Get a cached client_credentials access token, refreshing if expired.

    Unlike Zitadel's long-lived PAT, IdentityServer4 issues short-lived
    (~1hr) tokens via client_credentials, so this can't be a static config
    value - it has to be fetched and cached per-request.
    """
    cached = frappe.cache().get_value(_TOKEN_CACHE_KEY)
    if cached:
        return cached

    client_id = config.get('api_client_id')
    client_secret = config.get('api_client_secret')
    if not client_id or not client_secret:
        frappe.throw(
            "IdentityServer API client credentials not configured. "
            "Set ticktix.api.client_id and ticktix.api.client_secret."
        )

    token_url = config['base_url'] + '/connect/token'
    import base64
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'client_credentials',
        'scope': config.get('api_scope') or 'identityserver_admin_api offline_access'
    }

    response = requests.post(token_url, headers=headers, data=data, timeout=15)
    response.raise_for_status()
    token_data = response.json()

    access_token = token_data['access_token']
    expires_in = int(token_data.get('expires_in', 3600))
    frappe.cache().set_value(
        _TOKEN_CACHE_KEY, access_token,
        expires_in_sec=max(expires_in - _TOKEN_EXPIRY_BUFFER_SEC, 30)
    )
    return access_token


def _headers(config):
    return {
        'Authorization': f'Bearer {_get_token(config)}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }


def search_user_by_email(config, email):
    """Search IdentityServer for a user by email. Returns the user id if found, else None.

    Response is {"pageSize", "totalCount", "users": [...]}, not a bare list -
    confirmed 2026-09-04 against authapi.ticktix.com.
    """
    api_base = config['provision_api']
    url = f"{api_base.rstrip('/')}/api/Users"
    response = requests.get(url, params={'searchText': email}, headers=_headers(config), timeout=15)
    response.raise_for_status()
    users = response.json().get('users', [])

    for user in users:
        if (user.get('email') or '').lower() == email.lower():
            return user.get('id')
    return None


def create_user(config, user_doc):
    """Create a user in IdentityServer, then set a password if configured. Returns the new user id.

    POST /api/Users (IdentityUserDto: userName/email/emailConfirmed) has no
    password field - confirmed against the live swagger spec at
    https://authapi.ticktix.com/swagger/v1/swagger.json 2026-09-04. A user
    created without a follow-up call has no credential at all and cannot
    log in (every attempt fails as invalid, incrementing accessFailedCount,
    rather than erroring visibly) - so when initial_password is configured
    this makes a second call to POST /api/Users/ChangePassword
    ({userId, password, confirmPassword}) right after creation.
    """
    api_base = config['provision_api']
    url = f"{api_base.rstrip('/')}/api/Users"

    payload = {
        'UserName': user_doc.email,
        'Email': user_doc.email,
        'EmailConfirmed': True
    }

    response = requests.post(url, json=payload, headers=_headers(config), timeout=15)
    response.raise_for_status()
    result = response.json() if response.content else {}
    user_id = result.get('id')

    initial_password = config.get('initial_password')
    if user_id and initial_password:
        set_password(config, user_id, initial_password)

    return user_id


def set_password(config, user_id, password):
    """Set a user's password via POST /api/Users/ChangePassword.

    Confirmed 2026-09-04: this is what actually activates a login-capable
    account - a user created by create_user() alone has no credential.
    """
    api_base = config['provision_api']
    url = f"{api_base.rstrip('/')}/api/Users/ChangePassword"
    payload = {
        'userId': user_id,
        'password': password,
        'confirmPassword': password
    }
    response = requests.post(url, json=payload, headers=_headers(config), timeout=15)
    response.raise_for_status()
