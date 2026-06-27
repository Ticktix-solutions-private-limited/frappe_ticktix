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
            'ticktix_base_url': identity_server.get('base_url', 'https://login.ticktix.com'),
            'ticktix_authorize_url': identity_server.get('authorize_url', '/connect/authorize'),
            'ticktix_token_url': identity_server.get('token_url', '/connect/token'),
            'ticktix_userinfo_url': identity_server.get('userinfo_url', '/connect/userinfo'),
            'ticktix_endsession_url': identity_server.get('endsession_url', '/connect/endsession'),
            'ticktix_provision_api': identity_server.get('provision_api', 'https://authapi.ticktix.com'),
            'ticktix_jwks_uri': identity_server.get('jwks_uri', '/.well-known/openid-configuration/jwks'),
            'ticktix_admin_email': api_config.get('admin_email', 'facilitix@ticktix.com'),
            'ticktix_api_client_id': api_config.get('client_id'),
            'ticktix_api_client_secret': api_config.get('client_secret'),
            'ticktix_api_scope': api_config.get('scope', 'identityserver_admin_api'),
            'ticktix_redirect_url_template': oauth_config.get('redirect_url_template', '/api/method/frappe.integrations.oauth2_logins.custom/ticktix'),
            'jwt_enabled': jwt_config.get('enabled', False),
            'jwt_audience': jwt_config.get('audience'),
            'jwt_auto_provision': jwt_config.get('auto_provision', False)
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

def get_hr_config() -> Dict[str, Any]:
    """Convenience function to get HR configuration"""
    return get_config_manager().get_hr_config()