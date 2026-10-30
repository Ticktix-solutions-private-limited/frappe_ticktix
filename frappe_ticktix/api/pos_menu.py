# Copyright (c) 2026, Ticktix Solutions private limited and contributors
# For license information, please see license.txt
"""Whitelisted API endpoints for POS Menu.

Each menu section (Breakfast, Lunch Meals, Lunch Other, Snacks, Dinner) has
its own Start Time (optional) / End Time (mandatory) window. Outside that
window the section's actual menu items are withheld and a status message is
returned instead — e.g. "Counter not yet started" / "Counter closed".
"""

from __future__ import annotations

from datetime import datetime, time as time_cls
from typing import Any, Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import get_datetime, nowtime

# Section definition: (label, start field, end field, table field)
_SECTIONS = [
    ("breakfast", "Breakfast", "breakfaststarttime", "breakfastendtime", "breakfastmenulines"),
    ("lunch_meals", "Lunch Meals", "lunchmealsstarttime", "lunchmealsendtime", "lunchmealsmenulines"),
    ("lunch_other", "Lunch Other", "lunchotherstarttime", "lunchotherendtime", "lunchothermenulines"),
    ("snacks", "Snacks", "snacksstarttime", "snacksendtime", "snacksmenulines"),
    ("dinner", "Dinner", "dinnerstarttime", "dinnerendtime", "dinnermenulines"),
]


def _to_time(value: Any) -> Optional[time_cls]:
    """Coerce a Frappe Time field value (timedelta/str/None) into datetime.time."""
    if value in (None, ""):
        return None
    # Frappe stores Time fields as timedelta internally, but the value coming
    # from get_all()/as_dict rows can be a timedelta, a string, or already a time.
    if isinstance(value, time_cls):
        return value
    if hasattr(value, "seconds") and hasattr(value, "days"):
        # datetime.timedelta
        total_seconds = int(value.total_seconds())
        hh = (total_seconds // 3600) % 24
        mm = (total_seconds % 3600) // 60
        ss = total_seconds % 60
        return time_cls(hour=hh, minute=mm, second=ss)
    try:
        return get_datetime(f"2000-01-01 {value}").time()
    except Exception:
        return None


def _section_status(now: time_cls, start: Optional[time_cls], end: time_cls) -> Dict[str, Any]:
    """Return {"open": bool, "message": str|None} for one section."""
    if start is not None and now < start:
        return {"open": False, "message": _("Counter not yet started")}
    if now > end:
        return {"open": False, "message": _("Counter closed")}
    return {"open": True, "message": None}


@frappe.whitelist()
def get_pos_menu(pos_menu: str) -> Dict[str, Any]:
    """Return POS Menu section data, gated by each section's start/end time.

    Args:
        pos_menu: Name of the POS Menu document.

    Returns:
        Dict keyed by section id, each containing ``label``, ``open``,
        ``message`` (when closed) and ``items`` (when open).
    """
    if not pos_menu:
        frappe.throw(_("pos_menu is required."))

    if not frappe.db.exists("POS Menu", pos_menu):
        frappe.throw(_("POS Menu '{0}' not found.").format(pos_menu), frappe.DoesNotExistError)

    if not frappe.has_permission("POS Menu", "read", pos_menu):
        frappe.throw(_("You do not have permission to read this POS Menu."), frappe.PermissionError)

    doc = frappe.get_doc("POS Menu", pos_menu)
    now = get_datetime(f"2000-01-01 {nowtime()}").time()

    result: Dict[str, Any] = {"name": doc.name}

    for key, label, start_field, end_field, table_field in _SECTIONS:
        start = _to_time(doc.get(start_field))
        end = _to_time(doc.get(end_field))

        if end is None:
            # End time is mandatory on the doctype; if somehow missing, treat
            # the section as closed rather than leaking unrestricted data.
            result[key] = {
                "label": label,
                "open": False,
                "message": _("Counter closed"),
                "items": [],
            }
            continue

        status = _section_status(now, start, end)

        if status["open"]:
            items: List[Dict[str, Any]] = [row.as_dict() for row in doc.get(table_field) or []]
            result[key] = {
                "label": label,
                "open": True,
                "message": None,
                "items": items,
            }
        else:
            result[key] = {
                "label": label,
                "open": False,
                "message": status["message"],
                "items": [],
            }

    return result
