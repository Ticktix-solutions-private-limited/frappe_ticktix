"""Demo data for a facility-management business (Facilitix).

Loaded and cleared from TickTix Settings (see demo/api.py). Packs are listed in
demo/packs.py. Never loaded by install or migrate.
"""

import frappe

from frappe_ticktix.demo import utils


def seed_phase(phase):
	frappe.flags.in_demo_seed = True
	frappe.flags.mute_emails = True

	if phase == "masters":
		from frappe_ticktix.demo import masters as m

		utils.step("company", m.create_company)
		utils.step("company defaults", m.tune_company)
		utils.step("uoms", m.create_uoms)
		utils.step("item groups", m.create_item_groups)
		utils.step("items", m.create_items)
		utils.step("price lists & prices", m.create_price_lists_and_prices)
		utils.step("customers", m.create_customers)
		utils.step("suppliers", m.create_suppliers)
		utils.step("hr masters", m.create_hr_masters)
		utils.step("holiday list", m.create_holiday_list)
		utils.step("leave types", m.create_leave_types)
		utils.step("shift types", m.create_shift_types)
	elif phase == "hr":
		from frappe_ticktix.demo import hr

		hr.run()
	elif phase == "transactions":
		from frappe_ticktix.demo import erpnext_txns as t

		t.run()
	elif phase == "crm_support":
		from frappe_ticktix.demo import crm_support as c

		c.run()
	elif phase == "ticktix":
		from frappe_ticktix.demo import ticktix_custom as k

		k.run()
	else:
		frappe.throw(f"Unknown phase {phase}. Choose from masters, hr, transactions, crm_support, ticktix")
