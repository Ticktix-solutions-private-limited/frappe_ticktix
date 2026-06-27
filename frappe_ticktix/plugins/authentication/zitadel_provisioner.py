"""
Zitadel User Provisioning

Provisions existing Frappe users into Zitadel via the Management API
and creates User Social Login mappings so OAuth login works.

Usage:
    bench --site <site> execute frappe_ticktix.plugins.authentication.zitadel_provisioner.provision_existing_users
    bench --site <site> execute frappe_ticktix.plugins.authentication.zitadel_provisioner.provision_single_user --kwargs '{"user_email":"john@example.com"}'

Requires ticktix.api.service_account_token in common_site_config.json (a Zitadel PAT).
"""

import frappe
import requests


def _get_provisioning_config():
    from ...config.config_manager import get_auth_config, get_config_manager

    auth_config = get_auth_config()
    service_token = auth_config.get('ticktix_service_account_token')

    if not service_token:
        frappe.throw(
            "Zitadel service account token not configured. "
            "Set ticktix.api.service_account_token in common_site_config.json."
        )

    return {
        'base_url': auth_config.get('ticktix_base_url', 'https://login.ticktix.com').rstrip('/'),
        'service_token': service_token,
        'admin_email': auth_config.get('ticktix_admin_email', 'facilitix@ticktix.com').lower()
    }


def _zitadel_headers(service_token):
    return {
        'Authorization': f'Bearer {service_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
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


def _create_zitadel_user(base_url, headers, user_doc):
    """Create a human user in Zitadel. Returns the new userId."""
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
    """Hook: after_insert on User. Pushes the new user to Zitadel.

    Raises on failure so the User creation rolls back — a Frappe user
    without a corresponding Zitadel account cannot authenticate.
    """
    if doc.name in ('Guest', 'Administrator'):
        return
    if not doc.email:
        return

    from ...config.config_manager import get_auth_config
    auth_config = get_auth_config()
    if not auth_config.get('ticktix_service_account_token'):
        return

    config = _get_provisioning_config()
    headers = _zitadel_headers(config['service_token'])
    base_url = config['base_url']

    zitadel_id = _search_zitadel_user_by_email(base_url, headers, doc.email)

    if not zitadel_id:
        zitadel_id = _create_zitadel_user(base_url, headers, doc)

    if not zitadel_id:
        frappe.throw(f"Failed to provision {doc.email} in Zitadel: no userId returned")

    _ensure_social_login_mapping(doc, zitadel_id)
    frappe.logger().info(f"Provisioned {doc.email} to Zitadel: {zitadel_id}")


def provision_single_user(user_email):
    """Provision a single Frappe user into Zitadel.

    1. Skip if already has a User Social Login mapping for ticktix.
    2. Search Zitadel by email — if found, create mapping.
    3. If not found, create user in Zitadel, then create mapping.
    """
    config = _get_provisioning_config()
    headers = _zitadel_headers(config['service_token'])
    base_url = config['base_url']

    if not frappe.db.exists('User', user_email):
        return {'status': 'error', 'message': f'User {user_email} not found in Frappe'}

    user_doc = frappe.get_doc('User', user_email)
    email = user_doc.email
    if not email:
        return {'status': 'error', 'message': 'User has no email'}

    existing_mapping = user_doc.get_social_login_userid('ticktix')
    if existing_mapping:
        return {'status': 'skipped', 'message': f'Already mapped to {existing_mapping}', 'zitadel_id': existing_mapping}

    try:
        zitadel_id = _search_zitadel_user_by_email(base_url, headers, email)

        if zitadel_id:
            _ensure_social_login_mapping(user_doc, zitadel_id)
            return {'status': 'mapped', 'message': 'Found in Zitadel, mapping created', 'zitadel_id': zitadel_id}

        zitadel_id = _create_zitadel_user(base_url, headers, user_doc)
        if not zitadel_id:
            return {'status': 'error', 'message': 'Zitadel returned no userId'}

        _ensure_social_login_mapping(user_doc, zitadel_id)
        return {'status': 'created', 'message': 'Created in Zitadel and mapped', 'zitadel_id': zitadel_id}

    except requests.exceptions.HTTPError as e:
        error_detail = ''
        try:
            error_detail = e.response.json()
        except Exception:
            error_detail = e.response.text[:200] if e.response else str(e)
        return {'status': 'error', 'message': f'Zitadel API error: {error_detail}'}
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
