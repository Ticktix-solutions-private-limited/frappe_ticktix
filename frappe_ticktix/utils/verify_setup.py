"""
TickTix OAuth Integration Verification Module

This module provides functions to verify the TickTix OAuth integration
through Frappe's API endpoints.

API Endpoints:
- /api/method/frappe_ticktix.utils.verify_setup.quick_status
- /api/method/frappe_ticktix.utils.verify_setup.verify_complete_integration
- /api/method/frappe_ticktix.utils.verify_setup.get_test_oauth_url
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
        'total_checks': 6,
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
        from frappe_ticktix.config.config_manager import get_auth_config
        auth_config = get_auth_config()
        admin_user = frappe.get_doc('User', 'Administrator')
        admin_mapped = bool(admin_user.get_social_login_userid('ticktix'))
        admin_email_correct = admin_user.email == auth_config.get('ticktix_admin_email', 'facilitix@ticktix.com')
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

