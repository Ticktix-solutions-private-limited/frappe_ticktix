# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class DailyTravelSummary(Document):
    """Stores one processed travel summary per employee per calendar date.

    Uniqueness is enforced via before_save so no two records share the same
    (employee, summary_date) pair.  The processing service uses upsert logic
    and never relies on this hook for its own writes — the hook is a
    last-resort guard against accidental UI duplicates.
    """

    def before_save(self) -> None:
        self._enforce_unique_employee_date()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enforce_unique_employee_date(self) -> None:
        """Raise if another record already exists for this (employee, date)."""
        if not self.employee or not self.summary_date:
            return

        existing = frappe.db.get_value(
            "Daily Travel Summary",
            filters={
                "employee": self.employee,
                "summary_date": self.summary_date,
            },
            fieldname="name",
        )

        if existing and existing != self.name:
            frappe.throw(
                _(
                    "A Daily Travel Summary for employee {0} on {1} already exists "
                    "({2}). Delete or reprocess the existing record."
                ).format(
                    frappe.bold(self.employee),
                    frappe.bold(str(self.summary_date)),
                    frappe.bold(existing),
                ),
                frappe.DuplicateEntryError,
            )
