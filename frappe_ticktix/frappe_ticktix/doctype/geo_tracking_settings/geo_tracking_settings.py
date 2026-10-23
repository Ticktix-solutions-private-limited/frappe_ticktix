# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class GeoTrackingSettings(Document):
    """Single DocType holding configurable thresholds for geo travel processing."""

    # No custom logic needed — this is a settings-only document.
    # All fields have safe defaults defined in the JSON schema.
    pass


def get_settings() -> "GeoTrackingSettings":
    """Return the singleton Geo Tracking Settings document.

    Always use this helper rather than frappe.get_single() directly so
    callers get type hints and a single point of truth for the DocType name.
    """
    return frappe.get_single("Geo Tracking Settings")
