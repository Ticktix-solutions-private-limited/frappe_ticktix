"""
User Provisioning (Zitadel and IdentityServer4)

Provisions Frappe users into whichever IdP the site is configured for and
creates User Social Login mappings so OAuth login works. Which backend is
used is selected per-site by ticktix.identity_server.provider
("zitadel", the default, or "identityserver"); the two products have
unrelated admin APIs, so the actual request logic for each lives in its
own module - this one for Zitadel, identityserver_provisioner.py for
IdentityServer4 (login.ticktix.com). The public functions below
(auto_provision_user, provision_single_user, provision_existing_users)
are the shared entry points and dispatch to whichever backend applies.

Usage:
    bench --site <site> execute frappe_ticktix.plugins.authentication.zitadel_provisioner.provision_existing_users
    bench --site <site> execute frappe_ticktix.plugins.authentication.zitadel_provisioner.provision_single_user --kwargs '{"user_email":"john@example.com"}'

Zitadel backend requires ticktix.api.service_account_token (a Zitadel PAT)
and ticktix.identity_server.org_id. IdentityServer backend requires
ticktix.api.client_id/client_secret and ticktix.identity_server.provision_api.
"""

import frappe
import requests


def _get_provisioning_config():
    from ...config.config_manager import get_auth_config, require_org_id

    auth_config = get_auth_config()
    provider = auth_config.get('ticktix_identity_provider', 'zitadel')
    base_url = auth_config.get('ticktix_base_url', 'https://login.ticktix.com').rstrip('/')

    config = {
        'provider': provider,
        'base_url': base_url,
        'admin_email': auth_config.get('ticktix_admin_email', 'facilitix@ticktix.com').lower(),
        'initial_password': auth_config.get('ticktix_initial_password')
    }

    if provider == 'identityserver':
        client_id = auth_config.get('ticktix_api_client_id')
        client_secret = auth_config.get('ticktix_api_client_secret')
        if not client_id or not client_secret:
            frappe.throw(
                "IdentityServer API client credentials not configured. "
                "Set ticktix.api.client_id and ticktix.api.client_secret."
            )
        # IdentityServer's admin API lives on a separate host from the IdP
        # itself (authapi.ticktix.com vs login.ticktix.com) - falling back
        # to base_url would just 404, same as pointing the Zitadel backend
        # at the wrong host does.
        provision_api = auth_config.get('ticktix_provision_api')
        if not provision_api:
            frappe.throw("ticktix.identity_server.provision_api not configured for the identityserver provider.")

        config.update({
            'api_client_id': client_id,
            'api_client_secret': client_secret,
            'api_scope': auth_config.get('ticktix_api_scope'),
            'provision_api': provision_api
        })
        return config

    service_token = auth_config.get('ticktix_service_account_token')
    if not service_token:
        frappe.throw(
            "Zitadel service account token not configured. "
            "Set ticktix.api.service_account_token in common_site_config.json."
        )
    config.update({
        'service_token': service_token,
        'org_id': require_org_id(auth_config)
    })
    return config


def _is_provisioning_configured(auth_config):
    """Cheap pre-check mirroring _get_provisioning_config's requirements,
    used by the after_insert/after_save hooks to skip quietly on a config
    gap instead of throwing and rolling back unrelated User saves."""
    provider = auth_config.get('ticktix_identity_provider', 'zitadel')
    if provider == 'identityserver':
        return bool(auth_config.get('ticktix_api_client_id') and auth_config.get('ticktix_api_client_secret')
                     and auth_config.get('ticktix_provision_api'))
    return bool(auth_config.get('ticktix_service_account_token') and auth_config.get('ticktix_org_id'))


def _search_user(config, email):
    if config['provider'] == 'identityserver':
        from .identityserver_provisioner import search_user_by_email
        return search_user_by_email(config, email)
    headers = _zitadel_headers(config['service_token'], config['org_id'])
    return _search_zitadel_user_by_email(config['base_url'], headers, email)


def _create_user(config, user_doc):
    if config['provider'] == 'identityserver':
        from .identityserver_provisioner import create_user
        return create_user(config, user_doc)
    headers = _zitadel_headers(config['service_token'], config['org_id'])
    return _create_zitadel_user(config['base_url'], headers, user_doc, config.get('initial_password'))


def _zitadel_headers(service_token, org_id):
    return {
        'Authorization': f'Bearer {service_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'x-zitadel-orgid': org_id
    }


def _search_zitadel_user_by_email(base_url, headers, email):
    """Search Zitadel for a user by email. Returns userId if found, else None."""
    url = f"{base_url}/management/v1/users/_search"
    payload = {
        "queries": [
            {
                "emailQuery": {
                    "emailAddress": email,
                    "method": "TEXT_QUERY_METHOD_EQUALS"
                }
            }
        ]
    }

    response = requests.post(url, json=payload, headers=headers, timeout=15)
    response.raise_for_status()
    data = response.json()

    results = data.get('result', [])
    if results:
        return results[0].get('id')
    return None


def _create_zitadel_user(base_url, headers, user_doc, initial_password=None):
    """Create a human user in Zitadel. Returns the new userId.

    Without a password Zitadel leaves the user in the Initial state: the
    account exists but has no credential, cannot sign in, and the console
    offers only "Resend activation mail". Supplying initial_password (from
    ticktix.api.default_initial_password) creates the user Active instead,
    since the email is already sent as verified.
    """
    first_name = user_doc.first_name or user_doc.email.split('@')[0]
    last_name = user_doc.last_name or '-'

    url = f"{base_url}/management/v1/users/human"
    payload = {
        "userName": user_doc.email,
        "profile": {
            "firstName": first_name,
            "lastName": last_name,
            "displayName": user_doc.full_name or first_name
        },
        "email": {
            "email": user_doc.email,
            "isEmailVerified": True
        }
    }

    if initial_password:
        payload["initialPassword"] = initial_password

    response = requests.post(url, json=payload, headers=headers, timeout=15)
    response.raise_for_status()
    return response.json().get('userId')


def _ensure_social_login_mapping(user_doc, zitadel_user_id):
    """Create or update the User Social Login mapping for the ticktix provider."""
    existing = user_doc.get_social_login_userid('ticktix')

    if existing == zitadel_user_id:
        return False

    if existing:
        for sl in user_doc.social_logins:
            if sl.provider == 'ticktix':
                sl.userid = zitadel_user_id
                break
    else:
        user_doc.set_social_login_userid('ticktix', userid=zitadel_user_id, username=user_doc.email)

    user_doc.flags.ignore_permissions = True
    user_doc.save()
    return True


def auto_provision_user(doc, method=None):
    """Hook: after_insert on User. Pushes the new user to the configured IdP.

    Raises on failure so the User creation rolls back — a Frappe user
    without a corresponding IdP account cannot authenticate.
    """
    if doc.name in ('Guest', 'Administrator'):
        return
    if not doc.email:
        return

    from ...config.config_manager import get_auth_config
    auth_config = get_auth_config()
    if not _is_provisioning_configured(auth_config):
        # Config gap, not an IdP failure - skip quietly rather than blocking
        # every User creation in the system (auto_provision_user has no
        # try/except, so an uncaught throw here would roll back unrelated
        # User inserts across the whole app, not just OAuth-related ones).
        frappe.logger().warning(f"Skipping IdP provisioning for {doc.email}: provisioning not fully configured")
        return

    config = _get_provisioning_config()

    external_id = _search_user(config, doc.email)
    if not external_id:
        external_id = _create_user(config, doc)

    if not external_id:
        frappe.throw(f"Failed to provision {doc.email} in {config['provider']}: no user id returned")

    _ensure_social_login_mapping(doc, external_id)
    frappe.logger().info(f"Provisioned {doc.email} to {config['provider']}: {external_id}")


def provision_on_email_update(doc, method=None):
    """Hook: after_save on User. Pushes users to Zitadel once they gain an email.

    Covers users created without an email (e.g. some Website Users) whose
    email is filled in on a later save — after_insert provisioning had
    nothing to provision at creation time for these.
    """
    if doc.name in ('Guest', 'Administrator') or not doc.enabled:
        return
    if not doc.email:
        return
    if doc.get_social_login_userid('ticktix'):
        return
    if not doc.has_value_changed('email'):
        return

    from ...config.config_manager import get_auth_config
    auth_config = get_auth_config()
    if not _is_provisioning_configured(auth_config):
        # Config gap, not an IdP failure - skip quietly instead of letting
        # it fall into the try/except below and get logged indistinguishably
        # from a real API failure on every subsequent email-change save.
        frappe.logger().warning(f"Skipping IdP provisioning for {doc.email}: provisioning not fully configured")
        return

    try:
        config = _get_provisioning_config()

        external_id = _search_user(config, doc.email)
        if not external_id:
            external_id = _create_user(config, doc)

        if not external_id:
            frappe.logger().error(f"Failed to provision {doc.email} in {config['provider']} after email update: no user id returned")
            return

        _ensure_social_login_mapping(doc, external_id)
        frappe.logger().info(f"Provisioned {doc.email} to {config['provider']} after email update: {external_id}")
    except Exception as e:
        frappe.log_error(
            message=f"Failed to provision {doc.email} after email update: {str(e)}",
            title='IdP Provisioning Error'
        )


def provision_single_user(user_email):
    """Provision a single Frappe user into the currently configured IdP.

    1. Search the IdP by email.
    2. If found, ensure the mapping points at that id.
    3. If not found, create the user in the IdP, then create the mapping.

    Does NOT skip just because a 'ticktix' mapping already exists - that
    mapping may belong to a different provider than the one currently
    configured (e.g. an IdentityServer GUID left over from before a switch
    to Zitadel, or vice versa - both write to the same provider='ticktix'
    field, so a stale mapping from the other IdP would otherwise be
    mistaken for "already provisioned here" forever). _ensure_social_login_mapping
    below is a no-op when the found id already matches what's stored, so
    this costs nothing for users genuinely already mapped to this provider.
    """
    config = _get_provisioning_config()

    if not frappe.db.exists('User', user_email):
        return {'status': 'error', 'message': f'User {user_email} not found in Frappe'}

    user_doc = frappe.get_doc('User', user_email)
    email = user_doc.email
    if not email:
        return {'status': 'error', 'message': 'User has no email'}

    existing_mapping = user_doc.get_social_login_userid('ticktix')

    try:
        external_id = _search_user(config, email)

        if external_id:
            changed = _ensure_social_login_mapping(user_doc, external_id)
            if not changed:
                return {'status': 'skipped', 'message': f"Already correctly mapped to {external_id} in {config['provider']}", 'zitadel_id': external_id}
            message = (f"Found in {config['provider']}, mapping updated (was {existing_mapping})"
                       if existing_mapping else f"Found in {config['provider']}, mapping created")
            return {'status': 'mapped', 'message': message, 'zitadel_id': external_id}

        external_id = _create_user(config, user_doc)
        if not external_id:
            return {'status': 'error', 'message': f"{config['provider']} returned no user id"}

        _ensure_social_login_mapping(user_doc, external_id)
        return {'status': 'created', 'message': f"Created in {config['provider']} and mapped", 'zitadel_id': external_id}

    except requests.exceptions.HTTPError as e:
        error_detail = ''
        try:
            error_detail = e.response.json()
        except Exception:
            error_detail = e.response.text[:200] if e.response else str(e)
        return {'status': 'error', 'message': f"{config['provider']} API error: {error_detail}"}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def provision_existing_users():
    """Provision all enabled Frappe users into Zitadel.

    Skips Guest, Administrator (handled via login_administrator_user),
    and users that already have a ticktix mapping.

    Usage:
        bench --site <site> execute frappe_ticktix.plugins.authentication.zitadel_provisioner.provision_existing_users
    """
    config = _get_provisioning_config()
    admin_email = config['admin_email']

    users = frappe.get_all('User',
        filters={
            'enabled': 1,
            'name': ['not in', ['Guest', 'Administrator']]
        },
        fields=['name', 'email']
    )

    results = {'total': len(users), 'created': 0, 'mapped': 0, 'skipped': 0, 'errors': 0, 'details': []}

    print(f"\nProvisioning {len(users)} users into Zitadel at {config['base_url']}...")
    print("=" * 60)

    for user_data in users:
        email = user_data.email
        if not email:
            results['skipped'] += 1
            print(f"  SKIP   {user_data.name}: no email")
            continue

        if email.lower() == admin_email:
            results['skipped'] += 1
            print(f"  SKIP   {email}: admin account (handled by login_administrator_user)")
            continue

        result = provision_single_user(user_data.name)
        status = result['status']

        if status == 'created':
            results['created'] += 1
            print(f"  CREATE {email} -> {result['zitadel_id']}")
        elif status == 'mapped':
            results['mapped'] += 1
            print(f"  MAP    {email} -> {result['zitadel_id']}")
        elif status == 'skipped':
            results['skipped'] += 1
            print(f"  SKIP   {email}: {result['message']}")
        else:
            results['errors'] += 1
            print(f"  ERROR  {email}: {result['message']}")

        results['details'].append(f"{status.upper()} {email}: {result['message']}")

    frappe.db.commit()

    print("=" * 60)
    print(f"Done: {results['created']} created, {results['mapped']} mapped, "
          f"{results['skipped']} skipped, {results['errors']} errors")

    return results
