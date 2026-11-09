"""Create an Employee from a Candidate that is ready for onboarding.

Everything the Candidate already holds is mapped across. Required Employee
fields that cannot be mapped (e.g. Company) are reported by
``get_missing_fields`` so the client can ask for them before creating.
"""

import frappe
from frappe import _

READY_STATUS = "Ready to Create Employee"
CONVERTED_STATUS = "Converted to Employee"

# Employee fieldname -> Candidate fieldname
FIELD_MAP = {
	"first_name": "applicant_name",
	"gender": "gender",
	"date_of_birth": "date_of_birth",
	"date_of_joining": "date_of_joining",
	"designation": "designation",
	"branch": "branch",
	"marital_status": "marital_status",
	"personal_email": "emailid",
	"cell_number": "phone_number",
	"current_address": "current_address",
	"permanent_address": "permanent_address",
	"bank_name": "bank_name",
	"bank_ac_no": "bank_ac_no",
	"ifsc_code": "ifsc_code",
	"custom_nominee": "nominee",
	"custom_uan": "uan",
	"custom_esi_number": "esi_no",
	"custom_candidate": "name",
}

# Employee child table -> Candidate child table
TABLE_MAP = {
	"custom_family_detail": "familuydetails",
	"custom_emp_documents": "kyc_documents",
}

DEFAULTS = {"status": "Active"}
SKIP_REQUIRED = {"naming_series"}
SKIP_ROW_KEYS = {"name", "owner", "creation", "modified", "modified_by", "parent", "parentfield", "parenttype", "idx", "docstatus", "doctype"}


def _get_candidate(candidate):
	doc = frappe.get_doc("Candidate", candidate)
	doc.check_permission("read")
	if doc.status != READY_STATUS:
		frappe.throw(_("Candidate status must be {0}").format(frappe.bold(READY_STATUS)))
	return doc


def _default_company():
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def _build_values(candidate):
	values = dict(DEFAULTS)
	meta = frappe.get_meta("Employee")
	for emp_field, cand_field in FIELD_MAP.items():
		value = candidate.get(cand_field)
		if value not in (None, "") and meta.has_field(emp_field):
			values[emp_field] = value
	company = _default_company()
	if company:
		values["company"] = company
	return values


@frappe.whitelist()
def get_missing_fields(candidate):
	"""Required Employee fields the Candidate cannot supply, as dialog fields."""
	values = _build_values(_get_candidate(candidate))
	missing = []
	for df in frappe.get_meta("Employee").fields:
		if not df.reqd or df.fieldname in SKIP_REQUIRED or df.hidden:
			continue
		if df.fieldtype in frappe.model.no_value_fields or df.fieldtype == "Table":
			continue
		if values.get(df.fieldname) in (None, "") and not df.default:
			missing.append(
				{
					"fieldname": df.fieldname,
					"label": df.label,
					"fieldtype": df.fieldtype,
					"options": df.options,
					"reqd": 1,
				}
			)
	# Company is only defaulted; let the user confirm it.
	if "company" in values and not any(m["fieldname"] == "company" for m in missing):
		missing.insert(
			0,
			{
				"fieldname": "company",
				"label": "Company",
				"fieldtype": "Link",
				"options": "Company",
				"reqd": 1,
				"default": values["company"],
			},
		)
	return missing


@frappe.whitelist()
def create_employee(candidate, extra=None):
	"""Create the Employee, link it back and mark the Candidate as converted."""
	doc = _get_candidate(candidate)
	frappe.has_permission("Employee", "create", throw=True)

	existing = frappe.db.get_value("Employee", {"custom_candidate": doc.name})
	if existing:
		frappe.throw(
			_("Employee {0} already exists for this Candidate").format(
				frappe.get_desk_link("Employee", existing)
			)
		)

	values = _build_values(doc)
	values.update({k: v for k, v in (frappe.parse_json(extra) or {}).items() if v not in (None, "")})

	employee = frappe.new_doc("Employee")
	employee.update(values)
	for emp_table, cand_table in TABLE_MAP.items():
		if not employee.meta.has_field(emp_table):
			continue
		for row in doc.get(cand_table) or []:
			employee.append(emp_table, {k: v for k, v in row.as_dict().items() if k not in SKIP_ROW_KEYS})
	employee.insert()

	doc.db_set("status", CONVERTED_STATUS)
	return employee.name
