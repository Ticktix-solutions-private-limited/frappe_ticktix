"""Geo tracking APIs for check-in/out and live location batches."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import frappe
from frappe.utils import now_datetime

from ...config.config_manager import get_config_manager


DEFAULT_MAX_BATCH_SIZE = 200


def _get_geo_config() -> Dict[str, Any]:
    config_manager = get_config_manager()
    ticktix_config = config_manager.get_config_value("ticktix", {})
    hr_config = ticktix_config.get("hr", {}) if isinstance(ticktix_config, dict) else {}
    return hr_config.get("geo_tracking", {}) if isinstance(hr_config, dict) else {}


def _ensure_enabled() -> None:
    config = _get_geo_config()
    if config.get("enabled", True) is False:
        frappe.throw("Geo tracking is disabled")


def _get_employee_for_user(user: str) -> Optional[str]:
    return frappe.db.get_value("Employee", {"user_id": user}, "name")


def _is_hr_role(user: str) -> bool:
    roles = frappe.get_roles(user)
    return any(role in {"HR Manager", "HR User", "System Manager"} for role in roles)


def _resolve_employee(employee: Optional[str]) -> str:
    user = frappe.session.user
    if user == "Guest":
        frappe.throw("Authentication required")

    if employee:
        if employee == _get_employee_for_user(user) or _is_hr_role(user):
            return employee
        frappe.throw("Not permitted to submit for this employee")

    employee_name = _get_employee_for_user(user)
    if not employee_name:
        frappe.throw("No Employee linked to current user")
    return employee_name


def _coerce_float(value: Any, field_label: str) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        frappe.throw(f"Invalid {field_label}")
    return None


def _validate_coordinates(latitude: Optional[float], longitude: Optional[float]) -> None:
    if latitude is None or longitude is None:
        return
    if not (-90 <= latitude <= 90):
        frappe.throw("Latitude must be between -90 and 90")
    if not (-180 <= longitude <= 180):
        frappe.throw("Longitude must be between -180 and 180")


@frappe.whitelist()
def punch_in(
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    device_id: Optional[str] = None,
    checkin_time: Optional[str] = None,
    employee: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an Employee Checkin (IN) with optional coordinates."""
    _ensure_enabled()
    employee_name = _resolve_employee(employee)

    lat_value = _coerce_float(latitude, "latitude")
    lon_value = _coerce_float(longitude, "longitude")
    _validate_coordinates(lat_value, lon_value)

    doc = frappe.new_doc("Employee Checkin")
    doc.employee = employee_name
    doc.log_type = "IN"
    doc.time = checkin_time or now_datetime()
    doc.device_id = device_id
    doc.latitude = lat_value
    doc.longitude = lon_value

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "name": doc.name,
        "employee": doc.employee,
        "log_type": doc.log_type,
        "time": doc.time,
    }


@frappe.whitelist()
def punch_out(
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    device_id: Optional[str] = None,
    checkin_time: Optional[str] = None,
    employee: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an Employee Checkin (OUT) with optional coordinates."""
    _ensure_enabled()
    employee_name = _resolve_employee(employee)

    lat_value = _coerce_float(latitude, "latitude")
    lon_value = _coerce_float(longitude, "longitude")
    _validate_coordinates(lat_value, lon_value)

    doc = frappe.new_doc("Employee Checkin")
    doc.employee = employee_name
    doc.log_type = "OUT"
    doc.time = checkin_time or now_datetime()
    doc.device_id = device_id
    doc.latitude = lat_value
    doc.longitude = lon_value

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "name": doc.name,
        "employee": doc.employee,
        "log_type": doc.log_type,
        "time": doc.time,
    }


def _normalize_point(point: Dict[str, Any]) -> Dict[str, Any]:
    lat = point.get("latitude", point.get("lat"))
    lon = point.get("longitude", point.get("lng", point.get("long")))
    captured_at = point.get("captured_at", point.get("timestamp", point.get("time")))
    accuracy = point.get("accuracy")
    speed = point.get("speed")
    heading = point.get("heading")
    altitude = point.get("altitude")

    lat_value = _coerce_float(lat, "latitude")
    lon_value = _coerce_float(lon, "longitude")
    _validate_coordinates(lat_value, lon_value)

    return {
        "latitude": lat_value,
        "longitude": lon_value,
        "captured_at": captured_at,
        "accuracy": _coerce_float(accuracy, "accuracy") if accuracy is not None else None,
        "speed": _coerce_float(speed, "speed") if speed is not None else None,
        "heading": _coerce_float(heading, "heading") if heading is not None else None,
        "altitude": _coerce_float(altitude, "altitude") if altitude is not None else None,
    }


@frappe.whitelist()
def upload_live_points(
    points: Iterable[Dict[str, Any]] | str,
    employee: Optional[str] = None,
    device_id: Optional[str] = None,
    source: str = "background",
    batch_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Upload a batch of live geo points."""
    _ensure_enabled()
    employee_name = _resolve_employee(employee)

    parsed_points = frappe.parse_json(points) if isinstance(points, str) else points
    if not isinstance(parsed_points, list) or not parsed_points:
        frappe.throw("Points payload must be a non-empty list")

    config = _get_geo_config()
    max_batch = int(config.get("max_batch_size", DEFAULT_MAX_BATCH_SIZE))
    if len(parsed_points) > max_batch:
        frappe.throw(f"Batch size exceeds limit ({max_batch})")

    created = 0
    for point in parsed_points:
        normalized = _normalize_point(point)
        if normalized.get("latitude") is None or normalized.get("longitude") is None:
            continue

        doc = frappe.new_doc("Live GEO Tracking V2")
        doc.employee = employee_name
        doc.user = frappe.session.user
        doc.captured_at = normalized.get("captured_at") or now_datetime()
        doc.latitude = normalized.get("latitude")
        doc.longitude = normalized.get("longitude")
        doc.accuracy = normalized.get("accuracy")
        doc.speed = normalized.get("speed")
        doc.heading = normalized.get("heading")
        doc.altitude = normalized.get("altitude")
        doc.device_id = device_id
        doc.source = source
        doc.batch_id = batch_id
        doc.insert(ignore_permissions=True)
        created += 1

    frappe.db.commit()
    return {
        "status": "success",
        "created": created,
        "employee": employee_name,
    }


@frappe.whitelist()
def get_live_points(
    employee: Optional[str] = None,
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    limit: Optional[int] = 500,
) -> List[Dict[str, Any]]:
    """Fetch live geo points for a specific employee and time range."""
    _ensure_enabled()
    employee_name = _resolve_employee(employee)

    filters = [["Live GEO Tracking V2", "employee", "=", employee_name]]
    if from_time:
        filters.append(["Live GEO Tracking V2", "captured_at", ">=", from_time])
    if to_time:
        filters.append(["Live GEO Tracking V2", "captured_at", "<=", to_time])

    return frappe.get_all(
        "Live GEO Tracking V2",
        filters=filters,
        fields=[
            "name",
            "employee",
            "user",
            "captured_at",
            "latitude",
            "longitude",
            "accuracy",
            "speed",
            "heading",
            "altitude",
            "device_id",
            "source",
            "batch_id",
        ],
        order_by="captured_at asc",
        limit=int(limit) if limit else 500,
    )
