# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class LocationTrackingSettings(Document):
    """Holds dynamically tunable mobile location-tracking config.

    This is a regular (non-Single) DocType so it is reachable via the
    standard REST list API (``/api/resource/Location Tracking Settings``)
    rather than the single-document API. This is the server-side source of
    truth for the knobs that the mobile app's background geolocation client
    should honour, without requiring an app store release to change them
    (e.g. point density, mode-switch speed threshold, accuracy filter,
    batching/retry behaviour).

    Deliberately excluded from this DocType (kept hardcoded in the mobile
    client instead):
      - staleSendingRecoveryMs / maxBatchesPerFlush: internal reliability
        plumbing, not tuning levers — a bad remote value here could cause
        duplicate sends or other subtle bugs.
      - The `accuracy` enum values used by the native SDK
        (Location.Accuracy.Balanced / .High): these map to native OS
        constants; a bad string from a remote config would silently fail
        rather than degrade gracefully.
    """

    # No custom logic needed — this is a settings-only document.
    # All fields have safe defaults defined in the JSON schema.
    pass


def get_settings() -> "LocationTrackingSettings | None":
    """Return the active Location Tracking Settings record.

    Now that this DocType allows multiple rows (needed for the REST list
    API), "the" settings record is defined as the most recently modified
    one. If your rollout uses more than one row (e.g. per-region tuning),
    fetch by name directly instead of using this helper.

    Returns None if no record has been created yet.
    """
    name = frappe.db.get_value(
        "Location Tracking Settings", {}, "name", order_by="modified desc"
    )
    return frappe.get_doc("Location Tracking Settings", name) if name else None
