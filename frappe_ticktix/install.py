import frappe
import json


def after_install():
    """Setup TickTix login configuration after app installation"""
    print("Setting up TickTix login integration...")
    
    # Setup Administrator user email first
    setup_administrator_user()
    
    # Setup Social Login Key
    setup_ticktix_social_login()
    
    # Disable other login methods
    disable_other_login_methods()
    
    # Setup HTTPS enforcement
    setup_https_enforcement()
    
    # Setup company logo
    setup_company_logo()
    
    # Provision all existing users with email addresses to TickTix IDP
    provision_existing_users()
    
    # Setup HR customizations
    setup_hr_customizations()
    
    # Apply attendance overrides (for custom status validation)
    apply_attendance_overrides()
    
    # Apply payroll overrides
    apply_payroll_overrides()
    
    print("TickTix login integration setup completed!")


def after_migrate():
    """
    Run after every migration (bench migrate)
    Ensures custom fields and configurations are always up-to-date
    """
    print("\n" + "=" * 70)
    print("FRAPPE_TICKTIX: Running post-migration setup...")
    print("=" * 70)
    
    # Setup HR customizations (includes custom fields)
    # This runs on every migrate to ensure fields exist
    setup_hr_customizations()
    
    # Apply attendance overrides (for custom status validation)
    apply_attendance_overrides()
    
    # Apply payroll overrides
    apply_payroll_overrides()
    
    print("=" * 70)
    print("FRAPPE_TICKTIX: Post-migration setup completed!")
    print("=" * 70)


def before_uninstall():
    """Clean up TickTix configuration before app uninstall"""
    print("Cleaning up TickTix login integration...")
    
    try:
        # 1. Remove TickTix Social Login Key
        if frappe.db.exists('Social Login Key', 'ticktix'):
            try:
                frappe.delete_doc('Social Login Key', 'ticktix', ignore_permissions=True, force=True)
                print("✓ TickTix Social Login Key removed")
            except Exception as delete_error:
                # Fallback: Direct database deletion if document delete fails
                try:
                    frappe.db.sql("DELETE FROM `tabSocial Login Key` WHERE name = 'ticktix'")
                    frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype = 'Social Login Key' AND name = 'ticktix'")
                    print("✓ TickTix Social Login Key removed (direct DB)")
                except Exception as db_error:
                    print(f"⚠ Could not remove Social Login Key: {delete_error}")
        
        # 2. Reset login methods back to username/password
        frappe.db.set_single_value('System Settings', 'disable_user_pass_login', 0)
        frappe.db.set_single_value('System Settings', 'login_with_email_link', 1)
        print("✓ Username/password login re-enabled")
        print("✓ Email link login re-enabled")
        
        # 3. Reset app branding to Frappe default
        frappe.db.set_single_value('System Settings', 'app_name', 'Frappe')
        print("✓ App name reset to 'Frappe'")
        
        # 4. Remove email from Administrator account (keep the account)
        if frappe.db.exists('User', 'Administrator'):
            current_email = frappe.db.get_value('User', 'Administrator', 'email')
            if current_email and current_email.strip():
                # Clear the email but keep the account
                frappe.db.set_value('User', 'Administrator', 'email', '')
                print(f"✓ Administrator email cleared (was: {current_email})")
            else:
                print("✓ Administrator email already empty")
        
        frappe.db.commit()
        print("✓ TickTix cleanup completed successfully!")
        print("✓ System restored to standard Frappe authentication")
        
    except Exception as e:
        print(f"Error during cleanup: {e}")
        try:
            frappe.db.rollback()
        except:
            pass  # Ignore rollback errors
        # Don't raise error to avoid breaking uninstall process
        print("⚠ Some cleanup steps may have failed, but uninstall will continue")


def update_social_login_redirect_url(social_login_key):
    """Update Social Login Key redirect URL to use relative URL (Frappe will make it absolute automatically)"""
    try:
        from frappe_ticktix.config.config_manager import get_auth_config
        auth_config = get_auth_config()
        
        # Use relative redirect URL - Frappe automatically converts to absolute URL using site's base URL
        redirect_uri_template = auth_config.get('ticktix_redirect_url_template', '/api/method/frappe.integrations.oauth2_logins.custom/ticktix')
        
        if social_login_key.redirect_url != redirect_uri_template:
            old_redirect_url = social_login_key.redirect_url
            social_login_key.redirect_url = redirect_uri_template
            print(f"✓ Updated redirect URL from: {old_redirect_url}")
            print(f"✓ Updated redirect URL to: {redirect_uri_template}")
            print(f"✓ Frappe will automatically convert this to absolute URL using site's base URL")
        else:
            print(f"✓ Redirect URL already correct: {redirect_uri_template}")
            
    except Exception as e:
        print(f"Warning: Could not update redirect URL: {e}")
        # Don't raise error as this shouldn't break the setup


def setup_administrator_user():
    """Setup Administrator user with configured admin email"""
    try:
        # Get admin email from configuration using ConfigManager
        from frappe_ticktix.config.config_manager import get_auth_config
        auth_config = get_auth_config()
        admin_email = auth_config.get('ticktix_admin_email', 'facilitix@ticktix.com')
        
        # Update Administrator user email
        if frappe.db.exists('User', 'Administrator'):
            admin_doc = frappe.get_doc('User', 'Administrator')
            
            if admin_doc.email != admin_email:
                admin_doc.email = admin_email
                admin_doc.save(ignore_permissions=True)
                frappe.db.commit()
                print(f"✓ Administrator email updated to {admin_email}")
            else:
                print(f"✓ Administrator email already set to {admin_email}")
                
            # Always attempt to setup TickTix mapping
            setup_administrator_ticktix_mapping(admin_doc, admin_email)
        else:
            print("⚠ Administrator user not found")
            
    except Exception as e:
        print(f"Error setting up Administrator user: {e}")
        frappe.db.rollback()
        raise


def setup_administrator_ticktix_mapping(admin_doc, admin_email):
    """Setup the TickTix user ID mapping for Administrator user"""
    try:
        # Check if Administrator already has TickTix mapping
        if admin_doc.get_social_login_userid('ticktix'):
            print("✓ Administrator already has TickTix user ID mapping")
            return
            
        # Import here to avoid circular imports during installation
        from frappe_ticktix.plugins.authentication.login_callback import check_user_exists_in_idp, get_api_access_token
        
        # Get API access token for TickTix API calls
        access_token = get_api_access_token()
        if not access_token:
            print("⚠ Could not get TickTix API access token")
            return
            
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Check if admin user exists in TickTix IDP and get User ID
        from frappe_ticktix.config.config_manager import get_auth_config
        auth_config = get_auth_config()
        api_base = auth_config.get('ticktix_provision_api', 'https://authapi.ticktix.com')
        check_result = check_user_exists_in_idp(admin_email, headers, api_base)
        
        if check_result['exists'] and check_result.get('user_id'):
            user_id = check_result['user_id']
            # Map the TickTix user ID to Administrator
            admin_doc.set_social_login_userid('ticktix', userid=user_id)
            admin_doc.save(ignore_permissions=True)
            frappe.db.commit()
            print(f"✓ Administrator mapped to TickTix user ID: {user_id}")
        else:
            print(f"⚠ Administrator account {admin_email} not found in TickTix IDP")
            print("  Please ensure the account exists in TickTix before using OAuth login")
            
    except Exception as e:
        print(f"Note: Could not setup Administrator TickTix mapping: {e}")
        # Don't raise error as this might fail during initial setup


def setup_ticktix_social_login():
    """Create and configure TickTix Social Login Key"""
    try:
        # Check if already exists
        if frappe.db.exists('Social Login Key', 'ticktix'):
            print("TickTix Social Login Key already exists")
            # Update existing configuration to ensure proper user ID mapping
            social_login_key = frappe.get_doc('Social Login Key', 'ticktix')
            social_login_key.user_id_property = 'sub'  # Use 'sub' for OAuth2 standard user ID
            social_login_key.sign_ups = 'Deny'  # Keep signup disabled - Administrator should be pre-associated
            
            # Update redirect URL to use absolute URL with tenant-specific base URL
            update_social_login_redirect_url(social_login_key)
            
            social_login_key.save(ignore_permissions=True)
            frappe.db.commit()
            print("✓ TickTix Social Login Key updated with proper user ID mapping")
            return
            
        # Get TickTix config using ConfigManager
        from frappe_ticktix.config.config_manager import get_auth_config
        
        auth_config = get_auth_config()
        
        # Check if OAuth credentials are configured
        client_id = auth_config.get('ticktix_client_id')
        client_secret = auth_config.get('ticktix_client_secret')
        
        if not client_id or not client_secret:
            print("⚠ TickTix OAuth credentials not configured in common_site_config.json")
            print("  Skipping Social Login Key creation.")
            print("  Add OAuth credentials under 'ticktix.oauth' section to enable OAuth login")
            return
        
        # Create Social Login Key for TickTix
        social_login_key = frappe.new_doc('Social Login Key')
        social_login_key.name = 'ticktix'
        social_login_key.provider_name = 'TickTix'
        social_login_key.enable_social_login = 1
        social_login_key.client_id = client_id
        social_login_key.client_secret = client_secret
        social_login_key.base_url = auth_config.get('ticktix_base_url', 'https://login.ticktix.com')
        social_login_key.authorize_url = auth_config.get('ticktix_authorize_url', '/connect/authorize')
        social_login_key.access_token_url = auth_config.get('ticktix_token_url', '/connect/token')
        social_login_key.api_endpoint = auth_config.get('ticktix_userinfo_url', '/connect/userinfo')
        social_login_key.custom_base_url = 1  # Enable custom base URL handling
        social_login_key.redirect_url = auth_config.get('ticktix_redirect_url_template', '/api/method/frappe.integrations.oauth2_logins.custom/ticktix')
        
        # Get auth params from nested OAuth config structure using ConfigManager
        from frappe_ticktix.config.config_manager import get_config_manager
        config_manager = get_config_manager()
        ticktix_config = config_manager.get_config_value('ticktix', {})
        oauth_params = ticktix_config.get('oauth', {}).get('auth_params', {}) if isinstance(ticktix_config, dict) else {}
        social_login_key.auth_url_data = json.dumps(oauth_params)
        
        social_login_key.user_id_property = 'sub'  # Use 'sub' for OAuth2 standard user ID
        social_login_key.sign_ups = 'Deny'  # Keep signup disabled - Administrator should be pre-associated
        
        # Update redirect URL to use absolute URL with tenant-specific base URL
        update_social_login_redirect_url(social_login_key)
        
        social_login_key.insert(ignore_permissions=True)
        frappe.db.commit()
        print("✓ TickTix Social Login Key created successfully with proper user ID mapping")
        
    except Exception as e:
        print(f"Error creating TickTix Social Login Key: {e}")
        frappe.db.rollback()
        raise


def disable_other_login_methods():
    """Disable username/password login and email link login as per requirements"""
    try:
        frappe.db.set_single_value('System Settings', 'disable_user_pass_login', 1)
        frappe.db.set_single_value('System Settings', 'login_with_email_link', 0)
        frappe.db.commit()
        print("✓ Username/Password login disabled")
        print("✓ Login with Email Link disabled")
    except Exception as e:
        print(f"Error disabling login methods: {e}")
        frappe.db.rollback()
        raise


def setup_https_enforcement():
    """Enable HTTPS enforcement for security"""
    try:
        # Enable HTTPS in Website Settings if the field exists
        if frappe.db.has_column('Website Settings', 'force_https'):
            frappe.db.set_single_value('Website Settings', 'force_https', 1)
            print("✓ HTTPS enforcement enabled")
        else:
            print("⚠ HTTPS enforcement field not found in Website Settings")
        
        frappe.db.commit()
    except Exception as e:
        print(f"Note: HTTPS enforcement setup skipped: {e}")
        # Don't raise error as this might not be available in all Frappe versions


def setup_company_logo():
    """Setup TickTix branding using configuration from ConfigManager"""
    try:
        # Get branding configuration
        from frappe_ticktix.plugins.branding.logo_manager import get_branding_config
        branding = get_branding_config()
        
        print(f"Setting up branding: {branding['app_name']}")
        
        # Update System Settings (use db.set_single_value to avoid validation issues)
        try:
            frappe.db.set_single_value('System Settings', 'app_name', branding['app_name'])
            print(f"✓ System Settings app_name set to: {branding['app_name']}")
        except Exception as e:
            print(f"⚠ System Settings error: {e}")
        
        # Update Website Settings
        try:
            website_settings = frappe.get_single('Website Settings')
            website_settings.app_name = branding['app_name']
            website_settings.app_logo = branding['company_logo']
            if hasattr(website_settings, 'favicon'):
                website_settings.favicon = branding['favicon']
            website_settings.save(ignore_permissions=True)
            print(f"✓ Website Settings updated:")
            print(f"  - App Name: {branding['app_name']}")
            print(f"  - Logo: {branding['company_logo']}")
        except Exception as e:
            print(f"⚠ Website Settings error: {e}")
        
        # Update Navbar Settings
        try:
            if frappe.db.exists('Navbar Settings'):
                navbar_settings = frappe.get_single('Navbar Settings')
                navbar_settings.app_logo = branding['company_logo']
                navbar_settings.save(ignore_permissions=True)
                print(f"✓ Navbar Settings logo set to: {branding['company_logo']}")
        except Exception as e:
            print(f"⚠ Navbar Settings error: {e}")
        
        frappe.db.commit()
        print(f"✓ Company branding configured successfully")
        
    except Exception as e:
        print(f"⚠ Company branding setup encountered an error: {e}")
        # Don't raise error as this is not critical


@frappe.whitelist()
def manual_setup_administrator_mapping():
    """Manual utility to setup Administrator TickTix user ID mapping after installation"""
    if not frappe.has_permission('System Settings', 'write'):
        frappe.throw("Insufficient permissions")
        
    try:
        from frappe_ticktix.config.config_manager import get_auth_config
        auth_config = get_auth_config()
        admin_email = auth_config.get('ticktix_admin_email', 'facilitix@ticktix.com')
        admin_doc = frappe.get_doc('User', 'Administrator')
        
        # Update email if needed
        if admin_doc.email != admin_email:
            admin_doc.email = admin_email
            admin_doc.save(ignore_permissions=True)
            
        # Setup the mapping
        setup_administrator_ticktix_mapping(admin_doc, admin_email)
        
        return {
            'status': 'success',
            'message': f'Administrator mapping setup for {admin_email}',
            'admin_email': admin_email,
            'ticktix_user_id': admin_doc.get_social_login_userid('ticktix')
        }
        
    except Exception as e:
        frappe.log_error(
            message=f"Failed to setup Administrator mapping: {str(e)}",
            title='Administrator Mapping Error'
        )
        return {'status': 'error', 'message': str(e)}


def provision_existing_users():
    """Provision all existing users with email addresses to TickTix IDP during installation"""
    try:
        print("Provisioning existing users to TickTix IDP...")
        
        # Get all enabled users with email addresses (excluding Administrator and Guest)
        users = frappe.get_all('User', 
            filters={
                'enabled': 1,
                'email': ['!=', ''],
                'name': ['not in', ['Administrator', 'Guest']]
            },
            fields=['name', 'email', 'user_type', 'first_name', 'last_name', 'full_name']
        )
        
        if not users:
            print("✓ No existing users found to provision")
            return
            
        print(f"Found {len(users)} existing users to provision...")
        
        # Import here to avoid circular imports during installation
        from frappe_ticktix.plugins.authentication.login_callback import (
            get_api_access_token, 
            check_user_exists_in_idp, 
            create_user_in_idp,
            create_social_login_mapping
        )
        
        def is_valid_email(email):
            """Check if email format is valid for TickTix provisioning."""
            if not email or not isinstance(email, str):
                return False
            # Basic email validation
            import re
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            return re.match(pattern, email) is not None
        
        # Get API access token for TickTix API calls
        access_token = get_api_access_token()
        if not access_token:
            print("⚠ Could not get TickTix API access token for user provisioning")
            return
            
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Get API base URL from config using ConfigManager
        from frappe_ticktix.config.config_manager import get_auth_config
        auth_config = get_auth_config()
        api_base = auth_config.get('ticktix_provision_api', 'https://authapi.ticktix.com')
        
        success_count = 0
        error_count = 0
        
        for user_data in users:
            try:
                email = user_data.get('email')
                if not email:
                    continue
                
                # Validate email format
                if not is_valid_email(email):
                    print(f"  Processing user: {email} (System User)")
                    print(f"    ✗ Invalid email format, skipping")
                    error_count += 1
                    continue
                    
                print(f"  Processing user: {email} ({user_data.get('user_type', 'Unknown')})")
                
                # Get the full user document
                user_doc = frappe.get_doc('User', user_data.get('name'))
                
                # Skip if user already has TickTix mapping
                if user_doc.get_social_login_userid('ticktix'):
                    print(f"    ✓ Already has TickTix mapping, skipping")
                    continue
                
                # Check if user exists in TickTix IDP
                check_result = check_user_exists_in_idp(email, headers, api_base)
                
                ticktix_user_id = None
                
                if check_result['exists']:
                    # User exists in IDP, get their ID
                    ticktix_user_id = check_result.get('user_id')
                    print(f"    ✓ User exists in TickTix IDP with ID: {ticktix_user_id}")
                else:
                    # User doesn't exist, create them in IDP
                    create_result = create_user_in_idp(user_doc, headers, api_base)
                    if create_result['status'] == 'success':
                        ticktix_user_id = create_result.get('user_id')
                        print(f"    ✓ Created user in TickTix IDP with ID: {ticktix_user_id}")
                    elif create_result['status'] == 'exists':
                        # User was created by another process, try to get their ID
                        recheck_result = check_user_exists_in_idp(email, headers, api_base)
                        if recheck_result['exists']:
                            ticktix_user_id = recheck_result.get('user_id')
                            print(f"    ✓ User exists in TickTix IDP with ID: {ticktix_user_id}")
                    else:
                        print(f"    ✗ Failed to create user in TickTix IDP: {create_result.get('message', 'Unknown error')}")
                        error_count += 1
                        continue
                
                # Create social login mapping if we have a TickTix user ID
                if ticktix_user_id:
                    create_social_login_mapping(user_doc, ticktix_user_id)
                    print(f"    ✓ Social login mapping created")
                    success_count += 1
                else:
                    print(f"    ✗ Could not obtain TickTix user ID, skipping mapping")
                    error_count += 1
                    
            except Exception as e:
                print(f"    ✗ Error processing user {user_data.get('email', 'Unknown')}: {str(e)}")
                error_count += 1
                continue
        
        # Summary
        print(f"✓ User provisioning completed: {success_count} successful, {error_count} errors")
        
        if error_count > 0:
            print(f"⚠ Some users had errors during provisioning. Check the logs for details.")
            
    except Exception as e:
        print(f"Error during existing user provisioning: {e}")
        # Don't raise error as this shouldn't break the installation


@frappe.whitelist()
def manual_provision_existing_users():
    """Manual utility to provision all existing users to TickTix IDP (can be run after installation)"""
    if not frappe.has_permission('System Settings', 'write'):
        frappe.throw("Insufficient permissions")
        
    try:
        # Run the provisioning process
        provision_existing_users()
        
        return {
            'status': 'success',
            'message': 'Existing user provisioning completed. Check console output for details.'
        }
        
    except Exception as e:
        frappe.log_error(
            message=f"Failed to provision existing users: {str(e)}",
            title='User Provisioning Error'
        )
        return {'status': 'error', 'message': str(e)}


@frappe.whitelist()
def update_redirect_url():
    """Manual utility to update Social Login Key redirect URL to use tenant-specific absolute URL"""
    if not frappe.has_permission('System Settings', 'write'):
        frappe.throw("Insufficient permissions")
        
    try:
        if not frappe.db.exists('Social Login Key', 'ticktix'):
            return {'status': 'error', 'message': 'TickTix Social Login Key not found'}
            
        social_login_key = frappe.get_doc('Social Login Key', 'ticktix')
        old_redirect_url = social_login_key.redirect_url
        
        # Update the redirect URL
        update_social_login_redirect_url(social_login_key)
        
        # Save if changed
        if social_login_key.redirect_url != old_redirect_url:
            social_login_key.save(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                'status': 'success',
                'message': 'Redirect URL updated successfully',
                'old_url': old_redirect_url,
                'new_url': social_login_key.redirect_url
            }
        else:
            return {
                'status': 'success',
                'message': 'Redirect URL already correct',
                'current_url': social_login_key.redirect_url
            }
        
    except Exception as e:
        frappe.log_error(
            message=f"Failed to update redirect URL: {str(e)}",
            title='Redirect URL Update Error'
        )
        return {'status': 'error', 'message': str(e)}


# Manual setup methods removed - logo is now handled dynamically through logo_utils.py
# The logo configuration is read directly from site_config.json and common_site_config.json
# No manual setup needed as the logo_utils.get_company_logo() function handles this automatically


def setup_hr_customizations():
    """
    Setup HR module customizations
    - Add custom status options to Attendance
    - Add custom fields to Attendance
    - Install client scripts for UI overrides
    - Add any other HR-related customizations
    """
    print("\n" + "=" * 70)
    print("FRAPPE_TICKTIX: Setting up HR customizations...")
    print("=" * 70)
    
    try:
        create_attendance_custom_fields()
        create_shift_assignment_custom_fields()
        customize_attendance_status()
        install_attendance_client_scripts()
        print("✓ HR customizations completed successfully")
    except Exception as e:
        print(f"⚠ HR customizations encountered an error: {e}")
        # Don't raise error to avoid breaking installation


def create_attendance_custom_fields():
    """
    Create custom fields for Attendance doctype
    Adds operations, tracking, and integration fields
    """
    print("\n📋 Creating Attendance custom fields...")

    try:
        from frappe_ticktix.custom.custom_field.attendance import create_custom_fields

        create_custom_fields()

    except Exception as e:
        print(f"   ⚠️  Could not create custom fields: {e}")
        import traceback
        traceback.print_exc()
        frappe.db.rollback()


def create_shift_assignment_custom_fields():
    """Create custom fields for Shift Assignment doctype."""
    print("\n📋 Creating Shift Assignment custom fields...")

    try:
        from frappe_ticktix.custom.custom_field.shift_assignment import create_custom_fields

        create_custom_fields()

    except Exception as e:
        print(f"   ⚠️  Could not create Shift Assignment custom fields: {e}")
        import traceback
        traceback.print_exc()
        frappe.db.rollback()


def customize_attendance_status():
    """
    Add custom status options to Attendance DocType
    Based on one_fm status options with name change:
    - Weekly Off (renamed from one_fm's "Day Off")
    - Client Day Off, Holiday, On Hold
    Uses: Property Setter with proper doc creation (not helper function)
    """
    print("\n📋 Customizing Attendance status options...")
    
    try:
        # Extended status options from one_fm (Day Off → Weekly Off)
        new_options = """Present
Absent
On Leave
Half Day
Work From Home
Weekly Off
Client Day Off
Holiday
On Hold"""
        
        # Check if Property Setter already exists
        if frappe.db.exists("Property Setter", {
            "doc_type": "Attendance",
            "field_name": "status",
            "property": "options"
        }):
            # Update existing
            ps = frappe.get_doc("Property Setter", {
                "doc_type": "Attendance",
                "field_name": "status",
                "property": "options"
            })
            ps.value = new_options
            ps.save(ignore_permissions=True)
            print("   ✅ Updated existing Property Setter")
        else:
            # Create new Property Setter
            ps = frappe.get_doc({
                "doctype": "Property Setter",
                "doctype_or_field": "DocField",
                "doc_type": "Attendance",
                "field_name": "status",
                "property": "options",
                "value": new_options,
                "property_type": "Text"
            })
            ps.insert(ignore_permissions=True)
            print("   ✅ Created new Property Setter")
        
        print("   ✅ Added extended status options:")
        for option in new_options.strip().split('\n'):
            if option.strip():
                print(f"      - {option}")
        
        # Clear cache to ensure changes reflect immediately
        frappe.clear_cache(doctype="Attendance")
        
        frappe.db.commit()
        
    except Exception as e:
        print(f"   ⚠️  Could not customize Attendance status: {e}")
        import traceback
        traceback.print_exc()
        frappe.db.rollback()


def install_attendance_client_scripts():
    """
    Install client scripts to override hardcoded status options in HRMS JavaScript.
    These scripts ensure the UI dropdowns show all custom status options.
    """
    print("\n📋 Installing Attendance client scripts...")
    
    try:
        from frappe_ticktix.plugins.hr.attendance.client_scripts import get_client_scripts
        
        scripts = get_client_scripts()
        created_count = 0
        updated_count = 0
        
        for script_config in scripts:
            script_name = script_config['name']
            
            if frappe.db.exists('Client Script', script_name):
                # Update existing
                script_doc = frappe.get_doc('Client Script', script_name)
                script_doc.dt = script_config['dt']
                script_doc.view = script_config['view']
                script_doc.enabled = script_config['enabled']
                script_doc.script = script_config['script']
                script_doc.save(ignore_permissions=True)
                updated_count += 1
                print(f"   ✅ Updated: {script_name}")
            else:
                # Create new
                script_doc = frappe.get_doc({
                    'doctype': 'Client Script',
                    'name': script_name,
                    'dt': script_config['dt'],
                    'view': script_config['view'],
                    'enabled': script_config['enabled'],
                    'script': script_config['script']
                })
                script_doc.insert(ignore_permissions=True)
                created_count += 1
                print(f"   ✅ Created: {script_name}")
        
        frappe.db.commit()
        print(f"   ✅ Client scripts installed: {created_count} created, {updated_count} updated")
        
    except Exception as e:
        print(f"   ⚠️  Could not install client scripts: {e}")
        import traceback
        traceback.print_exc()
        frappe.db.rollback()


def apply_payroll_overrides():
    """
    Apply monkey-patch overrides to Salary Slip for custom attendance status handling.
    This ensures payroll calculations correctly treat:
    - "On Hold" as absent (reduces payment_days)
    - "Weekly Off", "Day Off", "Holiday", "Client Day Off" as paid days
    """
    print("\n📋 Applying payroll overrides...")
    
    try:
        from frappe_ticktix.plugins.hr.payroll.salary_slip_override import apply_salary_slip_overrides
        
        apply_salary_slip_overrides()
        print("   ✅ Payroll overrides applied successfully")
        
    except Exception as e:
        print(f"   ⚠️  Could not apply payroll overrides: {e}")
        import traceback
        traceback.print_exc()


def apply_attendance_overrides():
    """
    Apply monkey-patch overrides to HRMS Attendance class.
    This ensures the validate method uses our custom status list
    instead of the hardcoded HRMS status list.
    """
    print("\n📋 Applying attendance overrides...")
    
    try:
        from frappe_ticktix.plugins.hr.attendance.attendance_status_override import apply_attendance_overrides as _apply
        
        _apply()
        print("   ✅ Attendance overrides applied successfully")
        
    except Exception as e:
        print(f"   ⚠️  Could not apply attendance overrides: {e}")
        import traceback
        traceback.print_exc()
