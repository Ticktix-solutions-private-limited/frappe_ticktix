"""
Centralized configuration manager for frappe_ticktix
Handles reading from site_config.json and common_site_config.json with proper hierarchy
"""

import frappe
import json
import os
from typing import Any, Optional, Dict


class ConfigManager:
    """Centralized configuration management with proper hierarchy"""
    
    def __init__(self):
        self._cache = {}
        self._cache_timeout = 300  # 5 minutes
        self._last_cache_time = 0
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with hierarchy: common_site_config.json merged with site_config.json
        Site config properties override common config properties
        
        Args:
            key: Configuration key to fetch
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        try:
            # Check cache first
            if self._is_cache_valid() and key in self._cache:
                return self._cache.get(key, default)
            
            # Refresh cache if needed
            if not self._is_cache_valid():
                self._refresh_cache()
            
            # Start with common config (base)
            common_config = self._get_common_site_config()
            common_value = common_config.get(key)
            
            # Get site config (override)
            site_config = self._get_site_config()
            site_value = site_config.get(key)
            
            # If both exist and are dicts, merge them (site overrides common)
            if isinstance(common_value, dict) and isinstance(site_value, dict):
                merged_value = self._deep_merge(common_value, site_value)
                self._cache[key] = merged_value
                return merged_value
            
            # If site has the value, use it (override)
            if site_value is not None:
                self._cache[key] = site_value
                return site_value
            
            # Fall back to common config
            if common_value is not None:
                self._cache[key] = common_value
                return common_value
            
            # Cache the default value
            self._cache[key] = default
            return default
            
        except Exception as e:
            frappe.log_error(f"Error reading config for {key}: {e}", "Config Manager")
            return default
    
    def _get_common_site_config(self) -> dict:
        """Read common_site_config.json directly from file"""
        try:
            sites_path = frappe.get_site_path('..')
            common_config_path = os.path.join(sites_path, 'common_site_config.json')
            
            if os.path.exists(common_config_path):
                with open(common_config_path, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            frappe.log_error(f"Error reading common_site_config.json: {e}", "Config Manager")
            return {}
    
    def _deep_merge(self, base: dict, override: dict) -> dict:
        """
        Deep merge two dictionaries, with override taking priority
        
        Args:
            base: Base dictionary
            override: Override dictionary (takes priority)
            
        Returns:
            Merged dictionary
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def get_branding_config(self) -> Dict[str, Any]:
        """Get all branding-related configuration from grouped structure"""
        # Try new grouped structure first, fallback to old flat structure
        ticktix_config = self.get_config_value('ticktix', {})
        website_settings = ticktix_config.get('website_settings', {})
        
        return {
            'company_logo': website_settings.get('company_logo', 'https://login.ticktix.com/images/ticktix.jpg'),
            'app_name': website_settings.get('app_name', 'Facilitix'),
            'app_title': website_settings.get('app_title', 'Facilitix Platform'),
            'favicon': website_settings.get('favicon'),
            'splash_image': website_settings.get('splash_image')
        }
    
    def get_auth_config(self) -> Dict[str, Any]:
        """Get all authentication-related configuration from grouped structure"""
        # Try new grouped structure first, fallback to old flat structure
        ticktix_config = self.get_config_value('ticktix', {})
        oauth_config = ticktix_config.get('oauth', {})
        identity_server = ticktix_config.get('identity_server', {})
        jwt_config = ticktix_config.get('jwt', {})

        # Get API config from grouped structure
        api_config = ticktix_config.get('api', {})

        return {
            'ticktix_client_id': oauth_config.get('client_id'),
            'ticktix_client_secret': oauth_config.get('client_secret'),
            'ticktix_mobile_client_id': oauth_config.get('mobile_client_id'),
            'ticktix_base_url': identity_server.get('base_url', 'https://login.ticktix.com'),
            'ticktix_authorize_url': identity_server.get('authorize_url', '/oauth/v2/authorize'),
            'ticktix_token_url': identity_server.get('token_url', '/oauth/v2/token'),
            'ticktix_userinfo_url': identity_server.get('userinfo_url', '/oidc/v1/userinfo'),
            'ticktix_endsession_url': identity_server.get('endsession_url', '/oidc/v1/end_session'),
            'ticktix_jwks_uri': identity_server.get('jwks_uri', '/oauth/v2/keys'),
            'ticktix_org_id': identity_server.get('org_id'),
            'ticktix_project_id': identity_server.get('project_id'),
            'ticktix_admin_email': api_config.get('admin_email', 'facilitix@ticktix.com'),
            'ticktix_redirect_url_template': oauth_config.get('redirect_url_template', '/api/method/frappe.integrations.oauth2_logins.custom/ticktix'),
            'jwt_enabled': jwt_config.get('enabled', False),
            'jwt_audience': jwt_config.get('audience'),
            'jwt_auto_provision': jwt_config.get('auto_provision', False),
            'ticktix_service_account_token': api_config.get('service_account_token'),
            'ticktix_initial_password': api_config.get('default_initial_password'),
            'ticktix_identity_provider': identity_server.get('provider', 'zitadel'),
            'ticktix_provision_api': identity_server.get('provision_api'),
            'ticktix_api_client_id': api_config.get('client_id'),
            'ticktix_api_client_secret': api_config.get('client_secret'),
            'ticktix_api_scope': api_config.get('scope', 'identityserver_admin_api offline_access')
        }
    
    def get_s3_config(self) -> Dict[str, Any]:
        """Get S3 attachment storage configuration from grouped structure.

        Expected shape in common_site_config.json / site_config.json:
            "ticktix": {
                "storage": {
                    "s3": {
                        "enabled": true,
                        "bucket_name": "...",
                        "region_name": "ap-south-1",
                        "folder_name": "attachment",
                        "aws_key": "...",
                        "aws_secret": "...",
                        "signed_url_expiry_time": 120,
                        "delete_file_from_cloud": false
                    }
                }
            }
        """
        ticktix_config = self.get_config_value('ticktix', {})
        storage_config = ticktix_config.get('storage', {})
        s3_config = storage_config.get('s3', {})

        return {
            's3_enabled': s3_config.get('enabled', False),
            's3_bucket_name': s3_config.get('bucket_name'),
            's3_region_name': s3_config.get('region_name'),
            's3_folder_name': s3_config.get('folder_name'),
            's3_aws_key': s3_config.get('aws_key'),
            's3_aws_secret': s3_config.get('aws_secret'),
            's3_signed_url_expiry_time': s3_config.get('signed_url_expiry_time', 120),
            's3_delete_file_from_cloud': s3_config.get('delete_file_from_cloud', False),
        }

    def get_hr_config(self) -> Dict[str, Any]:
        """Get all HR-related configuration (for future use)"""
        # Get HR config from grouped structure 
        ticktix_config = self.get_config_value('ticktix', {})
        hr_config = ticktix_config.get('hr', {})
        
        return {
            'hr_employee_id_patterns': hr_config.get('employee_id_patterns', {}),
            'hr_attendance_rules': hr_config.get('attendance_rules', {}),
            'hr_enable_client_dayoff': hr_config.get('enable_client_dayoff', False),
            'geo_tracking': hr_config.get('geo_tracking', {})
        }
    
    def _get_site_config(self) -> Dict[str, Any]:
        """Read site-specific configuration"""
        try:
            site_config_path = frappe.get_site_path("site_config.json")
            if os.path.exists(site_config_path):
                with open(site_config_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            frappe.log_error(f"Error reading site config: {e}", "Config Manager")
        
        return {}
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid"""
        import time
        return (time.time() - self._last_cache_time) < self._cache_timeout
    
    def _refresh_cache(self) -> None:
        """Refresh the configuration cache"""
        import time
        self._cache.clear()
        self._last_cache_time = time.time()
    
    def clear_cache(self) -> None:
        """Clear the configuration cache"""
        self._cache.clear()
        self._last_cache_time = 0


# Global instance
_config_manager = None

def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

def get_config_value(key: str, default: Any = None) -> Any:
    """Convenience function to get configuration value"""
    return get_config_manager().get_config_value(key, default)

def get_branding_config() -> Dict[str, Any]:
    """Convenience function to get branding configuration"""
    return get_config_manager().get_branding_config()

def get_auth_config() -> Dict[str, Any]:
    """Convenience function to get auth configuration"""
    return get_config_manager().get_auth_config()

def get_s3_config() -> Dict[str, Any]:
    """Convenience function to get S3 attachment storage configuration"""
    return get_config_manager().get_s3_config()

def require_org_id(auth_config: Dict[str, Any]) -> str:
    """Return ticktix_org_id from an already-fetched auth_config, or hard-fail.

    org_id scopes both the Zitadel login flow (via the
    urn:zitadel:iam:org:id:{org_id} authorize-request scope) and Management
    API provisioning calls (via the x-zitadel-orgid header). There is no
    un-scoped fallback - every site must set its own org.
    """
    org_id = auth_config.get('ticktix_org_id')
    if not org_id:
        frappe.throw(
            "Zitadel org_id not configured. "
            "Set ticktix.identity_server.org_id in site_config.json."
        )
    return str(org_id)

_ORG_SCOPE_TOKENS = "urn:zitadel:iam:org:id:{org_id} urn:zitadel:iam:user:resourceowner"

def build_org_scope(org_id: str, base_scope: str = "openid profile email") -> str:
    """Build an OAuth scope string that enforces Zitadel org membership.

    Zitadel enforces org membership itself when this scope is requested at
    the authorize step - a user who isn't a member of org_id fails at
    Zitadel's own login UI, before ever redirecting back to Frappe.
    """
    return f"{base_scope} {_ORG_SCOPE_TOKENS.format(org_id=org_id)}"

def ensure_org_scope(auth_params: Dict[str, Any], org_id: str) -> Dict[str, Any]:
    """Ensure an auth_params dict's scope includes the Zitadel org-enforcement tokens.

    Appends the org/resourceowner scope tokens to whatever scope is already
    present - including a site's custom ticktix.oauth.auth_params override -
    instead of silently dropping org enforcement whenever a site customizes
    auth_params for an unrelated reason. Returns a new dict; does not mutate
    the input.
    """
    org_tokens = _ORG_SCOPE_TOKENS.format(org_id=org_id)
    existing_scope = auth_params.get('scope', 'openid profile email')
    if 'urn:zitadel:iam:org:id:' in existing_scope:
        return auth_params
    result = dict(auth_params)
    result['scope'] = f"{existing_scope} {org_tokens}"
    return result

def get_hr_config() -> Dict[str, Any]:
    """Convenience function to get HR configuration"""
    return get_config_manager().get_hr_config()

def get_scopes_from_social_login_key(provider: str = "ticktix", fallback: Optional[list] = None) -> list:
    """Read the OAuth scope list from the Social Login Key's `auth_url_data` JSON field.

    The Social Login Key doctype (browser OAuth login flow) and mobile_api_info's
    discovery response (mobile PKCE flow) both need the same org/project scope
    tokens (e.g. urn:zitadel:iam:org:id:..., urn:zitadel:iam:org:project:id:...:aud).
    Rather than keep two separately-maintained copies of that scope string (one in
    site_config.json's ticktix.identity_server, one hand-typed into Social Login
    Key's Auth URL Data), this reads it once from Social Login Key and lets that be
    the single source of truth. Falls back to the caller-supplied default scopes if
    the Social Login Key record or its scope isn't set, so this stays a soft
    dependency - a missing/blank field doesn't break discovery.
    """
    try:
        auth_url_data = frappe.db.get_value("Social Login Key", provider, "auth_url_data")
        if auth_url_data:
            scope_str = json.loads(auth_url_data).get("scope")
            if scope_str:
                return scope_str.split()
    except Exception as e:
        frappe.log_error(f"Error reading scope from Social Login Key '{provider}': {e}", "Config Manager")
    return fallback or []

def get_oauth_urls_from_social_login_key(provider: str = "ticktix", fallback: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Read base_url/authorize_url/access_token_url straight from Social Login Key.

    Same reasoning as get_scopes_from_social_login_key: the browser OAuth login
    flow's endpoint URLs live on this doctype already, so mobile_api_info should
    read them from there instead of keeping a second, separately-maintained copy
    in site_config.json's ticktix.identity_server. Social Login Key has no
    jwks_uri field, so that one still has to come from site_config.

    Returns a dict with base_url/authorize_url/access_token_url, falling back to
    the caller-supplied defaults for any field that's missing/blank, so a partial
    or absent Social Login Key record doesn't break discovery.
    """
    fallback = fallback or {}
    result = dict(fallback)
    try:
        doc_values = frappe.db.get_value(
            "Social Login Key", provider,
            ["base_url", "authorize_url", "access_token_url"], as_dict=True,
        )
        if doc_values:
            for key in ("base_url", "authorize_url", "access_token_url"):
                if doc_values.get(key):
                    result[key] = doc_values[key]
    except Exception as e:
        frappe.log_error(f"Error reading OAuth URLs from Social Login Key '{provider}': {e}", "Config Manager")
    return result