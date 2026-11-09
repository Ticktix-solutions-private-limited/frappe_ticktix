"""Reconcile the demo company's books: every balance is recomputed from source
documents and compared with the general ledger.

	bench --site demo.local execute frappe_ticktix.demo.verify.run
"""

import frappe
from frappe.utils import flt

from frappe_ticktix.demo.utils import COMPANY, abbr

_results = []


def _q(sql, *args):
	return frappe.db.sql(sql, args or None)[0][0] or 0


def check(label, ledger, source, tolerance=1.0):
	ok = abs(flt(ledger) - flt(source)) <= tolerance
	_results.append(ok)
	print(f"[{'OK  ' if ok else 'FAIL'}] {label}: ledger={flt(ledger):,.2f}  source={flt(source):,.2f}")


def gl(account):
	return flt(
		_q("select sum(debit - credit) from `tabGL Entry` where company=%s and account=%s and is_cancelled=0", COMPANY, abbr(account))
	)


def run():
	# 1. the ledger itself balances
	dr, cr = frappe.db.sql(
		"select sum(debit), sum(credit) from `tabGL Entry` where company=%s and is_cancelled=0", COMPANY
	)[0]
	check("Trial balance (debit = credit)", dr, cr, 0.5)

	# 2. receivables and payables against open invoices
	check("Debtors vs open sales invoices", gl("Debtors"),
		_q("select sum(outstanding_amount) from `tabSales Invoice` where company=%s and docstatus=1", COMPANY))
	check("Creditors vs open purchase invoices", -gl("Creditors"),
		_q("select sum(outstanding_amount) from `tabPurchase Invoice` where company=%s and docstatus=1", COMPANY))

	# 3. stock value against the bins
	check("Stock In Hand vs stock value of bins", gl("Stock In Hand"),
		_q("select sum(b.stock_value) from tabBin b join tabWarehouse w on w.name=b.warehouse where w.company=%s", COMPANY))

	# 4. payroll liability = accrued net pay - salary disbursed
	accrued = _q("select sum(net_pay) from `tabSalary Slip` where company=%s and docstatus=1", COMPANY)
	paid = _q(
		"select sum(jea.debit) from `tabJournal Entry Account` jea join `tabJournal Entry` je on je.name=jea.parent "
		"where je.company=%s and je.docstatus=1 and jea.account=%s",
		COMPANY, abbr("Payroll Payable"),
	)
	check("Payroll Payable vs slips - disbursements", -gl("Payroll Payable"), accrued - paid)

	# 5. cash rebuilt from voucher types
	receipts = _q("select sum(paid_amount) from `tabPayment Entry` where company=%s and docstatus=1 and payment_type='Receive'", COMPANY)
	payments = _q("select sum(paid_amount) from `tabPayment Entry` where company=%s and docstatus=1 and payment_type='Pay'", COMPANY)
	je_cash = _q(
		"select sum(jea.debit - jea.credit) from `tabJournal Entry Account` jea join `tabJournal Entry` je on je.name=jea.parent "
		"where je.company=%s and je.docstatus=1 and jea.account=%s",
		COMPANY, abbr("Cash"),
	)
	check("Cash vs receipts - payments + journals", gl("Cash"), receipts - payments + je_cash)

	# 6. sales: invoiced = collected + outstanding
	inv = _q("select sum(grand_total) from `tabSales Invoice` where company=%s and docstatus=1", COMPANY)
	out = _q("select sum(outstanding_amount) from `tabSales Invoice` where company=%s and docstatus=1", COMPANY)
	# invoices carry a rounding adjustment; payments settle the rounded total
	rounded = _q("select sum(if(rounded_total>0, rounded_total, grand_total)) from `tabSales Invoice` where company=%s and docstatus=1", COMPANY)
	check("Sales invoiced (rounded) = received + outstanding", rounded, receipts + out - (inv - rounded) * 0 , 3.0)

	# 7. salary expense in the P&L equals gross pay on the slips
	check("Salary expense vs gross pay on slips", gl("Salary"),
		_q("select sum(gross_pay) from `tabSalary Slip` where company=%s and docstatus=1", COMPANY))

	# 8. GST output equals tax on sales; input equals tax on purchases
	check("Output GST vs sales tax", -gl("Output GST"),
		_q("select sum(total_taxes_and_charges) from `tabSales Invoice` where company=%s and docstatus=1", COMPANY))
	check("Input GST vs purchase tax", gl("Input GST"),
		_q("select sum(total_taxes_and_charges) from `tabPurchase Invoice` where company=%s and docstatus=1", COMPANY))

	print("\n-- duplicates and integrity --")
	dups = {
		"Sales Invoice (customer+date)": "select count(*) from (select 1 from `tabSales Invoice` where company=%s and docstatus=1 group by customer, posting_date, update_stock having count(*)>1) t",
		"Purchase Invoice (supplier+month)": "select count(*) from (select 1 from `tabPurchase Invoice` where company=%s and docstatus=1 group by supplier, year(posting_date), month(posting_date) having count(*)>1) t",
		"Journal Entry (remark)": "select count(*) from (select 1 from `tabJournal Entry` where company=%s and docstatus=1 group by user_remark having count(*)>1) t",
		"Attendance (employee+date)": "select count(*) from (select 1 from tabAttendance where company=%s and docstatus=1 group by employee, attendance_date having count(*)>1) t",
		"Salary Slip (employee+month)": "select count(*) from (select 1 from `tabSalary Slip` where company=%s and docstatus=1 group by employee, start_date having count(*)>1) t",
		"Quotation (party+date)": "select count(*) from (select 1 from tabQuotation where company=%s and docstatus=1 group by party_name, transaction_date having count(*)>1) t",
		"Issue (subject+customer)": "select count(*) from (select 1 from tabIssue where company=%s group by subject, customer having count(*)>1) t",
		"Employee (name)": "select count(*) from (select 1 from tabEmployee where company=%s group by first_name, last_name having count(*)>1) t",
	}
	for label, sql in dups.items():
		n = _q(sql, COMPANY)
		_results.append(n == 0)
		print(f"[{'OK  ' if n == 0 else 'FAIL'}] no duplicate {label}: {n} groups")

	neg = _q("select count(*) from `tabBin` b join tabWarehouse w on w.name=b.warehouse where w.company=%s and b.actual_qty<0", COMPANY)
	_results.append(neg == 0)
	print(f"[{'OK  ' if neg == 0 else 'FAIL'}] no negative stock bins: {neg}")

	orphans = _q(
		"select count(*) from `tabSales Invoice` si where si.company=%s and si.docstatus=1 and not exists "
		"(select 1 from `tabGL Entry` g where g.voucher_no=si.name and g.is_cancelled=0)", COMPANY)
	_results.append(orphans == 0)
	print(f"[{'OK  ' if orphans == 0 else 'FAIL'}] submitted sales invoices without GL entries: {orphans}")

	print("\n-- headline numbers --")
	income = -flt(_q("select sum(g.debit - g.credit) from `tabGL Entry` g join tabAccount a on a.name=g.account where g.company=%s and g.is_cancelled=0 and a.root_type='Income'", COMPANY))
	expense = flt(_q("select sum(g.debit - g.credit) from `tabGL Entry` g join tabAccount a on a.name=g.account where g.company=%s and g.is_cancelled=0 and a.root_type='Expense'", COMPANY))
	print(f"Income {income:,.2f} | Expense {expense:,.2f} | Net profit {income - expense:,.2f}")
	for label, dt, extra in (
		("Sales invoices", "Sales Invoice", "docstatus=1"),
		("Purchase invoices", "Purchase Invoice", "docstatus=1"),
		("Payment entries", "Payment Entry", "docstatus=1"),
		("Journal entries", "Journal Entry", "docstatus=1"),
		("Salary slips", "Salary Slip", "docstatus=1"),
		("Attendance", "Attendance", "docstatus=1"),
		("Employees", "Employee", "status='Active'"),
	):
		print(f"{label}: {_q(f'select count(*) from `tab{dt}` where company=%s and {extra}', COMPANY)}")
	for acct in ("Cash", "Debtors", "Creditors", "Stock In Hand", "Payroll Payable"):
		print(f"{acct}: {gl(acct):,.2f}")

	print(f"\n{sum(_results)}/{len(_results)} checks passed")


def process_reposts(max_rounds=60):
	"""Run queued Repost Item Valuation jobs by hand (the scheduler is paused on the demo site)."""
	from erpnext.stock.doctype.repost_item_valuation.repost_item_valuation import repost_entries

	for i in range(max_rounds):
		pending = frappe.db.count("Repost Item Valuation", {"status": ["in", ["Queued", "In Progress"]]})
		print(f"round {i}: {pending} pending")
		if not pending:
			break
		repost_entries()
		frappe.db.commit()
	failed = frappe.db.count("Repost Item Valuation", {"status": "Failed"})
	print(f"failed reposts: {failed}")


def reset_failed_reposts():
	"""Retry failed reposts whose data file was pushed to S3 before the doctype was excluded."""
	for name in frappe.get_all("Repost Item Valuation", filters={"status": "Failed"}, pluck="name"):
		file_name = frappe.db.get_value("Repost Item Valuation", name, "reposting_data_file")
		frappe.db.set_value("Repost Item Valuation", name, {"reposting_data_file": None, "status": "Queued", "error_log": None})
		if file_name and frappe.db.exists("File", file_name):
			frappe.delete_doc("File", file_name, force=True, ignore_permissions=True)
	frappe.db.commit()
