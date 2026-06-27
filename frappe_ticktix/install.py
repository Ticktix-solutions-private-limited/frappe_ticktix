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

    # Re-sync TickTix Social Login Key from common_site_config.json/site_config.json
    setup_ticktix_social_login()

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

            if admin_doc.get_social_login_userid('ticktix'):
                print("✓ Administrator already has TickTix user ID mapping")
            else:
                print("  Administrator TickTix mapping will be created on first OAuth login")
        else:
            print("⚠ Administrator user not found")

    except Exception as e:
        print(f"Error setting up Administrator user: {e}")
        frappe.db.rollback()
        raise


def _apply_auth_config_to_social_login(social_login_key, auth_config):
    """Apply OAuth endpoint/credential configuration (TickTix/Zitadel) to a Social Login Key doc."""
    # Only overwrite credentials if configured, so we don't blank out an existing key
    if auth_config.get('ticktix_client_id'):
        social_login_key.client_id = auth_config.get('ticktix_client_id')
    if auth_config.get('ticktix_client_secret'):
        social_login_key.client_secret = auth_config.get('ticktix_client_secret')

    social_login_key.base_url = auth_config.get('ticktix_base_url', 'https://login.ticktix.com')
    social_login_key.authorize_url = auth_config.get('ticktix_authorize_url', '/oauth/v2/authorize')
    social_login_key.access_token_url = auth_config.get('ticktix_token_url', '/oauth/v2/token')
    social_login_key.api_endpoint = auth_config.get('ticktix_userinfo_url', '/oidc/v1/userinfo')
    social_login_key.custom_base_url = 1  # Enable custom base URL handling

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


def setup_ticktix_social_login():
    """Create and configure the TickTix Social Login Key from the configured OIDC endpoints"""
    try:
        from frappe_ticktix.config.config_manager import get_auth_config
        auth_config = get_auth_config()

        # Check if already exists
        if frappe.db.exists('Social Login Key', 'ticktix'):
            print("TickTix Social Login Key already exists - syncing from configuration")
            social_login_key = frappe.get_doc('Social Login Key', 'ticktix')
            _apply_auth_config_to_social_login(social_login_key, auth_config)
            social_login_key.save(ignore_permissions=True)
            frappe.db.commit()
            print("✓ TickTix Social Login Key updated from configuration")
            return

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
        social_login_key.redirect_url = auth_config.get('ticktix_redirect_url_template', '/api/method/frappe.integrations.oauth2_logins.custom/ticktix')
        _apply_auth_config_to_social_login(social_login_key, auth_config)

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
