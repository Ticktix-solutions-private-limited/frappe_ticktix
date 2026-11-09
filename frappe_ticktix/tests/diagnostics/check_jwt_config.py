#!/usr/bin/env python3
"""
Diagnostic script for prep-hrms.ticktix.com
Run this via: bench --site prep-hrms.ticktix.com execute frappe_ticktix.diagnostics.check_jwt_config
Or copy content and paste into: bench --site prep-hrms.ticktix.com console
"""

import frappe
import json

def check_jwt_config():
    print("\n" + "="*80)
    print("PREP-HRMS JWT CONFIGURATION DIAGNOSTIC")
    print("="*80)

    # Test 1: Check _get_common_site_config (base config)
    print("\n1. _get_common_site_config() - Base Config:")
    from frappe_ticktix.config.config_manager import get_config_manager
    config_manager = get_config_manager()
    common_config = config_manager._get_common_site_config()
    ticktix_common = common_config.get('ticktix', {})
    print(json.dumps(ticktix_common, indent=2, default=str))

    # Test 2: Check _get_site_config (site overrides)
    print("\n2. _get_site_config() - Site Overrides:")
    site_config = config_manager._get_site_config()
    ticktix_site = site_config.get('ticktix', {})
    print(json.dumps(ticktix_site, indent=2, default=str))

    # Test 3: Check get_config_value (deep merged result)
    print("\n3. get_config_value('ticktix') - Deep Merged Result:")
    ticktix_config = config_manager.get_config_value('ticktix', {})
    print(json.dumps(ticktix_config, indent=2, default=str))

    # Test 4: Check get_auth_config result (all properties)
    print("\n4. get_auth_config() - All Properties:")
    auth_config = config_manager.get_auth_config()
    print(json.dumps(auth_config, indent=2, default=str))

    # Test 5: Check get_branding_config result
    print("\n5. get_branding_config():")
    branding_config = config_manager.get_branding_config()
    print(json.dumps(branding_config, indent=2, default=str))

    # Test 6: Check recent error logs
    print("\n6. Recent JWT-related Error Logs:")
    try:
        errors = frappe.get_all('Error Log', 
            fields=['name', 'error', 'creation'],
            filters={'error': ['like', '%JWT%']},
            order_by='creation desc',
            limit=3
        )
        
        if errors:
            for err in errors:
                print(f"\n   {err.creation}")
                print(f"   {err.error[:300]}...")
        else:
            print("   No JWT-related errors found")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")

    print("\n" + "="*80)
    print("DIAGNOSTIC COMPLETE")
    print("="*80 + "\n")

if __name__ == "__main__":
    check_jwt_config()
