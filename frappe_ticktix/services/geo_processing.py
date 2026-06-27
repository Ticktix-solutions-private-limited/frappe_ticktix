# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt
"""Geo travel processing orchestration layer.

Responsibilities:
  - Read raw GPS records from ``Live GEO Tracking V2``
  - Dispatch per-employee calculation via the pure-math service
  - Upsert results into ``Daily Travel Summary``
  - Implement idempotency (status-gate pattern)
  - Expose the scheduler entry-point and the manual reprocess API

This is the ONLY service file that imports Frappe.
"""

from __future__ import annotations

import traceback
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import frappe
from frappe.utils import now_datetime

from .distance_calculator import SettingsSnapshot, TravelMetrics, calculate_travel_metrics
from .geo_utils import date_to_str, today_date

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DOCTYPE_RAW = "Live GEO Tracking V2"
_DOCTYPE_SUMMARY = "Daily Travel Summary"
_DOCTYPE_SETTINGS = "Geo Tracking Settings"

# A summary stuck in "Processing" for more than this many hours is stale.
_STALE_PROCESSING_HOURS = 2

_MAX_POINTS_HARD_CAP = 50_000  # absolute safety cap regardless of settings


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

def _logger() -> Any:
    return frappe.logger("geo_tracking", with_more_info=False)


# ---------------------------------------------------------------------------
# Settings loader
# ---------------------------------------------------------------------------

def _load_settings() -> SettingsSnapshot:
    """Read Geo Tracking Settings and return an immutable SettingsSnapshot.

    Falls back to safe defaults if the DocType has never been saved.
    """
    try:
        doc = frappe.get_single(_DOCTYPE_SETTINGS)
        return SettingsSnapshot(
            max_speed_kmh=float(doc.max_speed_kmh or 120.0),
            min_distance_meters=float(doc.min_distance_meters or 10.0),
            max_accuracy_meters=float(doc.max_accuracy_meters or 50.0),
            session_gap_seconds=int(doc.session_gap_seconds or 900),
            enable_debug_logging=bool(doc.enable_debug_logging),
        )
    except Exception:  # noqa: BLE001
        _logger().warning("Could not load Geo Tracking Settings — using defaults")
        return SettingsSnapshot()


# ---------------------------------------------------------------------------
# Scheduler entry point
# ---------------------------------------------------------------------------

def run_daily_travel_summary(target_date: Optional[str] = None) -> Dict[str, Any]:
    """Nightly batch job entry point (called by Frappe scheduler at 00:30).

    Args:
        target_date:
            ISO-8601 date string (``YYYY-MM-DD``) to process.
            Defaults to yesterday if not supplied. Pass explicitly for reruns.

    Returns:
        A dict summarising ``employees_processed``, ``employees_skipped``,
        ``employees_failed``, and ``duration_seconds``.
    """
    started_at = datetime.now()
    log = _logger()

    # --- Resolve target date ---
    if target_date:
        try:
            process_date: date = date.fromisoformat(str(target_date))
        except ValueError:
            frappe.throw(f"Invalid target_date: '{target_date}'. Expected YYYY-MM-DD.")
    else:
        process_date = today_date() - timedelta(days=1)

    date_str = date_to_str(process_date)
    log.info(f"[GeoProcessing] Job started | target_date={date_str}")

    # --- Discover employees active on this date ---
    employees = _get_distinct_employees_for_date(date_str)
    total = len(employees)
    log.info(f"[GeoProcessing] Found {total} employees with GPS data on {date_str}")

    settings = _load_settings()

    processed = skipped = failed = 0

    for employee in employees:
        try:
            result = _process_employee(employee, date_str, settings, force=False)
            if result == "skipped":
                skipped += 1
            else:
                processed += 1
        except Exception:  # noqa: BLE001
            failed += 1
            log.error(
                f"[GeoProcessing] Unhandled error for {employee} on {date_str}:\n"
                + traceback.format_exc()
            )
            _mark_failed(employee, date_str, traceback.format_exc())

    duration = (datetime.now() - started_at).total_seconds()
    log.info(
        f"[GeoProcessing] Job complete | date={date_str} "
        f"processed={processed} skipped={skipped} failed={failed} "
        f"duration={duration:.1f}s"
    )

    return {
        "target_date": date_str,
        "employees_total": total,
        "employees_processed": processed,
        "employees_skipped": skipped,
        "employees_failed": failed,
        "duration_seconds": round(duration, 1),
    }


# ---------------------------------------------------------------------------
# Per-employee processing
# ---------------------------------------------------------------------------

def _process_employee(
    employee: str,
    date_str: str,
    settings: SettingsSnapshot,
    force: bool = False,
) -> str:
    """Process a single employee for a single date.

    Returns:
        ``"skipped"``   — already completed and ``force=False``.
        ``"processed"`` — summary written successfully.

    Raises:
        Any exception from the calculation or DB write layer (caller handles).
    """
    log = _logger()

    # --- Idempotency gate ---
    existing_name, existing_status, existing_processed_at = _get_existing_summary(
        employee, date_str
    )

    if existing_name:
        if existing_status == "Completed" and not force:
            log.info(
                f"[GeoProcessing] SKIP {employee} on {date_str} — already Completed"
            )
            return "skipped"

        if existing_status == "Processing":
            if not _is_stale(existing_processed_at):
                log.info(
                    f"[GeoProcessing] SKIP {employee} on {date_str} — Processing (active)"
                )
                return "skipped"
            else:
                log.warning(
                    f"[GeoProcessing] Stale Processing record for {employee} on {date_str} — reprocessing"
                )

    # --- Mark as Processing (distributed lock) ---
    # Capture the returned doc name — this is the record we must UPDATE
    # on all subsequent writes. Without this, a second _upsert_summary
    # with existing_name=None would try to INSERT again and hit the
    # before_save uniqueness guard.
    processing_name = _upsert_summary(
        employee=employee,
        date_str=date_str,
        existing_name=existing_name,
        status="Processing",
        processed_at=now_datetime(),
        metrics=None,
        error_log=None,
    )

    # --- Fetch raw GPS records ---
    raw_records = _fetch_raw_records(employee, date_str, settings)
    raw_count = len(raw_records)

    if raw_count > _MAX_POINTS_HARD_CAP:
        log.warning(
            f"[GeoProcessing] {employee} on {date_str} has {raw_count} points — "
            f"capping to {_MAX_POINTS_HARD_CAP}"
        )
        raw_records = raw_records[:_MAX_POINTS_HARD_CAP]

    # --- Run pure-math calculation ---
    metrics = calculate_travel_metrics(raw_records, settings)

    # Override raw_data_count with the actual un-capped total for audit
    metrics.raw_data_count = raw_count

    # --- Upsert Completed summary (always UPDATE the Processing record) ---
    summary_name = _upsert_summary(
        employee=employee,
        date_str=date_str,
        existing_name=processing_name,   # ← use the name created above, never None
        status="Completed",
        processed_at=now_datetime(),
        metrics=metrics,
        error_log=None,
    )

    log.info(
        f"[GeoProcessing] OK {employee} on {date_str} | "
        f"raw={raw_count} valid_pts={metrics.total_points} "
        f"dist={metrics.total_distance_km_rounded}km "
        f"time={metrics.total_travel_time} "
        f"avg_spd={metrics.average_speed_kmh}km/h"
    )

    if settings.enable_debug_logging and metrics.debug_log:
        for line in metrics.debug_log:
            log.debug(f"  [segment] {line}")

    return "processed"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_distinct_employees_for_date(date_str: str) -> List[str]:
    """Return list of distinct employee IDs that have GPS records on *date_str*."""
    rows = frappe.db.sql(
        """
        SELECT DISTINCT employee
        FROM   `tabLive GEO Tracking V2`
        WHERE  DATE(captured_at) = %s
          AND  employee IS NOT NULL
          AND  employee != ''
        ORDER  BY employee
        """,
        (date_str,),
        as_list=True,
    )
    return [r[0] for r in rows]


def _fetch_raw_records(
    employee: str, date_str: str, settings: SettingsSnapshot
) -> List[Dict[str, Any]]:
    """Fetch GPS records for one employee on one date, sorted by captured_at ASC.

    Uses explicit field list — never SELECT *.
    """
    return frappe.db.get_all(
        _DOCTYPE_RAW,
        filters=[
            ["employee", "=", employee],
            ["captured_at", ">=", f"{date_str} 00:00:00"],
            ["captured_at", "<=", f"{date_str} 23:59:59"],
        ],
        fields=["name", "employee", "captured_at", "latitude", "longitude",
                "accuracy", "speed", "heading", "altitude", "source"],
        order_by="captured_at asc",
        limit=_MAX_POINTS_HARD_CAP + 1,  # +1 so we can detect overflow
    )


def _get_existing_summary(
    employee: str, date_str: str
) -> tuple[Optional[str], Optional[str], Optional[datetime]]:
    """Return (name, status, processed_at) for an existing summary or (None, None, None)."""
    row = frappe.db.get_value(
        _DOCTYPE_SUMMARY,
        filters={"employee": employee, "summary_date": date_str},
        fieldname=["name", "status", "processed_at"],
        as_dict=True,
    )
    if row:
        return row.name, row.status, row.processed_at
    return None, None, None


def _is_stale(processed_at: Optional[Any]) -> bool:
    """Return True if processed_at is older than _STALE_PROCESSING_HOURS."""
    if processed_at is None:
        return True
    if isinstance(processed_at, str):
        try:
            processed_at = datetime.fromisoformat(processed_at)
        except ValueError:
            return True
    cutoff = datetime.now() - timedelta(hours=_STALE_PROCESSING_HOURS)
    return processed_at < cutoff


def _upsert_summary(
    employee: str,
    date_str: str,
    existing_name: Optional[str],
    status: str,
    processed_at: Any,
    metrics: Optional[TravelMetrics],
    error_log: Optional[str],
) -> str:
    """Insert or update a Daily Travel Summary document.

    Uses ignore_permissions so the scheduler worker (which may run as
    Administrator or a system user) always has write access.

    Returns the document ``name``.
    """
    if existing_name:
        doc = frappe.get_doc(_DOCTYPE_SUMMARY, existing_name)
    else:
        doc = frappe.new_doc(_DOCTYPE_SUMMARY)
        doc.employee = employee
        doc.summary_date = date_str

    doc.status = status
    doc.processed_at = processed_at

    if metrics is not None:
        doc.total_distance_km = metrics.total_distance_km_rounded
        doc.total_travel_time = metrics.total_travel_time
        doc.average_speed_kmh = metrics.average_speed_kmh
        doc.total_points = metrics.total_points
        doc.raw_data_count = metrics.raw_data_count

    if error_log is not None:
        doc.error_log = error_log[:10000]  # cap to avoid DB column overflow

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return doc.name


def _mark_failed(employee: str, date_str: str, error_text: str) -> None:
    """Best-effort: mark the summary as Failed with error details."""
    try:
        existing_name, _, _ = _get_existing_summary(employee, date_str)
        _upsert_summary(
            employee=employee,
            date_str=date_str,
            existing_name=existing_name,
            status="Failed",
            processed_at=now_datetime(),
            metrics=None,
            error_log=error_text,
        )
    except Exception:  # noqa: BLE001
        _logger().error(
            f"[GeoProcessing] Could not mark Failed for {employee} on {date_str}"
        )


# ---------------------------------------------------------------------------
# Manual reprocess (called from API layer)
# ---------------------------------------------------------------------------

def reprocess_employee_summary(employee: str, target_date: str) -> Dict[str, Any]:
    """Force-reprocess a specific (employee, date) pair.

    Requires the caller to have ``System Manager`` or ``HR Manager`` role —
    enforced in the API layer before calling this function.

    Args:
        employee:    Frappe Employee document name (e.g. ``EMP-0001``).
        target_date: ISO-8601 date string (``YYYY-MM-DD``).

    Returns:
        Dict with ``status`` and summary metrics.
    """
    log = _logger()

    if not frappe.db.exists("Employee", employee):
        frappe.throw(f"Employee '{employee}' does not exist.")

    try:
        process_date = date.fromisoformat(str(target_date))
    except ValueError:
        frappe.throw(f"Invalid date: '{target_date}'. Expected YYYY-MM-DD.")

    date_str = date_to_str(process_date)
    settings = _load_settings()

    log.info(f"[GeoProcessing] Manual reprocess: {employee} on {date_str}")

    result = _process_employee(employee, date_str, settings, force=True)

    _, _, _ = _get_existing_summary(employee, date_str)
    summary = frappe.db.get_value(
        _DOCTYPE_SUMMARY,
        {"employee": employee, "summary_date": date_str},
        [
            "name", "status", "total_distance_km", "total_travel_time",
            "average_speed_kmh", "total_points", "raw_data_count",
        ],
        as_dict=True,
    )

    return {
        "action": result,
        "employee": employee,
        "date": date_str,
        "summary": summary or {},
    }
