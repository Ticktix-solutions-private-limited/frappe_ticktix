"""Leads, opportunities and support issues for the demo company."""

import frappe
from frappe.utils import add_days

from frappe_ticktix.demo.utils import COMPANY, make, rng, step, today

LEADS = [
	("Arvind", "Menon", "Zenith Software Park", "arvind.menon@zenith-demo.example", "Reference", "Open"),
	("Farah", "Khan", "Crescent Medical Centre", "farah.khan@crescent-demo.example", "Cold Calling", "Replied"),
	("Joseph", "D'Souza", "St. Mary's Public School", "joseph@stmarys-demo.example", "Existing Customer", "Interested"),
	("Meera", "Krishnan", "Bayview Business Centre", "meera@bayview-demo.example", "Advertisement", "Open"),
	("Harish", "Patel", "Gateway Cold Storage", "harish@gateway-demo.example", "Exhibition", "Quotation"),
	("Sangeetha", "Rao", "Palm Grove Villas", "sangeetha@palmgrove-demo.example", "Reference", "Open"),
]

ISSUE_TYPES = ["Housekeeping Complaint", "Security Incident", "Maintenance Request", "Billing Query", "Staffing Request"]

# customer, type, subject, priority, status, days ago, resolution
ISSUES = [
	("Orchid Tech Park", "Housekeeping Complaint", "Washrooms on Tower A 4th floor not cleaned during night shift", "High", "Closed", 52, "Night shift roster corrected; supervisor now signs off a checklist."),
	("Orchid Tech Park", "Maintenance Request", "AMC visit requested for lobby lighting flicker", "Medium", "Closed", 38, "Electrician replaced two faulty drivers and re-tested the circuit."),
	("Sunrise Multispeciality Hospital", "Housekeeping Complaint", "Request for additional staff in the OT corridor", "High", "Closed", 30, "Two extra housekeeping staff deployed from Bengaluru bench."),
	("Metro Square Mall", "Security Incident", "Unauthorised entry attempt at service gate B", "High", "Resolved", 21, "CCTV reviewed; gate protocol reinforced and guard briefed."),
	("Metro Square Mall", "Billing Query", "September invoice GST breakup mismatch", "Medium", "Replied", 15, None),
	("Greenfield International School", "Staffing Request", "Need extra canteen helper for exam week", "Medium", "Closed", 27, "Temporary helper arranged for 5 working days."),
	("Greenfield International School", "Maintenance Request", "Garden irrigation timer not working", "Low", "Open", 9, None),
	("Apex Logistics Hub", "Security Incident", "Night guard absent at Dock 3", "High", "Resolved", 12, "Replacement guard sent; absentee issued a warning."),
	("Apex Logistics Hub", "Billing Query", "Request for quarterly pest control invoice copy", "Low", "Closed", 18, "Copy emailed to the client accounts team."),
	("Lakeview Residents Welfare Association", "Housekeeping Complaint", "Clubhouse cleaning schedule missed on Sunday", "Medium", "Open", 5, None),
	("Lakeview Residents Welfare Association", "Maintenance Request", "Overhead tank cleaning due", "Medium", "Open", 3, None),
	("Sunrise Multispeciality Hospital", "Billing Query", "Please share contract rate card for FY26-27", "Low", "Closed", 44, "Rate card shared and acknowledged."),
]


def run():
	step("lead sources & priorities", create_lookups)
	step("leads", create_leads)
	step("opportunities", create_opportunities)
	step("issue types", create_issue_types)
	step("issues", create_issues)


def create_lookups():
	for src in ("Reference", "Cold Calling", "Existing Customer", "Advertisement", "Exhibition"):
		make({"doctype": "Lead Source", "source_name": src}, filters={"name": src})
	for prio in ("Low", "Medium", "High"):
		make({"doctype": "Issue Priority", "name": prio}, filters={"name": prio})


def create_leads():
	for first, last, org, email, source, status in LEADS:
		make(
			{
				"doctype": "Lead",
				"first_name": first,
				"last_name": last,
				"company_name": org,
				"email_id": email,
				"source": source,
				"status": status,
				"territory": "India",
				"company": COMPANY,
			},
			filters={"email_id": email},
		)


def create_opportunities():
	picks = [(0, 480000, 20), (4, 360000, 10), (2, 210000, 35), (1, 540000, 28)]
	for idx, amount, days in picks:
		email = LEADS[idx][3]
		lead = frappe.db.get_value("Lead", {"email_id": email}, "name")
		if not lead:
			continue
		make(
			{
				"doctype": "Opportunity",
				"opportunity_from": "Lead",
				"party_name": lead,
				"company": COMPANY,
				"status": "Open",
				"opportunity_type": "Sales",
				"transaction_date": add_days(today(), -days),
				"expected_closing": add_days(today(), 30 - days // 2),
				"opportunity_amount": amount,
				"currency": "INR",
				"conversion_rate": 1,
			},
			filters={"party_name": lead, "company": COMPANY},
		)


def create_issue_types():
	for t in ISSUE_TYPES:
		make({"doctype": "Issue Type", "name": t}, filters={"name": t})


def create_issues():
	for customer, itype, subject, priority, status, ago, resolution in ISSUES:
		opened = add_days(today(), -ago)
		doc = make(
			{
				"doctype": "Issue",
				"subject": subject,
				"customer": customer,
				"company": COMPANY,
				"issue_type": itype,
				"priority": priority,
				"status": "Open",
				"opening_date": opened,
				"raised_by": f"facilities@{customer.split()[0].lower()}-demo.example",
				"description": f"<p>{subject}. Reported by the client facilities team.</p>",
			},
			filters={"subject": subject, "customer": customer},
		)
		if status != "Open" and doc.status == "Open":
			frappe.db.set_value("Issue", doc.name, "status", status)
			if resolution:
				frappe.db.set_value("Issue", doc.name, "resolution_details", resolution)
