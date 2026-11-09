"""Purchases, sales, payments, journal entries and projects for the demo company."""

import frappe
from frappe.utils import add_days, add_months, flt, get_last_day, getdate

from frappe_ticktix.demo.masters import GOODS
from frappe_ticktix.demo.utils import COMPANY, abbr, fiscal_start, make, month_starts, record, rng, step, today

WH = abbr("Stores")
CC = abbr("Main")

# customer -> list of (item_code, monthly rate, every_n_months)
CONTRACTS = {
	"Orchid Tech Park": [("SVC-HK", 185000, 1), ("SVC-SEC", 240000, 1), ("SVC-AMC", 60000, 1)],
	"Sunrise Multispeciality Hospital": [("SVC-HK", 220000, 1), ("SVC-SEC", 175000, 1), ("SVC-PEST", 18000, 3)],
	"Greenfield International School": [("SVC-HK", 95000, 1), ("SVC-GRDN", 22000, 1), ("SVC-CNTN", 130000, 1)],
	"Metro Square Mall": [("SVC-HK", 310000, 1), ("SVC-SEC", 280000, 1), ("SVC-AMC", 90000, 1)],
	"Apex Logistics Hub": [("SVC-SEC", 150000, 1), ("SVC-PEST", 15000, 3)],
	"Lakeview Residents Welfare Association": [("SVC-HK", 65000, 1), ("SVC-GRDN", 18000, 1)],
}

# Customers that pay slowly, so ageing reports have something to show
SLOW_PAYERS = {"Metro Square Mall", "Apex Logistics Hub"}

PURCHASES = [
	# supplier, month index, [(item, qty)]
	("CleanPro Chemicals", "monthly", [("CON-FLR", 40), ("CON-TLT", 40), ("CON-GLS", 30), ("CON-SAN", 25), ("CON-BAG", 60), ("CON-CLT", 20), ("CON-FRSH", 25)]),
	("SparkEquip Traders", 0, [("EQP-SCRB", 3), ("EQP-VAC", 2), ("CON-MOP", 25)]),
	("UniformKart Textiles", 0, [("UNI-SET", 40)]),
	("UniformKart Textiles", 4, [("UNI-SET", 15)]),
]


def run():
	step("opening capital", opening_capital)
	step("purchases", create_purchases)
	step("sales invoices (services)", create_service_invoices)
	step("sales invoices (supplies)", create_supply_invoices)
	step("quotations & orders", create_quotes_and_orders)
	step("expense journals", create_expenses)
	step("payroll payments", create_salary_payments)
	step("projects & tasks", create_projects)


def _clip(d):
	d = getdate(d)
	return min(d, getdate(today()))


def opening_capital():
	make(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": COMPANY,
			"posting_date": fiscal_start(),
			"user_remark": "Opening capital infused by promoters",
			"accounts": [
				{"account": abbr("Cash"), "debit_in_account_currency": 6000000, "cost_center": CC},
				{"account": abbr("Shareholders Funds"), "credit_in_account_currency": 6000000, "cost_center": CC},
			],
		},
		filters={"company": COMPANY, "user_remark": "Opening capital infused by promoters"},
		submit=True,
	)


def _tax(account, desc="GST 18%"):
	return {
		"category": "Total",
		"add_deduct_tax": "Add",
		"charge_type": "On Net Total",
		"account_head": account,
		"description": desc,
		"rate": 18,
		"cost_center": CC,
	}


def _pay(doctype, name, date, amount=None):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	# a rerun finds the invoice again; never pay it twice
	if frappe.db.exists("Payment Entry Reference", {"reference_doctype": doctype, "reference_name": name, "docstatus": 1}):
		return None
	if flt(frappe.db.get_value(doctype, name, "outstanding_amount")) <= 0:
		return None

	pe = get_payment_entry(doctype, name, party_amount=amount)
	pe.posting_date = _clip(date)
	pe.reference_no = f"TXN{rng.randint(100000, 999999)}"
	pe.reference_date = _clip(date)
	pe.mode_of_payment = "Cash"
	if pe.payment_type == "Receive":
		pe.paid_to = abbr("Cash")
	else:
		pe.paid_from = abbr("Cash")
	pe.flags.ignore_permissions = True
	pe.insert()
	pe.submit()
	record("Payment Entry", pe.name)
	return pe


def create_purchases():
	rates = {code: rate for code, _n, _g, rate, _s in GOODS}
	months = month_starts()
	last_month = months[-1]
	for supplier, when, lines in PURCHASES:
		picks = months if when == "monthly" else [months[when]] if when < len(months) else []
		for m in picks:
			# one bill per supplier per month; the date is random, so match on the month
			if frappe.db.exists(
				"Purchase Invoice",
				{
					"supplier": supplier,
					"company": COMPANY,
					"posting_date": ["between", [m, get_last_day(m)]],
					"docstatus": ["<", 2],
				},
			):
				continue
			date = _clip(add_days(m, rng.randint(2, 9)))
			items = []
			for code, qty in lines:
				factor = rng.uniform(0.95, 1.06)
				items.append(
					{
						"item_code": code,
						"qty": max(1, round(qty * rng.uniform(0.8, 1.2))) if when == "monthly" else qty,
						"rate": round(rates[code] * factor),
						"warehouse": WH,
						"cost_center": CC,
					}
				)
			pi = make(
				{
					"doctype": "Purchase Invoice",
					"supplier": supplier,
					"company": COMPANY,
					"posting_date": date,
					"set_posting_time": 1,
					"bill_no": f"{supplier[:3].upper()}/{date:%y%m%d}/{rng.randint(100, 999)}",
					"bill_date": date,
					"due_date": add_days(date, 30),
					"update_stock": 1,
					"set_warehouse": WH,
					"items": items,
					"taxes": [_tax(abbr("Input GST"))],
				},
				submit=True,
			)
			# pay everything except the latest month's bills
			if m != last_month:
				_pay("Purchase Invoice", pi.name, add_days(date, rng.randint(12, 28)))


def create_service_invoices():
	months = month_starts()
	for ci, (customer, lines) in enumerate(CONTRACTS.items()):
		for mi, m in enumerate(months):
			month_end = get_last_day(m)
			if getdate(month_end) > getdate(today()):
				continue  # bill only completed months
			items = []
			for code, rate, every in lines:
				if mi % every:
					continue
				items.append(
					{
						"item_code": code,
						"qty": 1,
						"rate": round(rate * (1 + 0.005 * mi)) if code != "SVC-PEST" else rate,
						"income_account": abbr("Service"),
						"cost_center": CC,
						"description": f"{frappe.db.get_value('Item', code, 'item_name')} for {m:%B %Y}",
					}
				)
			if not items:
				continue
			posting = getdate(month_end)
			si = make(
				{
					"doctype": "Sales Invoice",
					"customer": customer,
					"company": COMPANY,
					"posting_date": posting,
					"set_posting_time": 1,
					"due_date": add_days(posting, 30),
					"items": items,
					"taxes": [_tax(abbr("Output GST"))],
				},
				filters={"customer": customer, "posting_date": posting, "company": COMPANY, "docstatus": ["<", 2], "update_stock": 0},
				submit=True,
			)

			age_days = (getdate(today()) - posting).days
			if customer in SLOW_PAYERS:
				# pay only invoices older than ~75 days, and leave one overdue
				if age_days > 75 and mi % 4 != 3:
					_pay("Sales Invoice", si.name, add_days(posting, rng.randint(55, 70)))
				elif age_days > 75:
					_pay("Sales Invoice", si.name, add_days(posting, 62), amount=flt(si.grand_total) * 0.6)
			else:
				if age_days > 40:
					_pay("Sales Invoice", si.name, add_days(posting, rng.randint(14, 38)))
				elif age_days > 20 and ci % 2 == 0:
					_pay("Sales Invoice", si.name, add_days(posting, rng.randint(16, 20)), amount=flt(si.grand_total) * 0.5)


def create_supply_invoices():
	"""Sell consumables to two customers so stock moves out as well as in."""
	months = month_starts()
	for customer in ("Greenfield International School", "Lakeview Residents Welfare Association"):
		for mi, m in enumerate(months):
			if mi < 2 or mi % 2:
				continue
			posting = _clip(add_days(m, 18))
			items = []
			for code, qty in (("CON-FLR", 6), ("CON-SAN", 10), ("CON-BAG", 8)):
				std = frappe.db.get_value("Item", code, "standard_rate")
				items.append({"item_code": code, "qty": qty, "rate": std, "warehouse": WH, "cost_center": CC, "income_account": abbr("Sales")})
			si = make(
				{
					"doctype": "Sales Invoice",
					"customer": customer,
					"company": COMPANY,
					"posting_date": posting,
					"set_posting_time": 1,
					"due_date": add_days(posting, 15),
					"update_stock": 1,
					"set_warehouse": WH,
					"items": items,
					"taxes": [_tax(abbr("Output GST"))],
				},
				filters={"customer": customer, "posting_date": posting, "company": COMPANY, "docstatus": ["<", 2], "update_stock": 1},
				submit=True,
			)
			if (getdate(today()) - getdate(posting)).days > 30:
				_pay("Sales Invoice", si.name, add_days(posting, rng.randint(7, 14)))


def create_quotes_and_orders():
	from erpnext.selling.doctype.quotation.quotation import _make_sales_order

	specs = [
		("Orchid Tech Park", [("SVC-GRDN", 25000), ("SVC-PEST", 20000)], True, -40),
		("Sunrise Multispeciality Hospital", [("SVC-CNTN", 160000)], True, -25),
		("Apex Logistics Hub", [("SVC-HK", 90000)], False, -10),
		("Metro Square Mall", [("SVC-GRDN", 40000), ("SVC-PEST", 28000)], False, -4),
	]
	for customer, lines, ordered, offset in specs:
		date = _clip(add_days(today(), offset))
		q = make(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": customer,
				"company": COMPANY,
				"transaction_date": date,
				"valid_till": add_days(date, 30),
				"order_type": "Sales",
				"items": [{"item_code": c, "qty": 1, "rate": r, "cost_center": CC} for c, r in lines],
				"taxes": [_tax(abbr("Output GST"))],
			},
			filters={"party_name": customer, "transaction_date": date, "company": COMPANY},
			submit=True,
		)
		if ordered and not frappe.db.exists("Sales Order Item", {"prevdoc_docname": q.name}):
			so = _make_sales_order(q.name)
			so.transaction_date = _clip(add_days(date, 3))
			so.delivery_date = add_days(so.transaction_date, 20)
			for it in so.items:
				it.delivery_date = so.delivery_date
			so.flags.ignore_permissions = True
			so.insert()
			so.submit()
			record("Sales Order", so.name)


def create_expenses():
	for mi, m in enumerate(month_starts()):
		date = _clip(add_days(m, 4))
		for account, label, amount in (
			("Office Rent", "Office rent", 85000),
			("Utility Expenses", "Electricity & water", 18000 + rng.randint(-2500, 3500)),
			("Telephone Expenses", "Telephone & internet", 6500),
		):
			remark = f"{label} - {m:%b %Y}"
			make(
				{
					"doctype": "Journal Entry",
					"voucher_type": "Journal Entry",
					"company": COMPANY,
					"posting_date": date,
					"user_remark": remark,
					"accounts": [
						{"account": abbr(account), "debit_in_account_currency": amount, "cost_center": CC},
						{"account": abbr("Cash"), "credit_in_account_currency": amount},
					],
				},
				filters={"company": COMPANY, "user_remark": remark},
				submit=True,
			)


def create_salary_payments():
	rows = frappe.db.sql(
		"""select start_date, sum(net_pay) from `tabSalary Slip`
		where company=%s and docstatus=1 group by start_date order by start_date""",
		COMPANY,
	)
	# leave the most recent month unpaid so payables show a live balance
	for start, total in rows[:-1]:
		remark = f"Salary disbursement - {getdate(start):%b %Y}"
		date = _clip(add_days(get_last_day(start), 3))
		make(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Cash Entry",
				"company": COMPANY,
				"posting_date": date,
				"user_remark": remark,
				"accounts": [
					{"account": abbr("Payroll Payable"), "debit_in_account_currency": flt(total), "cost_center": CC},
					{"account": abbr("Cash"), "credit_in_account_currency": flt(total)},
				],
			},
			filters={"company": COMPANY, "user_remark": remark},
			submit=True,
		)


def create_projects():
	sites = {
		"Orchid Tech Park": "Tower A & B Facility Operations",
		"Sunrise Multispeciality Hospital": "Hospital Housekeeping & Hygiene Programme",
		"Greenfield International School": "Campus Services Rollout",
		"Metro Square Mall": "Mall Operations & Security",
		"Apex Logistics Hub": "Warehouse Security & Pest Control",
		"Lakeview Residents Welfare Association": "Residential Maintenance Contract",
	}
	tasks = [
		("Site survey and manpower plan", "Completed", "High", -150),
		("Staff deployment and induction", "Completed", "High", -135),
		("Consumables stocking", "Completed", "Medium", -120),
		("Monthly audit & quality inspection", "Working", "Medium", -10),
		("Client review meeting", "Open", "Low", 10),
	]
	for customer, name in sites.items():
		start = fiscal_start()
		p = make(
			{
				"doctype": "Project",
				"project_name": name,
				"company": COMPANY,
				"customer": customer,
				"status": "Open",
				"expected_start_date": add_days(start, 10),
				"expected_end_date": add_days(start, 350),
				"priority": "Medium",
				"cost_center": CC,
			},
			filters={"project_name": name, "company": COMPANY},
		)
		for subject, status, prio, offset in tasks:
			make(
				{
					"doctype": "Task",
					"subject": subject,
					"project": p.name,
					"company": COMPANY,
					"status": status,
					"priority": prio,
					"exp_start_date": add_days(today(), offset),
					"exp_end_date": add_days(today(), offset + 6),
				},
				filters={"subject": subject, "project": p.name},
			)


def dedupe_purchases():
	"""Keep the first purchase invoice per supplier per month; cancel and delete the rest
	(with their payments). Needed once, after reruns created month duplicates."""
	rows = frappe.get_all(
		"Purchase Invoice",
		filters={"company": COMPANY, "docstatus": 1},
		fields=["name", "supplier", "posting_date"],
		order_by="name asc",
	)
	seen, extras = set(), []
	for r in rows:
		key = (r.supplier, r.posting_date.year, r.posting_date.month)
		if key in seen:
			extras.append(r.name)
		seen.add(key)

	for pi in extras:
		for pe in frappe.get_all(
			"Payment Entry Reference",
			filters={"reference_doctype": "Purchase Invoice", "reference_name": pi, "docstatus": 1},
			pluck="parent",
		):
			doc = frappe.get_doc("Payment Entry", pe)
			doc.flags.ignore_permissions = True
			doc.cancel()
			frappe.delete_doc("Payment Entry", pe, force=True, ignore_permissions=True)
		doc = frappe.get_doc("Purchase Invoice", pi)
		doc.flags.ignore_permissions = True
		doc.cancel()
		frappe.delete_doc("Purchase Invoice", pi, force=True, ignore_permissions=True)
		frappe.db.commit()
	print(f"removed {len(extras)} duplicate purchase invoices")
