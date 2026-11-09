# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt
"""Pure Python utility helpers for geo tracking.

No Frappe imports — this module is fully unit-testable without a running
Frappe instance.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Optional
from frappe.utils import now_datetime

# ---------------------------------------------------------------------------
# Datetime parsing
# ---------------------------------------------------------------------------

_DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
]


def parse_datetime(value: object) -> Optional[datetime]:
    """Parse *value* into a :class:`datetime` object.

    Accepts:
    - A :class:`datetime` instance (returned as-is).
    - A :class:`str` in any of the common ISO-8601 variants stored by Frappe.
    - ``None`` or empty string → returns ``None``.

    Returns ``None`` for any unparseable input rather than raising so that
    callers can skip bad points gracefully.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    raw = str(value).strip()
    if not raw:
        return None

    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue

    return None  # unparseable — caller must skip the point


# ---------------------------------------------------------------------------
# Coordinate validation
# ---------------------------------------------------------------------------

def validate_coordinates(latitude: object, longitude: object) -> bool:
    """Return ``True`` if both coordinates are valid WGS-84 values.

    Valid ranges:
    - latitude:  -90.0 … 90.0
    - longitude: -180.0 … 180.0
    - Both must be non-None and convertible to float.
    """
    try:
        lat = float(latitude)  # type: ignore[arg-type]
        lon = float(longitude)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False

    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


# ---------------------------------------------------------------------------
# Duration formatting
# ---------------------------------------------------------------------------

def format_duration(total_seconds: float) -> str:
    """Convert *total_seconds* to ``HH:MM:SS`` string.

    Examples::

        format_duration(3661)   # → "01:01:01"
        format_duration(0)      # → "00:00:00"
        format_duration(86399)  # → "23:59:59"

    Hours are not capped — values > 24 h are represented correctly (e.g. 25 h
    would be ``"25:00:00"``).
    """
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def parse_duration(value: str) -> float:
    """Convert a ``HH:MM:SS`` string back to total seconds.

    Returns 0.0 for invalid / empty input.
    """
    if not value:
        return 0.0
    parts = str(value).split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + int(s)
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + int(s)
    except (ValueError, TypeError):
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def today_date() -> date:
    """Return today's date (wrapper makes it easy to patch in tests)."""
    return now_datetime().date()


def date_to_str(d: date) -> str:
    """Convert a :class:`date` to ``YYYY-MM-DD`` string."""
    return d.strftime("%Y-%m-%d")
