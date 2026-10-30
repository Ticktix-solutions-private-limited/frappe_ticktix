# Employee ID Auto-Generation Plugin

Automatically generates unique employee IDs when new employees are created using a flexible pattern-based system.

## Quick Start

### 1. Run Migration (Add Custom Fields)

```bash
cd /home/sagivasan/ticktix
bench --site ticktix.local execute frappe_ticktix.patches.add_abbr_custom_fields.execute
```

### 2. Configure Settings

Add to `common_site_config.json` or `site_config.json`:

```json
{
  "hr_employee_id_settings": {
    "enabled": true,
    "pattern": "{COMPANY_ABBR}-{DEPARTMENT_ABBR}-{YY}-{####}"
  }
}
```

### 3. Set Abbreviations

Go to Department, Branch, or Employment Type doctypes and set the **Abbreviation** field.

### 4. Create Employee

Create a new employee - the ID will be auto-generated!

## Documentation

See [EMPLOYEE_ID_GENERATION.md](../../../../docs/plugins/EMPLOYEE_ID_GENERATION.md) for:
- Complete configuration options
- Available tokens
- Pattern examples
- API reference
- Troubleshooting

## Pattern Examples

| Pattern | Output Example | Counter Scope |
|---------|----------------|---------------|
| `EMP-{####}` | `EMP-0001` | Global |
| `{DEPARTMENT_ABBR}-{####}` | `IT-0001` | Per department |
| `{COMPANY_ABBR}-{YY}-{####}` | `TTX-25-0001` | Per company + year |
| `{BRANCH_ABBR}-{DEPARTMENT_ABBR}-{####}` | `HO-IT-0001` | Per branch + dept |

## Architecture

```
employee_id_generator/
├── __init__.py              # Plugin exports
├── token_resolver.py        # Token parsing and resolution
├── counter_manager.py       # Counter with auto-detected scoping
├── validators.py            # Pattern and uniqueness validation
├── id_generator.py          # Core generation engine
└── hooks.py                 # Frappe hooks
```

## Features

✅ **Auto-Detected Counter Scoping** - No manual scope configuration needed  
✅ **Hybrid Abbreviation Resolution** - Config → Custom Field → Auto-Fallback  
✅ **Smart Defaults** - Zero-padding and reset behavior auto-detected from pattern  
✅ **Uniqueness Guaranteed** - Auto-retry on duplicates (max 100 attempts)  
✅ **Manual Override** - Optional manual ID entry support  
✅ **Validation** - Pattern and field validation at startup  

## Testing

```bash
# Test in console
bench --site ticktix.local console

>>> from frappe_ticktix.plugins.hr.employee_id_generator import preview_employee_id
>>> emp = frappe.get_doc("Employee", "EMP-001")
>>> preview_employee_id(emp)
'TTX-IT-25-0001'
```

## Related Plugins

- [Attendance](../attendance/) - Attendance tracking
- [Checkin](../checkin/) - Employee checkin/checkout
- [Payroll](../payroll/) - Payroll processing
