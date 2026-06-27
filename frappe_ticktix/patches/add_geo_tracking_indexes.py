# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt
"""One-time migration: add performance indexes for the geo travel system.

Indexes created
---------------
On ``tabLive GEO Tracking V2`` (raw GPS table):
  idx_geo_emp_date   — (employee, captured_at)   PRIMARY processing query
  idx_geo_date       — (captured_at)              Scheduler DISTINCT employee query
  idx_geo_batch      — (batch_id)                 Ingestion deduplication

On ``tabDaily Travel Summary`` (summary table):
  idx_dts_emp_date   — (employee, summary_date)   Upsert checks + API queries

Each index creation is wrapped in its own try/except so a duplicate-index
error on a re-run of this patch does not abort the entire migration.
"""

from __future__ import annotations

import frappe


# Map: (table_name, index_name, [column, ...])
_INDEXES = [
    # Raw GPS table
    (
        "tabLive GEO Tracking V2",
        "idx_geo_emp_date",
        ["employee", "captured_at"],
    ),
    (
        "tabLive GEO Tracking V2",
        "idx_geo_date",
        ["captured_at"],
    ),
    (
        "tabLive GEO Tracking V2",
        "idx_geo_batch",
        ["batch_id"],
    ),
    # Summary table
    (
        "tabDaily Travel Summary",
        "idx_dts_emp_date",
        ["employee", "summary_date"],
    ),
]


def execute() -> None:
    """Entry point called by Frappe's patch runner."""
    for table, index_name, columns in _INDEXES:
        _safe_add_index(table, index_name, columns)

    frappe.db.commit()
    frappe.logger("geo_tracking").info(
        "[Patch] add_geo_tracking_indexes: all indexes applied."
    )


def _safe_add_index(table: str, index_name: str, columns: list[str]) -> None:
    """Add an index, silently skipping if it already exists."""
    try:
        # Check whether the index already exists in the information schema
        existing = frappe.db.sql(
            """
            SELECT COUNT(*)
            FROM   information_schema.statistics
            WHERE  table_schema = DATABASE()
              AND  table_name   = %s
              AND  index_name   = %s
            """,
            (table, index_name),
        )
        if existing and existing[0][0] > 0:
            frappe.logger("geo_tracking").info(
                f"[Patch] Index {index_name} on {table} already exists — skipping."
            )
            return

        col_list = ", ".join(f"`{c}`" for c in columns)
        frappe.db.sql(
            f"CREATE INDEX `{index_name}` ON `{table}` ({col_list})"
        )
        frappe.logger("geo_tracking").info(
            f"[Patch] Created index {index_name} on {table} ({col_list})."
        )
    except Exception as exc:  # noqa: BLE001
        # Log but do not re-raise — allow other indexes to proceed
        frappe.logger("geo_tracking").warning(
            f"[Patch] Could not create index {index_name} on {table}: {exc}"
        )
