"""Load, top-up and clear the demo data from the desk (TickTix Settings).

Nothing here runs from install or migrate hooks; everything starts with a click.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

from frappe_ticktix.demo import packs as registry
from frappe_ticktix.demo import utils

STATE = utils.STATE
STALE_AFTER_HOURS = 3  # a "Loading"/"Clearing" run older than this is treated as dead
JOB_TIMEOUT = 4 * 60 * 60

# queue records that are only meaningful while their vouchers exist; removed in bulk
QUEUE_DOCTYPE = "Repost Item Valuation"


# --- status -----------------------------------------------------------------


def _state():
	return frappe.get_single(STATE)


def _busy(state):
	if state.status not in ("Loading", "Clearing") or not state.started_on:
		return False
	return get_datetime(state.started_on) > add_to_date(now_datetime(), hours=-STALE_AFTER_HOURS)


def _loaded_versions(state):
	return {row.pack: cint(row.version) for row in state.packs}


def _pending_packs(state):
	loaded = _loaded_versions(state)
	return [p for p in registry.PACKS if loaded.get(p["name"], 0) < p["version"]]


@frappe.whitelist()
def get_status():
	frappe.only_for("System Manager")
	state = _state()
	pending = _pending_packs(state)
	loaded = _loaded_versions(state)
	return {
		"status": state.status,
		"busy": _busy(state),
		"action": state.current_action,
		"percent": state.progress_percent or 0,
		"message": state.progress_message,
		"anchor_date": utils.stored_anchor(),
		"error": state.last_error,
		"has_data": bool(loaded),
		"pending": [p["label"] for p in pending],
		"company": utils.COMPANY,
	}


# --- load -------------------------------------------------------------------


def _check_can_load(state):
	apps = frappe.get_installed_apps()
	missing = [a for a in ("erpnext", "hrms") if a not in apps]
	if missing:
		frappe.throw(_("Demo data needs these apps installed: {0}").format(", ".join(missing)))

	if _busy(state):
		frappe.throw(_("Demo data is already {0}. Please wait for it to finish.").format(state.status.lower()))

	if not _loaded_versions(state):
		# first load: refuse to collide with something that is not ours
		if frappe.db.exists("Company", utils.COMPANY):
			frappe.throw(_("A company named {0} already exists on this site.").format(utils.COMPANY))
		clash = frappe.db.get_value("Company", {"abbr": utils.ABBR}, "name")
		if clash:
			frappe.throw(_("Company {0} already uses the abbreviation {1}.").format(clash, utils.ABBR))

	for pack in _pending_packs(state):
		unmet = [r for r in pack["requires"] if r not in _loaded_versions(state) and r not in {p["name"] for p in _pending_packs(state)}]
		if unmet:
			frappe.throw(_("Pack {0} needs {1}").format(pack["name"], ", ".join(unmet)))


@frappe.whitelist()
def load_demo_data():
	frappe.only_for("System Manager")
	state = _state()
	_check_can_load(state)
	if not _pending_packs(state):
		frappe.throw(_("Demo data is already up to date."))

	frappe.db.set_single_value(
		STATE,
		{
			"status": "Loading",
			"current_action": "Load",
			"progress_percent": 0,
			"progress_message": "Queued…",
			"started_on": now_datetime(),
			"finished_on": None,
			"last_error": None,
		},
	)
	frappe.db.commit()
	frappe.enqueue(
		"frappe_ticktix.demo.api.run_load",
		queue="long",
		timeout=JOB_TIMEOUT,
		job_id="ticktix_demo_data",
		deduplicate=True,
	)
	return get_status()


def run_load():
	frappe.flags.in_demo_seed = True
	frappe.flags.mute_emails = True
	utils.failed_steps.clear()
	state = _state()
	pending = _pending_packs(state)

	if not utils.stored_anchor():
		frappe.db.set_single_value(STATE, "anchor_date", utils.anchor())
		frappe.db.commit()

	utils.start_progress(sum(p.get("expected_steps", len(p["steps"])) for p in pending))
	try:
		for pack in pending:
			utils.current_pack = pack["name"]
			failed_before = len(utils.failed_steps)
			for label, path, kwargs in pack["steps"]:
				utils.progress(f"{pack['name']}: {label}")
				frappe.get_attr(path)(**kwargs)
			if len(utils.failed_steps) == failed_before:
				_mark_pack_loaded(pack)

		utils.progress("Updating stock valuation…", 96)
		_process_reposts()

		if utils.failed_steps:
			_finish("Failed", "\n".join(utils.failed_steps))
		else:
			_finish("Loaded", None)
	except Exception:
		frappe.db.rollback()
		frappe.log_error("Demo data load failed")
		_finish("Failed", frappe.get_traceback())
	finally:
		utils.current_pack = None


def _mark_pack_loaded(pack):
	state = _state()
	row = next((r for r in state.packs if r.pack == pack["name"]), None)
	if not row:
		row = state.append("packs", {"pack": pack["name"]})
	row.version = pack["version"]
	row.loaded_on = now_datetime()
	state.flags.ignore_permissions = True
	state.save()
	frappe.db.commit()


def _process_reposts(max_rounds=60):
	"""Run queued stock revaluations now, so balances are right when the job ends."""
	from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import repost_entries

	for _i in range(max_rounds):
		if not frappe.db.count("Repost Item Valuation", {"status": ["in", ["Queued", "In Progress"]]}):
			break
		repost_entries()
		frappe.db.commit()


def _finish(status, error):
	frappe.db.set_single_value(
		STATE,
		{
			"status": status,
			"progress_percent": 100 if status == "Loaded" else None,
			"progress_message": {
				"Loaded": "Demo data is ready.",
				"Failed": "Stopped with errors. You can click Load Demo Data again to continue.",
				"Not Loaded": "Demo data cleared.",
			}.get(status, ""),
			"finished_on": now_datetime(),
			"last_error": error,
		},
	)
	frappe.db.commit()
	frappe.publish_realtime("ticktix_demo_progress", {"done": True, "status": status})


# --- clear ------------------------------------------------------------------


def _refuse_if_in_use():
	blockers = find_blockers()
	if blockers:
		frappe.throw(
			_("Demo data cannot be cleared while your own records use it. Remove or change these first:")
			+ "<br>"
			+ "<br>".join(f"{b['doctype']} {b['name']}" for b in blockers[:20])
			+ (f"<br>… and {len(blockers) - 20} more" if len(blockers) > 20 else ""),
			title=_("Demo data is in use"),
		)


@frappe.whitelist()
def clear_demo_data():
	frappe.only_for("System Manager")
	state = _state()
	if _busy(state):
		frappe.throw(_("Demo data is already {0}. Please wait for it to finish.").format(state.status.lower()))
	if not _loaded_versions(state) and not frappe.db.count("TickTix Demo Record"):
		frappe.throw(_("There is no demo data to clear."))
	_refuse_if_in_use()

	frappe.db.set_single_value(
		STATE,
		{
			"status": "Clearing",
			"current_action": "Clear",
			"progress_percent": 0,
			"progress_message": "Queued…",
			"started_on": now_datetime(),
			"finished_on": None,
			"last_error": None,
		},
	)
	frappe.db.commit()
	frappe.enqueue(
		"frappe_ticktix.demo.api.run_clear",
		queue="long",
		timeout=JOB_TIMEOUT,
		job_id="ticktix_demo_data",
		deduplicate=True,
	)
	return get_status()


# ledgers, queue rows and company-owned masters are removed in bulk, not one by one
BULK_REMOVED = {
	"GL Entry", "Stock Ledger Entry", "Payment Ledger Entry", "Bin", "Repost Item Valuation",
	"Account", "Cost Center", "Warehouse", "Company",
}


def _company_doctypes():
	"""Document types that carry a company field (the demo company owns its rows)."""
	names = frappe.get_all(
		"DocField", filters={"fieldname": "company", "fieldtype": "Link", "options": "Company"}, pluck="parent"
	)
	out = []
	for dt in set(names) - BULK_REMOVED:
		meta = frappe.get_meta(dt)
		if meta.istable or meta.issingle or meta.is_virtual or not frappe.db.table_exists(dt):
			continue
		out.append(dt)
	return sorted(out)


def _company_docs():
	"""Every document that belongs to the demo company, whoever created it."""
	rows = []
	for dt in _company_doctypes():
		for name in frappe.get_all(dt, filters={"company": utils.COMPANY}, pluck="name"):
			rows.append((dt, name))
	return rows


def find_blockers():
	"""Documents outside the demo company that use a demo record.

	Deleting the demo record would leave these with a link to nothing."""
	from frappe.desk.form.linked_with import (
		get_referencing_documents,
		get_references_across_doctypes_by_link_field,
	)

	demo = {(d, n) for d, n in utils.tracked() if frappe.db.exists(d, n)}
	inside = set(_company_docs())

	by_doctype = {}
	for dt, name in demo:
		if dt not in BULK_REMOVED:
			by_doctype.setdefault(dt, []).append(name)

	blockers = {}

	def add(from_dt, from_name, target_dt):
		key = (from_dt, from_name)
		if key not in demo and key not in inside:
			blockers.setdefault(key, set()).add(target_dt)

	# Link fields, including those inside child tables
	refs = get_references_across_doctypes_by_link_field(to_doctypes=list(by_doctype)) if by_doctype else {}
	for target_dt, names in by_doctype.items():
		for link in refs.get(target_dt, []):
			if link["doctype"] in BULK_REMOVED:
				continue
			try:
				meta = frappe.get_meta(link["doctype"])
				# singles and virtual doctypes have no table of their own
				if meta.issingle or meta.is_virtual or not frappe.db.table_exists(link["doctype"]):
					continue
				link = {**link, "is_child": meta.istable}
				found = get_referencing_documents(target_dt, names, link)
			except Exception:
				continue
			for from_dt, from_names in found.items():
				for from_name in from_names:
					add(from_dt, from_name, target_dt)

		# Dynamic links (Address / Contact rows pointing at a customer, supplier, ...)
		for row in frappe.get_all(
			"Dynamic Link",
			filters={"link_doctype": target_dt, "link_name": ["in", names]},
			fields=["parenttype", "parent"],
		):
			add(row.parenttype, row.parent, target_dt)

	return [
		{"doctype": dt, "name": name, "uses": sorted(uses)} for (dt, name), uses in sorted(blockers.items())
	]


@frappe.whitelist()
def check_clear():
	"""What clearing would do, so the desk can warn or refuse before anything is deleted."""
	frappe.only_for("System Manager")
	tracked = {(d, n) for d, n in utils.tracked()}
	own_in_company = {}
	for dt, name in _company_docs():
		if (dt, name) not in tracked:
			own_in_company[dt] = own_in_company.get(dt, 0) + 1
	return {
		"blockers": find_blockers(),
		"own_in_company": own_in_company,
		"demo_records": len(tracked),
		"company": utils.COMPANY,
	}


def run_clear():
	frappe.flags.in_demo_seed = True
	frappe.flags.mute_emails = True
	leftovers = []
	try:
		# the data may have changed since the button was clicked
		blockers = find_blockers()
		if blockers:
			# nothing was deleted: the demo data is still intact and loaded
			_finish(
				"Loaded",
				"Not cleared. These records use demo data:\n"
				+ "\n".join(f"{b['doctype']} {b['name']}" for b in blockers[:50]),
			)
			return
		utils.start_progress(1)
		utils.progress("Collecting demo records…", 2)
		records = [(d, n) for d, n in utils.tracked()]
		extra = _company_docs()

		# newest first: later documents depend on earlier ones
		order = {}
		for dt, name in records + extra:
			order[(dt, name)] = frappe.db.get_value(dt, name, "creation") if frappe.db.exists(dt, name) else None
		docs = sorted((k for k, v in order.items() if v), key=lambda k: order[k], reverse=True)

		total = len(docs) or 1
		failed = []
		for i, (dt, name) in enumerate(docs):
			if i % 25 == 0:
				utils.progress(f"Removing {dt} ({i}/{len(docs)})", 5 + i / total * 80)
			if not _delete(dt, name):
				failed.append((dt, name))

		# a second and third pass catches records that were blocked by a link to a
		# record that has been removed since
		for _pass in range(2):
			failed = [d for d in failed if not _delete(*d)]

		utils.progress("Removing ledger entries…", 88)
		_purge_queue_records()
		_purge_ledgers()

		utils.progress("Removing the demo company…", 92)
		if frappe.db.exists("Company", utils.COMPANY):
			try:
				frappe.delete_doc("Company", utils.COMPANY, ignore_permissions=True, force=True)
				frappe.db.commit()
			except Exception:
				frappe.db.rollback()
				failed.append(("Company", utils.COMPANY))
				frappe.log_error("Demo clear: company delete failed")

		_purge_company_masters()
		failed = [d for d in failed if frappe.db.exists(*d)]
		leftovers = failed
		if not leftovers:
			utils.progress("Verifying nothing is left…", 97)
			leftovers = _remaining()

		if leftovers:
			lines = [f"{dt} {name}" for dt, name in leftovers[:50]]
			_finish("Failed", "Could not remove:\n" + "\n".join(lines))
			return

		_reset_state()
		_finish("Not Loaded", None)
	except Exception:
		frappe.db.rollback()
		frappe.log_error("Demo data clear failed")
		_finish("Failed", frappe.get_traceback())


def _delete(doctype, name):
	if not frappe.db.exists(doctype, name):
		return True
	try:
		doc = frappe.get_doc(doctype, name)
		doc.flags.ignore_permissions = True
		if getattr(doc, "docstatus", 0) == 1:
			doc.cancel()
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		frappe.db.commit()
		return True
	except Exception:
		frappe.db.rollback()
		return False


def _purge_queue_records():
	"""Stock revaluation jobs (and the data files attached to them) for the demo company."""
	names = frappe.get_all(QUEUE_DOCTYPE, filters={"company": utils.COMPANY}, pluck="name")
	if not names:
		return
	for f in frappe.get_all(
		"File", filters={"attached_to_doctype": QUEUE_DOCTYPE, "attached_to_name": ["in", names]}, pluck="name"
	):
		try:
			frappe.delete_doc("File", f, force=True, ignore_permissions=True)
		except Exception:
			frappe.db.rollback()
	frappe.db.delete(QUEUE_DOCTYPE, {"name": ["in", names]})
	frappe.db.commit()


def _purge_ledgers():
	"""Cancelling and deleting a voucher leaves its reversal rows behind in the ledgers
	(that is how Frappe keeps an audit trail), so drop the demo company's rows."""
	for dt in ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry"):
		frappe.db.delete(dt, {"company": utils.COMPANY})
	frappe.db.commit()


def _purge_company_masters():
	"""Accounts, cost centers and warehouses belong to the company. Company deletion
	normally removes them; sweep up any that were left behind."""
	warehouses = frappe.get_all("Warehouse", filters={"company": utils.COMPANY}, pluck="name")
	if warehouses:
		frappe.db.delete("Bin", {"warehouse": ["in", warehouses]})
	for dt in ("Mode of Payment Account", "Party Account"):
		if frappe.db.has_column(dt, "company"):
			frappe.db.delete(dt, {"company": utils.COMPANY})
	for dt in ("Account", "Cost Center", "Warehouse"):
		frappe.db.delete(dt, {"company": utils.COMPANY})
	frappe.db.commit()


def _remaining():
	"""Anything demo-related still on the site after clearing."""
	left = []
	for dt, name in utils.tracked():
		if frappe.db.exists(dt, name):
			left.append((dt, name))
	if frappe.db.exists("Company", utils.COMPANY):
		left.append(("Company", utils.COMPANY))
	for dt in ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry"):
		if frappe.db.count(dt, {"company": utils.COMPANY}):
			left.append((dt, f"rows for {utils.COMPANY}"))
	return left


def _reset_state():
	frappe.db.delete("TickTix Demo Record")
	frappe.db.delete("TickTix Demo Pack")
	frappe.db.set_single_value(STATE, "anchor_date", None)
	frappe.db.commit()
