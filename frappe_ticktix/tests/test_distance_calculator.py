# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt
"""Unit tests for distance_calculator and geo_utils.

These tests require NO Frappe instance — run with plain pytest:

    cd apps/frappe_ticktix
    python -m pytest frappe_ticktix/tests/test_distance_calculator.py -v

All fixtures use hardcoded, known-good GPS coordinates so results can be
verified against external reference calculators.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from frappe_ticktix.services.distance_calculator import (
    SettingsSnapshot,
    TravelMetrics,
    calculate_travel_metrics,
    haversine_km,
)
from frappe_ticktix.services.geo_utils import (
    format_duration,
    parse_datetime,
    parse_duration,
    validate_coordinates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(offset_minutes: int = 0) -> str:
    """Return a fixed ISO datetime string offset by *offset_minutes*."""
    base = datetime(2026, 1, 15, 8, 0, 0)
    return (base + timedelta(minutes=offset_minutes)).strftime("%Y-%m-%d %H:%M:%S")


def _point(lat: float, lon: float, offset_minutes: int, accuracy: float = 5.0) -> dict:
    return {
        "lat": lat,
        "long": lon,
        "device_date_time": _ts(offset_minutes),
        "accuracy": accuracy,
    }


# Known reference pair: Kuala Lumpur city centre → Petronas Towers (~1.13 km)
_KL_CENTER = (3.1478, 101.6953)
_PETRONAS  = (3.1579, 101.7120)

# Default settings for tests (strict)
_SETTINGS = SettingsSnapshot(
    max_speed_kmh=120.0,
    min_distance_meters=10.0,
    max_accuracy_meters=50.0,
    session_gap_seconds=900,
    enable_debug_logging=True,
)


# ===========================================================================
# geo_utils tests
# ===========================================================================

class TestGeoUtils(unittest.TestCase):

    # --- parse_datetime ---

    def test_parse_datetime_standard_format(self):
        dt = parse_datetime("2026-01-15 08:00:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.hour, 8)

    def test_parse_datetime_with_microseconds(self):
        dt = parse_datetime("2026-01-15 08:00:00.123456")
        self.assertIsNotNone(dt)

    def test_parse_datetime_iso_t_format(self):
        dt = parse_datetime("2026-01-15T08:30:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.minute, 30)

    def test_parse_datetime_passthrough_datetime(self):
        raw = datetime(2026, 1, 15, 9, 0)
        self.assertIs(parse_datetime(raw), raw)

    def test_parse_datetime_none_returns_none(self):
        self.assertIsNone(parse_datetime(None))

    def test_parse_datetime_empty_string_returns_none(self):
        self.assertIsNone(parse_datetime(""))

    def test_parse_datetime_garbage_returns_none(self):
        self.assertIsNone(parse_datetime("not-a-date"))

    # --- validate_coordinates ---

    def test_valid_coordinates(self):
        self.assertTrue(validate_coordinates(3.1478, 101.6953))

    def test_latitude_out_of_range(self):
        self.assertFalse(validate_coordinates(91.0, 101.0))
        self.assertFalse(validate_coordinates(-91.0, 101.0))

    def test_longitude_out_of_range(self):
        self.assertFalse(validate_coordinates(3.0, 181.0))
        self.assertFalse(validate_coordinates(3.0, -181.0))

    def test_none_coordinates(self):
        self.assertFalse(validate_coordinates(None, 100.0))
        self.assertFalse(validate_coordinates(3.0, None))

    def test_string_coordinates_coerced(self):
        self.assertTrue(validate_coordinates("3.1478", "101.6953"))

    # --- format_duration ---

    def test_format_duration_zero(self):
        self.assertEqual(format_duration(0), "00:00:00")

    def test_format_duration_one_hour(self):
        self.assertEqual(format_duration(3600), "01:00:00")

    def test_format_duration_mixed(self):
        self.assertEqual(format_duration(3661), "01:01:01")

    def test_format_duration_over_24h(self):
        self.assertEqual(format_duration(90000), "25:00:00")

    # --- parse_duration ---

    def test_parse_duration_roundtrip(self):
        self.assertEqual(parse_duration(format_duration(3661)), 3661)

    def test_parse_duration_empty(self):
        self.assertEqual(parse_duration(""), 0.0)


# ===========================================================================
# haversine_km tests
# ===========================================================================

class TestHaversine(unittest.TestCase):

    def test_known_distance_kl(self):
        dist = haversine_km(*_KL_CENTER, *_PETRONAS)
        # Haversine (R=6371 km): KL Centre → Petronas ≈ 2.17 km
        self.assertAlmostEqual(dist, 2.17, delta=0.05)

    def test_zero_distance(self):
        dist = haversine_km(3.1478, 101.6953, 3.1478, 101.6953)
        self.assertAlmostEqual(dist, 0.0, places=6)

    def test_symmetry(self):
        d1 = haversine_km(3.0, 101.0, 4.0, 102.0)
        d2 = haversine_km(4.0, 102.0, 3.0, 101.0)
        self.assertAlmostEqual(d1, d2, places=6)

    def test_known_distance_equator(self):
        # 1 degree of longitude at equator using R=6371 km ≈ 111.195 km
        dist = haversine_km(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(dist, 111.19, delta=0.1)


# ===========================================================================
# calculate_travel_metrics — happy-path tests
# ===========================================================================

class TestCalculateTravelMetricsHappyPath(unittest.TestCase):

    def test_empty_points_returns_zero_metrics(self):
        m = calculate_travel_metrics([], _SETTINGS)
        self.assertEqual(m.total_distance_km, 0.0)
        self.assertEqual(m.total_travel_seconds, 0.0)
        self.assertEqual(m.raw_data_count, 0)

    def test_single_point_returns_zero_metrics(self):
        points = [_point(3.1478, 101.6953, 0)]
        m = calculate_travel_metrics(points, _SETTINGS)
        self.assertEqual(m.total_distance_km, 0.0)
        self.assertEqual(m.raw_data_count, 1)

    def test_two_valid_points_accumulates_distance(self):
        # ~1.88 km apart, 5 minutes apart → speed ~22.5 km/h → passes all filters
        points = [
            _point(*_KL_CENTER, offset_minutes=0),
            _point(*_PETRONAS,  offset_minutes=5),
        ]
        m = calculate_travel_metrics(points, _SETTINGS)
        self.assertGreater(m.total_distance_km, 1.0)
        self.assertGreater(m.total_travel_seconds, 0)
        self.assertEqual(m.raw_data_count, 2)

    def test_travel_time_format(self):
        points = [
            _point(3.1478, 101.6953, 0),
            _point(3.1579, 101.7120, 5),
        ]
        m = calculate_travel_metrics(points, _SETTINGS)
        # Should be "00:05:00" — 5 minutes = 300 seconds
        self.assertEqual(m.total_travel_time, "00:05:00")

    def test_average_speed_computed(self):
        points = [
            _point(*_KL_CENTER, 0),
            _point(*_PETRONAS,  5),
        ]
        m = calculate_travel_metrics(points, _SETTINGS)
        # 1.88 km in 5 min = 22.56 km/h approximately
        self.assertGreater(m.average_speed_kmh, 15.0)
        self.assertLess(m.average_speed_kmh, 35.0)

    def test_rounded_distance_3dp(self):
        points = [
            _point(*_KL_CENTER, 0),
            _point(*_PETRONAS,  5),
        ]
        m = calculate_travel_metrics(points, _SETTINGS)
        self.assertEqual(m.total_distance_km_rounded, round(m.total_distance_km, 3))

    def test_multiple_segments_accumulate(self):
        # Three collinear points moving north, each ~1 km apart, 10 min apart
        points = [
            _point(3.0000, 101.0000, 0),
            _point(3.0090, 101.0000, 10),   # ~1 km north
            _point(3.0180, 101.0000, 20),   # another ~1 km north
        ]
        m = calculate_travel_metrics(points, _SETTINGS)
        self.assertAlmostEqual(m.total_distance_km, 2.0, delta=0.05)
        self.assertEqual(m.total_travel_seconds, 1200.0)  # 20 minutes = 1200 s


# ===========================================================================
# calculate_travel_metrics — noise filter tests
# ===========================================================================

class TestNoiseFilters(unittest.TestCase):

    def test_filter_gps_jitter_under_10m(self):
        """Points < 10 m apart must be discarded (GPS jitter)."""
        # 0.000001 degree ≈ 0.11 m — well under 10 m threshold
        points = [
            _point(3.0000000, 101.0000000, 0),
            _point(3.0000001, 101.0000001, 1),
        ]
        m = calculate_travel_metrics(points, _SETTINGS)
        self.assertEqual(m.total_distance_km, 0.0)
        self.assertEqual(m.total_travel_seconds, 0.0)

    def test_filter_unrealistic_speed(self):
        """Segments > 120 km/h must be discarded."""
        # 50 km in 10 seconds = 18000 km/h — clearly a GPS error
        points = [
            _point(3.0000, 101.0000, 0),
            _point(3.4500, 101.0000, 0),  # same timestamp + 0 min = instantaneous
        ]
        # Use same timestamp but add 10 seconds via manual construction
        base = datetime(2026, 1, 15, 8, 0, 0)
        points = [
            {"lat": 3.0000, "long": 101.0000,
             "device_date_time": base.strftime("%Y-%m-%d %H:%M:%S"), "accuracy": 5.0},
            {"lat": 3.4500, "long": 101.0000,
             "device_date_time": (base + timedelta(seconds=10)).strftime("%Y-%m-%d %H:%M:%S"),
             "accuracy": 5.0},
        ]
        m = calculate_travel_metrics(points, _SETTINGS)
        self.assertEqual(m.total_distance_km, 0.0)

    def test_filter_session_gap(self):
        """Segments with elapsed time > session_gap_seconds must not count travel time."""
        settings = SettingsSnapshot(session_gap_seconds=60)  # 1 minute gap threshold
        points = [
            _point(3.0000, 101.0000, 0),
            _point(3.0090, 101.0000, 30),  # 30 min gap > 1 min threshold
        ]
        m = calculate_travel_metrics(points, settings)
        # Distance segment is discarded because elapsed > session_gap_seconds
        self.assertEqual(m.total_travel_seconds, 0.0)

    def test_filter_poor_accuracy(self):
        """Points with accuracy > max_accuracy_meters must be skipped entirely."""
        settings = SettingsSnapshot(max_accuracy_meters=20.0)
        points = [
            _point(3.0000, 101.0000, 0, accuracy=5.0),   # good
            _point(3.0090, 101.0000, 10, accuracy=100.0), # poor — skip
        ]
        m = calculate_travel_metrics(points, settings)
        # Only 1 valid point → no segments possible
        self.assertEqual(m.total_distance_km, 0.0)

    def test_filter_missing_timestamp(self):
        """Points with None or unparseable device_date_time must be skipped."""
        points = [
            {"lat": 3.0000, "long": 101.0000, "device_date_time": None, "accuracy": 5},
            {"lat": 3.0090, "long": 101.0000, "device_date_time": "bad-date", "accuracy": 5},
            _point(3.0180, 101.0000, 5),  # only valid one
        ]
        m = calculate_travel_metrics(points, _SETTINGS)
        self.assertEqual(m.raw_data_count, 3)
        # Only 1 valid point → no segments
        self.assertEqual(m.total_distance_km, 0.0)

    def test_filter_invalid_coordinates(self):
        """Points with out-of-range coordinates must be skipped."""
        points = [
            {"lat": 999.0, "long": 101.0, "device_date_time": _ts(0), "accuracy": 5},
            _point(3.0000, 101.0000, 5),
            _point(3.0090, 101.0000, 10),
        ]
        m = calculate_travel_metrics(points, _SETTINGS)
        self.assertEqual(m.raw_data_count, 3)
        # 2 valid points → 1 segment
        self.assertGreater(m.total_distance_km, 0.0)

    def test_duplicate_points_removed(self):
        """Exact duplicate (lat, lon, ts) triples must be deduplicated."""
        p = _point(3.0000, 101.0000, 0)
        points = [p, p, _point(3.0090, 101.0000, 10)]
        m = calculate_travel_metrics(points, _SETTINGS)
        self.assertEqual(m.raw_data_count, 3)
        # After dedup: 2 unique points → 1 segment
        self.assertGreater(m.total_distance_km, 0.0)

    def test_out_of_order_points_handled(self):
        """Out-of-order timestamps after sort must not produce negative elapsed."""
        points = [
            _point(3.0090, 101.0000, 10),  # later point first in list
            _point(3.0000, 101.0000, 0),   # earlier point second
        ]
        m = calculate_travel_metrics(points, _SETTINGS)
        # Should process normally after sort
        self.assertGreater(m.total_distance_km, 0.0)
        self.assertGreater(m.total_travel_seconds, 0.0)


# ===========================================================================
# TravelMetrics property tests
# ===========================================================================

class TestTravelMetricsProperties(unittest.TestCase):

    def test_travel_time_zero_seconds(self):
        m = TravelMetrics()
        self.assertEqual(m.total_travel_time, "00:00:00")

    def test_average_speed_zero_time(self):
        m = TravelMetrics(total_distance_km=10.0, total_travel_seconds=0.0)
        self.assertEqual(m.average_speed_kmh, 0.0)

    def test_average_speed_correct(self):
        # 10 km in 1 hour = 10 km/h
        m = TravelMetrics(total_distance_km=10.0, total_travel_seconds=3600.0)
        self.assertEqual(m.average_speed_kmh, 10.0)

    def test_rounded_distance(self):
        m = TravelMetrics(total_distance_km=1.23456789)
        self.assertEqual(m.total_distance_km_rounded, 1.235)


# ===========================================================================
# SettingsSnapshot defaults test
# ===========================================================================

class TestSettingsSnapshotDefaults(unittest.TestCase):

    def test_default_values(self):
        s = SettingsSnapshot()
        self.assertEqual(s.max_speed_kmh, 120.0)
        self.assertEqual(s.min_distance_meters, 10.0)
        self.assertEqual(s.max_accuracy_meters, 50.0)
        self.assertEqual(s.session_gap_seconds, 900)
        self.assertFalse(s.enable_debug_logging)


if __name__ == "__main__":
    unittest.main()
