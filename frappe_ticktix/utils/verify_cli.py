#!/usr/bin/env python3
"""
TickTix OAuth Integration Verification CLI Script

This is a standalone script to verify that the TickTix OAuth integration 
is properly configured and working.

Usage:
    python verify_ticktix_oauth.py

Requirements:
- Run from the Frappe bench directory
- TickTix site should be accessible
"""

import os
import sys

# Add paths for Frappe and TickTix app
sys.path.insert(0, 'apps/frappe')
sys.path.insert(0, 'apps/frappe_ticktix')

def main():
    try:
        import frappe
        from urllib.parse import urlencode
        
        # Initialize Frappe
        os.environ['FRAPPE_SITE'] = 'ticktix.local'
        frappe.init(site='ticktix.local', sites_path='sites')
        frappe.connect()
        
        print('🔍 TICKTIX OAUTH INTEGRATION VERIFICATION')
        print('='*60)
        
        checks = []
        
        # Check 1: OAuth-only settings
        password_disabled = bool(frappe.db.get_single_value('System Settings', 'disable_user_pass_login'))
        email_disabled = not bool(frappe.db.get_single_value('System Settings', 'login_with_email_link'))
        oauth_only = password_disabled and email_disabled
        checks.append(1 if oauth_only else 0)
        print(f'1️⃣  OAuth-Only Authentication: {"✅" if oauth_only else "❌"} {"Enabled" if oauth_only else "Disabled"}')
        
        # Check 2: Social Login Key
        social_login_exists = frappe.db.exists('Social Login Key', 'ticktix')
        checks.append(1 if social_login_exists else 0)
        print(f'2️⃣  TickTix Social Login Key: {"✅" if social_login_exists else "❌"} {"Found" if social_login_exists else "Missing"}')
        
        # Check 3: Administrator mapping
        from frappe_ticktix.config.config_manager import get_auth_config
        auth_config = get_auth_config()
        admin_user = frappe.get_doc('User', 'Administrator')
        admin_mapped = bool(admin_user.get_social_login_userid('ticktix'))
        admin_email_correct = admin_user.email == auth_config.get('ticktix_admin_email', 'facilitix@ticktix.com')
        checks.append(1 if admin_mapped and admin_email_correct else 0)
        print(f'3️⃣  Administrator Mapping: {"✅" if admin_mapped and admin_email_correct else "❌"} {"Properly Configured" if admin_mapped and admin_email_correct else "Issues Found"}')
        
        # Check 4: OAuth handlers
        try:
            from frappe_ticktix.plugins.authentication.login_callback import custom_oauth_handler, handle_ticktix_oauth
            handlers_ok = callable(custom_oauth_handler) and callable(handle_ticktix_oauth)
        except:
            handlers_ok = False
        checks.append(1 if handlers_ok else 0)
        print(f'4️⃣  OAuth Handlers: {"✅" if handlers_ok else "❌"} {"Available" if handlers_ok else "Missing"}')
        
        # Check 5: JWT Decoder
        try:
            from frappe_ticktix.plugins.authentication.login_callback import get_ticktix_user_info_from_code
            jwt_ok = callable(get_ticktix_user_info_from_code)
        except:
            jwt_ok = False
        checks.append(1 if jwt_ok else 0)
        print(f'5️⃣  JWT Decoder: {"✅" if jwt_ok else "❌"} {"Available" if jwt_ok else "Missing"}')
        
        # Check 6: Installation hooks
        try:
            from frappe_ticktix.install import after_install, disable_other_login_methods
            install_ok = callable(after_install) and callable(disable_other_login_methods)
        except:
            install_ok = False
        checks.append(1 if install_ok else 0)
        print(f'6️⃣  Installation Hooks: {"✅" if install_ok else "❌"} {"Available" if install_ok else "Missing"}')
        
        # Summary
        checks_passed = sum(checks)
        total_checks = len(checks)
        success_rate = checks_passed / total_checks
        
        print(f'\n📊 SUMMARY: {checks_passed}/{total_checks} checks passed ({success_rate:.0%})')
        
        if checks_passed == total_checks:
            print('🎉 ALL SYSTEMS GO! OAuth-only authentication is fully configured!')
            print('   ✓ Password login disabled')
            print('   ✓ TickTix OAuth enabled')  
            print('   ✓ Administrator mapped')
            print('   ✓ Custom handlers active')
            print('   ✓ JWT decoder working')
            print('   ✓ Installation hooks ready')
        elif success_rate >= 0.8:
            print('⚠️  Mostly configured - minor issues detected')
        else:
            print('❌ Major configuration issues detected')
        
        # Generate test OAuth URL
        print('\n🔗 Test OAuth URL:')
        if social_login_exists:
            social_login = frappe.get_doc('Social Login Key', 'ticktix')
            params = {
                'client_id': social_login.client_id,
                'response_type': 'code',
                'scope': 'openid profile email',
                'redirect_uri': f'http://ticktix.local:8000{social_login.redirect_url}',
                'state': 'verification_test'
            }
            oauth_url = f'{social_login.base_url}{social_login.authorize_url}?{urlencode(params)}'
            print(oauth_url)
            print('\n📋 Test Instructions:')
            print('1. Copy the URL above')
            print('2. Open in browser')
            print('3. Login with facilitix@ticktix.com')
            print('4. Should redirect back and login as Administrator')
            print('5. Verify /login page only shows TickTix option')
        else:
            print('❌ Cannot generate OAuth URL - Social Login Key missing')
        
        # Additional details
        if admin_mapped:
            ticktix_user_id = admin_user.get_social_login_userid('ticktix')
            print(f'\n📋 Administrator Details:')
            print(f'   Email: {admin_user.email}')
            print(f'   TickTix User ID: {ticktix_user_id}')
        
        print('\n✅ VERIFICATION COMPLETE')
        
        # Return success code
        return 0 if checks_passed == total_checks else 1
        
    except Exception as e:
        print(f'\n❌ VERIFICATION FAILED: {str(e)}')
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
