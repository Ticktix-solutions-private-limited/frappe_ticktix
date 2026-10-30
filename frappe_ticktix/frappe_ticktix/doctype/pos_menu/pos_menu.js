// Copyright (c) 2026, Ticktix Solutions private limited and contributors
// For license information, please see license.txt

// End Time for a section is only mandatory once the user has actually added
// food items to that section's table. mandatory_depends_on in pos_menu.json
// (and clear_time_for_empty_sections in pos_menu.py) already enforce this on
// save, but two things need help on the client:
//   1. The red "required" indicator only re-evaluates on form refresh — it
//      doesn't react to grid row add/remove on its own.
//   2. Frappe auto-fills every "Time" field with the current time the moment
//      a new document is created (frappe.model.create_new), so on a brand
//      new POS Menu every start/end time already shows "now" even though
//      nothing has been added yet. We clear that stray value for any
//      section that has no items so the form matches what will actually be
//      saved.
// This script keeps both in sync live as rows change.

const POS_MENU_SECTION_MAP = {
	breakfastmenulines: { start: "breakfaststarttime", end: "breakfastendtime" },
	lunchmealsmenulines: { start: "lunchmealsstarttime", end: "lunchmealsendtime" },
	lunchothermenulines: { start: "lunchotherstarttime", end: "lunchotherendtime" },
	snacksmenulines: { start: "snacksstarttime", end: "snacksendtime" },
	dinnermenulines: { start: "dinnerstarttime", end: "dinnerendtime" },
};

function pos_menu_sync_sections(frm) {
	Object.entries(POS_MENU_SECTION_MAP).forEach(([table_field, { start, end }]) => {
		const has_items = (frm.doc[table_field] || []).length > 0;

		frm.toggle_reqd(end, has_items);

		if (!has_items) {
			// Clear the auto-filled "now" default so an untouched section
			// doesn't show a stray time before the user has added anything.
			if (frm.doc[start]) frm.set_value(start, "");
			if (frm.doc[end]) frm.set_value(end, "");
		}

		frm.refresh_field(start);
		frm.refresh_field(end);
	});
}

frappe.ui.form.on("POS Menu", {
	refresh: pos_menu_sync_sections,
	breakfastmenulines_add: pos_menu_sync_sections,
	breakfastmenulines_remove: pos_menu_sync_sections,
	lunchmealsmenulines_add: pos_menu_sync_sections,
	lunchmealsmenulines_remove: pos_menu_sync_sections,
	lunchothermenulines_add: pos_menu_sync_sections,
	lunchothermenulines_remove: pos_menu_sync_sections,
	snacksmenulines_add: pos_menu_sync_sections,
	snacksmenulines_remove: pos_menu_sync_sections,
	dinnermenulines_add: pos_menu_sync_sections,
	dinnermenulines_remove: pos_menu_sync_sections,
});
