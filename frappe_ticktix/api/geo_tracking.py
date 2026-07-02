# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt
"""Whitelisted API endpoints for the daily travel summary system.

This layer is intentionally thin — it handles:
  - Input validation and permission checks
  - Delegation to the services layer
  - Structured JSON response formatting

No business logic lives here.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import frappe
from frappe import _

from ..services.geo_processing import reprocess_employee_summary, run_daily_travel_summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ROLES_ALLOWED_REPROCESS = {"System Manager", "HR Manager"}


def _require_roles(*roles: str) -> None:
    """Raise PermissionError if the session user holds none of *roles*."""
    user_roles = set(frappe.get_roles(frappe.session.user))
    if not user_roles.intersection(roles):
        frappe.throw(
            _(
                "You do not have permission to perform this action. "
                "Required role: {0}"
            ).format(", ".join(roles)),
            frappe.PermissionError,
        )


def _parse_date(value: str, field_name: str) -> date:
    """Parse *value* as ISO-8601 date or throw a descriptive 400."""
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        frappe.throw(
            _(f"Invalid {field_name}: '{{0}}'. Expected YYYY-MM-DD format.").format(value)
        )


def _validate_date_range(from_date: date, to_date: date) -> None:
    if from_date > to_date:
        frappe.throw(_("from_date must be on or before to_date."))
    delta = (to_date - from_date).days
    if delta > 365:
        frappe.throw(_("Date range cannot exceed 365 days."))


def _validate_employee(employee: str) -> str:
    """Return employee_name if valid, otherwise throw 404."""
    if not frappe.db.exists("Employee", employee):
        frappe.throw(
            _(f"Employee '{{0}}' not found.").format(employee),
            frappe.DoesNotExistError,
        )
    return employee


def _get_employee_full_name(employee: str) -> str:
    return frappe.db.get_value("Employee", employee, "employee_name") or employee


# ---------------------------------------------------------------------------
# Endpoint 1 — get_employee_travel_summary
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_employee_travel_summary(
    employee: str,
    from_date: str,
    to_date: str,
    include_empty: bool = False,
) -> Dict[str, Any]:
    """Return daily travel summaries for one employee over a date range.

    Args:
        employee:      Frappe Employee name (e.g. ``EMP-0001``).
        from_date:     Start date inclusive, ``YYYY-MM-DD``.
        to_date:       End date inclusive, ``YYYY-MM-DD``.
        include_empty: If ``True``, pad missing dates with zero-value entries.

    Returns:
        JSON with ``employee``, ``employee_name``, ``summary`` list, and
        aggregated ``aggregates`` block.

    Raises:
        frappe.PermissionError  — caller lacks read permission.
        frappe.DoesNotExistError — employee not found.
        frappe.ValidationError  — invalid date range.
    """
    # --- Input validation (order matters) ---
    if not employee:
        frappe.throw(_("employee is required."))
    if not from_date:
        frappe.throw(_("from_date is required."))
    if not to_date:
        frappe.throw(_("to_date is required."))

    from_d = _parse_date(from_date, "from_date")
    to_d = _parse_date(to_date, "to_date")
    _validate_date_range(from_d, to_d)
    _validate_employee(employee)

    # Permission check — read on Daily Travel Summary
    if not frappe.has_permission("Daily Travel Summary", "read"):
        frappe.throw(
            _("You do not have permission to read Daily Travel Summary."),
            frappe.PermissionError,
        )

    # --- Query summaries ---
    rows = frappe.db.get_all(
        "Daily Travel Summary",
        filters=[
            ["employee", "=", employee],
            ["summary_date", ">=", str(from_d)],
            ["summary_date", "<=", str(to_d)],
        ],
        fields=[
            "summary_date",
            "total_distance_km",
            "total_travel_time",
            "average_speed_kmh",
            "total_points",
            "raw_data_count",
            "status",
        ],
        order_by="summary_date asc",
    )

    # --- Build summary list (optionally padded with empty dates) ---
    summary: List[Dict[str, Any]] = []

    if include_empty:
        row_by_date = {str(r["summary_date"]): r for r in rows}
        current = from_d
        while current <= to_d:
            ds = str(current)
            if ds in row_by_date:
                r = row_by_date[ds]
                summary.append(_format_row(r))
            else:
                summary.append(_empty_row(ds))
            current += timedelta(days=1)
    else:
        for r in rows:
            summary.append(_format_row(r))

    # --- Aggregates (computed in Python, no second SQL) ---
    completed = [s for s in summary if s["status"] == "Completed"]
    total_dist = round(sum(s["total_distance_km"] for s in completed), 3)
    travel_days = len(completed)
    avg_daily = round(total_dist / travel_days, 3) if travel_days else 0.0

    return {
        "employee": employee,
        "employee_name": _get_employee_full_name(employee),
        "from_date": str(from_d),
        "to_date": str(to_d),
        "summary": summary,
        "aggregates": {
            "total_distance_km": total_dist,
            "total_travel_days": travel_days,
            "average_daily_distance_km": avg_daily,
        },
    }


def _format_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "date": str(row.get("summary_date", "")),
        "total_distance_km": float(row.get("total_distance_km") or 0),
        "total_travel_time": row.get("total_travel_time") or "00:00:00",
        "average_speed_kmh": float(row.get("average_speed_kmh") or 0),
        "total_points": int(row.get("total_points") or 0),
        "raw_data_count": int(row.get("raw_data_count") or 0),
        "status": row.get("status") or "Pending",
    }


def _empty_row(date_str: str) -> Dict[str, Any]:
    return {
        "date": date_str,
        "total_distance_km": 0.0,
        "total_travel_time": "00:00:00",
        "average_speed_kmh": 0.0,
        "total_points": 0,
        "raw_data_count": 0,
        "status": "No Data",
    }


# ---------------------------------------------------------------------------
# Endpoint 2 — get_team_travel_summary
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_team_travel_summary(
    from_date: str,
    to_date: str,
    department: Optional[str] = None,
    employees: Optional[str] = None,
) -> Dict[str, Any]:
    """Return aggregated travel summaries for a team / department.

    Args:
        from_date:   Start date inclusive, ``YYYY-MM-DD``.
        to_date:     End date inclusive, ``YYYY-MM-DD``.
        department:  Optional department name to filter employees.
        employees:   Optional JSON array string of employee IDs.

    Returns:
        JSON with a list of per-employee aggregated summaries.
    """
    if not from_date or not to_date:
        frappe.throw(_("from_date and to_date are required."))

    from_d = _parse_date(from_date, "from_date")
    to_d = _parse_date(to_date, "to_date")
    _validate_date_range(from_d, to_d)

    if not frappe.has_permission("Daily Travel Summary", "read"):
        frappe.throw(
            _("You do not have permission to read Daily Travel Summary."),
            frappe.PermissionError,
        )

    # --- Build employee filter ---
    # filtered_emp_ids is populated when a department or explicit employee list
    # is given; it is passed directly to _team_summary_orm so the function does
    # not have to re-derive the list from the filter structure.
    filtered_emp_ids: List[str] = []

    if employees:
        emp_list = frappe.parse_json(employees) if isinstance(employees, str) else employees
        if isinstance(emp_list, list) and emp_list:
            filtered_emp_ids = list(emp_list)

    elif department:
        dept_emp_ids = frappe.db.get_all(
            "Employee",
            filters={"department": department, "status": "Active"},
            pluck="name",
        )
        if not dept_emp_ids:
            return {"from_date": str(from_d), "to_date": str(to_d), "team": []}
        filtered_emp_ids = dept_emp_ids

    # --- Aggregate via SQL for efficiency ---
    if not department and not employees:
        # No filter — return all employees
        rows = frappe.db.sql(
            """
            SELECT
                employee,
                COUNT(*)                    AS travel_days,
                SUM(total_distance_km)      AS total_distance_km,
                AVG(average_speed_kmh)      AS avg_speed_kmh,
                SUM(total_points)           AS total_points,
                SUM(raw_data_count)         AS raw_data_count
            FROM   `tabDaily Travel Summary`
            WHERE  summary_date BETWEEN %s AND %s
              AND  status = 'Completed'
            GROUP  BY employee
            ORDER  BY total_distance_km DESC
            """,
            (str(from_d), str(to_d)),
            as_dict=True,
        )
    else:
        # Filtered path — pass the explicit employee list to the helper
        rows = _team_summary_orm(filtered_emp_ids, from_d, to_d)

    team = [
        {
            "employee": r["employee"],
            "employee_name": _get_employee_full_name(r["employee"]),
            "travel_days": int(r.get("travel_days") or 0),
            "total_distance_km": round(float(r.get("total_distance_km") or 0), 3),
            "avg_speed_kmh": round(float(r.get("avg_speed_kmh") or 0), 2),
            "total_points": int(r.get("total_points") or 0),
        }
        for r in rows
    ]

    return {
        "from_date": str(from_d),
        "to_date": str(to_d),
        "department": department,
        "team": team,
    }


def _team_summary_orm(
    emp_ids: List[str], from_d: date, to_d: date
) -> List[Dict[str, Any]]:
    """SQL query for department/employee-filtered team summaries.

    Args:
        emp_ids: Explicit list of employee IDs to include.  Must not be empty
                 (callers should guard before calling).
        from_d:  Start date (inclusive).
        to_d:    End date (inclusive).

    Returns:
        Rows with per-employee aggregate columns, ordered by total distance
        descending.  Only ``Completed`` summaries are counted.
    """
    if not emp_ids:
        return []

    placeholders = ", ".join(["%s"] * len(emp_ids))
    return frappe.db.sql(
        f"""
        SELECT
            employee,
            COUNT(*)               AS travel_days,
            SUM(total_distance_km) AS total_distance_km,
            AVG(average_speed_kmh) AS avg_speed_kmh,
            SUM(total_points)      AS total_points,
            SUM(raw_data_count)    AS raw_data_count
        FROM   `tabDaily Travel Summary`
        WHERE  summary_date BETWEEN %s AND %s
          AND  status = 'Completed'
          AND  employee IN ({placeholders})
        GROUP  BY employee
        ORDER  BY total_distance_km DESC
        """,
        (str(from_d), str(to_d), *emp_ids),
        as_dict=True,
    )


# ---------------------------------------------------------------------------
# Endpoint 3 — reprocess_travel_summary
# ---------------------------------------------------------------------------

@frappe.whitelist()
def reprocess_travel_summary(employee: str, target_date: str) -> Dict[str, Any]:
    """Manually trigger reprocessing for one (employee, date) pair.

    Requires ``System Manager`` or ``HR Manager`` role.

    Args:
        employee:    Frappe Employee name.
        target_date: ISO-8601 date string.

    Returns:
        Dict with ``action`` (``"processed"``), ``employee``, ``date``,
        and ``summary`` metrics.
    """
    _require_roles(*_ROLES_ALLOWED_REPROCESS)

    if not employee:
        frappe.throw(_("employee is required."))
    if not target_date:
        frappe.throw(_("target_date is required."))

    _validate_employee(employee)
    _parse_date(target_date, "target_date")  # validates format

    return reprocess_employee_summary(employee, target_date)


# ---------------------------------------------------------------------------
# Endpoint 4 — trigger_batch_processing (manual full-day run)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def trigger_batch_processing(target_date: Optional[str] = None) -> Dict[str, Any]:
    """Manually trigger the full nightly batch for a given date.

    Only ``System Manager`` may call this.

    Args:
        target_date: Optional ISO-8601 date (``YYYY-MM-DD``).
                     Defaults to **yesterday** when omitted — matching the
                     behaviour of the 00:30 nightly scheduler, which always
                     processes the previous calendar day.

    Returns:
        Job summary dict from :func:`run_daily_travel_summary`.
    """
    _require_roles("System Manager")

    if target_date:
        _parse_date(target_date, "target_date")

    return run_daily_travel_summary(target_date=target_date)
