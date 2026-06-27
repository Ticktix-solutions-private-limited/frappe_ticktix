"""
JWT Token Validation for IdentityServer

This module handles JWT token validation against IdentityServer including:
- Public key validation using JWKS endpoints
- Signature verification  
- Claims validation
- Token caching for performance
"""

import frappe
import jwt
import json
import requests
from jwt.algorithms import RSAAlgorithm
from datetime import datetime, timedelta
from urllib.parse import urljoin


# Cache for JWKS public keys
_jwks_cache = {}
_cache_expiry = None


def validate_jwt_token_with_jwks(token, config=None):
    """
    Validate JWT token using IdentityServer's JWKS endpoint for public key verification.
    
    Args:
        token (str): JWT token string
        config (dict): JWT configuration, if not provided will use get_jwt_config()
        
    Returns:
        dict: Decoded JWT payload or None if invalid
    """
    if not config:
        config = get_jwt_config()
    
    try:
        frappe.log_error(f"[JWT DEBUG] Starting JWKS validation for token", "JWT Debug")
        
        # Get unverified header to find key ID
        unverified_header = jwt.get_unverified_header(token)
        key_id = unverified_header.get('kid')
        algorithm = unverified_header.get('alg', 'RS256')
        
        frappe.log_error(f"[JWT DEBUG] Token header - kid: {key_id}, alg: {algorithm}", "JWT Debug")
        
        # Get public key from JWKS
        public_key = get_public_key_from_jwks(config, key_id)
        if not public_key:
            frappe.log_error(f"[JWT DEBUG] Could not find public key for kid: {key_id}", "JWT Debug")
            frappe.log_error(f"Could not find public key for kid: {key_id}", "JWT JWKS")
            return None
        
        frappe.log_error(f"[JWT DEBUG] Successfully retrieved public key for kid: {key_id}", "JWT Debug")
        
        # Decode and verify JWT with public key
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[algorithm],
            options={"verify_signature": True, "verify_exp": True, "verify_aud": False}
        )
        
        frappe.log_error(f"[JWT DEBUG] JWT decode successful, payload issuer: {payload.get('iss')}", "JWT Debug")
        
        # Additional validation
        if not validate_jwt_claims(payload, config):
            frappe.log_error(f"[JWT DEBUG] JWT claims validation failed", "JWT Debug")
            return None
        
        frappe.log_error(f"[JWT DEBUG] JWT validation completely successful", "JWT Debug")
        return payload
        
    except jwt.ExpiredSignatureError:
        frappe.log_error("[JWT DEBUG] JWT token has expired", "JWT Debug")
        frappe.log_error("JWT token has expired", "JWT Validation")
        return None
    except jwt.InvalidTokenError as e:
        frappe.log_error(f"[JWT DEBUG] Invalid JWT token: {str(e)}", "JWT Debug")
        frappe.log_error(f"Invalid JWT token: {str(e)}", "JWT Validation")
        return None
    except Exception as e:
        frappe.log_error(f"[JWT DEBUG] JWT JWKS validation error: {str(e)}", "JWT Debug")
        frappe.log_error(f"JWT JWKS validation error: {str(e)}", "JWT Validation")
        return None


def validate_jwt_token_with_secret(token, config=None):
    """
    Validate JWT token using shared secret (HMAC).
    
    Args:
        token (str): JWT token string  
        config (dict): JWT configuration
        
    Returns:
        dict: Decoded JWT payload or None if invalid
    """
    if not config:
        config = get_jwt_config()
        
    secret_key = config.get('secret_key')
    if not secret_key:
        frappe.log_error("JWT secret key not configured", "JWT Configuration")
        return None
    
    try:
        algorithm = config.get('algorithm', 'HS256')
        
        # Decode and verify JWT with shared secret
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[algorithm],
            options={"verify_signature": True, "verify_exp": True}
        )
        
        # Additional validation
        if not validate_jwt_claims(payload, config):
            return None
            
        return payload
        
    except jwt.ExpiredSignatureError:
        frappe.log_error("JWT token has expired", "JWT Validation")
        return None
    except jwt.InvalidTokenError as e:
        frappe.log_error(f"Invalid JWT token: {str(e)}", "JWT Validation") 
        return None
    except Exception as e:
        frappe.log_error(f"JWT secret validation error: {str(e)}", "JWT Validation")
        return None


def get_public_key_from_jwks(config, key_id=None):
    """
    Fetch public key from IdentityServer's JWKS endpoint.
    
    Args:
        config (dict): JWT configuration containing JWKS URL
        key_id (str): Key ID to look for, if None uses first key
        
    Returns:
        str: Public key in PEM format or None if not found
    """
    global _jwks_cache, _cache_expiry
    
    jwks_uri = config.get('jwks_uri')
    frappe.log_error(f"[JWT DEBUG] JWKS URI from config: {jwks_uri}", "JWT Debug")
    
    if not jwks_uri:
        # Get JWKS URI from discovery document
        issuer = config.get('issuer')
        if issuer:
            discovery_uri = urljoin(issuer, '/.well-known/openid-configuration')
            frappe.log_error(f"[JWT DEBUG] Trying discovery URI: {discovery_uri}", "JWT Debug")
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Frappe JWT Validator)',
                    'Accept': 'application/json'
                }
                discovery_response = requests.get(discovery_uri, timeout=10, headers=headers, verify=True)
                discovery_response.raise_for_status()
                discovery_data = discovery_response.json()
                jwks_uri = discovery_data.get('jwks_uri')
                frappe.log_error(f"[JWT DEBUG] Discovery found JWKS URI: {jwks_uri}", "JWT Debug")
                if not jwks_uri:
                    frappe.log_error("No jwks_uri found in discovery document", "JWT Configuration")
                    return None
            except Exception as e:
                frappe.log_error(f"Failed to fetch discovery document: {str(e)}", "JWT Configuration")
                return None
        else:
            frappe.log_error("No JWKS URI or issuer configured", "JWT Configuration")
            return None
    
    # Check cache first
    cache_key = f"{jwks_uri}:{key_id or 'default'}"
    if _cache_expiry and datetime.now() < _cache_expiry and cache_key in _jwks_cache:
        frappe.log_error(f"[JWT DEBUG] Using cached key for {key_id}", "JWT Debug")
        return _jwks_cache[cache_key]
    
    frappe.log_error(f"[JWT DEBUG] Fetching JWKS from: {jwks_uri}", "JWT Debug")
    
    try:
        # Fetch JWKS with proper headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Frappe JWT Validator)',
            'Accept': 'application/json'
        }
        response = requests.get(jwks_uri, timeout=10, headers=headers, verify=True)
        response.raise_for_status()
        jwks_data = response.json()
        
        frappe.log_error(f"[JWT DEBUG] JWKS response contains {len(jwks_data.get('keys', []))} keys", "JWT Debug")
        
        # Find the right key
        keys = jwks_data.get('keys', [])
        target_key = None
        
        if key_id:
            # Look for specific key ID
            for key in keys:
                if key.get('kid') == key_id:
                    target_key = key
                    frappe.log_error(f"[JWT DEBUG] Found matching key for kid: {key_id}", "JWT Debug")
                    break
        else:
            # Use first available key
            if keys:
                target_key = keys[0]
                frappe.log_error(f"[JWT DEBUG] Using first available key", "JWT Debug")
        
        if not target_key:
            frappe.log_error(f"[JWT DEBUG] Key not found in JWKS for kid: {key_id}", "JWT Debug")
            frappe.log_error(f"Key not found in JWKS: {key_id}", "JWT JWKS")
            return None
        
        # Convert JWK to PEM format
        if target_key.get('kty') == 'RSA':
            public_key = RSAAlgorithm.from_jwk(json.dumps(target_key))
            frappe.log_error(f"[JWT DEBUG] Successfully converted JWK to RSA public key", "JWT Debug")
        else:
            frappe.log_error(f"[JWT DEBUG] Unsupported key type: {target_key.get('kty')}", "JWT Debug")
            frappe.log_error(f"Unsupported key type: {target_key.get('kty')}", "JWT JWKS")
            return None
        
        # Cache the key (expire in 1 hour)
        _jwks_cache[cache_key] = public_key
        _cache_expiry = datetime.now() + timedelta(hours=1)
        
        frappe.log_error(f"[JWT DEBUG] Key cached successfully for {key_id}", "JWT Debug")
        return public_key
        
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"[JWT DEBUG] JWKS HTTP error: {str(e)}", "JWT Debug")
        frappe.log_error(f"Failed to fetch JWKS: {str(e)}", "JWT JWKS")
        return None
    except Exception as e:
        frappe.log_error(f"[JWT DEBUG] JWKS processing error: {str(e)}", "JWT Debug")
        frappe.log_error(f"JWKS processing error: {str(e)}", "JWT JWKS")
        return None


def validate_jwt_claims(payload, config):
    """
    Validate JWT claims against configuration.
    
    Args:
        payload (dict): Decoded JWT payload
        config (dict): JWT configuration
        
    Returns:
        bool: True if claims are valid
    """
    # Validate issuer
    expected_issuer = config.get('issuer')
    if expected_issuer and payload.get('iss') != expected_issuer:
        frappe.log_error(f"JWT issuer mismatch: {payload.get('iss')} != {expected_issuer}", "JWT Claims")
        return False
    
    # Validate audience
    expected_audience = config.get('audience')
    if expected_audience:
        token_audience = payload.get('aud')
        # Audience can be a string or list
        if isinstance(token_audience, list):
            if expected_audience not in token_audience:
                frappe.log_error(f"JWT audience mismatch: {expected_audience} not in {token_audience}", "JWT Claims")
                return False
        else:
            if token_audience != expected_audience:
                frappe.log_error(f"JWT audience mismatch: {token_audience} != {expected_audience}", "JWT Claims")
                return False
    
    # Validate scope if required
    required_scopes = config.get('required_scopes', [])
    if required_scopes:
        token_scopes = payload.get('scope', '').split() or payload.get('scp', [])
        for required_scope in required_scopes:
            if required_scope not in token_scopes:
                frappe.log_error(f"JWT missing required scope: {required_scope}", "JWT Claims")
                return False
    
    # Validate custom claims if configured
    custom_claims = config.get('custom_claims', {})
    for claim_name, expected_value in custom_claims.items():
        actual_value = payload.get(claim_name)
        if actual_value != expected_value:
            frappe.log_error(f"JWT custom claim mismatch: {claim_name} = {actual_value} != {expected_value}", "JWT Claims")
            return False
    
    return True


def get_jwt_config():
    """
    Get JWT configuration leveraging existing TickTix configuration.
    
    Returns:
        dict: Complete JWT configuration
    """
    # Import ConfigManager here to avoid circular imports
    from ...config.config_manager import get_config_manager
    
    config_manager = get_config_manager()
    auth_config = config_manager.get_auth_config()
    
    # The issuer and JWKS URI come from auth config
    issuer = auth_config.get('ticktix_base_url', 'https://login.ticktix.com')
    jwks_suffix = auth_config.get('ticktix_jwks_uri', '/.well-known/openid-configuration/jwks')
    jwks_uri = f"{issuer}{jwks_suffix}"
    
    config = {
        'enabled': auth_config.get('jwt_enabled', True),
        'validation_method': 'jwks',  # Always use JWKS for security
        'algorithm': 'RS256',  # Standard for JWKS
        'issuer': issuer,
        'audience': auth_config.get('jwt_audience', None),
        'jwks_uri': jwks_uri,
        'auto_provision_users': auth_config.get('jwt_auto_provision', False),
        'allowed_email_domains': []  # No email domain restrictions - allow any email provider
    }
    
    # Default roles and scopes for all custom apps
    config.update({
        'default_roles': ['Desk User'],
        'required_scopes': [],  # No specific scopes required
        'custom_claims': {},
        'default_user_type': 'System User',
        'allow_username_mapping': True,  # Allow mapping by username
        'role_to_user_type_mapping': {},  # Map JWT roles to Frappe user types
        'jwt_role_mapping': {},  # Map JWT roles to Frappe roles
        'required_claims_for_provisioning': [],  # Required claims for auto-provisioning
        'required_roles_for_provisioning': []  # Required roles for auto-provisioning
    })
    
    return config


def validate_jwt_token(token):
    """
    Main JWT validation function that uses appropriate method based on configuration.
    
    Args:
        token (str): JWT token string
        
    Returns:
        dict: Decoded JWT payload or None if invalid
    """
    config = get_jwt_config()
    
    if not config.get('enabled'):
        frappe.log_error("JWT authentication is disabled", "JWT Configuration")
        return None
    
    validation_method = config.get('validation_method', 'jwks')
    
    if validation_method == 'jwks':
        return validate_jwt_token_with_jwks(token, config)
    elif validation_method == 'secret':
        return validate_jwt_token_with_secret(token, config)
    else:
        frappe.log_error(f"Unknown JWT validation method: {validation_method}", "JWT Configuration")
        return None


def clear_jwks_cache():
    """Clear the JWKS cache (useful for testing or when keys are rotated)."""
    global _jwks_cache, _cache_expiry
    _jwks_cache.clear()
    _cache_expiry = None


@frappe.whitelist()
def test_jwt_config():
    """Test endpoint to validate JWT configuration."""
    if not frappe.has_permission('System Settings'):
        frappe.throw("Insufficient permissions")
    
    config = get_jwt_config()
    
    result = {
        'config': config,
        'validation_method': config.get('validation_method'),
        'jwks_reachable': False,
        'errors': []
    }
    
    if config.get('validation_method') == 'jwks':
        # Test JWKS connectivity
        jwks_uri = config.get('jwks_uri')
        if jwks_uri:
            try:
                # Add headers to mimic browser request
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Frappe JWT Validator)',
                    'Accept': 'application/json'
                }
                response = requests.get(jwks_uri, timeout=10, headers=headers, verify=True)
                result['jwks_status_code'] = response.status_code
                result['jwks_response_headers'] = dict(response.headers)
                
                if response.status_code == 200:
                    result['jwks_reachable'] = True
                    jwks_data = response.json()
                    result['jwks_keys'] = len(jwks_data.get('keys', []))
                    result['jwks_sample_key'] = jwks_data.get('keys', [{}])[0] if jwks_data.get('keys') else None
                else:
                    result['errors'].append(f"JWKS endpoint returned {response.status_code}: {response.text[:200]}")
            except requests.exceptions.RequestException as e:
                result['errors'].append(f"JWKS HTTP error: {str(e)}")
            except Exception as e:
                result['errors'].append(f"JWKS connectivity error: {str(e)}")
        else:
            result['errors'].append("JWKS URI not configured")
    
    elif config.get('validation_method') == 'secret':
        if not config.get('secret_key'):
            result['errors'].append("JWT secret key not configured")
    
    if not config.get('issuer'):
        result['errors'].append("JWT issuer not configured")
        
    return result