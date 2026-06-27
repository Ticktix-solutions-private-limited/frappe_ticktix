import frappe
import requests
import base64
import json
from datetime import datetime, timedelta
from ...config.config_manager import get_config_manager


def get_ticktix_user_info_from_code(authorization_code):
    """
    Exchange authorization code for tokens and extract user info from JWT.
    """
    try:
        # Get Social Login Key configuration
        social_login = frappe.get_doc("Social Login Key", "ticktix")
        
        # Use the same redirect URI construction as Frappe's OAuth system
        # This ensures the redirect_uri matches exactly between authorization and token exchange
        redirect_uri = frappe.utils.get_url(social_login.redirect_url)
        
        # Exchange authorization code for tokens
        token_url = f"{social_login.base_url.rstrip('/')}/connect/token"
        
        # Get client_secret (automatically decrypted by Frappe)
        client_secret = social_login.client_secret
        if not client_secret:
            frappe.throw("Client secret not configured in Social Login Key")
        
        token_data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': redirect_uri,
            'client_id': social_login.client_id,
            'client_secret': client_secret
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        # Log the request details for debugging (remove in production)
        frappe.logger().debug(f"TickTix Token Request - URL: {token_url}")
        frappe.logger().debug(f"TickTix Token Request - Redirect URI: {redirect_uri}")
        frappe.logger().debug(f"TickTix Token Request - Client ID: {social_login.client_id}")
        
        response = requests.post(token_url, data=token_data, headers=headers, timeout=10)
        
        # Enhanced error handling
        if response.status_code != 200:
            error_msg = f"Token exchange failed: {response.status_code} {response.reason}"
            try:
                error_details = response.json()
                error_msg += f" - Details: {error_details}"
            except:
                error_msg += f" - Response: {response.text[:200]}"
            frappe.logger().error(f"TickTix OAuth Error: {error_msg}")
            frappe.throw(f"Failed to get token from TickTix: {error_msg}")
        
        response.raise_for_status()
        token_response = response.json()
        
        # Extract and decode the id_token JWT
        id_token = token_response.get('id_token')
        if not id_token:
            frappe.throw("No id_token received from TickTix")
        
        # Decode JWT payload (we skip signature verification for now since we trust the HTTPS connection)
        # In production, you should verify the JWT signature
        jwt_parts = id_token.split('.')
        if len(jwt_parts) != 3:
            frappe.throw("Invalid JWT format from TickTix")
        
        # Decode the payload (middle part)
        payload_b64 = jwt_parts[1]
        # Add padding if needed
        payload_b64 += '=' * (4 - len(payload_b64) % 4)
        payload_json = base64.b64decode(payload_b64).decode('utf-8')
        user_info = json.loads(payload_json)
        
        frappe.logger().info(f"Decoded JWT user info: {user_info}")
        
        return user_info
        
    except requests.exceptions.RequestException as e:
        frappe.logger().error(f"Token exchange failed: {str(e)}")
        frappe.throw(f"Failed to get user information from TickTix: {str(e)}")
    except json.JSONDecodeError as e:
        frappe.logger().error(f"JWT decode failed: {str(e)}")
        frappe.throw(f"Failed to decode user information from TickTix: {str(e)}")
    except Exception as e:
        frappe.logger().error(f"Unexpected error in token exchange: {str(e)}")
        frappe.throw(f"Authentication error: {str(e)}")


# Cache for access tokens to avoid repeated authentication
_token_cache = {}


def get_api_access_token():
    """Get access token using client credentials flow for TickTix Auth API."""
    config_manager = get_config_manager()
    auth_config = config_manager.get_auth_config()
    
    client_id = auth_config.get('ticktix_api_client_id')
    client_secret = auth_config.get('ticktix_api_client_secret')
    
    # Use the same base URL and token path as main OAuth config
    base_url = auth_config.get('ticktix_base_url', 'https://login.ticktix.com')
    token_path = auth_config.get('ticktix_token_url', '/connect/token')
    token_url = f"{base_url.rstrip('/')}{token_path}"
    
    scope = auth_config.get('ticktix_api_scope', 'identityserver_admin_api')
    
    if not client_id or not client_secret:
        frappe.throw("TickTix API client credentials not configured")
    
    # Check if we have a valid cached token
    cache_key = f"{client_id}_{token_url}"
    if cache_key in _token_cache:
        cached_token = _token_cache[cache_key]
        if cached_token['expires_at'] > datetime.now():
            return cached_token['access_token']
    
    # Request new access token using client credentials
    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        'grant_type': 'client_credentials',
        'scope': scope
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        
        token_data = response.json()
        access_token = token_data['access_token']
        expires_in = token_data.get('expires_in', 3600)
        
        # Cache the token (expire 5 minutes early for safety)
        expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
        _token_cache[cache_key] = {
            'access_token': access_token,
            'expires_at': expires_at
        }
        
        return access_token
        
    except requests.exceptions.RequestException as e:
        frappe.log_error(
            message=f"Failed to create social login mapping for {user_doc.email}: {str(e)}",
            title='Social Login Mapping Error'
        )


def handle_user_email_update(doc, method):
    """Handle email updates for existing users without email addresses.
    
    This function is called when a User document is saved and checks:
    1. If the user previously had no email and now has one
    2. If so, auto-provisions them to TickTix IDP and creates social login mapping
    """
    # Skip for built-in system users or disabled users
    if doc.name in ['Administrator', 'Guest'] or not doc.enabled:
        return
    
    # Check if this is an email addition (user previously had no email)
    if not doc.email:
        return  # Still no email, nothing to do
    
    # Check if user already has TickTix social login mapping
    existing_mapping = doc.get_social_login_userid('ticktix')
    if existing_mapping:
        frappe.logger().info(f"User {doc.email} already has TickTix mapping: {existing_mapping}")
        return  # Already has mapping, nothing to do
    
    # Check if this is actually a new email (not just a save without changes)
    if hasattr(doc, '_doc_before_save'):
        old_email = doc._doc_before_save.get('email')
        if old_email == doc.email:
            return  # Email didn't change, nothing to do
        
        if old_email:
            frappe.logger().info(f"User {doc.name} email changed from {old_email} to {doc.email}")
        else:
            frappe.logger().info(f"User {doc.name} got new email: {doc.email}")
    
    # Email was added or changed, provision to TickTix
    try:
        frappe.logger().info(f"Auto-provisioning user {doc.email} (email update) to TickTix...")
        
        # Get API access token for TickTix
        access_token = get_api_access_token()
        if not access_token:
            frappe.logger().warning(f"Could not get TickTix API access token for user {doc.email}")
            return
            
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Get API base URL from config using ConfigManager
        config_manager = get_config_manager()
        auth_config = config_manager.get_auth_config()
        api_base = auth_config.get('ticktix_provision_api', 'https://authapi.ticktix.com')
        
        # Check if user already exists in TickTix IDP and get User ID
        check_result = check_user_exists_in_idp(doc.email, headers, api_base)
        
        ticktix_user_id = None
        
        if check_result['exists']:
            # User exists in IDP, get their ID
            ticktix_user_id = check_result.get('user_id')
            frappe.logger().info(f"User {doc.email} already exists in TickTix IDP with ID: {ticktix_user_id}")
        else:
            # User doesn't exist, create them in IDP
            create_result = create_user_in_idp(doc, headers, api_base)
            if create_result['status'] == 'success':
                ticktix_user_id = create_result.get('user_id')
                frappe.logger().info(f"Created user {doc.email} in TickTix IDP with ID: {ticktix_user_id}")
            elif create_result['status'] == 'exists':
                # User was created by another process, try to get their ID
                recheck_result = check_user_exists_in_idp(doc.email, headers, api_base)
                if recheck_result['exists']:
                    ticktix_user_id = recheck_result.get('user_id')
                    frappe.logger().info(f"User {doc.email} exists in TickTix IDP with ID: {ticktix_user_id}")
            else:
                frappe.logger().error(f"Failed to create user {doc.email} in TickTix IDP: {create_result}")
                return
        
        # Create social login mapping if we have a TickTix user ID
        if ticktix_user_id:
            create_social_login_mapping(doc, ticktix_user_id)
            frappe.logger().info(f"Successfully set up TickTix mapping for {doc.email} after email update")
        else:
            frappe.logger().warning(f"Could not obtain TickTix user ID for {doc.email}, skipping social login mapping")
            
    except Exception as e:
        frappe.log_error(
            message=f"Auto-provision failed for user {doc.email} (email update): {str(e)}",
            title='TickTix Auto-Provision Error'
        )
        frappe.throw(f"Authentication with TickTix API failed: {str(e)}")


def check_user_exists_in_idp(email, headers, api_base):
    """Check if a user exists in TickTix Identity Server by email using searchText."""
    try:
        # Use the /api/Users endpoint with searchText parameter to find user by email
        check_url = f"{api_base.rstrip('/')}/api/Users"
        params = {'searchText': email}
        
        resp = requests.get(check_url, params=params, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            response_data = resp.json()
            # Handle paginated response structure
            users_data = []
            if isinstance(response_data, dict) and 'users' in response_data:
                # Paginated response: {"pageSize": 10, "totalCount": 1, "users": [...]}
                users_data = response_data['users']
            elif isinstance(response_data, list):
                # Direct array response (fallback)
                users_data = response_data
            
            # Search through the returned users to find exact email match
            if users_data:
                for user in users_data:
                    if user.get('email', '').lower() == email.lower():
                        return {
                            'exists': True,
                            'user_id': user.get('id'),
                            'user_data': user
                        }
            # If we get here, no exact email match was found
            return {'exists': False}
        elif resp.status_code == 404:
            return {'exists': False}
        else:
            frappe.logger().warning(f"Unexpected response checking user existence: {resp.status_code} - {resp.text}")
            return {'exists': False}
            
    except requests.exceptions.RequestException as e:
        frappe.logger().warning(f"Error checking user existence: {str(e)}")
        return {'exists': False}


@frappe.whitelist()
def update_administrator_user():
    """Manual utility to update the Administrator user with configured admin email and provision to Identity Server."""
    if not frappe.has_permission('User', 'write'):
        frappe.throw("Insufficient permissions")
    
    # Get admin email from configuration using ConfigManager
    config_manager = get_config_manager()
    auth_config = config_manager.get_auth_config()
    admin_email = auth_config.get('ticktix_admin_email', 'facilitix@ticktix.com')
    
    try:
        # Update Administrator user email
        admin_doc = frappe.get_doc('User', 'Administrator')
        admin_doc.email = admin_email
        admin_doc.save(ignore_permissions=True)
        
        frappe.logger().info(f"Updated Administrator email to {admin_email}")
        
        # Provision to Identity Server
        frappe.session.user = 'Administrator'
        result = ticktix_post_provision()
        
        return {
            'status': 'success',
            'message': f'Administrator user updated to {admin_email} and provisioned',
            'admin_email': admin_email,
            'provision_result': result
        }
        
    except Exception as e:
        frappe.log_error(
            message=f"Failed to setup Administrator user: {str(e)}", 
            title='Administrator Setup Error'
        )
        return {'status': 'error', 'message': str(e)}


@frappe.whitelist(allow_guest=True)
def custom_oauth_handler(code=None, state=None):
    """
    Custom OAuth handler that intercepts TickTix OAuth callbacks.
    This is called by Frappe's OAuth system via hooks.py override.
    """
    frappe.logger().info("=== Custom OAuth handler called ===")
    
    # Extract provider from URL path
    path = frappe.request.path[1:].split("/")
    if len(path) >= 4 and path[3]:
        provider = path[3]
        
        if provider == "ticktix":
            # Handle TickTix OAuth with custom logic
            return handle_ticktix_oauth()
        else:
            # Fall back to default Frappe OAuth handling
            from frappe.integrations.oauth2_logins import login_via_oauth2, decoder_compat
            if frappe.db.exists("Social Login Key", provider):
                return login_via_oauth2(provider, code, state, decoder=decoder_compat)
            else:
                frappe.throw(f"Unknown OAuth provider: {provider}")
    else:
        frappe.throw("Invalid OAuth callback URL")


@frappe.whitelist(allow_guest=True)
def handle_ticktix_oauth():
    """
    Handle TickTix OAuth callback with special Administrator mapping logic.
    """
    try:
        # Get OAuth parameters from request
        code = frappe.form_dict.get('code')
        state = frappe.form_dict.get('state')
        
        if not code:
            frappe.throw("Authorization code is missing")
        
        frappe.logger().info(f"Processing TickTix OAuth callback with code: {code[:20]}...")
        
        # Get user info from TickTix using our custom token exchange
        user_info = get_ticktix_user_info_from_code(code)
        
        # Extract user details
        email = user_info.get('email', '').lower()
        ticktix_user_id = user_info.get('sub') or user_info.get('id')
        
        frappe.logger().info(f"TickTix user: {email}, User ID: {ticktix_user_id}")
        
        if not email or not ticktix_user_id:
            frappe.throw("Invalid user information from TickTix")
        
        # Check if this is the admin email that should map to Administrator
        config_manager = get_config_manager()
        auth_config = config_manager.get_auth_config()
        admin_email = auth_config.get('ticktix_admin_email', 'facilitix@ticktix.com').lower()
        
        if email == admin_email:
            # Handle Administrator login
            return login_administrator_user(ticktix_user_id, email, state)
        else:
            # Check if user already exists with this TickTix mapping
            existing_user = frappe.db.get_value("User Social Login", 
                                               {"provider": "ticktix", "userid": ticktix_user_id}, 
                                               "parent")
            
            if existing_user:
                # Login existing user
                frappe.logger().info(f"Logging in existing user: {existing_user}")
                from frappe.utils.oauth import login_oauth_user
                login_oauth_user(user_info, provider="ticktix", state=state)
            else:
                # No existing mapping found and signups are disabled
                frappe.logger().warning(f"No user mapping found for TickTix ID: {ticktix_user_id}")
                frappe.respond_as_web_page(
                    "Signup is Disabled",
                    "Your account is not authorized to access this system. Please contact your administrator.",
                    success=False,
                    http_status_code=403
                )
        
    except Exception as e:
        frappe.logger().error(f"TickTix OAuth error: {str(e)}")
        frappe.respond_as_web_page(
            "Login Error",
            f"Authentication failed: {str(e)}",
            success=False,
            http_status_code=500
        )


def login_administrator_user(ticktix_user_id, email, state):
    """
    Handle Administrator login with TickTix OAuth mapping.
    """
    try:
        admin_user = frappe.get_doc("User", "Administrator")
        
        # Ensure Administrator has the correct email
        if admin_user.email != email:
            admin_user.email = email
            admin_user.flags.ignore_permissions = True
            admin_user.save()
        
        # Check/create TickTix social login mapping
        existing_mapping = admin_user.get_social_login_userid('ticktix')
        
        if not existing_mapping:
            # Create new mapping
            admin_user.set_social_login_userid('ticktix', userid=ticktix_user_id, username=email)
            admin_user.flags.ignore_permissions = True
            admin_user.save()
            frappe.logger().info(f"Created TickTix mapping for Administrator: {ticktix_user_id}")
        elif existing_mapping != ticktix_user_id:
            # Update existing mapping if User ID changed
            for social_login in admin_user.social_logins:
                if social_login.provider == 'ticktix':
                    social_login.userid = ticktix_user_id
                    break
            admin_user.flags.ignore_permissions = True
            admin_user.save()
            frappe.logger().info(f"Updated TickTix mapping for Administrator: {ticktix_user_id}")
        
        # Login the Administrator
        frappe.local.login_manager.login_as("Administrator")
        frappe.db.commit()
        
        # Handle redirect
        from frappe.utils.oauth import redirect_post_login
        import json
        import base64
        
        try:
            if state:
                decoded_state = json.loads(base64.b64decode(state).decode("utf-8"))
                redirect_to = decoded_state.get('redirect_to')
            else:
                redirect_to = None
        except:
            redirect_to = None
        
        redirect_post_login(desk_user=True, redirect_to=redirect_to, provider="ticktix")
        
    except Exception as e:
        frappe.logger().error(f"Administrator login error: {str(e)}")
        frappe.throw(f"Failed to login Administrator: {str(e)}")


@frappe.whitelist(allow_guest=True)
def ticktix_oauth_callback(code=None, state=None):
    """
    Legacy callback - redirects to new handler.
    This exists for backward compatibility.
    """
    return handle_ticktix_oauth()


@frappe.whitelist(allow_guest=True) 
def ticktix_post_provision(code=None, state=None):
    """Post-provision hook called after OAuth code exchange by frappe.

    This function provisions new users in TickTix Identity Server using 
    client credentials authentication flow with the auth API.
    """
    config_manager = get_config_manager()
    auth_config = config_manager.get_auth_config()
    api_base = auth_config.get('ticktix_provision_api', 'https://authapi.ticktix.com')
    
    # Get current user context
    user = frappe.session.user if hasattr(frappe, 'session') else frappe.local.session.user
    if not user or user == 'Guest':
        return {'status': 'skipped', 'reason': 'no-user'}

    # Get user document
    try:
        doc = frappe.get_doc('User', user)
    except frappe.DoesNotExistError:
        return {'status': 'error', 'reason': 'user-not-found'}

    # Prepare user payload for TickTix API (tenant not needed for OAuth)
    payload = {
        'email': doc.email,
        'firstName': doc.first_name or doc.full_name or '',
        'lastName': doc.last_name or '',
        'username': doc.name,
        'isActive': True,
        'emailConfirmed': True,  # Assume email is verified since coming from OAuth
        'roles': ['User']  # Default role, adjust as needed
    }

    # Get access token using client credentials
    try:
        access_token = get_api_access_token()
    except Exception as e:
        return {'status': 'error', 'reason': 'auth-failed', 'message': str(e)}

    # Call TickTix API headers
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    try:
        # First check if user exists
        check_result = check_user_exists_in_idp(doc.email, headers, api_base)
        if check_result['exists']:
            frappe.logger().info(f"User {doc.email} already exists in TickTix Identity Server")
            return {
                'status': 'exists', 
                'message': 'User already exists in Identity Server',
                'user_id': check_result.get('user_id')
            }

        # User doesn't exist, create them
        create_url = f"{api_base.rstrip('/')}/api/Users"
        create_payload = {
            'UserName': doc.name,
            'Email': doc.email,
            'EmailConfirmed': True
        }
        
        resp = requests.post(create_url, json=create_payload, headers=headers, timeout=10)
        resp = requests.post(create_url, json=create_payload, headers=headers, timeout=10)
        
        if resp.status_code == 200 or resp.status_code == 201:
            # User created successfully
            frappe.logger().info(f"User {doc.email} provisioned successfully in TickTix Identity Server")
            return {
                'status': 'success', 
                'code': resp.status_code,
                'user_id': resp.json().get('id') if resp.content else None
            }
        elif resp.status_code == 409 or resp.status_code == 400:
            # User already exists or validation error - check if it's duplicate
            error_msg = resp.text
            if 'already exists' in error_msg.lower() or 'duplicate' in error_msg.lower():
                frappe.logger().info(f"User {doc.email} already exists in TickTix Identity Server")
                return {
                    'status': 'exists', 
                    'code': resp.status_code,
                    'message': 'User already exists'
                }
            else:
                frappe.log_error(
                    message=f"TickTix API validation error {resp.status_code}: {resp.text}",
                    title='TickTix Provision Error'
                )
                return {
                    'status': 'error', 
                    'code': resp.status_code, 
                    'message': resp.text
                }
        else:
            # Other error
            frappe.log_error(
                message=f"TickTix API returned {resp.status_code}: {resp.text}",
                title='TickTix Provision Error'
            )
            return {
                'status': 'error', 
                'code': resp.status_code, 
                'message': resp.text
            }
            
    except requests.exceptions.RequestException as e:
        frappe.log_error(
            message=f"Failed to provision user in TickTix: {str(e)}", 
            title='TickTix Provision Error'
        )
        return {'status': 'error', 'message': str(e)}


@frappe.whitelist()
def provision_existing_users():
    """Manual utility to provision all existing Frappe users to TickTix IDP"""
    if not frappe.has_permission('User', 'write'):
        frappe.throw("Insufficient permissions to provision users")
    
    # Get all enabled users (excluding Administrator and Guest)
    users = frappe.get_all('User', 
                          filters={
                              'enabled': 1,
                              'name': ['not in', ['Administrator', 'Guest']]
                          },
                          fields=['name', 'email', 'first_name', 'last_name', 'full_name', 'user_type'])
    
    results = {
        'total_users': len(users),
        'provisioned': 0,
        'existing': 0,
        'failed': 0,
        'details': []
    }
    
    try:
        # Get API access token
        access_token = get_api_access_token()
        if not access_token:
            frappe.throw("Could not get TickTix API access token")
            
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Get API base URL from config using ConfigManager
        config_manager = get_config_manager()
        auth_config = config_manager.get_auth_config()
        api_base = auth_config.get('ticktix_provision_api', 'https://authapi.ticktix.com')
        
        for user_data in users:
            try:
                user_doc = frappe.get_doc('User', user_data.name)
                
                # Check if user exists in IDP
                check_result = check_user_exists_in_idp(user_data.email, headers, api_base)
                
                if check_result['exists']:
                    ticktix_user_id = check_result.get('user_id')
                    # Create/update social login mapping
                    create_social_login_mapping(user_doc, ticktix_user_id)
                    results['existing'] += 1
                    results['details'].append(f"✓ {user_data.email} ({user_data.user_type}): Already exists in IDP, mapping updated")
                else:
                    # Create user in IDP
                    create_result = create_user_in_idp(user_doc, headers, api_base)
                    if create_result['status'] == 'success':
                        ticktix_user_id = create_result.get('user_id')
                        if ticktix_user_id:
                            create_social_login_mapping(user_doc, ticktix_user_id)
                            results['provisioned'] += 1
                            results['details'].append(f"✓ {user_data.email} ({user_data.user_type}): Created in IDP and mapped")
                        else:
                            results['failed'] += 1
                            results['details'].append(f"✗ {user_data.email} ({user_data.user_type}): Created in IDP but no user ID returned")
                    else:
                        results['failed'] += 1
                        results['details'].append(f"✗ {user_data.email} ({user_data.user_type}): {create_result['message']}")
                        
            except Exception as e:
                results['failed'] += 1
                results['details'].append(f"✗ {user_data.email}: {str(e)}")
                
        return results
        
    except Exception as e:
        frappe.throw(f"Provisioning failed: {str(e)}")


@frappe.whitelist()
def check_user_mapping_status():
    """Check the social login mapping status for all users"""
    if not frappe.has_permission('User', 'read'):
        frappe.throw("Insufficient permissions")
    
    users = frappe.get_all('User', 
                          filters={
                              'enabled': 1
                          },
                          fields=['name', 'email', 'user_type'])
    
    results = {
        'total_users': len(users),
        'mapped': 0,
        'unmapped': 0,
        'details': []
    }
    
    for user_data in users:
        try:
            user_doc = frappe.get_doc('User', user_data.name)
            ticktix_mapping = user_doc.get_social_login_userid('ticktix')
            
            if ticktix_mapping:
                results['mapped'] += 1
                results['details'].append(f"✓ {user_data.email} ({user_data.user_type}): Mapped to {ticktix_mapping}")
            else:
                results['unmapped'] += 1
                results['details'].append(f"○ {user_data.email} ({user_data.user_type}): No TickTix mapping")
                
        except Exception as e:
            results['details'].append(f"✗ {user_data.email}: Error checking mapping - {str(e)}")
    
    return results


def auto_provision_user(doc, method):
    """Automatically provision new users to TickTix IDP and create social login mapping.
    
    This function is called via document event hook when a new User is created.
    It performs:
    1. Creates the user account in TickTix IDP (if it doesn't exist)
    2. Sets up the social login mapping for OAuth authentication
    
    Works for all user types (System User, Website User, etc.)
    """
    # Skip for built-in system users or disabled users
    if doc.name in ['Administrator', 'Guest'] or not doc.enabled:
        return
    
    # Skip if user doesn't have a valid email
    if not doc.email:
        frappe.logger().info(f"Skipping auto-provision for user {doc.name}: no email address")
        return
    
    # Validate email format
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, doc.email):
        frappe.logger().info(f"Skipping auto-provision for user {doc.name}: invalid email format '{doc.email}'")
        return
    
    try:
        frappe.logger().info(f"Auto-provisioning user {doc.email} (Type: {doc.user_type}) to TickTix...")
        
        # Get API access token for TickTix
        access_token = get_api_access_token()
        if not access_token:
            frappe.logger().warning(f"Could not get TickTix API access token for user {doc.email}")
            return
            
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Get API base URL from config using ConfigManager
        config_manager = get_config_manager()
        auth_config = config_manager.get_auth_config()
        api_base = auth_config.get('ticktix_provision_api', 'https://authapi.ticktix.com')
        
        # Check if user already exists in TickTix IDP and get User ID
        check_result = check_user_exists_in_idp(doc.email, headers, api_base)
        
        ticktix_user_id = None
        
        if check_result['exists']:
            # User exists in IDP, get their ID
            ticktix_user_id = check_result.get('user_id')
            frappe.logger().info(f"User {doc.email} already exists in TickTix IDP with ID: {ticktix_user_id}")
        else:
            # User doesn't exist, create them in IDP
            create_result = create_user_in_idp(doc, headers, api_base)
            if create_result['status'] == 'success':
                ticktix_user_id = create_result.get('user_id')
                frappe.logger().info(f"Created user {doc.email} in TickTix IDP with ID: {ticktix_user_id}")
            elif create_result['status'] == 'exists':
                # User was created by another process, try to get their ID
                recheck_result = check_user_exists_in_idp(doc.email, headers, api_base)
                if recheck_result['exists']:
                    ticktix_user_id = recheck_result.get('user_id')
                    frappe.logger().info(f"User {doc.email} exists in TickTix IDP with ID: {ticktix_user_id}")
            else:
                frappe.logger().error(f"Failed to create user {doc.email} in TickTix IDP: {create_result}")
                return
        
        # Create social login mapping if we have a TickTix user ID
        if ticktix_user_id:
            create_social_login_mapping(doc, ticktix_user_id)
        else:
            frappe.logger().warning(f"Could not obtain TickTix user ID for {doc.email}, skipping social login mapping")
            
    except Exception as e:
        frappe.log_error(
            message=f"Auto-provision failed for user {doc.email}: {str(e)}",
            title='TickTix Auto-Provision Error'
        )


def create_user_in_idp(user_doc, headers, api_base):
    """Create a user in TickTix Identity Provider - simplified version"""
    try:
        create_url = f"{api_base.rstrip('/')}/api/Users"
        
        # Use email as both username and email (no complex username generation)
        create_payload = {
            'UserName': user_doc.email,
            'Email': user_doc.email,
            'EmailConfirmed': True,
            'FirstName': user_doc.first_name or '',
            'LastName': user_doc.last_name or '',
            'FullName': user_doc.full_name or user_doc.email
        }
        
        response = requests.post(create_url, json=create_payload, headers=headers, timeout=10)
        
        if response.status_code in [200, 201]:
            # User created successfully
            response_data = response.json() if response.content else {}
            frappe.logger().info(f"Created user in TickTix IDP: {user_doc.email}")
            return {
                'status': 'success',
                'user_id': response_data.get('id'),
                'message': f'User created successfully: {user_doc.email}'
            }
        elif response.status_code == 400:
            # Check if user already exists
            error_data = response.json() if response.content else {}
            if (isinstance(error_data, dict) and 'errors' in error_data):
                errors = error_data.get('errors', {})
                if 'DuplicateEmail' in errors or 'DuplicateUserName' in errors:
                    # User already exists - this is expected, not an error
                    return {
                        'status': 'exists',
                        'message': 'User already exists in TickTix IDP'
                    }
            
            # Other validation error
            return {
                'status': 'error',
                'message': f"Validation error: {error_data}"
            }
        else:
            # Other HTTP error
            return {
                'status': 'error', 
                'message': f"HTTP {response.status_code}: {response.text}"
            }
            
    except requests.exceptions.RequestException as e:
        return {
            'status': 'error',
            'message': f"Request failed: {str(e)}"
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f"Unexpected error: {str(e)}"
        }


def create_social_login_mapping(user_doc, ticktix_user_id):
    """Create social login mapping for the user"""
    try:
        # Check if mapping already exists
        existing_mapping = user_doc.get_social_login_userid('ticktix')
        
        if existing_mapping:
            if existing_mapping == ticktix_user_id:
                frappe.logger().info(f"Social login mapping already exists for {user_doc.email}")
                return
            else:
                # Update existing mapping
                for social_login in user_doc.social_logins:
                    if social_login.provider == 'ticktix':
                        social_login.userid = ticktix_user_id
                        break
                frappe.logger().info(f"Updated social login mapping for {user_doc.email}: {ticktix_user_id}")
        else:
            # Create new mapping
            user_doc.set_social_login_userid('ticktix', userid=ticktix_user_id, username=user_doc.email)
            frappe.logger().info(f"Created social login mapping for {user_doc.email}: {ticktix_user_id}")
        
        # Save the user document with the new mapping
        user_doc.flags.ignore_permissions = True
        user_doc.save()
        frappe.db.commit()
        
    except Exception as e:
        frappe.logger().error(f"Failed to create social login mapping for {user_doc.email}: {str(e)}")
        raise
