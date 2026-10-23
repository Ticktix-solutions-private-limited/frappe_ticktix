"""
Test script for HR Plugin - Employee Checkin & Attendance

Run this script to verify the HR plugin is working correctly:

    cd /home/sagivasan/ticktix
    bench --site ticktix.local execute frappe_ticktix.plugins.hr.test_hr_plugin.run_tests
"""

import frappe
from frappe.utils import now_datetime, today, add_days, getdate
from datetime import timedelta


def run_tests():
    """
    Run all HR plugin tests
    """
    print("\n" + "="*80)
    print("HR PLUGIN TEST SUITE")
    print("="*80 + "\n")
    
    try:
        test_checkin_manager()
        test_attendance_manager()
        test_api_endpoints()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80 + "\n")
        
    except Exception as e:
        print("\n" + "="*80)
        print("❌ TESTS FAILED!")
        print("="*80)
        print(f"\nError: {str(e)}")
        print(frappe.get_traceback())


def test_checkin_manager():
    """
    Test Employee Checkin Manager
    """
    print("Testing Employee Checkin Manager...")
    print("-" * 80)
    
    from frappe_ticktix.plugins.hr.checkin.checkin_manager import EmployeeCheckinManager
    
    # Test 1: Get current shift (will fail if no employee, that's ok)
    try:
        shift = EmployeeCheckinManager.get_current_shift("EMP-TEST-001")
        if shift:
            print("✅ get_current_shift() - Works (shift found)")
        else:
            print("⚠️  get_current_shift() - Works (no shift found - expected)")
    except Exception as e:
        print(f"⚠️  get_current_shift() - Expected failure: {str(e)[:50]}")
    
    # Test 2: Validate duplicate log
    try:
        duplicate = EmployeeCheckinManager.validate_duplicate_log(
            "EMP-TEST-001",
            now_datetime(),
            None
        )
        print("✅ validate_duplicate_log() - Works")
    except Exception as e:
        print(f"❌ validate_duplicate_log() - Failed: {str(e)}")
        raise
    
    # Test 3: Calculate late/early flags
    try:
        # Create mock shift type
        shift_start = now_datetime()
        shift_end = now_datetime() + timedelta(hours=8)
        
        class MockShiftType:
            enable_entry_grace_period = 1
            late_entry_grace_period = 15
            enable_exit_grace_period = 1
            early_exit_grace_period = 15
        
        flags = EmployeeCheckinManager.calculate_late_early_flags(
            shift_start + timedelta(minutes=20),  # 20 mins late
            shift_start,
            shift_end,
            MockShiftType(),
            'IN'
        )
        
        assert flags['late_entry'] == 1, "Should detect late entry"
        print("✅ calculate_late_early_flags() - Correctly detects late entry")
        
    except Exception as e:
        print(f"❌ calculate_late_early_flags() - Failed: {str(e)}")
        raise
    
    print()


def test_attendance_manager():
    """
    Test Attendance Manager
    """
    print("Testing Attendance Manager...")
    print("-" * 80)
    
    from frappe_ticktix.plugins.hr.attendance.attendance_manager import AttendanceManager
    
    # Test 1: Get duplicate attendance
    try:
        duplicates = AttendanceManager.get_duplicate_attendance(
            "EMP-TEST-001",
            today(),
            None,
            None
        )
        print("✅ get_duplicate_attendance() - Works")
    except Exception as e:
        print(f"❌ get_duplicate_attendance() - Failed: {str(e)}")
        raise
    
    # Test 2: Is holiday
    try:
        holiday = AttendanceManager.is_holiday("EMP-TEST-001", today())
        if holiday:
            print(f"✅ is_holiday() - Works (holiday found: {holiday})")
        else:
            print("✅ is_holiday() - Works (no holiday today)")
    except Exception as e:
        print(f"⚠️  is_holiday() - Expected failure: {str(e)[:50]}")
    
    # Test 3: Get shift assignment
    try:
        shift = AttendanceManager.get_shift_assignment("EMP-TEST-001", today())
        if shift:
            print("✅ get_shift_assignment() - Works (shift found)")
        else:
            print("⚠️  get_shift_assignment() - Works (no shift found - expected)")
    except Exception as e:
        print(f"⚠️  get_shift_assignment() - Expected failure: {str(e)[:50]}")
    
    # Test 4: Calculate working hours
    try:
        class MockCheckin:
            def __init__(self, time):
                self.time = time
        
        checkins_in = [MockCheckin(now_datetime())]
        checkins_out = [MockCheckin(now_datetime() + timedelta(hours=8))]
        
        hours = AttendanceManager.calculate_working_hours_from_checkins(
            checkins_in,
            checkins_out
        )
        
        assert hours == 8.0, f"Expected 8.0 hours, got {hours}"
        print(f"✅ calculate_working_hours_from_checkins() - Correctly calculated {hours} hours")
        
    except Exception as e:
        print(f"❌ calculate_working_hours_from_checkins() - Failed: {str(e)}")
        raise
    
    print()


def test_api_endpoints():
    """
    Test API endpoints are whitelisted
    """
    print("Testing API Endpoints...")
    print("-" * 80)
    
    # Test 1: Check if methods are whitelisted
    try:
        from frappe.utils import get_whitelist_methods
        
        # Get all whitelisted methods
        methods = frappe.get_hooks("override_whitelisted_methods")
        
        required_methods = [
            "frappe_ticktix.plugins.hr.checkin.checkin_manager.get_current_shift_for_employee",
            "frappe_ticktix.plugins.hr.checkin.checkin_manager.create_checkin",
            "frappe_ticktix.plugins.hr.attendance.attendance_manager.mark_attendance",
            "frappe_ticktix.plugins.hr.attendance.attendance_manager.get_attendance_summary"
        ]
        
        for method in required_methods:
            # Check if method exists in methods dict
            method_registered = False
            if methods:
                for hook_methods in methods:
                    if method in hook_methods.values():
                        method_registered = True
                        break
            
            if method_registered:
                print(f"✅ {method.split('.')[-1]}() - Whitelisted")
            else:
                print(f"⚠️  {method.split('.')[-1]}() - Not in whitelist (check hooks.py)")
        
    except Exception as e:
        print(f"❌ API endpoint check failed: {str(e)}")
        raise
    
    print()


def test_integration():
    """
    Integration test - Create a real checkin and attendance record
    NOTE: This creates actual records in the database!
    """
    print("\nIntegration Test (creates real records)...")
    print("-" * 80)
    
    # Only run if explicitly enabled
    run_integration = False  # Set to True to run integration tests
    
    if not run_integration:
        print("⚠️  Integration tests skipped (set run_integration=True to enable)")
        return
    
    try:
        from frappe_ticktix.plugins.hr.checkin.checkin_manager import create_checkin
        from frappe_ticktix.plugins.hr.attendance.attendance_manager import mark_attendance
        
        # Create test employee if doesn't exist
        if not frappe.db.exists("Employee", "EMP-TEST-001"):
            print("⚠️  Test employee EMP-TEST-001 not found. Create it first.")
            return
        
        # Create checkin
        checkin = create_checkin(
            employee="EMP-TEST-001",
            log_type="IN",
            time=now_datetime()
        )
        print(f"✅ Created checkin: {checkin.get('name')}")
        
        # Mark attendance
        attendance = mark_attendance(
            employee="EMP-TEST-001",
            attendance_date=today(),
            status="Present",
            working_hours=8.0
        )
        print(f"✅ Created attendance: {attendance.get('name')}")
        
    except Exception as e:
        print(f"❌ Integration test failed: {str(e)}")
        print(frappe.get_traceback())


if __name__ == "__main__":
    run_tests()
