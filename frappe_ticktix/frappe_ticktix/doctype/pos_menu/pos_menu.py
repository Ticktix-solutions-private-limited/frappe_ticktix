# Copyright (c) 2026, Ticktix Solutions private limited and contributors
# For license information, please see license.txt

from frappe.model.document import Document

# Section: (menu items table field, start time field, end time field)
POS_MENU_SECTIONS = [
	("breakfastmenulines", "breakfaststarttime", "breakfastendtime"),
	("lunchmealsmenulines", "lunchmealsstarttime", "lunchmealsendtime"),
	("lunchothermenulines", "lunchotherstarttime", "lunchotherendtime"),
	("snacksmenulines", "snacksstarttime", "snacksendtime"),
	("dinnermenulines", "dinnerstarttime", "dinnerendtime"),
]


class POSMenu(Document):
	def validate(self):
		self.clear_time_for_empty_sections()

	def clear_time_for_empty_sections(self):
		"""Frappe's core new-doc handling auto-fills every ``Time`` field
		with the current time (frappe.model.create_new.set_dynamic_default_values),
		regardless of whether the section actually has any menu items.

		Only a section that has food items added should carry a start/end
		time — for every other, untouched section, clear out that stray
		auto-filled current-time value so it isn't persisted.
		"""
		for table_field, start_field, end_field in POS_MENU_SECTIONS:
			if not self.get(table_field):
				self.set(start_field, None)
				self.set(end_field, None)
