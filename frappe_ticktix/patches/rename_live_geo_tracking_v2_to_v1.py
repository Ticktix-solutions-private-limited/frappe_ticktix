# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt
"""Rename DocType and fields for Live GEO Tracking.

Changes applied
---------------
DocType : "Live GEO Tracking V2"  →  "Live GEO Tracking"
Fields  : latitude    →  lat
          longitude   →  long
          captured_at →  device_date_time

Indexes : drops old indexes that referenced ``captured_at`` and recreates
          them on ``device_date_time`` so the query planner still benefits.

This patch runs in [pre_model_sync] so the rename is complete before Frappe
syncs the new live_geo_tracking.json DocType definition.
"""

from __future__ import annotations

import frappe
from frappe.model.rename_doc import rename_doc


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OLD_DOCTYPE = "Live GEO Tracking V2"
_NEW_DOCTYPE = "Live GEO Tracking"
_OLD_TABLE   = f"tab{_OLD_DOCTYPE}"
_NEW_TABLE   = f"tab{_NEW_DOCTYPE}"

_COLUMN_RENAMES = [
    ("latitude",    "lat",              "DOUBLE"),
    ("longitude",   "long",             "DOUBLE"),
    ("captured_at", "device_date_time", "DATETIME(6)"),
]

# Indexes that referenced old column names — drop before rename, recreate after
_OLD_INDEXES = ["idx_geo_emp_date", "idx_geo_date"]
_NEW_INDEXES = [
    ("idx_geo_emp_date", ["employee", "device_date_time"]),
    ("idx_geo_date",     ["device_date_time"]),
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def execute() -> None:
    log = frappe.logger("geo_tracking")

    # ------------------------------------------------------------------
    # 1. Rename DocType (renames tabDocType record + DB table)
    # ------------------------------------------------------------------
    if frappe.db.exists("DocType", _OLD_DOCTYPE) and not frappe.db.exists("DocType", _NEW_DOCTYPE):
        log.info(f"[Patch] Renaming DocType '{_OLD_DOCTYPE}' → '{_NEW_DOCTYPE}'")
        rename_doc("DocType", _OLD_DOCTYPE, _NEW_DOCTYPE, force=True, ignore_if_exists=True)
        frappe.db.commit()
        log.info("[Patch] DocType rename committed.")
    else:
        log.info(
            f"[Patch] DocType rename skipped "
            f"(old_exists={frappe.db.exists('DocType', _OLD_DOCTYPE)}, "
            f"new_exists={frappe.db.exists('DocType', _NEW_DOCTYPE)})"
        )

    # After this point the table is `tabLive GEO Tracking`.
    # Bail early if the table doesn't exist at all (fresh install).
    if not _table_exists(_NEW_TABLE):
        log.info(f"[Patch] Table {_NEW_TABLE} not found — nothing more to do.")
        return

    # ------------------------------------------------------------------
    # 2. Drop old indexes that reference captured_at before renaming
    # ------------------------------------------------------------------
    for idx in _OLD_INDEXES:
        _drop_index_if_exists(_NEW_TABLE, idx, log)

    # ------------------------------------------------------------------
    # 3. Rename columns
    # ------------------------------------------------------------------
    for old_col, new_col, col_type in _COLUMN_RENAMES:
        _rename_column(_NEW_TABLE, old_col, new_col, col_type, log)

    frappe.db.commit()

    # ------------------------------------------------------------------
    # 4. Recreate indexes on new column names
    # ------------------------------------------------------------------
    for idx_name, columns in _NEW_INDEXES:
        _create_index_if_missing(_NEW_TABLE, idx_name, columns, log)

    frappe.db.commit()
    log.info("[Patch] rename_live_geo_tracking_v2_to_v1 completed.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_exists(table: str) -> bool:
    result = frappe.db.sql(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = %s",
        (table,),
    )
    return bool(result and result[0][0] > 0)


def _column_exists(table: str, column: str) -> bool:
    result = frappe.db.sql(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(result and result[0][0] > 0)


def _index_exists(table: str, index_name: str) -> bool:
    result = frappe.db.sql(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s",
        (table, index_name),
    )
    return bool(result and result[0][0] > 0)


def _drop_index_if_exists(table: str, index_name: str, log) -> None:
    if _index_exists(table, index_name):
        try:
            frappe.db.sql(f"DROP INDEX `{index_name}` ON `{table}`")
            log.info(f"[Patch] Dropped index {index_name} on {table}.")
        except Exception as exc:
            log.warning(f"[Patch] Could not drop index {index_name}: {exc}")
    else:
        log.info(f"[Patch] Index {index_name} not found on {table} — skipping drop.")


def _rename_column(table: str, old_col: str, new_col: str, col_type: str, log) -> None:
    if not _column_exists(table, old_col):
        if _column_exists(table, new_col):
            log.info(f"[Patch] Column {new_col} already exists in {table} — skipping rename.")
        else:
            log.warning(f"[Patch] Neither {old_col} nor {new_col} found in {table} — skipping.")
        return

    try:
        frappe.db.sql(
            f"ALTER TABLE `{table}` CHANGE COLUMN `{old_col}` `{new_col}` {col_type}"
        )
        log.info(f"[Patch] Renamed column {old_col} → {new_col} in {table}.")
    except Exception as exc:
        log.error(f"[Patch] Failed to rename column {old_col} → {new_col}: {exc}")
        raise


def _create_index_if_missing(table: str, index_name: str, columns: list, log) -> None:
    if _index_exists(table, index_name):
        log.info(f"[Patch] Index {index_name} already exists on {table} — skipping.")
        return
    try:
        col_list = ", ".join(f"`{c}`" for c in columns)
        frappe.db.sql(f"CREATE INDEX `{index_name}` ON `{table}` ({col_list})")
        log.info(f"[Patch] Created index {index_name} on {table} ({col_list}).")
    except Exception as exc:
        log.warning(f"[Patch] Could not create index {index_name}: {exc}")
