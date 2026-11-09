# Helpdesk Plugin

This plugin manages integration between ERPNext customizations and Frappe Helpdesk.

## Features

### 1. Custom Field Synchronization

Automatically syncs custom mandatory fields from HD Ticket doctype customization to HD Ticket Template, ensuring they appear in the Helpdesk ticket creation form.

#### How It Works

1. **Auto-Sync**: When you add/modify a mandatory custom field on HD Ticket in ERPNext, it automatically syncs to the Helpdesk template
2. **Template Integration**: Fields are added to the "Default" HD Ticket Template
3. **Form Display**: Synced fields appear in the Helpdesk ticket creation form (both agent and customer portal)

#### Usage

**Automatic Sync (Recommended)**:
- Simply add custom mandatory fields to HD Ticket via ERPNext Customize Form
- The plugin automatically detects and syncs them to Helpdesk

**Manual Sync**:
```python
# Via Python
from frappe_ticktix.plugins.helpdesk.template_sync import HelpdeskTemplateSyncManager

manager = HelpdeskTemplateSyncManager(template_name="Default")
result = manager.sync_custom_fields()
print(result)
```

**Via API**:
```bash
# Sync fields
bench --site sitename execute frappe_ticktix.plugins.helpdesk.template_sync.sync_helpdesk_template_fields

# Or via HTTP
curl -X POST "https://your-site.com/api/method/frappe_ticktix.plugins.helpdesk.template_sync.sync_helpdesk_template_fields" \
  -H "Authorization: token <api-key>:<api-secret>"
```

**Get Template Info**:
```bash
# Check which fields are in the template
bench --site sitename execute frappe_ticktix.plugins.helpdesk.template_sync.get_helpdesk_template_info
```

## Architecture

```
ERPNext Customize Form
    ↓
Add Custom Field (mandatory) to HD Ticket
    ↓
doc_events hook triggers
    ↓
HelpdeskTemplateSyncManager.sync_custom_fields()
    ↓
Field added to HD Ticket Template
    ↓
Field appears in Helpdesk ticket creation form
```

## Configuration

### Hooks

The plugin uses the following hooks in `hooks.py`:

```python
doc_events = {
    "Custom Field": {
        "after_insert": "frappe_ticktix.plugins.helpdesk.template_sync.auto_sync_on_custom_field_change",
        "after_save": "frappe_ticktix.plugins.helpdesk.template_sync.auto_sync_on_custom_field_change"
    }
}
```

### API Endpoints

- `sync_helpdesk_template_fields` - Manually trigger field synchronization
- `get_helpdesk_template_info` - Get information about template fields

## Files

```
plugins/helpdesk/
├── __init__.py
├── template_sync.py       # Main sync manager class
└── README.md              # This file
```

## Troubleshooting

### Fields not showing in Helpdesk form

1. Check if custom field is mandatory in ERPNext:
   ```bash
   bench --site sitename console
   >>> frappe.get_value("Custom Field", {"dt": "HD Ticket", "fieldname": "store"}, "reqd")
   ```

2. Check if field is in template:
   ```python
   from frappe_ticktix.plugins.helpdesk.template_sync import get_helpdesk_template_info
   print(get_helpdesk_template_info())
   ```

3. Manually trigger sync:
   ```python
   from frappe_ticktix.plugins.helpdesk.template_sync import sync_helpdesk_template_fields
   result = sync_helpdesk_template_fields()
   print(result)
   ```

### Check logs

```bash
# Check error logs
bench --site sitename console
>>> frappe.get_all("Error Log", filters={"method": ["like", "%helpdesk%"]}, limit=10)
```

## Example: Adding Store Field

1. **Add custom field in ERPNext**:
   - Go to Customize Form → HD Ticket
   - Add field: `store` (Link to Store doctype)
   - Set as mandatory
   - Save

2. **Auto-sync happens automatically**

3. **Verify in Helpdesk**:
   - Go to Helpdesk → New Ticket
   - "Store" field should appear before Subject
   - Field will be marked as required

## Future Enhancements

- [ ] Support for non-mandatory fields with config option
- [ ] Selective sync by field type
- [ ] Sync field order/position
- [ ] Support for multiple templates
- [ ] Field removal sync
- [ ] Bidirectional sync (template → custom field)
