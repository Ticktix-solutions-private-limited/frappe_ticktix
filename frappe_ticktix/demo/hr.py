"""Employees, leave, attendance and payroll for the demo company."""

import frappe
from frappe.utils import add_days, add_months, get_first_day, get_last_day, getdate

from frappe_ticktix.demo.utils import COMPANY, abbr, fiscal_start, make, rng, step, today

HOLIDAY_LIST = "Facilitix Holidays FY26-27"
STRUCTURE = "Facilitix Staff Structure"

# first, last, gender, department, designation, branch, dob, joining, base salary, phone
EMPLOYEES = [
	("Rajesh", "Kumar", "Male", "Operations", "Operations Manager", "Chennai", "1984-03-12", "2022-06-01", 68000),
	("Priya", "Ramesh", "Female", "Operations", "Site Manager", "Chennai", "1988-07-25", "2023-01-09", 52000),
	("Suresh", "Babu", "Male", "Operations", "Site Manager", "Bengaluru", "1986-11-02", "2023-03-15", 52000),
	("Anitha", "Selvam", "Female", "Housekeeping", "Housekeeping Supervisor", "Chennai", "1990-01-18", "2023-05-02", 28000),
	("Mohan", "Raj", "Male", "Housekeeping", "Housekeeping Supervisor", "Bengaluru", "1989-09-30", "2023-08-21", 28000),
	("Lakshmi", "Narayanan", "Female", "Housekeeping", "Housekeeping Staff", "Chennai", "1995-04-09", "2024-01-08", 17500),
	("Kavitha", "Murugan", "Female", "Housekeeping", "Housekeeping Staff", "Chennai", "1993-12-21", "2024-02-12", 17500),
	("Selvi", "Palani", "Female", "Housekeeping", "Housekeeping Staff", "Chennai", "1996-06-14", "2024-04-01", 17500),
	("Geetha", "Anand", "Female", "Housekeeping", "Housekeeping Staff", "Hyderabad", "1994-02-27", "2024-06-17", 17500),
	("Ravi", "Teja", "Male", "Housekeeping", "Housekeeping Staff", "Hyderabad", "1997-10-05", "2025-01-06", 17500),
	("Manjula", "Devi", "Female", "Housekeeping", "Housekeeping Staff", "Bengaluru", "1992-08-11", "2025-03-03", 17500),
	("Karthik", "Subramani", "Male", "Security", "Security Supervisor", "Chennai", "1985-05-23", "2022-11-14", 32000),
	("Venkatesh", "Iyer", "Male", "Security", "Security Supervisor", "Hyderabad", "1983-02-08", "2023-02-20", 32000),
	("Arun", "Prakash", "Male", "Security", "Security Guard", "Chennai", "1991-09-17", "2023-09-04", 19500),
	("Dinesh", "Kannan", "Male", "Security", "Security Guard", "Chennai", "1990-03-29", "2024-01-22", 19500),
	("Balaji", "Gopal", "Male", "Security", "Security Guard", "Bengaluru", "1988-12-06", "2024-05-13", 19500),
	("Murali", "Krishna", "Male", "Security", "Security Guard", "Hyderabad", "1989-07-19", "2024-09-02", 19500),
	("Senthil", "Nathan", "Male", "Maintenance", "Electrician", "Chennai", "1987-04-03", "2023-07-10", 26000),
	("Ganesan", "Pillai", "Male", "Maintenance", "Plumber", "Chennai", "1986-10-22", "2023-10-16", 24000),
	("Raman", "Sekar", "Male", "Canteen", "Canteen Chef", "Chennai", "1980-01-30", "2023-04-03", 30000),
	("Vimala", "Rani", "Female", "Canteen", "Canteen Helper", "Chennai", "1994-11-12", "2024-03-11", 16500),
	("Nisha", "Fathima", "Female", "HR & Admin", "HR Executive", "Chennai", "1993-06-08", "2023-06-05", 34000),
	("Vignesh", "Mani", "Male", "Accounts", "Accountant", "Chennai", "1991-08-26", "2023-02-01", 38000),
	("Deepa", "Chandran", "Female", "Sales", "Sales Executive", "Bengaluru", "1992-05-15", "2024-07-08", 36000),
	("Imran", "Sheikh", "Male", "Sales", "Sales Executive", "Hyderabad", "1990-03-04", "2025-06-02", 36000),
]

PAYROLL_MONTHS = 3  # completed months to run payroll for


def attendance_from():
	"""Attendance and leave start at the first day of the earliest payroll month."""
	return get_first_day(add_months(today(), -PAYROLL_MONTHS))


def run():
	step("employees", create_employees)
	step("salary components", create_salary_components)
	step("salary structure", create_salary_structure)
	step("salary assignments", create_salary_assignments)
	step("leave allocations", create_leave_allocations)
	step("leave applications", create_leave_applications)
	step("attendance", create_attendance)
	step("shift assignments", create_shift_assignments)
	step("payroll", run_payroll)


def employees():
	return frappe.get_all(
		"Employee",
		filters={"company": COMPANY, "status": "Active"},
		fields=["name", "employee_name", "date_of_joining", "department", "designation"],
		order_by="name",
	)


def create_employees():
	for i, (first, last, gender, dept, desig, branch, dob, doj, base) in enumerate(EMPLOYEES):
		ident = f"{first}.{last}".lower()
		if frappe.db.exists("Employee", {"first_name": first, "last_name": last, "company": COMPANY}):
			continue
		make(
			{
				"doctype": "Employee",
				"first_name": first,
				"last_name": last,
				"gender": gender,
				"date_of_birth": dob,
				"date_of_joining": doj,
				"company": COMPANY,
				"status": "Active",
				"department": abbr(dept),
				"designation": desig,
				"branch": branch,
				"holiday_list": HOLIDAY_LIST,
				"cell_number": f"9{rng.randint(100000000, 999999999)}",
				"company_email": f"{ident}@facilitix-demo.example",
				"custom_pf_eligible": 1 if base < 40000 else 0,
				"custom_esi_eligible": 1 if base < 21000 else 0,
			},
			filters={"first_name": first, "last_name": last, "company": COMPANY},
		)


def create_salary_components():
	specs = [
		("Basic Salary", "BS", "Earning", None, None),
		("House Rent Allowance", "HRA", "Earning", None, None),
		("Special Allowance", "SPL", "Earning", None, None),
		("Provident Fund", "PF", "Deduction", None, None),
		("Professional Tax", "PT", "Deduction", None, None),
	]
	# Only Basic is pro-rated by payment days; the rest are derived from it, and HRMS
	# refuses formulas that would be pro-rated twice.
	for name, ab, typ, _x, _y in specs:
		if name != "Basic Salary" and frappe.db.exists("Salary Component", name):
			frappe.db.set_value("Salary Component", name, "depends_on_payment_days", 0)
		account = abbr("Salary") if typ == "Earning" else abbr("PF & PT Payable")
		if frappe.db.exists("Salary Component", name):
			comp = frappe.get_doc("Salary Component", name)
			row = next((a for a in comp.accounts if a.company == COMPANY), None)
			if row is None:
				comp.append("accounts", {"company": COMPANY, "account": account})
			elif row.account != account:
				row.account = account
			else:
				continue
			comp.flags.ignore_permissions = True
			comp.save()
			continue
		make(
			{
				"doctype": "Salary Component",
				"salary_component": name,
				"salary_component_abbr": ab,
				"type": typ,
				"depends_on_payment_days": 1 if name == "Basic Salary" else 0,
				"accounts": [{"company": COMPANY, "account": account}],
			}
		)


def create_salary_structure():
	if frappe.db.exists("Salary Structure", STRUCTURE):
		return
	make(
		{
			"doctype": "Salary Structure",
			"name": STRUCTURE,
			"company": COMPANY,
			"currency": "INR",
			"is_active": "Yes",
			"payroll_frequency": "Monthly",
			"earnings": [
				{"salary_component": "Basic Salary", "abbr": "BS", "amount_based_on_formula": 1, "formula": "base * 0.5"},
				{"salary_component": "House Rent Allowance", "abbr": "HRA", "amount_based_on_formula": 1, "formula": "BS * 0.4", "depends_on_payment_days": 0},
				{"salary_component": "Special Allowance", "abbr": "SPL", "amount_based_on_formula": 1, "formula": "base - BS - HRA", "depends_on_payment_days": 0},
			],
			"deductions": [
				{"salary_component": "Provident Fund", "abbr": "PF", "amount_based_on_formula": 1, "formula": "BS * 0.12", "depends_on_payment_days": 0},
				{"salary_component": "Professional Tax", "abbr": "PT", "amount": 200, "depends_on_payment_days": 0},
			],
		},
		submit=True,
	)


def base_for(emp):
	for first, last, *_rest, base in EMPLOYEES:
		if emp.employee_name == f"{first} {last}":
			return base
	return 20000


def create_salary_assignments():
	for emp in employees():
		if frappe.db.exists("Salary Structure Assignment", {"employee": emp.name, "docstatus": 1}):
			continue
		frm = max(getdate(emp.date_of_joining), fiscal_start())
		make(
			{
				"doctype": "Salary Structure Assignment",
				"employee": emp.name,
				"salary_structure": STRUCTURE,
				"from_date": frm,
				"company": COMPANY,
				"base": base_for(emp),
				"currency": "INR",
			},
			filters={"employee": emp.name, "salary_structure": STRUCTURE},
			submit=True,
		)


def create_leave_allocations():
	fy_start = fiscal_start()
	fy_end = add_days(add_months(fy_start, 12), -1)
	for emp in employees():
		for leave_type, days in (("Casual Leave", 12), ("Sick Leave", 10), ("Earned Leave", 15)):
			if frappe.db.exists("Leave Allocation", {"employee": emp.name, "leave_type": leave_type, "docstatus": 1}):
				continue
			make(
				{
					"doctype": "Leave Allocation",
					"employee": emp.name,
					"leave_type": leave_type,
					"from_date": max(getdate(emp.date_of_joining), fy_start),
					"to_date": fy_end,
					"new_leaves_allocated": days,
					"company": COMPANY,
				},
				filters={"employee": emp.name, "leave_type": leave_type},
				submit=True,
			)


# (employee index, leave type, offset days from attendance_from(), span, status)
LEAVES = [
	(3, "Casual Leave", 5, 1, "Approved"),
	(5, "Sick Leave", 12, 2, "Approved"),
	(8, "Casual Leave", 26, 1, "Approved"),
	(13, "Earned Leave", 33, 3, "Approved"),
	(17, "Sick Leave", 47, 1, "Approved"),
	(21, "Casual Leave", 55, 2, "Approved"),
	(23, "Casual Leave", 70, 1, "Approved"),
	(6, "Casual Leave", 95, 2, "Open"),
	(10, "Sick Leave", 97, 1, "Open"),
]


def leave_dates():
	"""Dates covered by leave, per employee, so attendance does not collide."""
	out = {}
	emps = employees()
	for idx, _t, offset, span, _s in LEAVES:
		if idx >= len(emps):
			continue
		emp = emps[idx]
		d = getdate(add_days(attendance_from(), offset))
		for i in range(span):
			out.setdefault(emp.name, set()).add(getdate(add_days(d, i)))
	return out


def create_leave_applications():
	emps = employees()
	for idx, leave_type, offset, span, status in LEAVES:
		if idx >= len(emps):
			continue
		emp = emps[idx]
		frm = getdate(add_days(attendance_from(), offset))
		# keep leave out of Sundays so the day counts are clean
		while frm.weekday() == 6:
			frm = getdate(add_days(frm, 1))
		to = getdate(add_days(frm, span - 1))
		is_future = frm > getdate(today())
		make(
			{
				"doctype": "Leave Application",
				"employee": emp.name,
				"leave_type": leave_type,
				"from_date": frm,
				"to_date": to,
				"company": COMPANY,
				"status": "Open" if is_future else status,
				"posting_date": add_days(frm, -3) if not is_future else today(),
				"description": "Planned personal leave" if leave_type != "Sick Leave" else "Not feeling well",
			},
			filters={"employee": emp.name, "from_date": frm, "leave_type": leave_type},
			submit=(not is_future and status == "Approved"),
		)


def create_attendance():
	holidays = {
		getdate(r.holiday_date)
		for r in frappe.get_all("Holiday", filters={"parent": HOLIDAY_LIST}, fields=["holiday_date"])
	}
	on_leave = leave_dates()
	end = getdate(add_days(today(), -1))
	start = getdate(attendance_from())

	made = 0
	for emp in employees():
		d = max(start, getdate(emp.date_of_joining))
		while d <= end:
			if d not in holidays and d not in on_leave.get(emp.name, set()):
				if not frappe.db.exists("Attendance", {"employee": emp.name, "attendance_date": d, "docstatus": ["<", 2]}):
					roll = rng.random()
					status = "Present" if roll < 0.93 else ("Absent" if roll < 0.96 else "Half Day")
					doc = frappe.get_doc(
						{
							"doctype": "Attendance",
							"employee": emp.name,
							"attendance_date": d,
							"status": status,
							"company": COMPANY,
						}
					)
					doc.flags.ignore_permissions = True
					doc.insert()
					doc.submit()
					made += 1
					if made % 200 == 0:
						frappe.db.commit()
						print(f"   attendance: {made}")
			d = getdate(add_days(d, 1))
	frappe.db.commit()
	print(f"   attendance created: {made}")


def create_shift_assignments():
	for emp in employees():
		if emp.designation not in ("Security Supervisor", "Housekeeping Supervisor", "Site Manager"):
			continue
		make(
			{
				"doctype": "Shift Assignment",
				"employee": emp.name,
				"shift_type": "Day Shift",
				"company": COMPANY,
				"start_date": fiscal_start(),
				"status": "Active",
				"custom_enable_live_geo_tracking": 1,
			},
			filters={"employee": emp.name, "shift_type": "Day Shift"},
			submit=True,
		)


def run_payroll():
	for i in range(PAYROLL_MONTHS, 0, -1):
		first = get_first_day(add_months(today(), -i))
		last = get_last_day(first)
		if first < fiscal_start():
			continue
		label = first.strftime("%b %Y")
		if frappe.db.exists("Payroll Entry", {"company": COMPANY, "start_date": first, "docstatus": 1}):
			continue
		step(f"payroll {label}", _payroll_for_month, first, last)


def _payroll_for_month(first, last):
	from hrms.payroll.doctype.payroll_entry.payroll_entry import get_end_date

	pe = frappe.get_doc(
		{
			"doctype": "Payroll Entry",
			"company": COMPANY,
			"posting_date": last,
			"payroll_frequency": "Monthly",
			"start_date": first,
			"end_date": last,
			"currency": "INR",
			"exchange_rate": 1,
			"payroll_payable_account": abbr("Payroll Payable"),
			"cost_center": abbr("Main"),
			"payment_account": abbr("Cash"),
		}
	)
	pe.flags.ignore_permissions = True
	pe.insert()
	pe.fill_employee_details()
	pe.save()
	pe.submit()
	pe.create_salary_slips()
	frappe.db.commit()
	pe.reload()
	pe.submit_salary_slips()
	from frappe_ticktix.demo.utils import record

	record("Payroll Entry", pe.name)
	for ss in frappe.get_all("Salary Slip", filters={"payroll_entry": pe.name}, pluck="name"):
		record("Salary Slip", ss)


def reclass_deductions():
	"""One-off for a site seeded before deductions had their own account: payroll credited PF/PT
	to the Salary expense account. Move that credit to PF & PT Payable, month by month."""
	from frappe_ticktix.demo.masters import tune_company

	tune_company()
	create_salary_components()
	for start, ded in frappe.db.sql(
		"""select start_date, sum(total_deduction) from `tabSalary Slip`
		where company=%s and docstatus=1 group by start_date order by start_date""",
		COMPANY,
	):
		remark = f"Reclass PF & PT withheld - {getdate(start):%b %Y}"
		make(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": COMPANY,
				"posting_date": get_last_day(start),
				"user_remark": remark,
				"accounts": [
					{"account": abbr("Salary"), "debit_in_account_currency": ded, "cost_center": abbr("Main")},
					{"account": abbr("PF & PT Payable"), "credit_in_account_currency": ded, "cost_center": abbr("Main")},
				],
			},
			filters={"company": COMPANY, "user_remark": remark},
			submit=True,
		)
