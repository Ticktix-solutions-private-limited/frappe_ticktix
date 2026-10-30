import frappe
import requests
import base64
import json
from urllib.parse import urlencode
from frappe.utils import escape_html
from ...config.config_manager import get_config_manager


def get_ticktix_user_info_from_code(authorization_code):
    """
    Exchange authorization code for tokens and extract user info from JWT.

    Returns a tuple of (user_info, id_token).
    """
    try:
        # Get Social Login Key configuration
        social_login = frappe.get_doc("Social Login Key", "ticktix")

        # Use the same redirect URI construction as Frappe's OAuth system
        # This ensures the redirect_uri matches exactly between authorization and token exchange
        redirect_uri = frappe.utils.get_url(social_login.redirect_url)

        # Exchange authorization code for tokens
        config_manager = get_config_manager()
        auth_config = config_manager.get_auth_config()
        token_path = auth_config.get('ticktix_token_url', '/oauth/v2/token')
        if token_path.startswith('http'):
            token_url = token_path
        else:
            token_url = social_login.base_url.rstrip('/') + token_path

        # Get client_secret (decrypt from Frappe's __Auth table)
        client_secret = social_login.get_password('client_secret')
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

        # Zitadel returns email via the userinfo endpoint, not in the id_token.
        # Fall back to userinfo when email is missing.
        if not user_info.get('email'):
            access_token = token_response.get('access_token')
            if access_token:
                userinfo_path = auth_config.get('ticktix_userinfo_url', '/oidc/v1/userinfo')
                if userinfo_path.startswith('http'):
                    userinfo_url = userinfo_path
                else:
                    userinfo_url = social_login.base_url.rstrip('/') + userinfo_path

                userinfo_resp = requests.get(
                    userinfo_url,
                    headers={'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'},
                    timeout=10
                )
                userinfo_resp.raise_for_status()
                user_info.update(userinfo_resp.json())

        return user_info, id_token

    except requests.exceptions.RequestException as e:
        frappe.logger().error(f"Token exchange failed: {str(e)}")
        frappe.throw(f"Failed to get user information from TickTix: {str(e)}")
    except json.JSONDecodeError as e:
        frappe.logger().error(f"JWT decode failed: {str(e)}")
        frappe.throw(f"Failed to decode user information from TickTix: {str(e)}")
    except Exception as e:
        frappe.logger().error(f"Unexpected error in token exchange: {str(e)}")
        frappe.throw(f"Authentication error: {str(e)}")


def build_idp_logout_url(id_token=None):
    """Build the Zitadel end_session URL that ends the IdP session in this browser.

    Used on the rejection page so a user who is signed in at the IdP as someone
    who has no account on this site can sign out and pick another account.
    The id_token from the just-completed code exchange is passed as the hint.
    """
    auth_config = get_config_manager().get_auth_config()
    base_url = auth_config.get('ticktix_base_url') or 'https://login.ticktix.com'
    path = auth_config.get('ticktix_endsession_url') or '/oidc/v1/end_session'
    url = path if path.startswith('http') else base_url.rstrip('/') + path

    params = {'post_logout_redirect_uri': frappe.utils.get_url()}
    if id_token:
        params['id_token_hint'] = id_token
    return url + '?' + urlencode(params)


def cache_id_token(id_token):
    """Cache the OIDC id_token for the current session.

    Zitadel's RP-Initiated Logout endpoint (/oidc/v2/end_session) expects an
    id_token_hint; this lets ticktix_logout() retrieve the token issued at login.
    """
    if not id_token:
        return
    frappe.cache().set_value(f"ticktix_id_token:{frappe.session.sid}", id_token, expires_in_sec=86400)


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
        user_info, id_token = get_ticktix_user_info_from_code(code)

        # Extract user details
        email = user_info.get('email', '').lower()
        ticktix_user_id = user_info.get('sub') or user_info.get('id')

        frappe.logger().info(f"TickTix user: {email}, User ID: {ticktix_user_id}")

        resourceowner_id = user_info.get('urn:zitadel:iam:user:resourceowner:id')
        if resourceowner_id:
            resourceowner_name = user_info.get('urn:zitadel:iam:user:resourceowner:name')
            frappe.logger().info(f"TickTix user {email} authenticated in Zitadel org: {resourceowner_name} ({resourceowner_id})")

        if not email or not ticktix_user_id:
            frappe.throw("Invalid user information from TickTix")

        # Check if this is the admin email that should map to Administrator
        config_manager = get_config_manager()
        auth_config = config_manager.get_auth_config()
        admin_email = auth_config.get('ticktix_admin_email', 'facilitix@ticktix.com').lower()

        if email == admin_email:
            # Handle Administrator login
            return login_administrator_user(ticktix_user_id, email, state, id_token)
        else:
            # Check if user already exists with this TickTix mapping
            existing_user = frappe.db.get_value("User Social Login",
                                               {"provider": "ticktix", "userid": ticktix_user_id},
                                               "parent")

            if not existing_user:
                # No mapping for this Zitadel subject. Zitadel subject ids are
                # per-instance, so every pre-existing mapping breaks when the
                # instance changes (e.g. login.ticktix.com -> prep-authrix).
                # Re-bind by email if the User already exists locally; signups
                # stay disabled because an unknown email still falls through
                # to the 403 below.
                existing_user = rebind_social_login_by_email(email, ticktix_user_id, user_info)

            if existing_user:
                # Login existing user
                frappe.logger().info(f"Logging in existing user: {existing_user}")
                from frappe.utils.oauth import login_oauth_user
                login_oauth_user(user_info, provider="ticktix", state=state)
                cache_id_token(id_token)
            else:
                # No existing mapping found and signups are disabled
                frappe.logger().warning(f"No user mapping found for TickTix ID: {ticktix_user_id}")
                frappe.respond_as_web_page(
                    "Signup is Disabled",
                    f"The account <b>{escape_html(email)}</b> is not authorized to access this system. "
                    "Sign out and log in with a different account, or contact your administrator.",
                    success=False,
                    http_status_code=403,
                    primary_action=build_idp_logout_url(id_token),
                    primary_label="Sign out and use a different account"
                )

    except Exception as e:
        frappe.logger().error(f"TickTix OAuth error: {str(e)}")
        frappe.respond_as_web_page(
            "Login Error",
            f"Authentication failed: {str(e)}",
            success=False,
            http_status_code=500
        )


def rebind_social_login_by_email(email, ticktix_user_id, user_info=None):
    """Bind a Zitadel subject id to an existing User matched by email.

    Returns the User name on success, or None if no such User exists (in which
    case the caller must keep rejecting the login -- this is not a signup path).
    """
    if not frappe.db.exists("User", email):
        return None

    # Only an explicit false is treated as untrusted; a provider that omits the
    # claim entirely is left to the caller's existing behaviour.
    if user_info is not None and user_info.get("email_verified") is False:
        frappe.logger().warning(
            f"Refusing to bind TickTix ID {ticktix_user_id}: email {email} is not verified"
        )
        return None

    user_doc = frappe.get_doc("User", email)

    stale = [s.userid for s in user_doc.social_logins if s.provider == "ticktix"]
    if stale == [ticktix_user_id]:
        # Already bound; nothing to write.
        return user_doc.name

    if stale:
        frappe.logger().info(
            f"Replacing stale TickTix mapping(s) {stale} for {email} with {ticktix_user_id}"
        )
        # set_social_login_userid() only appends, so drop the old rows first to
        # avoid leaving two 'ticktix' entries on the user.
        user_doc.social_logins = [s for s in user_doc.social_logins if s.provider != "ticktix"]

    user_doc.set_social_login_userid("ticktix", userid=ticktix_user_id)
    user_doc.flags.ignore_permissions = True
    user_doc.save(ignore_permissions=True)
    frappe.db.commit()

    frappe.logger().info(f"Bound TickTix ID {ticktix_user_id} to existing user {email}")
    return user_doc.name


def login_administrator_user(ticktix_user_id, email, state, id_token=None):
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

        # Cache id_token for RP-Initiated Logout (after login_as, so it's keyed by the new session id)
        cache_id_token(id_token)

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
