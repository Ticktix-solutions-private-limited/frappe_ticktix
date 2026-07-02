"""
Branding Plugin - Logo and UI customization for frappe_ticktix
Migrated from logo_utils.py with improved structure and config management
"""

import frappe
import requests
import time
import os
from urllib.parse import urlparse
from frappe.utils import get_site_path
from ...config.config_manager import get_config_manager

# Constants
DEFAULT_LOGO_URL = "https://login.ticktix.com/images/ticktix.jpg"
DEFAULT_APP_NAME = "Facilitix"
DEFAULT_APP_TITLE = "Facilitix Platform"
CACHE_DURATION = 86400  # 24 hours in seconds
SUPPORTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico']

# Filename mapping for cached images
FILENAME_MAPPING = {
    'company_logo': 'companylogo',
    'splash_image': 'splashimage', 
    'favicon': 'favicon'
}


def get_file_extension(url):
    """Extract file extension from URL, default to .png"""
    try:
        _, ext = os.path.splitext(urlparse(url).path)
        return ext.lower() if ext.lower() in SUPPORTED_EXTENSIONS else '.png'
    except:
        return '.png'


def get_cached_filename(property_key, url):
    """Generate cached filename: property_key + extension from URL"""
    base_name = FILENAME_MAPPING.get(property_key, property_key)
    extension = get_file_extension(url)
    
    # Favicon special case: use .png unless .ico
    if property_key == 'favicon' and extension != '.ico':
        extension = '.png'
        
    return f"{base_name}{extension}"


def cache_image(url, property_key):
    """Download and cache external image, return local path or original URL"""
    if not url or not url.startswith('http'):
        return url
    
    try:
        # Setup cache directory and filename
        cache_dir = os.path.join(get_site_path(), "public", "files", "cached_images")
        os.makedirs(cache_dir, exist_ok=True)
        
        filename = get_cached_filename(property_key, url)
        filepath = os.path.join(cache_dir, filename)
        
        # Return cached file if recent (24 hours)
        if os.path.exists(filepath):
            file_age = time.time() - os.path.getmtime(filepath)
            if file_age < CACHE_DURATION:
                return f"/files/cached_images/{filename}"
        
        # Download and cache
        frappe.logger().info(f"Caching image: {url} → {filename}")
        response = requests.get(url, timeout=10, stream=True, 
                              headers={'User-Agent': 'Frappe/1.0'})
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return f"/files/cached_images/{filename}"
        
    except Exception as e:
        frappe.log_error(title="Logo caching failed", message=f"Failed to cache image from {url}: {e}")
        return url  # Fallback to original URL


def get_company_logo_url():
    """Get cached company logo URL for app_logo_url hook"""
    try:
        config_manager = get_config_manager()
        branding_config = config_manager.get_branding_config()
        return cache_image(branding_config['company_logo'], 'company_logo')
    except Exception as e:
        frappe.log_error(f"Error getting company logo URL: {e}")
        return DEFAULT_LOGO_URL


@frappe.whitelist(allow_guest=True)
def get_company_logo():
    """API: Get company logo with original and cached URLs"""
    try:
        config_manager = get_config_manager()
        branding_config = config_manager.get_branding_config()
        original_url = branding_config['company_logo']
        cached_url = cache_image(original_url, 'company_logo')
        
        return {
            'logo_url': cached_url,
            'original_url': original_url,
            'source': 'site_config'
        }
        
    except Exception as e:
        frappe.log_error(f"Error getting company logo: {e}")
        return {
            'logo_url': DEFAULT_LOGO_URL,
            'source': 'error_fallback'
        }


def get_branding_config():
    """Get complete branding configuration with cached images"""
    try:
        config_manager = get_config_manager()
        branding_config = config_manager.get_branding_config()
        
        # Get configuration values
        company_logo = branding_config['company_logo']
        app_name = branding_config['app_name']
        app_title = branding_config['app_title']
        favicon = branding_config['favicon'] or company_logo
        splash_image = branding_config['splash_image'] or company_logo
        
        # Cache all images and return local paths
        return {
            'company_logo': cache_image(company_logo, 'company_logo'),
            'app_name': app_name,
            'app_title': app_title,
            'favicon': cache_image(favicon, 'favicon'),
            'splash_image': cache_image(splash_image, 'splash_image'),
            'login_title': f'Login to {app_name}',
        }
    except Exception as e:
        frappe.log_error(f"Error getting branding config: {e}")
        # Return fallback configuration
        return {
            'company_logo': cache_image(DEFAULT_LOGO_URL, 'company_logo'),
            'app_name': DEFAULT_APP_NAME,
            'app_title': DEFAULT_APP_TITLE,
            'favicon': cache_image(DEFAULT_LOGO_URL, 'favicon'),
            'splash_image': cache_image(DEFAULT_LOGO_URL, 'splash_image'),
            'login_title': f'Login to {DEFAULT_APP_NAME}',
        }


def extend_bootinfo(bootinfo):
    """Add branding information to boot data for Desk/App interface"""
    try:
        branding = get_branding_config()
        
        # Update bootinfo with branding
        bootinfo.update({
            'app_logo_url': branding['company_logo'],
            'app_logo': branding['company_logo'],
            'app_name': branding['app_name'],
            'app_title': branding['app_title'],
            'favicon': branding['favicon'],
            'splash_image': branding['splash_image'],
            'company_logo': {'url': branding['company_logo'], 'source': 'site_config'}
        })
        
        # Add website context for login pages
        bootinfo.setdefault('website_context', {}).update({
            'app_name': branding['app_name'],
            'app_title': branding['app_title'],
            'login_title': branding['login_title'],
            'favicon': branding['favicon'],
            'splash_image': branding['splash_image'],
        })
        
        # Update Navbar Settings to ensure login page uses cached logo
        _update_navbar_settings(branding['company_logo'])
            
    except Exception as e:
        frappe.log_error(f"Error extending bootinfo: {e}")
        # Set fallback values
        bootinfo.update({
            'app_logo_url': cache_image(DEFAULT_LOGO_URL, 'company_logo'),
            'app_name': DEFAULT_APP_NAME,
            'app_title': DEFAULT_APP_TITLE
        })


def _update_navbar_settings(logo_url):
    """Update Navbar Settings with cached logo URL (called during bootinfo)"""
    try:
        if not frappe.db.exists("Navbar Settings"):
            return
            
        navbar = frappe.get_single("Navbar Settings")
        
        # Only update if different to avoid unnecessary DB writes
        if navbar.app_logo != logo_url:
            navbar.app_logo = logo_url
            navbar.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.logger().info(f"Updated Navbar Settings app_logo to: {logo_url}")
            
    except Exception as e:
        # Don't fail bootinfo if this update fails
        frappe.log_error(f"Failed to update Navbar Settings: {e}", "Branding Plugin")


def update_website_context(context):
    """Add branding information to website context for public pages"""
    try:
        branding = get_branding_config()
        context.update(branding)
        context['company_logo'] = branding['company_logo']  # Ensure both keys exist
        
    except Exception as e:
        frappe.log_error(f"Error updating website context: {e}")
        # Set fallback values
        fallback_logo = cache_image(DEFAULT_LOGO_URL, 'company_logo')
        context.update({
            'app_logo_url': fallback_logo,
            'company_logo': fallback_logo,
            'app_name': DEFAULT_APP_NAME,
            'app_title': DEFAULT_APP_TITLE,
            'login_title': f"Login to {DEFAULT_APP_NAME}",
        })


# API Endpoints
@frappe.whitelist()
def get_branding_info():
    """API: Get all branding information with cached images"""
    return get_branding_config()


@frappe.whitelist()
def clear_image_cache():
    """API: Clear cached images"""
    try:
        cache_dir = os.path.join(get_site_path(), "public", "files", "cached_images")
        if os.path.exists(cache_dir):
            import shutil
            shutil.rmtree(cache_dir)
            os.makedirs(cache_dir, exist_ok=True)
            return {"status": "success", "message": "Cache cleared successfully"}
    except Exception as e:
        frappe.log_error(f"Failed to clear cache: {e}", "Branding Plugin")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_navbar_logo():
    """API: Update Navbar Settings with cached logo (for manual sync)"""
    try:
        branding = get_branding_config()
        cached_logo = branding['company_logo']
        
        navbar = frappe.get_single("Navbar Settings")
        old_logo = navbar.app_logo
        navbar.app_logo = cached_logo
        navbar.save(ignore_permissions=True)
        frappe.db.commit()
        
        return {
            "status": "success",
            "message": "Navbar Settings updated",
            "old_logo": old_logo,
            "new_logo": cached_logo
        }
    except Exception as e:
        frappe.log_error(f"Failed to update Navbar Settings: {e}", "Branding Plugin")
        return {"status": "error", "message": str(e)}