"""
Patch to add custom attendance status options
Applies during: Installation or App Update
Uses: Property Setter + Client Scripts for complete UI coverage
"""
import frappe


def execute():
    """
    This patch adds custom status options to Attendance DocType
    Runs automatically when app is updated (bench migrate)
    
    Steps:
    1. Create/update Property Setter for status field options
    2. Install client scripts to override hardcoded JS dropdowns
    3. Clear cache for immediate effect
    """
    print("\n" + "=" * 70)
    print("PATCH: Adding custom Attendance status options...")
    print("=" * 70)
    
    try:
        # Step 1: Update Property Setter
        update_property_setter()
        
        # Step 2: Install client scripts
        install_client_scripts()
        
        # Step 3: Clear cache
        frappe.clear_cache(doctype="Attendance")
        frappe.clear_cache()
        
        frappe.db.commit()
        print("✅ Patch applied successfully!")
        print("=" * 70 + "\n")
        
    except Exception as e:
        print(f"⚠️  Could not apply patch: {e}")
        import traceback
        traceback.print_exc()
        frappe.db.rollback()
        # Don't raise error to avoid breaking migration


def update_property_setter():
    """Update Attendance status field options via Property Setter"""
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
    
    # Check if already customized
    if frappe.db.exists("Property Setter", {
        "doc_type": "Attendance",
        "field_name": "status",
        "property": "options"
    }):
        # Update existing Property Setter
        ps = frappe.get_doc("Property Setter", {
            "doc_type": "Attendance",
            "field_name": "status",
            "property": "options"
        })
        ps.value = new_options
        ps.save(ignore_permissions=True)
        print("✅ Updated existing Property Setter")
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
        print("✅ Created Property Setter")
    
    print("✅ Added extended status options:")
    for option in new_options.strip().split('\n'):
        if option.strip():
            print(f"   - {option}")


def install_client_scripts():
    """Install client scripts to override hardcoded HRMS JavaScript"""
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
                print(f"✅ Updated client script: {script_name}")
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
                print(f"✅ Created client script: {script_name}")
        
        print(f"✅ Client scripts: {created_count} created, {updated_count} updated")
        
    except Exception as e:
        print(f"⚠️  Could not install client scripts: {e}")
        import traceback
        traceback.print_exc()
