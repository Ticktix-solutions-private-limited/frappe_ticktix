"""Records for the frappe_ticktix doctypes: divisions, locations, client staff,
canteen menus and orders, candidates and live GPS tracking."""

import math
from datetime import datetime, timedelta

import frappe
from frappe.utils import add_days, getdate

from frappe_ticktix.demo.utils import COMPANY, abbr, fiscal_start, make, rng, step, today

DIVISIONS = [
	"Corporate Services Division",
	"Healthcare Division",
	"Education Division",
	"Retail & Malls Division",
	"Industrial & Logistics Division",
]

LOCATIONS = [
	"Chennai - Orchid Tech Park",
	"Chennai - Metro Square Mall",
	"Chennai - Lakeview Residency",
	"Bengaluru - Sunrise Hospital",
	"Hyderabad - Greenfield School",
	"Coimbatore - Apex Logistics Hub",
]

# customer code -> staff (name, email-local, mobile)
CLIENT_STAFF = {
	"Orchid Tech Park": [("Anil Verma", "anil.verma"), ("Shruti Nair", "shruti.nair"), ("Rohit Bansal", "rohit.bansal")],
	"Sunrise Multispeciality Hospital": [("Dr. Kavya Shetty", "kavya.shetty"), ("Naveen Gowda", "naveen.gowda")],
	"Greenfield International School": [("Sister Maria", "maria.joseph"), ("Prakash Reddy", "prakash.reddy"), ("Ananya Rao", "ananya.rao")],
	"Metro Square Mall": [("Zubair Ahmed", "zubair.ahmed"), ("Pooja Menon", "pooja.menon")],
}

CANDIDATES = [
	("Rahul Dev", "Male", "Security Guard", "Chennai", "Under Review", 1996),
	("Sunita Yadav", "Female", "Housekeeping Staff", "Bengaluru", "Under Review", 1998),
	("Mahesh Babu", "Male", "Electrician", "Hyderabad", "Deployed on Site", 1992),
	("Tamilselvi", "Female", "Housekeeping Staff", "Chennai", "Ready to Create Employee", 1995),
	("Gopal Krishnan", "Male", "Security Supervisor", "Chennai", "Pending Confirmation", 1987),
	("Farzana Begum", "Female", "Canteen Helper", "Chennai", "Deployed on Site", 1994),
	("Ashok Kumar", "Male", "Plumber", "Coimbatore", "Rejected / Not Continuing", 1990),
	("Bhavani Shankar", "Male", "Security Guard", "Hyderabad", "Under Review", 1999),
]

# (meal slot, category, preference, item, start, end) for the canteen menus
MENU = {
	"breakfast": [("Breakfast", "Tiffin", "Veg", "FD-IDLI"), ("Breakfast", "Tiffin", "Veg", "FD-DOSA")],
	"lunchmeals": [("Lunch", "Meals", "Veg", "FD-MEAL"), ("Lunch", "Meals", "Veg", "FD-CHAP")],
	"lunchother": [("Lunch", "Special", "Non-Veg", "FD-BRYN"), ("Lunch", "Special", "Veg", "FD-CURD")],
	"snacks": [("Evening Snacks", "Snacks", "Veg", "FD-SMSA"), ("Evening Snacks", "Beverages", "Veg", "FD-COFE")],
	"dinner": [("Dinner", "Meals", "Veg", "FD-CHAP"), ("Dinner", "Tiffin", "Veg", "FD-DOSA")],
}


def run():
	step("divisions", create_divisions)
	step("branch locations", create_locations)
	step("client staff", create_client_staff)
	step("pos menus", create_pos_menus)
	step("canteen orders", create_canteen_orders)
	step("candidates", create_candidates)
	step("live geo tracking", create_geo_tracking)


def create_divisions():
	for name in DIVISIONS:
		make(
			{"doctype": "Division", "division_name": name, "company": COMPANY, "is_group": 0},
			filters={"division_name": name, "company": COMPANY},
		)


def create_locations():
	for name in LOCATIONS:
		make(
			{"doctype": "Branch Location", "branchlocation_name": name, "company": COMPANY, "is_group": 0},
			filters={"branchlocation_name": name, "company": COMPANY},
		)


def _code(customer):
	return "".join(w[0] for w in customer.split()[:3]).upper()


def create_client_staff():
	n = 0
	for customer, people in CLIENT_STAFF.items():
		for name, local in people:
			n += 1
			code = f"{_code(customer)}-{n:03d}"
			make(
				{
					"doctype": "CustomerEmployee",
					"employeeid": code,
					"fullname": name,
					"email": f"{local}@{customer.split()[0].lower()}-demo.example",
					"mobile": f"9{rng.randint(100000000, 999999999)}",
					"customer": customer,
					"isactive": 1,
				},
				filters={"employeeid": code},
			)


def _lines(keys):
	out = []
	for slot, cat, pref, item in keys:
		price_name = frappe.db.get_value("Item Price", {"item_code": item, "price_list": "Standard Selling"}, "name")
		price = frappe.db.get_value("Item Price", price_name, "price_list_rate") if price_name else 0
		out.append(
			{
				"meal_slot": slot,
				"mealcategory": cat,
				"mealpreference": pref,
				"fooditem": item,
				"itemprice": price_name,
				"price": price,
			}
		)
	return out


def create_pos_menus():
	start = fiscal_start()
	for customer in ("Orchid Tech Park", "Greenfield International School", "Sunrise Multispeciality Hospital"):
		make(
			{
				"doctype": "POS Menu",
				"customer": customer,
				"validfrom": start,
				"validto": add_days(start, 364),
				"status": "Active",
				"plantype": "Daily",
				"breakfaststarttime": "07:30:00",
				"breakfastendtime": "09:30:00",
				"breakfastmenulines": _lines(MENU["breakfast"]),
				"lunchmealsstarttime": "12:00:00",
				"lunchmealsendtime": "14:30:00",
				"lunchmealsmenulines": _lines(MENU["lunchmeals"]),
				"lunchotherstarttime": "12:00:00",
				"lunchotherendtime": "14:30:00",
				"lunchothermenulines": _lines(MENU["lunchother"]),
				"snacksstarttime": "16:00:00",
				"snacksendtime": "17:30:00",
				"snacksmenulines": _lines(MENU["snacks"]),
				"dinnerstarttime": "19:30:00",
				"dinnerendtime": "21:30:00",
				"dinnermenulines": _lines(MENU["dinner"]),
			},
			filters={"customer": customer, "validfrom": start},
			submit=True,
		)


def create_canteen_orders():
	"""Meal Sales Orders placed by client staff over the last fortnight."""
	items = [("FD-MEAL", 90), ("FD-BRYN", 140), ("FD-DOSA", 60), ("FD-COFE", 20), ("FD-SMSA", 30)]
	for customer, people in CLIENT_STAFF.items():
		if customer not in ("Orchid Tech Park", "Greenfield International School"):
			continue
		for person_idx, (name, _local) in enumerate(people):
			ce = frappe.db.get_value("CustomerEmployee", {"fullname": name, "customer": customer}, "name")
			if not ce:
				continue
			for day in range(1, 8):
				date = getdate(add_days(today(), -day))
				if date.weekday() == 6:
					continue
				code, rate = items[(day + person_idx) % len(items)]
				so = make(
					{
						"doctype": "Sales Order",
						"customer": customer,
						"company": COMPANY,
						"transaction_date": date,
						"delivery_date": date,
						"set_warehouse": abbr("Stores"),
						"order_type": "Sales",
						"custom_customer_employee": ce,
						"custom_customer_order_status": "Served" if day > 1 else "Not-Served",
						"custom_payment_gateway_status": "Success",
						"custom_payment_gateway_order_id": f"order_demo{rng.randint(10**9, 10**10 - 1)}",
						"custom_payment_gateway_payment_id": f"pay_demo{rng.randint(10**9, 10**10 - 1)}",
						"items": [{"item_code": code, "qty": rng.randint(1, 2), "rate": rate, "delivery_date": date}],
					},
					filters={"customer": customer, "transaction_date": date, "custom_customer_employee": ce, "company": COMPANY},
					submit=True,
				)


def create_candidates():
	for i, (name, gender, desig, branch, status, birth_year) in enumerate(CANDIDATES):
		phone = f"98{rng.randint(10000000, 99999999)}"
		joined = add_days(today(), -rng.randint(5, 40))
		make(
			{
				"doctype": "Candidate",
				"applicant_name": name,
				"phone_number": phone,
				"emailid": f"{name.split()[0].lower()}.{i}@candidate-demo.example",
				"date_of_birth": f"{birth_year}-0{rng.randint(1, 9)}-1{rng.randint(0, 9)}",
				"gender": gender,
				"country": "India",
				"designation": desig,
				"branch": branch,
				"status": status,
				"marital_status": "Married" if i % 2 else "Single",
				"date_of_joining": joined,
				"deployed_date": joined if status == "Deployed on Site" else None,
				"nominee": "Spouse" if i % 2 else "Mother",
				"current_address": f"{rng.randint(1, 99)}, Gandhi Street, {branch}",
				"permanent_address": f"{rng.randint(1, 99)}, Nehru Nagar, {branch}",
				"bank_name": "State Bank of India",
				"candidate_rating": rng.choice([0.6, 0.8, 1.0]),
				"kyc_documents": [{"document_type": "Aadhar Card", "document": "/files/demo-aadhar-placeholder.pdf"}],
			},
			filters={"applicant_name": name, "phone_number": phone},
		)


def _haversine(a, b):
	r = 6371.0
	p1, p2 = math.radians(a[0]), math.radians(b[0])
	dphi, dl = p2 - p1, math.radians(b[1] - a[1])
	h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
	return 2 * r * math.asin(math.sqrt(h))


# Guindy -> Perungudi -> Sholinganallur -> Siruseri (OMR corridor, Chennai)
ROUTE = [(13.0067, 80.2206), (12.9716, 80.2430), (12.9010, 80.2279), (12.8270, 80.2210)]


def _point(t):
	"""Position along ROUTE for t in [0, 1]."""
	seg = min(int(t * (len(ROUTE) - 1)), len(ROUTE) - 2)
	local = t * (len(ROUTE) - 1) - seg
	a, b = ROUTE[seg], ROUTE[seg + 1]
	return a[0] + (b[0] - a[0]) * local, a[1] + (b[1] - a[1]) * local


def create_geo_tracking():
	supervisors = frappe.get_all(
		"Employee",
		filters={"company": COMPANY, "designation": ["in", ["Site Manager", "Housekeeping Supervisor", "Security Supervisor"]], "branch": "Chennai"},
		pluck="name",
	)[:3]
	for emp in supervisors:
		for day in range(1, 6):
			date = getdate(add_days(today(), -day))
			if date.weekday() == 6:
				continue
			if frappe.db.exists("Daily Travel Summary", {"employee": emp, "summary_date": date}):
				continue

			points, n = [], 24
			base = datetime.combine(date, datetime.min.time()) + timedelta(hours=9)
			for i in range(n):
				lat, lng = _point(i / (n - 1))
				lat += rng.uniform(-0.0004, 0.0004)
				lng += rng.uniform(-0.0004, 0.0004)
				points.append((base + timedelta(minutes=20 * i), lat, lng))

			batch = f"demo-{emp}-{date:%Y%m%d}"
			dist = 0.0
			for i, (ts, lat, lng) in enumerate(points):
				if i:
					dist += _haversine((points[i - 1][1], points[i - 1][2]), (lat, lng))
				doc = frappe.get_doc(
					{
						"doctype": "Live GEO Tracking",
						"employee": emp,
						"device_date_time": ts,
						"lat": lat,
						"long": lng,
						"accuracy": round(rng.uniform(4, 18), 1),
						"source": "punch" if i == 0 else "background",
						"device_id": f"demo-device-{emp[-2:]}",
						"batch_id": batch,
						"speed": round(rng.uniform(0, 14), 1),
						"heading": round(rng.uniform(0, 359), 1),
						"altitude": round(rng.uniform(5, 20), 1),
					}
				)
				doc.flags.ignore_permissions = True
				doc.insert()

			hours = (n - 1) * 20 / 60
			make(
				{
					"doctype": "Daily Travel Summary",
					"employee": emp,
					"summary_date": date,
					"status": "Completed",
					"processed_at": datetime.combine(date, datetime.min.time()) + timedelta(hours=23),
					"total_distance_km": round(dist, 2),
					"total_travel_time": f"{int(hours)}h {int(hours % 1 * 60)}m",
					"average_speed_kmh": round(dist / hours, 2),
					"total_points": n,
					"raw_data_count": n,
				},
				filters={"employee": emp, "summary_date": date},
				commit=False,
			)
		frappe.db.commit()
