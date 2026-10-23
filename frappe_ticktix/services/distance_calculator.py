# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt
"""Pure-math distance and time calculation engine.

CRITICAL: This module must have ZERO Frappe imports.
It accepts plain Python data structures (dicts, lists) and returns plain
Python results so it can be fully unit-tested without a Frappe instance.

Public API
----------
calculate_travel_metrics(points, settings) → TravelMetrics
    Main entry point.  Takes a list of raw GPS point dicts and a
    SettingsSnapshot, returns a TravelMetrics dataclass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .geo_utils import parse_datetime, validate_coordinates, format_duration


# ---------------------------------------------------------------------------
# Settings snapshot (passed in from the Frappe layer — no DB access here)
# ---------------------------------------------------------------------------

@dataclass
class SettingsSnapshot:
    """Immutable copy of Geo Tracking Settings fields used during calculation.

    All values have safe defaults matching the DocType defaults so unit tests
    can instantiate without any Frappe involvement.
    """

    max_speed_kmh: float = 120.0
    """Segments faster than this (km/h) are treated as GPS errors."""

    min_distance_meters: float = 10.0
    """Segments shorter than this (m) are treated as GPS jitter."""

    max_accuracy_meters: float = 50.0
    """Points with accuracy worse than this (m) are skipped."""

    session_gap_seconds: int = 900
    """Gaps longer than this (s) between consecutive points are session breaks."""

    enable_debug_logging: bool = False
    """When True, per-segment detail is included in the debug log list."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class TravelMetrics:
    """Aggregated travel metrics for one employee for one calendar day."""

    total_distance_km: float = 0.0
    total_travel_seconds: float = 0.0
    total_points: int = 0          # points used after all filters
    raw_data_count: int = 0        # all points before filtering
    filtered_count: int = 0        # points/segments discarded
    debug_log: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def total_travel_time(self) -> str:
        """Human-readable travel time as ``HH:MM:SS``."""
        return format_duration(self.total_travel_seconds)

    @property
    def average_speed_kmh(self) -> float:
        """Average speed during active movement (km/h), rounded to 2 dp."""
        if self.total_travel_seconds <= 0:
            return 0.0
        hours = self.total_travel_seconds / 3600.0
        return round(self.total_distance_km / hours, 2)

    @property
    def total_distance_km_rounded(self) -> float:
        """Final storable value rounded to 3 decimal places (1 m resolution)."""
        return round(self.total_distance_km, 3)


# ---------------------------------------------------------------------------
# Haversine formula
# ---------------------------------------------------------------------------

_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in **kilometres** between two WGS-84 points.

    Uses the Haversine formula which is accurate to < 0.3 % for distances
    up to ~1,000 km — sufficient for employee field tracking.

    Args:
        lat1, lon1: First point in decimal degrees.
        lat2, lon2: Second point in decimal degrees.

    Returns:
        Distance in kilometres (float).
    """
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(rlat1) * math.cos(rlat2) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_KM * c


# ---------------------------------------------------------------------------
# Point preparation
# ---------------------------------------------------------------------------

@dataclass
class _PreparedPoint:
    """Internal representation of a GPS point ready for segment processing."""

    lat: float
    lon: float
    ts: datetime
    accuracy: Optional[float]
    raw: Dict[str, Any]


def _prepare_points(
    raw_points: List[Dict[str, Any]],
    settings: SettingsSnapshot,
    debug_log: List[str],
) -> Tuple[List[_PreparedPoint], int, int]:
    """Parse, validate, deduplicate, and sort raw GPS dicts.

    Returns:
        (prepared_points, raw_count, skipped_count)
    """
    raw_count = len(raw_points)
    prepared: List[_PreparedPoint] = []
    skipped = 0

    for point in raw_points:
        lat = point.get("lat")
        lon = point.get("long")
        captured_raw = point.get("device_date_time")
        accuracy = point.get("accuracy")

        # --- Coordinate validation ---
        if not validate_coordinates(lat, lon):
            skipped += 1
            if settings.enable_debug_logging:
                debug_log.append(
                    f"SKIP invalid coords lat={lat} lon={lon}"
                )
            continue

        # --- Timestamp validation ---
        ts = parse_datetime(captured_raw)
        if ts is None:
            skipped += 1
            if settings.enable_debug_logging:
                debug_log.append(
                    f"SKIP missing/unparseable device_date_time='{captured_raw}'"
                )
            continue

        # --- Accuracy filter ---
        if (
            accuracy is not None
            and settings.max_accuracy_meters > 0
            and float(accuracy) > settings.max_accuracy_meters
        ):
            skipped += 1
            if settings.enable_debug_logging:
                debug_log.append(
                    f"SKIP poor accuracy={accuracy}m > {settings.max_accuracy_meters}m"
                )
            continue

        prepared.append(
            _PreparedPoint(
                lat=float(lat),
                lon=float(lon),
                ts=ts,
                accuracy=float(accuracy) if accuracy is not None else None,
                raw=point,
            )
        )

    # Sort ascending by timestamp (primary sort already done at DB level;
    # this is a defensive secondary sort for late-arriving or clock-drifted points)
    prepared.sort(key=lambda p: p.ts)

    # Deduplicate exact (lat, lon, ts) triples
    seen: set = set()
    deduped: List[_PreparedPoint] = []
    for p in prepared:
        key = (p.lat, p.lon, p.ts)
        if key not in seen:
            seen.add(key)
            deduped.append(p)
        else:
            skipped += 1
            if settings.enable_debug_logging:
                debug_log.append(f"SKIP duplicate point at {p.ts}")

    return deduped, raw_count, skipped


# ---------------------------------------------------------------------------
# Segment processing
# ---------------------------------------------------------------------------

def _process_segments(
    points: List[_PreparedPoint],
    settings: SettingsSnapshot,
    debug_log: List[str],
) -> Tuple[float, float, int, int]:
    """Iterate through point-pairs and accumulate valid travel metrics.

    Returns:
        (total_distance_km, total_travel_seconds, valid_segment_count, filtered_segments)
    """
    total_distance_km = 0.0
    total_travel_seconds = 0.0
    valid_segments = 0
    filtered_segments = 0

    for i in range(len(points) - 1):
        p_curr = points[i]
        p_next = points[i + 1]

        # --- Out-of-order / duplicate timestamp guard ---
        elapsed_seconds = (p_next.ts - p_curr.ts).total_seconds()
        if elapsed_seconds <= 0:
            filtered_segments += 1
            if settings.enable_debug_logging:
                debug_log.append(
                    f"SKIP non-positive elapsed={elapsed_seconds}s between "
                    f"{p_curr.ts} and {p_next.ts}"
                )
            continue

        # --- Haversine distance ---
        dist_km = haversine_km(p_curr.lat, p_curr.lon, p_next.lat, p_next.lon)

        # --- Filter 1: Minimum distance (GPS jitter) ---
        min_km = settings.min_distance_meters / 1000.0
        if dist_km < min_km:
            filtered_segments += 1
            if settings.enable_debug_logging:
                debug_log.append(
                    f"SKIP jitter dist={dist_km*1000:.1f}m < {settings.min_distance_meters}m"
                )
            continue

        # --- Filter 2: Maximum realistic speed ---
        speed_kmh = (dist_km / elapsed_seconds) * 3600.0
        if speed_kmh > settings.max_speed_kmh:
            filtered_segments += 1
            if settings.enable_debug_logging:
                debug_log.append(
                    f"SKIP unrealistic speed={speed_kmh:.1f}km/h > {settings.max_speed_kmh}km/h "
                    f"(dist={dist_km*1000:.1f}m, elapsed={elapsed_seconds:.0f}s)"
                )
            continue

        # --- Filter 3: Session gap ---
        if elapsed_seconds > settings.session_gap_seconds:
            filtered_segments += 1
            if settings.enable_debug_logging:
                debug_log.append(
                    f"SKIP session gap elapsed={elapsed_seconds:.0f}s > {settings.session_gap_seconds}s"
                )
            continue

        # --- All filters passed: accumulate ---
        total_distance_km += dist_km
        total_travel_seconds += elapsed_seconds
        valid_segments += 1

        if settings.enable_debug_logging:
            debug_log.append(
                f"OK  dist={dist_km*1000:.1f}m speed={speed_kmh:.1f}km/h elapsed={elapsed_seconds:.0f}s"
            )

    return total_distance_km, total_travel_seconds, valid_segments, filtered_segments


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------

def calculate_travel_metrics(
    raw_points: List[Dict[str, Any]],
    settings: Optional[SettingsSnapshot] = None,
) -> TravelMetrics:
    """Calculate travel distance and time from a list of raw GPS point dicts.

    This is the single entry point for the distance calculation layer.
    It is stateless and has no Frappe dependencies — pass the settings
    in from the Frappe orchestration layer.

    Args:
        raw_points:
            List of dicts, each with at minimum:
            ``lat``, ``long``, ``device_date_time``.
            Optional: ``accuracy``, ``speed``, ``heading``, ``altitude``.
        settings:
            A :class:`SettingsSnapshot` with filter thresholds.  Defaults
            to safe production values if not provided.

    Returns:
        A :class:`TravelMetrics` instance with all aggregated results.
    """
    if settings is None:
        settings = SettingsSnapshot()

    metrics = TravelMetrics()
    debug_log = metrics.debug_log

    if not raw_points:
        return metrics

    # Step 1: Prepare, validate, deduplicate, sort
    prepared, raw_count, prep_skipped = _prepare_points(
        raw_points, settings, debug_log
    )
    metrics.raw_data_count = raw_count

    if len(prepared) < 2:
        # Fewer than 2 valid points → no segments possible
        metrics.total_points = len(prepared)
        metrics.filtered_count = raw_count - len(prepared)
        return metrics

    # Step 2: Process segments
    dist_km, travel_secs, valid_segs, filtered_segs = _process_segments(
        prepared, settings, debug_log
    )

    # Step 3: Populate metrics
    metrics.total_distance_km = dist_km
    metrics.total_travel_seconds = travel_secs
    metrics.total_points = len(prepared) - filtered_segs  # points contributing to valid segs
    metrics.filtered_count = prep_skipped + filtered_segs

    # Clamp to safe range
    metrics.total_points = max(0, metrics.total_points)

    return metrics
