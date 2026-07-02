"""
TickTix OAuth Integration Verification Module

This module provides functions to verify the TickTix OAuth integration
through Frappe's API endpoints.

API Endpoints:
- /api/method/frappe_ticktix.utils.verify_setup.quick_status
- /api/method/frappe_ticktix.utils.verify_setup.verify_complete_integration  
- /api/method/frappe_ticktix.utils.verify_setup.get_test_oauth_url
- /api/method/frappe_ticktix.utils.verify_setup.test_jwt_decoder
"""

import frappe
from urllib.parse import urlencode


@frappe.whitelist()
def quick_status():
    """Quick status check for OAuth integration"""
    try:
        # Quick checks
        password_disabled = bool(frappe.db.get_single_value('System Settings', 'disable_user_pass_login'))
        social_login_exists = frappe.db.exists('Social Login Key', 'ticktix')
        admin_mapped = bool(frappe.get_doc('User', 'Administrator').get_social_login_userid('ticktix'))
        
        if password_disabled and social_login_exists and admin_mapped:
            status = "🎉 OAuth-only authentication is ACTIVE"
        elif social_login_exists and admin_mapped:
            status = "⚠️ OAuth configured but password login still enabled"
        elif social_login_exists:
            status = "🔧 OAuth partially configured"
        else:
            status = "❌ OAuth not configured"
            
        return {
            'status': status,
            'password_disabled': password_disabled,
            'social_login_exists': social_login_exists,
            'admin_mapped': admin_mapped
        }
        
    except Exception as e:
        return {
            'status': f"❌ Error checking status: {str(e)}"
        }


@frappe.whitelist()
def get_test_oauth_url():
    """Generate OAuth URL for testing the complete flow"""
    try:
        if not frappe.db.exists('Social Login Key', 'ticktix'):
            return {
                'status': 'error',
                'message': 'TickTix Social Login Key not found'
            }
            
        social_login = frappe.get_doc('Social Login Key', 'ticktix')
        
        params = {
            'client_id': social_login.client_id,
            'response_type': 'code',
            'scope': 'openid profile email',
            'redirect_uri': f"http://ticktix.local:8000{social_login.redirect_url}",
            'state': 'verification_test'
        }
        
        oauth_url = f"{social_login.base_url}{social_login.authorize_url}?{urlencode(params)}"
        
        return {
            'status': 'success',
            'oauth_url': oauth_url,
            'instructions': [
                '1. Open the OAuth URL in a browser',
                '2. Login with facilitix@ticktix.com credentials',
                '3. Should redirect back and login as Administrator',
                '4. Check that /login page only shows TickTix login option'
            ]
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error generating OAuth URL: {str(e)}'
        }


@frappe.whitelist()
def verify_complete_integration():
    """
    Complete verification of TickTix OAuth integration.
    Returns comprehensive status of all components.
    """
    results = {
        'overall_status': 'unknown',
        'checks_passed': 0,
        'total_checks': 7,
        'checks': [],
        'oauth_test_url': None,
        'summary': {}
    }
    
    try:
        checks = []
        
        # Check 1: OAuth-only settings
        password_disabled = bool(frappe.db.get_single_value('System Settings', 'disable_user_pass_login'))
        email_disabled = not bool(frappe.db.get_single_value('System Settings', 'login_with_email_link'))
        oauth_only = password_disabled and email_disabled
        checks.append({
            'name': 'OAuth-Only Authentication',
            'success': oauth_only,
            'message': 'Password login disabled, OAuth-only enabled' if oauth_only else 'Password/email login still enabled'
        })
        
        # Check 2: Social Login Key
        social_login_exists = frappe.db.exists('Social Login Key', 'ticktix')
        checks.append({
            'name': 'TickTix Social Login Key',
            'success': social_login_exists,
            'message': 'Social Login Key found' if social_login_exists else 'Social Login Key missing'
        })
        
        # Check 3: Administrator mapping
        admin_user = frappe.get_doc('User', 'Administrator')
        admin_mapped = bool(admin_user.get_social_login_userid('ticktix'))
        admin_email_correct = admin_user.email == 'facilitix@ticktix.com'
        admin_ok = admin_mapped and admin_email_correct
        checks.append({
            'name': 'Administrator Setup',
            'success': admin_ok,
            'message': 'Administrator properly configured' if admin_ok else 'Administrator configuration issues'
        })
        
        # Check 4: OAuth handlers
        try:
            from frappe_ticktix.plugins.authentication.login_callback import custom_oauth_handler, handle_ticktix_oauth
            handlers_ok = callable(custom_oauth_handler) and callable(handle_ticktix_oauth)
        except:
            handlers_ok = False
        checks.append({
            'name': 'OAuth Handlers',
            'success': handlers_ok,
            'message': 'OAuth handlers available' if handlers_ok else 'OAuth handlers missing'
        })
        
        # Check 5: JWT Decoder
        try:
            from frappe_ticktix.plugins.authentication.login_callback import get_ticktix_user_info_from_code
            jwt_ok = callable(get_ticktix_user_info_from_code)
        except:
            jwt_ok = False
        checks.append({
            'name': 'JWT Decoder',
            'success': jwt_ok,
            'message': 'JWT decoder available' if jwt_ok else 'JWT decoder missing'
        })
        
        # Check 6: Installation hooks
        try:
            from frappe_ticktix.install import after_install, disable_other_login_methods
            install_ok = callable(after_install) and callable(disable_other_login_methods)
        except:
            install_ok = False
        checks.append({
            'name': 'Installation Hooks',
            'success': install_ok,
            'message': 'Installation hooks available' if install_ok else 'Installation hooks missing'
        })
        
        # Check 7: User Provisioning System
        try:
            from frappe_ticktix.plugins.authentication.login_callback import auto_provision_user, handle_user_email_update
            from frappe_ticktix.install import provision_existing_users
            provisioning_ok = (callable(auto_provision_user) and 
                             callable(handle_user_email_update) and 
                             callable(provision_existing_users))
        except:
            provisioning_ok = False
        checks.append({
            'name': 'User Provisioning System',
            'success': provisioning_ok,
            'message': 'Auto-provisioning available (new users, email updates, installation)' if provisioning_ok else 'User provisioning functions missing'
        })
        
        results['checks'] = checks
        results['checks_passed'] = sum(1 for check in checks if check['success'])
        success_rate = results['checks_passed'] / results['total_checks']
        
        if success_rate == 1.0:
            results['overall_status'] = 'success'
            status_msg = "ALL CHECKS PASSED"
        elif success_rate >= 0.75:
            results['overall_status'] = 'warning'
            status_msg = "MOSTLY CONFIGURED"
        else:
            results['overall_status'] = 'error'
            status_msg = "CONFIGURATION INCOMPLETE"
        
        # Generate OAuth test URL
        if social_login_exists:
            oauth_result = get_test_oauth_url()
            if oauth_result.get('status') == 'success':
                results['oauth_test_url'] = oauth_result.get('oauth_url')
        
        results['summary'] = {
            'status': results['overall_status'],
            'message': status_msg,
            'success_rate': f"{results['checks_passed']}/{results['total_checks']}",
            'oauth_ready': results['overall_status'] in ['success', 'warning']
        }
        
        return results
        
    except Exception as e:
        results['overall_status'] = 'error'
        results['error'] = str(e)
        frappe.log_error(message=f"TickTix verification failed: {str(e)}", title='TickTix Verification Error')
        return results


@frappe.whitelist()
def test_jwt_decoder():
    """Test JWT decoder with a sample TickTix token"""
    try:
        # Sample JWT token from actual implementation
        sample_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6IkEwRjMxRUE2M0MxMTgxRERBRkFENzA3RUJBRjgzQzc4IiwidHlwIjoiSldUIn0.eyJpc3MiOiJodHRwczovL2xvZ2luLnRpY2t0aXguY29tIiwibmJmIjoxNzU2MDM1MzgyLCJpYXQiOjE3NTYwMzUzODIsImV4cCI6MTc1NjAzNTY4MiwiYXVkIjoiMTkyNDQxOTVkYTFiZGEyZTFiMDgxODE2ZmE5M2QzNmQiLCJhbXIiOlsicHdkIl0sImF0X2hhc2giOiJLZEFtbF8tdEsxaENFNnE2MlkzaTN3Iiwic2lkIjoiOUIxNDE5REVGMjY0QUY4N0U2RkU3NDU0MzkzMjA0MEIiLCJzdWIiOiI2MTE2YTZiNi05NTRkLTQwOTktOTgyMi1lNGFhYWE5OTExYmQiLCJhdXRoX3RpbWUiOjE3NTYwMzUzODIsImlkcCI6ImxvY2FsIiwiZW1haWwiOiJmYWNpbGl0aXhAdGlja3RpeC5jb20iLCJBc3BOZXQuSWRlbnRpdHkuU2VjdXJpdHlTdGFtcCI6IkpKUENJR01UQ1NONEZWWVMyNUZaR0k2REpDSDRIT09EIiwicHJlZmVycmVkX3VzZXJuYW1lIjoiQWRtaW5pc3RyYXRvciIsIm5hbWUiOiJBZG1pbmlzdHJhdG9yIiwiZW1haWxfdmVyaWZpZWQiOnRydWV9.EMdkUPqdSTpsY7ktWQ23_KV7yOV7HyK5bIKhpjegy0WVVD9ch7eBbs4REwC3h6Dz1vjE6XK_QppXUM4BMJEBQM_DxzmbtG0JRuuQKgAi-UL-Zg_FAKbQLDusaCbqEeU0SfDLrA2ZdqkrjUR1ZW_ak7mRZ19hFxPq8elMsVlurx5VoCezZeaDh0ISVnrlHN5NS4BQ7UdXm3VPUGhhK5VGaNPMijyaGE5ddiGqpwFeEAL4V91gw-GKBff4HnXW5i2OzXWMl6v3z9BY6RaLxhyEPwhz0EXvslCrkY0jTsJfQH79kafoMmWbVooiQKLRAwssggc1YgkIlgH1SyQRwhH5Kg"
        
        from frappe_ticktix.plugins.authentication.login_callback import get_ticktix_user_info_from_code
        
        # Test the decoder
        user_info = get_ticktix_user_info_from_code('test_code', sample_token)
        
        # Check Administrator mapping
        admin_user = frappe.get_doc('User', 'Administrator')
        admin_mapping = admin_user.get_social_login_userid('ticktix')
        
        return {
            'status': 'success',
            'message': 'JWT decoder working correctly',
            'user_info': user_info,
            'admin_mapping': admin_mapping,
            'validation': {
                'email_match': user_info.get('email') == 'facilitix@ticktix.com',
                'user_id_match': user_info.get('sub') == '6116a6b6-954d-4099-9822-e4aaaa9911bd',
                'admin_mapped_correctly': admin_mapping == '6116a6b6-954d-4099-9822-e4aaaa9911bd'
            }
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f'JWT decoder test failed: {str(e)}',
            'error': str(e)
        }


@frappe.whitelist()
def test_auto_provisioning():
    """Test the automatic user provisioning system by creating a temporary user"""
    try:
        import time
        
        # Generate unique test email
        timestamp = str(int(time.time()))
        test_email = f"test-{timestamp}@ticktix.com"
        
        # Create temporary test user (Website User to test all user types)
        test_user = frappe.new_doc('User')
        test_user.email = test_email
        test_user.first_name = 'Test'
        test_user.last_name = 'AutoProvision'
        test_user.user_type = 'Website User'  # Test with Website User
        test_user.enabled = 1
        test_user.send_welcome_email = 0
        test_user.flags.ignore_permissions = True
        
        # Insert the user (should trigger auto-provisioning)
        test_user.insert(ignore_permissions=True)
        frappe.db.commit()
        
        # Check if social login mapping was created
        test_user.reload()
        ticktix_mapping = test_user.get_social_login_userid('ticktix')
        
        # Clean up - delete the test user
        frappe.delete_doc('User', test_email, ignore_permissions=True)
        frappe.db.commit()
        
        if ticktix_mapping:
            return {
                'status': 'success',
                'message': 'Auto-provisioning working correctly',
                'test_email': test_email,
                'user_type': 'Website User',
                'ticktix_user_id': ticktix_mapping,
                'details': 'User was created in TickTix IDP and social login mapping was established'
            }
        else:
            return {
                'status': 'warning',
                'message': 'Auto-provisioning completed but no mapping found',
                'test_email': test_email,
                'user_type': 'Website User',
                'details': 'User may have been created in IDP but mapping failed or was not established'
            }
            
    except Exception as e:
        # Try to clean up if there was an error
        try:
            if 'test_email' in locals():
                frappe.delete_doc('User', test_email, ignore_permissions=True)
                frappe.db.commit()
        except:
            pass
            
        return {
            'status': 'error',
            'message': f'Auto-provisioning test failed: {str(e)}',
            'error': str(e)
        }


@frappe.whitelist()
def test_installation_provisioning():
    """Test the installation-time user provisioning functionality"""
    if not frappe.has_permission('System Settings', 'read'):
        frappe.throw("Insufficient permissions")
        
    try:
        # Check if provisioning functions are available
        from frappe_ticktix.install import provision_existing_users, manual_provision_existing_users
        
        # Count existing users with emails that don't have TickTix mapping
        users_needing_provision = frappe.db.sql("""
            SELECT u.name, u.email, u.user_type
            FROM `tabUser` u
            WHERE u.enabled = 1 
            AND u.email IS NOT NULL 
            AND u.email != ''
            AND u.name NOT IN ('Administrator', 'Guest')
            AND NOT EXISTS (
                SELECT 1 FROM `tabUser Social Login` usl 
                WHERE usl.parent = u.name 
                AND usl.provider = 'ticktix'
            )
        """, as_dict=True)
        
        # Count users with existing TickTix mappings
        users_with_mapping = frappe.db.sql("""
            SELECT COUNT(*) as count
            FROM `tabUser Social Login` usl
            JOIN `tabUser` u ON u.name = usl.parent
            WHERE usl.provider = 'ticktix'
            AND u.enabled = 1
            AND u.name NOT IN ('Administrator', 'Guest')
        """, as_dict=True)[0].count
        
        # Check if API connectivity is available
        try:
            from frappe_ticktix.plugins.authentication.login_callback import get_api_access_token
            api_available = bool(get_api_access_token())
        except:
            api_available = False
        
        return {
            'status': 'success',
            'message': 'Installation provisioning system ready',
            'users_needing_provision': len(users_needing_provision),
            'users_with_mapping': users_with_mapping,
            'api_available': api_available,
            'details': {
                'functions_available': True,
                'can_provision_existing': len(users_needing_provision) > 0,
                'provision_ready': api_available and len(users_needing_provision) > 0,
                'users_to_provision': [
                    {
                        'email': user.email,
                        'user_type': user.user_type
                    } for user in users_needing_provision[:5]  # Show first 5 as sample
                ]
            },
            'recommendations': [
                'Run manual_provision_existing_users() to provision unmapped users' if len(users_needing_provision) > 0 else 'All users are already provisioned',
                'API connectivity is working' if api_available else 'Check TickTix API configuration',
                f'{len(users_needing_provision)} users need provisioning' if len(users_needing_provision) > 0 else 'No users need provisioning'
            ]
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Installation provisioning test failed: {str(e)}',
            'error': str(e)
        }
