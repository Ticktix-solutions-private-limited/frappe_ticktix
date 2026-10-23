# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt
"""Integration-style tests for the geo_processing orchestration layer.

These tests mock Frappe DB calls so they do NOT require a live Frappe
instance or database.  Run with:

    cd apps/frappe_ticktix
    python -m pytest frappe_ticktix/tests/test_geo_processing.py -v

Design: we patch ``frappe.db`` and related functions with unittest.mock
so the business logic paths (idempotency, status-gate, upsert, error
handling) are exercised without real DB I/O.
"""

from __future__ import annotations

import unittest
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, call

from frappe_ticktix.services.distance_calculator import SettingsSnapshot, TravelMetrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw_point(lat: float, lon: float, minutes_offset: int) -> Dict[str, Any]:
    base = datetime(2026, 1, 15, 8, 0, 0)
    from datetime import timedelta
    ts = (base + timedelta(minutes=minutes_offset)).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "name": f"GEO-{minutes_offset:04d}",
        "employee": "EMP-0001",
        "device_date_time": ts,
        "lat": lat,
        "long": lon,
        "accuracy": 5.0,
        "speed": None,
        "heading": None,
        "altitude": None,
        "source": "background",
    }


_SAMPLE_POINTS = [
    _make_raw_point(3.0000, 101.0000, 0),
    _make_raw_point(3.0090, 101.0000, 10),  # ~1 km apart, 10 min gap
    _make_raw_point(3.0180, 101.0000, 20),  # another ~1 km, 10 min gap
]

_DEFAULT_SETTINGS = SettingsSnapshot()

_DATE_STR = "2026-01-15"


# ===========================================================================
# distance_calculator integration (pure, no mock needed)
# ===========================================================================

class TestCalculateMetricsIntegration(unittest.TestCase):
    """End-to-end calculation test using realistic fixture data."""

    def test_three_points_two_segments(self):
        from frappe_ticktix.services.distance_calculator import calculate_travel_metrics
        m = calculate_travel_metrics(_SAMPLE_POINTS, _DEFAULT_SETTINGS)
        self.assertAlmostEqual(m.total_distance_km, 2.0, delta=0.1)
        self.assertEqual(m.total_travel_seconds, 1200.0)  # 20 minutes
        self.assertEqual(m.raw_data_count, 3)

    def test_all_filtered_returns_zero(self):
        from frappe_ticktix.services.distance_calculator import calculate_travel_metrics
        # Points with very poor accuracy — all skipped
        pts = [
            {**_make_raw_point(3.0, 101.0, 0), "accuracy": 200.0},
            {**_make_raw_point(3.0, 101.0, 10), "accuracy": 200.0},
        ]
        m = calculate_travel_metrics(pts, _DEFAULT_SETTINGS)
        self.assertEqual(m.total_distance_km, 0.0)
        self.assertEqual(m.total_points, 0)


# ===========================================================================
# Idempotency / status-gate tests (mocked Frappe)
# ===========================================================================

class TestIdempotencyGate(unittest.TestCase):
    """Verify the status-gate prevents duplicate processing."""

    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_skip_when_already_completed(self, mock_frappe):
        """An (employee, date) with status=Completed must be skipped."""
        from frappe_ticktix.services.geo_processing import _process_employee

        # Simulate existing Completed record
        mock_frappe.db.get_value.return_value = {
            "name": "DTS-0001",
            "status": "Completed",
            "processed_at": datetime(2026, 1, 15, 22, 5, 0),
        }

        result = _process_employee("EMP-0001", _DATE_STR, _DEFAULT_SETTINGS, force=False)
        self.assertEqual(result, "skipped")
        # Ensure no write was attempted
        mock_frappe.get_doc.assert_not_called()
        mock_frappe.new_doc.assert_not_called()

    @patch("frappe_ticktix.services.geo_processing.now_datetime")
    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_force_overrides_completed(self, mock_frappe, mock_now):
        """force=True must reprocess even if status=Completed."""
        from frappe_ticktix.services.geo_processing import _process_employee

        mock_now.return_value = datetime(2026, 1, 15, 22, 10, 0)

        # Existing Completed record
        mock_frappe.db.get_value.return_value = {
            "name": "DTS-0001",
            "status": "Completed",
            "processed_at": datetime(2026, 1, 15, 22, 5, 0),
        }

        # DB fetch returns empty points (avoid actual calculation)
        mock_frappe.db.get_all.return_value = []

        # get_doc returns a mock doc
        mock_doc = MagicMock()
        mock_doc.name = "DTS-0001"
        mock_frappe.get_doc.return_value = mock_doc

        result = _process_employee("EMP-0001", _DATE_STR, _DEFAULT_SETTINGS, force=True)
        # Should proceed (not skipped)
        self.assertEqual(result, "processed")

    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_skip_non_stale_processing(self, mock_frappe):
        """A recent Processing record (< 2 h old) must be skipped (active worker lock)."""
        from frappe_ticktix.services.geo_processing import _process_employee

        # Processing record started 30 min ago (not stale)
        recent = datetime.now().replace(microsecond=0)
        from datetime import timedelta
        recent = datetime.now() - timedelta(minutes=30)

        mock_frappe.db.get_value.return_value = {
            "name": "DTS-0002",
            "status": "Processing",
            "processed_at": recent,
        }

        result = _process_employee("EMP-0001", _DATE_STR, _DEFAULT_SETTINGS, force=False)
        self.assertEqual(result, "skipped")

    @patch("frappe_ticktix.services.geo_processing.now_datetime")
    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_reprocess_stale_processing(self, mock_frappe, mock_now):
        """A Processing record older than 2 h must be treated as stale and reprocessed."""
        from frappe_ticktix.services.geo_processing import _process_employee
        from datetime import timedelta

        mock_now.return_value = datetime(2026, 1, 15, 22, 10, 0)

        stale = datetime.now() - timedelta(hours=3)
        mock_frappe.db.get_value.return_value = {
            "name": "DTS-0003",
            "status": "Processing",
            "processed_at": stale,
        }

        # Return empty points so _process_employee can complete
        mock_frappe.db.get_all.return_value = []

        mock_doc = MagicMock()
        mock_doc.name = "DTS-0003"
        mock_frappe.get_doc.return_value = mock_doc

        result = _process_employee("EMP-0001", _DATE_STR, _DEFAULT_SETTINGS, force=False)
        self.assertEqual(result, "processed")


# ===========================================================================
# _get_distinct_employees_for_date (mocked)
# ===========================================================================

class TestGetDistinctEmployees(unittest.TestCase):

    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_returns_list_of_employee_ids(self, mock_frappe):
        from frappe_ticktix.services.geo_processing import _get_distinct_employees_for_date

        mock_frappe.db.sql.return_value = [
            ["EMP-0001"],
            ["EMP-0002"],
            ["EMP-0003"],
        ]

        result = _get_distinct_employees_for_date("2026-01-15")
        self.assertEqual(result, ["EMP-0001", "EMP-0002", "EMP-0003"])

    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_returns_empty_list_when_no_data(self, mock_frappe):
        from frappe_ticktix.services.geo_processing import _get_distinct_employees_for_date

        mock_frappe.db.sql.return_value = []
        result = _get_distinct_employees_for_date("2026-01-15")
        self.assertEqual(result, [])


# ===========================================================================
# _upsert_summary (mocked)
# ===========================================================================

class TestUpsertSummary(unittest.TestCase):

    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_insert_when_no_existing(self, mock_frappe):
        """When existing_name is None, a new doc should be created."""
        from frappe_ticktix.services.geo_processing import _upsert_summary

        mock_doc = MagicMock()
        mock_doc.name = "DTS-NEW-001"
        mock_frappe.new_doc.return_value = mock_doc

        metrics = TravelMetrics(
            total_distance_km=5.123,
            total_travel_seconds=3600,
            total_points=50,
            raw_data_count=60,
        )

        name = _upsert_summary(
            employee="EMP-0001",
            date_str=_DATE_STR,
            existing_name=None,
            status="Completed",
            processed_at=datetime(2026, 1, 15, 22, 5),
            metrics=metrics,
            error_log=None,
        )

        mock_frappe.new_doc.assert_called_once_with("Daily Travel Summary")
        mock_doc.save.assert_called_once()
        mock_frappe.db.commit.assert_called_once()

    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_update_when_existing(self, mock_frappe):
        """When existing_name is set, the existing doc should be fetched and saved."""
        from frappe_ticktix.services.geo_processing import _upsert_summary

        mock_doc = MagicMock()
        mock_doc.name = "DTS-EXIST-001"
        mock_frappe.get_doc.return_value = mock_doc

        _upsert_summary(
            employee="EMP-0001",
            date_str=_DATE_STR,
            existing_name="DTS-EXIST-001",
            status="Completed",
            processed_at=datetime(2026, 1, 15, 22, 5),
            metrics=None,
            error_log=None,
        )

        mock_frappe.get_doc.assert_called_once_with("Daily Travel Summary", "DTS-EXIST-001")
        mock_doc.save.assert_called_once()


# ===========================================================================
# run_daily_travel_summary (full orchestration, mocked)
# ===========================================================================

class TestRunDailyTravelSummary(unittest.TestCase):

    @patch("frappe_ticktix.services.geo_processing._process_employee")
    @patch("frappe_ticktix.services.geo_processing._get_distinct_employees_for_date")
    @patch("frappe_ticktix.services.geo_processing._load_settings")
    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_processes_all_employees(
        self,
        mock_frappe,
        mock_load_settings,
        mock_get_employees,
        mock_process,
    ):
        from frappe_ticktix.services.geo_processing import run_daily_travel_summary

        mock_load_settings.return_value = _DEFAULT_SETTINGS
        mock_get_employees.return_value = ["EMP-0001", "EMP-0002"]
        mock_process.return_value = "processed"

        result = run_daily_travel_summary("2026-01-15")

        self.assertEqual(result["employees_processed"], 2)
        self.assertEqual(result["employees_skipped"], 0)
        self.assertEqual(result["employees_failed"], 0)

    @patch("frappe_ticktix.services.geo_processing._process_employee")
    @patch("frappe_ticktix.services.geo_processing._get_distinct_employees_for_date")
    @patch("frappe_ticktix.services.geo_processing._load_settings")
    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_continues_after_single_employee_failure(
        self,
        mock_frappe,
        mock_load_settings,
        mock_get_employees,
        mock_process,
    ):
        """One employee failure must not abort the rest of the batch."""
        from frappe_ticktix.services.geo_processing import run_daily_travel_summary

        mock_load_settings.return_value = _DEFAULT_SETTINGS
        mock_get_employees.return_value = ["EMP-0001", "EMP-0002", "EMP-0003"]

        def side_effect(emp, *args, **kwargs):
            if emp == "EMP-0002":
                raise RuntimeError("Simulated DB error")
            return "processed"

        mock_process.side_effect = side_effect

        result = run_daily_travel_summary("2026-01-15")

        self.assertEqual(result["employees_processed"], 2)  # EMP-0001, EMP-0003
        self.assertEqual(result["employees_failed"], 1)     # EMP-0002

    @patch("frappe_ticktix.services.geo_processing._process_employee")
    @patch("frappe_ticktix.services.geo_processing._get_distinct_employees_for_date")
    @patch("frappe_ticktix.services.geo_processing._load_settings")
    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_counts_skipped_correctly(
        self,
        mock_frappe,
        mock_load_settings,
        mock_get_employees,
        mock_process,
    ):
        from frappe_ticktix.services.geo_processing import run_daily_travel_summary

        mock_load_settings.return_value = _DEFAULT_SETTINGS
        mock_get_employees.return_value = ["EMP-0001", "EMP-0002"]
        mock_process.return_value = "skipped"

        result = run_daily_travel_summary("2026-01-15")

        self.assertEqual(result["employees_skipped"], 2)
        self.assertEqual(result["employees_processed"], 0)

    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_invalid_date_throws(self, mock_frappe):
        from frappe_ticktix.services.geo_processing import run_daily_travel_summary

        mock_frappe.throw.side_effect = Exception("Invalid date")
        with self.assertRaises(Exception):
            run_daily_travel_summary("not-a-date")


# ===========================================================================
# Concurrent lock behaviour (idempotency stress tests)
# ===========================================================================

class TestConcurrentLockBehavior(unittest.TestCase):
    """Verify the distributed lock prevents two workers processing the same record.

    Simulates the scenario where two scheduler workers (or a scheduler +
    a manual API call) start processing the same (employee, date) at nearly
    the same time.  The second worker should detect the active Processing
    record and skip immediately.
    """

    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_second_worker_skips_when_first_holds_active_lock(self, mock_frappe):
        """Worker 2 must skip when Worker 1's Processing record is < 2 h old."""
        from frappe_ticktix.services.geo_processing import _process_employee
        from datetime import timedelta

        # Worker 1 created the Processing record 1 minute ago (very fresh)
        one_minute_ago = datetime.now() - timedelta(minutes=1)
        mock_frappe.db.get_value.return_value = {
            "name": "DTS-LOCK-001",
            "status": "Processing",
            "processed_at": one_minute_ago,
        }

        # Worker 2 must exit without writing anything
        result = _process_employee("EMP-0001", _DATE_STR, _DEFAULT_SETTINGS, force=False)

        self.assertEqual(result, "skipped")
        mock_frappe.get_doc.assert_not_called()
        mock_frappe.new_doc.assert_not_called()

    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_second_run_skips_after_first_completes(self, mock_frappe):
        """A second scheduler run for the same date must skip completed records.

        This is the normal nightly-idempotency path: the job ran at 00:30,
        processed all employees, and if it fires again (manual trigger) it
        must produce zero re-processed records.
        """
        from frappe_ticktix.services.geo_processing import _process_employee

        mock_frappe.db.get_value.return_value = {
            "name": "DTS-DONE-001",
            "status": "Completed",
            "processed_at": datetime(2026, 1, 15, 0, 35, 0),
        }

        result = _process_employee("EMP-0001", _DATE_STR, _DEFAULT_SETTINGS, force=False)

        self.assertEqual(result, "skipped")
        mock_frappe.get_doc.assert_not_called()
        mock_frappe.new_doc.assert_not_called()

    @patch("frappe_ticktix.services.geo_processing.now_datetime")
    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_stale_lock_allows_reprocessing_by_new_worker(self, mock_frappe, mock_now):
        """A lock older than 2 h (crashed worker) must be broken and reprocessed."""
        from frappe_ticktix.services.geo_processing import _process_employee
        from datetime import timedelta

        mock_now.return_value = datetime(2026, 1, 15, 22, 10, 0)

        # Lock is 3 hours old — the original worker clearly crashed
        three_hours_ago = datetime.now() - timedelta(hours=3)
        mock_frappe.db.get_value.return_value = {
            "name": "DTS-STALE-001",
            "status": "Processing",
            "processed_at": three_hours_ago,
        }

        # Return empty GPS points so processing completes quickly
        mock_frappe.db.get_all.return_value = []

        mock_doc = MagicMock()
        mock_doc.name = "DTS-STALE-001"
        mock_frappe.get_doc.return_value = mock_doc

        result = _process_employee("EMP-0001", _DATE_STR, _DEFAULT_SETTINGS, force=False)

        # Must reprocess — not skip
        self.assertEqual(result, "processed")

    @patch("frappe_ticktix.services.geo_processing.frappe")
    def test_force_bypasses_completed_but_not_active_processing(self, mock_frappe):
        """force=True overrides Completed status but respects a fresh Processing lock.

        A fresh Processing record means another worker is active right now.
        Even force=True should not break that lock (only staleness breaks it).
        """
        from frappe_ticktix.services.geo_processing import _process_employee
        from datetime import timedelta

        # Fresh Processing lock (30 min old — well within the 2-h window)
        thirty_min_ago = datetime.now() - timedelta(minutes=30)
        mock_frappe.db.get_value.return_value = {
            "name": "DTS-FRESH-001",
            "status": "Processing",
            "processed_at": thirty_min_ago,
        }

        result = _process_employee("EMP-0001", _DATE_STR, _DEFAULT_SETTINGS, force=True)

        # Must still skip — the active lock takes priority over force
        self.assertEqual(result, "skipped")
        mock_frappe.get_doc.assert_not_called()
        mock_frappe.new_doc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
