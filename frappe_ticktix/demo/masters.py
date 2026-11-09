"""Company, items, parties and HR masters for the Facilitix demo story."""

import frappe
from frappe.utils import add_days, getdate

from frappe_ticktix.demo.utils import ABBR, COMPANY, abbr, fiscal_start, make

SERVICES = [
	# code, name, uom
	("SVC-HK", "Housekeeping Service (Monthly)", "Nos"),
	("SVC-SEC", "Security Guard Service (Monthly)", "Nos"),
	("SVC-PEST", "Pest Control Service", "Nos"),
	("SVC-AMC", "Facility Maintenance AMC", "Nos"),
	("SVC-GRDN", "Landscaping & Gardening Service", "Nos"),
	("SVC-CNTN", "Canteen Management Service", "Nos"),
]

# code, name, group, buy rate, stock?
GOODS = [
	("CON-FLR", "Floor Cleaner 5L", "Consumable", 320, 1),
	("CON-TLT", "Toilet Cleaner 1L", "Consumable", 135, 1),
	("CON-GLS", "Glass Cleaner 500ml", "Consumable", 95, 1),
	("CON-SAN", "Hand Sanitizer 500ml", "Consumable", 180, 1),
	("CON-BAG", "Garbage Bags (Pack of 30)", "Consumable", 210, 1),
	("CON-CLT", "Microfiber Cloth (Pack of 5)", "Consumable", 250, 1),
	("CON-MOP", "Mop Set with Bucket", "Consumable", 780, 1),
	("CON-FRSH", "Air Freshener Refill", "Consumable", 165, 1),
	("EQP-SCRB", "Floor Scrubber Machine", "Products", 58000, 1),
	("EQP-VAC", "Industrial Vacuum Cleaner", "Products", 24500, 1),
	("UNI-SET", "Staff Uniform Set", "Consumable", 1150, 1),
]

FOOD = [
	("FD-IDLI", "Idli Sambar (2 pcs)", 35),
	("FD-DOSA", "Masala Dosa", 60),
	("FD-MEAL", "Veg Meals", 90),
	("FD-BRYN", "Chicken Biryani", 140),
	("FD-CHAP", "Chapati Combo", 85),
	("FD-CURD", "Curd Rice", 55),
	("FD-SMSA", "Samosa (2 pcs)", 30),
	("FD-COFE", "Filter Coffee", 20),
]

CUSTOMERS = [
	# name, group, city, state, gst
	("Orchid Tech Park", "Commercial", "Chennai", "Tamil Nadu", "33AABCO1234F1Z5"),
	("Sunrise Multispeciality Hospital", "Commercial", "Bengaluru", "Karnataka", "29AABCS5678G1Z2"),
	("Greenfield International School", "Non Profit", "Hyderabad", "Telangana", "36AABTG4321H1Z9"),
	("Metro Square Mall", "Commercial", "Chennai", "Tamil Nadu", "33AABCM8765J1Z1"),
	("Apex Logistics Hub", "Commercial", "Coimbatore", "Tamil Nadu", "33AABCA2468K1Z7"),
	("Lakeview Residents Welfare Association", "Individual", "Chennai", "Tamil Nadu", ""),
]

SUPPLIERS = [
	("CleanPro Chemicals", "Chennai"),
	("SparkEquip Traders", "Bengaluru"),
	("UniformKart Textiles", "Tiruppur"),
	("FreshFarm Foods", "Chennai"),
]

DEPARTMENTS = ["Operations", "Housekeeping", "Security", "Maintenance", "Canteen", "HR & Admin", "Accounts", "Sales"]

DESIGNATIONS = [
	"Operations Manager",
	"Site Manager",
	"Housekeeping Supervisor",
	"Housekeeping Staff",
	"Security Supervisor",
	"Security Guard",
	"Electrician",
	"Plumber",
	"Canteen Chef",
	"Canteen Helper",
	"HR Executive",
	"Accountant",
	"Sales Executive",
]

BRANCHES = ["Chennai", "Bengaluru", "Hyderabad", "Coimbatore"]
STATES = [("Tamil Nadu", "India"), ("Karnataka", "India"), ("Telangana", "India"), ("Kerala", "India"), ("Maharashtra", "India")]


def create_company():
	if frappe.db.exists("Company", COMPANY):
		return frappe.get_doc("Company", COMPANY)

	real = frappe.db.get_value("Company", {"name": ["not like", "\\_Test%"]}, ["chart_of_accounts", "country", "default_currency"], as_dict=True)
	doc = make(
		{
			"doctype": "Company",
			"company_name": COMPANY,
			"abbr": ABBR,
			"default_currency": "INR",
			"country": "India",
			"chart_of_accounts": (real and real.chart_of_accounts) or "India - Chart of Accounts",
			"enable_perpetual_inventory": 1,
		}
	)
	return doc


def tune_company():
	"""Wire up defaults the transactions rely on, and add a GST output account."""
	c = frappe.get_doc("Company", COMPANY)

	if not frappe.db.exists("Account", abbr("Output GST")):
		make(
			{
				"doctype": "Account",
				"account_name": "Output GST",
				"parent_account": abbr("Duties and Taxes"),
				"company": COMPANY,
				"account_type": "Tax",
				"is_group": 0,
			}
		)
	if not frappe.db.exists("Account", abbr("PF & PT Payable")):
		make(
			{
				"doctype": "Account",
				"account_name": "PF & PT Payable",
				"parent_account": abbr("Duties and Taxes"),
				"company": COMPANY,
				"is_group": 0,
			}
		)
	if not frappe.db.exists("Account", abbr("Input GST")):
		make(
			{
				"doctype": "Account",
				"account_name": "Input GST",
				"parent_account": abbr("Duties and Taxes"),
				"company": COMPANY,
				"account_type": "Tax",
				"is_group": 0,
			}
		)

	updates = {}
	for field, account in {
		"default_payroll_payable_account": "Payroll Payable",
		"default_bank_account": None,
	}.items():
		if account and frappe.db.exists("Account", abbr(account)) and not c.get(field):
			updates[field] = abbr(account)
	for field, value in updates.items():
		frappe.db.set_value("Company", COMPANY, field, value)

	return c.name


def create_uoms():
	if not frappe.db.exists("UOM", "Month"):
		make({"doctype": "UOM", "uom_name": "Month"})


def create_item_groups():
	for g in ("Services", "Consumable", "Products", "prepared food"):
		if not frappe.db.exists("Item Group", g):
			make({"doctype": "Item Group", "item_group_name": g, "parent_item_group": "All Item Groups", "is_group": 0})


def create_items():
	for code, name, uom in SERVICES:
		make(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": "Services",
				"stock_uom": uom,
				"is_stock_item": 0,
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"include_item_in_manufacturing": 0,
			},
			filters={"name": code},
		)
	for code, name, group, rate, stock in GOODS:
		make(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": group,
				"stock_uom": "Nos",
				"is_stock_item": stock,
				"valuation_rate": rate,
				"standard_rate": round(rate * 1.25),
				"include_item_in_manufacturing": 0,
			},
			filters={"name": code},
		)
	for code, name, price in FOOD:
		make(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": name,
				"item_group": "prepared food",
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"standard_rate": price,
				"include_item_in_manufacturing": 0,
			},
			filters={"name": code},
		)


def create_price_lists_and_prices():
	for pl, selling, buying in (("Standard Selling", 1, 0), ("Standard Buying", 0, 1)):
		if not frappe.db.exists("Price List", pl):
			make(
				{
					"doctype": "Price List",
					"price_list_name": pl,
					"currency": "INR",
					"selling": selling,
					"buying": buying,
					"enabled": 1,
				}
			)

	for code, name, price in FOOD:
		make(
			{
				"doctype": "Item Price",
				"item_code": code,
				"price_list": "Standard Selling",
				"price_list_rate": price,
				"currency": "INR",
			},
			filters={"item_code": code, "price_list": "Standard Selling"},
		)
	for code, name, group, rate, stock in GOODS:
		make(
			{
				"doctype": "Item Price",
				"item_code": code,
				"price_list": "Standard Buying",
				"price_list_rate": rate,
				"currency": "INR",
			},
			filters={"item_code": code, "price_list": "Standard Buying"},
		)


def create_customers():
	for name, group, city, state, gst in CUSTOMERS:
		cust = make(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Company",
				"customer_group": group,
				"territory": "India",
				"default_currency": "INR",
				"gstin": gst or None,
			},
			filters={"customer_name": name},
		)
		if not frappe.db.exists("Address", {"address_title": name}):
			make(
				{
					"doctype": "Address",
					"address_title": name,
					"address_type": "Billing",
					"address_line1": f"{(len(name) * 7) % 90 + 10}, Main Road",
					"city": city,
					"state": state,
					"country": "India",
					"pincode": "600001",
					"links": [{"link_doctype": "Customer", "link_name": cust.name}],
				},
				filters={"address_title": name},
			)


def create_suppliers():
	group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
	if not group:
		group = make({"doctype": "Supplier Group", "supplier_group_name": "Local", "parent_supplier_group": "All Supplier Groups"}).name
	for name, city in SUPPLIERS:
		make(
			{
				"doctype": "Supplier",
				"supplier_name": name,
				"supplier_group": group,
				"supplier_type": "Company",
				"country": "India",
				"default_currency": "INR",
			},
			filters={"supplier_name": name},
		)


def create_hr_masters():
	for dept in DEPARTMENTS:
		name = abbr(dept)
		if not frappe.db.exists("Department", name):
			make(
				{
					"doctype": "Department",
					"department_name": dept,
					"company": COMPANY,
					"parent_department": "All Departments",
					"is_group": 0,
				}
			)

	for d in DESIGNATIONS:
		make({"doctype": "Designation", "designation_name": d}, filters={"name": d})

	for b in BRANCHES:
		make({"doctype": "Branch", "branch": b}, filters={"name": b})

	for state, country in STATES:
		make({"doctype": "States", "statename": state, "country": country}, filters={"name": state})


def create_holiday_list():
	name = "Facilitix Holidays FY26-27"
	if frappe.db.exists("Holiday List", name):
		return name
	start = fiscal_start()
	end = getdate(add_days(start.replace(year=start.year + 1), -1))
	festivals = [
		("2026-08-15", "Independence Day"),
		("2026-09-14", "Vinayagar Chathurthi"),
		("2026-10-02", "Gandhi Jayanti"),
		("2026-10-20", "Ayudha Pooja"),
		("2026-11-08", "Deepavali"),
		("2026-12-25", "Christmas"),
		("2027-01-14", "Pongal"),
		("2027-01-26", "Republic Day"),
	]
	holidays = []
	d = start
	while d <= end:
		if d.weekday() == 6:
			holidays.append({"holiday_date": d, "description": "Sunday", "weekly_off": 1})
		d = getdate(add_days(d, 1))
	for dt, desc in festivals:
		# a festival that already falls on a Sunday is a duplicate date
		if start <= getdate(dt) <= end and getdate(dt).weekday() != 6:
			holidays.append({"holiday_date": getdate(dt), "description": desc})
	make(
		{
			"doctype": "Holiday List",
			"holiday_list_name": name,
			"from_date": start,
			"to_date": end,
			"holidays": holidays,
		}
	)
	return name


def create_leave_types():
	for name, maxdays, carry in (("Casual Leave", 12, 0), ("Sick Leave", 10, 0), ("Earned Leave", 15, 1)):
		make(
			{
				"doctype": "Leave Type",
				"leave_type_name": name,
				"max_leaves_allowed": maxdays,
				"is_carry_forward": carry,
			},
			filters={"name": name},
		)
	make(
		{"doctype": "Leave Type", "leave_type_name": "Leave Without Pay", "is_lwp": 1},
		filters={"name": "Leave Without Pay"},
	)


def create_shift_types():
	for name, start, end in (("Day Shift", "08:00:00", "17:00:00"), ("Night Shift", "20:00:00", "05:00:00")):
		make({"doctype": "Shift Type", "name": name, "start_time": start, "end_time": end}, filters={"name": name})
