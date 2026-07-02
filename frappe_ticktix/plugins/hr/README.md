# HR Plugin - Employee Checkin & Attendance

**Version:** 1.0.0  
**Status:** Active  
**Migration Date:** October 25, 2025

---

## 📋 Overview

This plugin handles employee checkin/checkout and attendance tracking functionality for frappe_ticktix. It has been migrated from **one_fm** with improvements and follows the plugin architecture pattern.

### **Key Features**
- ✅ **Employee Checkin/Checkout** - Track when employees arrive and leave
- ✅ **Attendance Tracking** - Automated attendance marking
- ✅ **Shift Validation** - Validate checkins against shift assignments
- ✅ **Late/Early Detection** - Automatically detect late arrivals and early departures
- ✅ **Supervisor Notifications** - Notify supervisors of attendance issues
- ✅ **Multiple Status Support** - Present, Absent, Leave, Holiday, Day Off, etc.
- ✅ **Auto-Attendance** - Daily scheduled task to mark absent for missing checkins

---

## 🏗️ Architecture

```
frappe_ticktix/plugins/hr/
├── __init__.py
├── checkin/
│   ├── __init__.py
│   └── checkin_manager.py          # Employee checkin logic
└── attendance/
    ├── __init__.py
    └── attendance_manager.py        # Attendance tracking logic
```

### **Integration Points**

**hooks.py Registration:**
```python
doc_events = {
    "Employee Checkin": {
        "validate": "...",
        "before_insert": "...",
        "after_insert": "..."
    },
    "Attendance": {
        "validate": "...",
        "before_save": "...",
        "on_submit": "..."
    }
}

scheduler_events = {
    "daily": [
        "mark_absent_for_missing_checkins"
    ]
}
```

---

## 🚀 Employee Checkin Module

### **Location:** `frappe_ticktix/plugins/hr/checkin/checkin_manager.py`

### **Core Classes**

#### **EmployeeCheckinManager**
Helper class with static methods for checkin operations.

**Methods:**
- `validate_duplicate_log(employee, time, name)` - Check for duplicate checkins
- `get_current_shift(employee, time)` - Get active shift for employee
- `calculate_late_early_flags(...)` - Determine if checkin is late or early

#### **EmployeeCheckinOverride**
Extends Frappe's `EmployeeCheckin` doctype with custom validation.

**Lifecycle Hooks:**
- `validate()` - Validates duplicate, finds shift, calculates late/early flags
- `before_insert()` - Sets date field from time
- `after_insert()` - Enqueues background processing and notifications

---

### **API Endpoints**

#### **1. Get Current Shift**
```python
GET /api/method/frappe_ticktix.plugins.hr.checkin.checkin_manager.get_current_shift_for_employee

Parameters:
- employee (optional): Employee ID (defaults to current user's employee)

Response:
{
  "name": "SHIFT-2025-001",
  "shift_type": "Morning Shift",
  "start_datetime": "2025-10-25 06:00:00",
  "end_datetime": "2025-10-25 14:00:00"
}
```

#### **2. Create Checkin**
```python
POST /api/method/frappe_ticktix.plugins.hr.checkin.checkin_manager.create_checkin

Parameters:
- employee (required): Employee ID
- log_type (required): 'IN' or 'OUT'
- time (optional): Checkin time (defaults to now)
- device_id (optional): Device identifier
- skip_auto_attendance (optional): 0 or 1 (default: 0)

Response:
{
  "name": "HR-EMP-CHK-2025-001",
  "employee": "EMP-001",
  "log_type": "IN",
  "time": "2025-10-25 06:15:00",
  "late_entry": 1,
  "shift_assignment": "SHIFT-2025-001"
}
```

---

### **Features Migrated from one_fm**

| Feature | Status | Changes |
|---------|--------|---------|
| Duplicate checkin validation | ✅ Migrated | Improved error messages |
| Shift assignment detection | ✅ Migrated | Simplified logic |
| Late entry detection | ✅ Migrated | Based on grace periods |
| Early exit detection | ✅ Migrated | Based on grace periods |
| Supervisor notifications | ✅ Migrated | Uses Frappe's email system |
| Background processing | ✅ Migrated | Uses Frappe's queue |

**Removed from one_fm:**
- ❌ GPS location validation (can be added later if needed)
- ❌ Photo capture (can be added later if needed)
- ❌ Penalty auto-creation (simplified for now)
- ❌ Push notifications (mobile app specific - can be added later)

---

## 📊 Attendance Module

### **Location:** `frappe_ticktix/plugins/hr/attendance/attendance_manager.py`

### **Core Classes**

#### **AttendanceManager**
Helper class with static methods for attendance operations.

**Methods:**
- `get_duplicate_attendance(employee, date, shift, name)` - Check for duplicates
- `is_holiday(employee, date)` - Check if date is a holiday
- `get_shift_assignment(employee, date)` - Get shift for date
- `calculate_working_hours_from_checkins(in, out)` - Calculate hours worked
- `mark_attendance_from_checkins(employee, date, shift)` - Auto-mark attendance

#### **AttendanceOverride**
Extends Frappe's `Attendance` doctype with custom validation.

**Lifecycle Hooks:**
- `validate()` - Validates status, duplicates, working hours
- `before_save()` - Auto-sets shift assignment
- `on_submit()` - Post-submit processing (future: payroll integration)

---

### **API Endpoints**

#### **1. Mark Attendance**
```python
POST /api/method/frappe_ticktix.plugins.hr.attendance.attendance_manager.mark_attendance

Parameters:
- employee (required): Employee ID
- attendance_date (required): Date (YYYY-MM-DD)
- status (required): Attendance status
- shift_assignment (optional): Shift Assignment ID
- working_hours (optional): Hours worked

Response:
{
  "name": "HR-ATT-2025-001",
  "employee": "EMP-001",
  "attendance_date": "2025-10-25",
  "status": "Present",
  "working_hours": 8.0
}
```

#### **2. Get Attendance Summary**
```python
GET /api/method/frappe_ticktix.plugins.hr.attendance.attendance_manager.get_attendance_summary

Parameters:
- employee (required): Employee ID
- from_date (required): Start date (YYYY-MM-DD)
- to_date (required): End date (YYYY-MM-DD)

Response:
{
  "total_days": 20,
  "present": 18,
  "absent": 1,
  "on_leave": 1,
  "half_day": 0,
  "work_from_home": 0,
  "day_off": 0,
  "holiday": 0,
  "total_working_hours": 144.0,
  "records": [...]
}
```

---

### **Scheduled Tasks**

#### **mark_absent_for_missing_checkins**
**Schedule:** Daily (runs at end of day)  
**Purpose:** Auto-mark attendance for previous day

**Logic:**
1. Get all shift assignments from yesterday
2. For each shift:
   - Skip if attendance already marked
   - Check if holiday → Mark "Holiday"
   - Check if on approved leave → Mark "On Leave"
   - Check if has checkins → Mark from checkins
   - No checkins → Mark "Absent"

---

### **Attendance Statuses**

| Status | Description | Working Hours Required |
|--------|-------------|----------------------|
| Present | Employee worked | Yes |
| Absent | Employee did not show up | No |
| On Leave | Approved leave application | No |
| Half Day | Partial attendance | Yes |
| Work From Home | Remote work | Yes |
| Day Off | Scheduled day off | No |
| Holiday | Public holiday | No |
| On Hold | Under investigation | No |

---

## 🔧 Configuration

### **Shift Type Settings**

Checkin validation depends on Shift Type configuration:

```
Shift Type: Morning Shift
├─ Start Time: 06:00:00
├─ End Time: 14:00:00
├─ Duration: 8 hours
├─ Enable Entry Grace Period: ✓
│  └─ Late Entry Grace Period: 15 minutes
├─ Enable Exit Grace Period: ✓
│  └─ Early Exit Grace Period: 15 minutes
├─ Begin Check-in Before Shift: 60 minutes
└─ Allow Check-out After Shift: 60 minutes
```

**Checkin Window:**
- Can check in: 05:00 - 15:00 (1 hour before/after shift)
- Late if checkin after: 06:15 (start + 15 min grace)
- Early exit if checkout before: 13:45 (end - 15 min grace)

---

## 📝 Usage Examples

### **Example 1: Mobile App Checkin Flow**

```python
import frappe
from datetime import datetime

# Step 1: Get current shift for employee
current_shift = frappe.call(
    "frappe_ticktix.plugins.hr.checkin.checkin_manager.get_current_shift_for_employee",
    employee="EMP-001"
)

if current_shift:
    # Step 2: Create checkin
    checkin = frappe.call(
        "frappe_ticktix.plugins.hr.checkin.checkin_manager.create_checkin",
        employee="EMP-001",
        log_type="IN",
        device_id="mobile_app_xyz"
    )
    
    # Step 3: Check if late
    if checkin.get("late_entry"):
        print("Warning: You have checked in late!")
else:
    print("No active shift found for current time")
```

### **Example 2: Manual Attendance Marking**

```python
import frappe

# Mark present attendance for employee
attendance = frappe.call(
    "frappe_ticktix.plugins.hr.attendance.attendance_manager.mark_attendance",
    employee="EMP-001",
    attendance_date="2025-10-25",
    status="Present",
    working_hours=8.0
)

print(f"Attendance marked: {attendance.name}")
```

### **Example 3: Monthly Attendance Report**

```python
import frappe

# Get attendance summary for October
summary = frappe.call(
    "frappe_ticktix.plugins.hr.attendance.attendance_manager.get_attendance_summary",
    employee="EMP-001",
    from_date="2025-10-01",
    to_date="2025-10-31"
)

print(f"Present Days: {summary['present']}")
print(f"Absent Days: {summary['absent']}")
print(f"Total Hours: {summary['total_working_hours']}")
```

---

## 🧪 Testing

### **Test Checkin Creation**

```bash
# In bench console
bench --site ticktix.local console

# Test code
from frappe_ticktix.plugins.hr.checkin.checkin_manager import create_checkin
from frappe.utils import now_datetime

result = create_checkin(
    employee="EMP-001",
    log_type="IN",
    time=now_datetime()
)

print(result)
```

### **Test Attendance Marking**

```bash
# In bench console
bench --site ticktix.local console

# Test code
from frappe_ticktix.plugins.hr.attendance.attendance_manager import mark_attendance
from frappe.utils import today

result = mark_attendance(
    employee="EMP-001",
    attendance_date=today(),
    status="Present",
    working_hours=8.0
)

print(result)
```

---

## 🔄 Migration Notes

### **What Changed from one_fm**

**Improvements:**
- ✅ Cleaner code structure (plugin pattern)
- ✅ Better error messages
- ✅ Simplified logic (removed Kuwait-specific features)
- ✅ Uses Frappe's built-in email system
- ✅ Better documentation
- ✅ Type hints and docstrings

**Removed Features:**
- GPS validation (can be re-added if needed)
- Photo capture (can be re-added if needed)
- Custom penalty creation (simplified)
- Push notifications (mobile-specific)
- Operations shift integration (will be added in operations plugin)

**Dependencies:**
- Requires: Employee, Shift Type, Shift Assignment doctypes (from HRMS)
- Optional: Leave Application, Holiday List (from HRMS)

---

## 🎯 Next Steps

### **Phase 2 - Enhanced Features**
- [ ] Add GPS location validation for checkins
- [ ] Add photo capture support
- [ ] Add mobile push notifications
- [ ] Add penalty auto-creation
- [ ] Add operations shift integration

### **Phase 3 - Reports & Analytics**
- [ ] Daily attendance report
- [ ] Monthly attendance summary
- [ ] Late arrival trends
- [ ] Absenteeism analysis
- [ ] Department-wise attendance

### **Phase 4 - Integration**
- [ ] Payroll integration (use attendance for salary calculation)
- [ ] Leave management integration
- [ ] Shift management plugin
- [ ] Operations plugin integration

---

## 📞 Support

**Documentation:** See this README  
**Issues:** Report in frappe_ticktix repository  
**Contact:** facilitix@ticktix.com

---

*Migrated from one_fm with ❤️ by Ticktix Solutions*
