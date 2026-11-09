"""Shared helpers for the demo data seeder.

Every document created through `make()` is recorded in "TickTix Demo Record", so
clearing can find and remove exactly what was loaded.
"""

import random

import frappe
from frappe.utils import add_days, getdate
from frappe.utils import today as _real_today

COMPANY = "Facilitix Demo Services Pvt Ltd"
ABBR = "FDS"
STATE = "TickTix Demo Data"
LEGACY_MANIFEST = "demo_seed_manifest.json"

# One fixed seed so repeated runs produce the same story
rng = random.Random(2026)


# the pack currently loading; stamped on every record it creates
current_pack = None
# labels of steps that failed during the current run
failed_steps = []


def anchor():
	"""The date the demo data is "as of". Fixed at the first load so packs added
	later line up with the existing data instead of starting a new timeline."""
	return stored_anchor() or getdate(_real_today())


def stored_anchor():
	"""The saved anchor date, or None. An unset Date can read back as 0001-01-01."""
	d = frappe.db.get_single_value(STATE, "anchor_date")
	d = getdate(d) if d else None
	return d if d and d.year > 2000 else None


def today():
	return str(anchor())


# percent shown in the desk dialog; only ever moves forward during a run
run_progress = {"last": 0.0, "done": 0, "expected": 1}


def start_progress(expected_steps):
	run_progress.update(last=0.0, done=0, expected=max(expected_steps, 1))


def progress(message, percent=None):
	"""Persist and broadcast load/clear progress for the desk dialog.

	Without an explicit percent the last one is kept, so the bar never drops back."""
	if percent is not None:
		run_progress["last"] = max(run_progress["last"], round(percent, 1))
	percent = run_progress["last"]
	frappe.db.set_single_value(STATE, {"progress_message": message, "progress_percent": percent})
	frappe.db.commit()
	frappe.publish_realtime("ticktix_demo_progress", {"message": message, "percent": percent})


def fiscal_start():
	fy = frappe.db.get_value(
		"Fiscal Year",
		{"disabled": 0, "year_start_date": ["<=", today()], "year_end_date": [">=", today()]},
		"year_start_date",
	)
	return getdate(fy) if fy else getdate(add_days(today(), -180))


def start_date():
	return fiscal_start()


def month_starts():
	"""First day of every month from the fiscal year start up to the current month."""
	d = fiscal_start().replace(day=1)
	end = getdate(today())
	out = []
	while d <= end:
		out.append(d)
		d = d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)
	return out


def abbr(name):
	return f"{name} - {ABBR}"


# --- tracking ---------------------------------------------------------------


def record(doctype, name):
	if frappe.db.exists("TickTix Demo Record", {"ref_doctype": doctype, "ref_name": name}):
		return
	# plain insert: this runs once per demo document, thousands of times per load
	now = frappe.utils.now()
	frappe.db.sql(
		"""insert into `tabTickTix Demo Record`
		(name, creation, modified, modified_by, owner, docstatus, idx, ref_doctype, ref_name, pack)
		values (%s, %s, %s, %s, %s, 0, 0, %s, %s, %s)""",
		(frappe.generate_hash(length=10), now, now, frappe.session.user, frappe.session.user, doctype, name, current_pack),
	)


# bookkeeping and ledger rows are not "demo records" (ledgers are purged by company)
UNTRACKED_DOCTYPES = {
	"TickTix Demo Record", "TickTix Demo Data", "Version", "Comment", "Error Log", "Activity Log",
	"Communication", "ToDo", "Email Queue", "Deleted Document", "Notification Log", "Document Follow",
	"Access Log", "Route History", "View Log", "Energy Point Log", "Scheduled Job Log", "RQ Job",
	"GL Entry", "Stock Ledger Entry", "Payment Ledger Entry", "Bin", "Repost Item Valuation",
	"Unreconcile Payment Entries", "File",
}


def track_insert(doc, method=None):
	"""doc_events hook (all doctypes, after_insert): while a demo load runs, record every
	document created, so side effects (contacts, item prices, slips, ...) are cleared too."""
	if not current_pack or not frappe.flags.get("in_demo_seed"):
		return
	if doc.doctype in UNTRACKED_DOCTYPES or doc.meta.istable:
		return
	record(doc.doctype, doc.name)


def tracked():
	"""Every recorded (doctype, name), oldest first."""
	return frappe.get_all(
		"TickTix Demo Record", fields=["ref_doctype", "ref_name"], order_by="creation asc", as_list=True
	)


# --- creation ---------------------------------------------------------------


def make(values, filters=None, submit=False, commit=True):
	"""Insert (and optionally submit) a document unless a match already exists.

	`filters` decides what "already exists" means; it defaults to the doc name
	when `values` carries one. Returns the document either way.
	"""
	doctype = values["doctype"]
	if filters is None and values.get("name"):
		filters = {"name": values["name"]}

	if filters:
		existing = frappe.db.get_value(doctype, filters, "name")
		if existing:
			return frappe.get_doc(doctype, existing)

	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = False
	doc.insert()
	if submit:
		doc.submit()
	record(doctype, doc.name)
	if commit:
		frappe.db.commit()
	return doc


def _step_done(label):
	run_progress["done"] += 1
	progress(label, min(run_progress["done"] / run_progress["expected"], 1) * 95)


def step(label, fn, *args, **kwargs):
	"""Run one seeding step; log failures instead of aborting the whole run."""
	progress(label)
	try:
		result = fn(*args, **kwargs)
		frappe.db.commit()
		print(f"[ok]   {label}")
		_step_done(label)
		return result
	except Exception:
		frappe.db.rollback()
		err = frappe.get_traceback()
		frappe.log_error(f"Demo seed step failed: {label}", err)
		last = err.strip().splitlines()[-1]
		failed_steps.append(f"{label}: {last}")
		print(f"[FAIL] {label}: {last}")
		_step_done(label)
		return None


def working_days(frm, to, off_weekday=6):
	"""All dates between frm and to (inclusive) except Sundays."""
	d, out = getdate(frm), []
	to = getdate(to)
	while d <= to:
		if d.weekday() != off_weekday:
			out.append(d)
		d = getdate(add_days(d, 1))
	return out
