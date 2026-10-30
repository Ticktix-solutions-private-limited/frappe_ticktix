"""
Custom fields for Employee doctype

Overview tab: nationality (under Salutation); probation, rehire, operations
              executive, division, location (Company Details section)
Joining     : candidate
Address & Contacts: alternate mobile (first section)
Salary      : gross / CTC contribution breakups, bank details verified
Personal Details: parents/spouse after Marital Status, Family Details section,
              then Aadhar details last
Profile     : education level (under bio / Cover Letter)
Statutorys  : PF / ESI / PT / LWF statutory compliance details
Documents   : employee document attachments

These fields already exist on the live site, so they are created only when
missing (update=False); existing field definitions are never overwritten, only
their position (insert_after) is kept in sync with this file.

The Family Details and Document child doctypes are shipped as fixtures
(fixtures/doctype.json) and are synced before after_migrate runs.
"""

# Nationality sits under Salutation; Company Details fields go after Branch
NATIONALITY_ANCHOR = "salutation"
COMPANY_DETAILS_ANCHOR = "branch"
# Joining tab, Address & Contacts tab (first section) and Salary tab placements
CANDIDATE_ANCHOR = "job_applicant"
CANDIDATE_PREFERRED_ANCHOR = "offer_date"  # used when present (Joining tab, live)
ALTERNATE_MOBILE_ANCHOR = "cell_number"
BREAKUP_ANCHOR = "provident_fund_account"  # last field of the Salary section
BANK_VERIFIED_ANCHOR = "bank_ac_no"
# Last standard field of the Personal Details tab (before "profile_tab")
DEFAULT_TAB_ANCHOR = "place_of_issue"
# First standard field after which the Statutorys tab is placed
STATUTORY_TAB_ANCHOR = "connections_tab"

# (fieldname, fieldtype, label, options)
NATIONALITY_FIELD = ("custom_nationality", "Data", "Nationality", None)

# Placed in the Overview tab's Company Details section (after "branch")
COMPANY_DETAILS_FIELDS = [
    ("custom_probation_status", "Select", "Probation Status", "\nProbation\nConfirmed"),
    ("custom_rehire_employee_info", "Link", "Rehire Employee Info", "Employee"),
    ("custom_operations_executive_name", "Data", "Operations Executive Name", None),
    ("custom_operations_executive_id", "Data", "Operations Executive ID", None),
    ("custom_division", "Link", "Division", "Division"),
    ("custom_location", "Link", "Location", "Branch Location"),
]

CANDIDATE_FIELD = ("custom_candidate", "Link", "Candidate", "Candidate")
ALTERNATE_MOBILE_FIELD = ("custom_alternate_mobile", "Data", "Alternate Mobile", None)
# Profile tab: under the Cover Letter (bio) text area
EDUCATION_LEVEL_ANCHOR = "bio"
EDUCATION_LEVEL_FIELD = ("custom_education_level", "Data", "Education Level", None)
BANK_VERIFIED_FIELD = ("custom_bank_details_verified", "Check", "Bank Details Verified", None)

# Salary tab: Breakup sections between the Salary and Bank Details sections
BREAKUP_FIELDS = [
    ("custom_breakupgross_contributors", "Section Break", "Breakup-Gross Contributors", None),
    ("custom_employer_contribution_to_pf", "Data", "Employer Contribution to PF", None),
    ("custom_column_break_wzcd6", "Column Break", None, None),
    ("custom_employer_contribution_to_esi", "Data", "Employer Contribution to ESI", None),
    ("custom_breakupctc_contributors", "Section Break", "Breakup-CTC Contributors", None),
    ("custom_gratutity_applicable", "Check", "Gratutity Applicable", None),
    ("custom_gratutity", "Data", "Gratutity", None),
    ("custom_column_break_jycvz", "Column Break", None, None),
    ("custom_other_benefits", "Data", "Other Benefits", None),
]

# Personal Details tab, first section: parents and spouse after Marital Status
PERSONAL_DETAILS_ANCHOR = "marital_status"
PERSONAL_DETAILS_FIELDS = [
    ("custom_fathers_name", "Data", "Father's Name", None),
    ("custom_fathers_occupation", "Data", "Father's Occupation", None),
    ("custom_mothers_name", "Data", "Mother's Name", None),
    ("custom_mothers_occupation", "Data", "Mother's Occupation", None),
    ("custom_spouse_name", "Data", "Spouse Name", None),
    ("custom_spouse_occupation", "Data", "Spouse Occupation", None),
]

# Second section, right after the first and before the Health Insurance section
FAMILY_DETAILS_ANCHOR = "health_details"
FAMILY_DETAILS_FIELDS = [
    ("custom_family_details_section", "Section Break", "Family Details Section", None),
    ("custom_family_detail", "Table", "Family Detail", "Family Details"),
    ("custom_nominee", "Data", "Nominee", None),
]

# Last on the tab, after Health Insurance and Passport Details (Aadhar only)
DEFAULT_TAB_FIELDS = [
    ("custom_aadhar_details", "Section Break", "Aadhar Details", None),
    ("custom_aadhar_number", "Data", "Aadhar Number", None),
    ("custom_aadhar_card_document_attachment", "Attach", "Aadhar Card Document Attachment", None),
]

STATUTORY_TAB_FIELDS = [
    ("custom_statutorys", "Tab Break", "Statutorys", None),
    ("custom_pf__esi_details", "Section Break", "PF & ESI Details", None),
    ("custom_pf_eligible", "Check", "PF Eligible", None),
    ("custom_pension_act", "Check", "Pension Act", None),
    ("custom_pf_number", "Data", "PF Number", None),
    ("custom_pf_state_dd", "Link", "PF State", "States"),
    ("custom_uan", "Data", "UAN", None),
    ("custom_pt_eligible", "Check", "PT Eligible", None),
    ("custom_pt_state", "Link", "PT State", "States"),
    ("custom_column_break_jtp2p", "Column Break", None, None),
    ("custom_esi_eligible", "Check", "ESI Eligible", None),
    ("custom_esi_number", "Data", "ESI Number", None),
    ("custom_esi_state_dd", "Link", "ESI State", "States"),
    ("custom_lwf_eligible", "Check", "LWF Eligible", None),
    ("custom_lwf_state_dd", "Link", "LWF State", "States"),
    ("custom_documents", "Tab Break", "Documents", None),
    ("custom_attach_files", "Section Break", "Attach Files", None),
    ("custom_emp_documents", "Table", "Documents", "Document"),
]

# Existing Data fields converted to Link (same varchar column, so no data change)
CONVERT_TO_LINK = {"custom_pt_state": "States"}

# Replaced by custom_pf_state_dd. Hidden, not deleted, so existing values are kept.
HIDDEN_FIELDS = ["custom_pf_state"]

# Section breaks created by an earlier version of this module. The live site
# uses custom_pf__esi_details instead, so these would show up as empty sections.
OBSOLETE_FIELDS = ["custom_pf", "custom_esi"]


def _chain(fields, anchor):
    """Turn an ordered field list into definitions linked by insert_after."""
    definitions = []
    for fieldname, fieldtype, label, options in fields:
        definition = {
            "fieldname": fieldname,
            "fieldtype": fieldtype,
            "insert_after": anchor,
        }
        if label:
            definition["label"] = label
        if options:
            definition["options"] = options
        definitions.append(definition)
        anchor = fieldname
    return definitions


def get_employee_custom_fields():
    """Returns custom field definitions for Employee doctype"""
    return {
        "Employee": _chain([NATIONALITY_FIELD], NATIONALITY_ANCHOR)
        + _chain(COMPANY_DETAILS_FIELDS, COMPANY_DETAILS_ANCHOR)
        + _chain([CANDIDATE_FIELD], CANDIDATE_ANCHOR)
        + _chain([ALTERNATE_MOBILE_FIELD], ALTERNATE_MOBILE_ANCHOR)
        + _chain(BREAKUP_FIELDS, BREAKUP_ANCHOR)
        + _chain([BANK_VERIFIED_FIELD], BANK_VERIFIED_ANCHOR)
        + _chain(PERSONAL_DETAILS_FIELDS, PERSONAL_DETAILS_ANCHOR)
        + _chain(FAMILY_DETAILS_FIELDS, FAMILY_DETAILS_ANCHOR)
        + _chain(DEFAULT_TAB_FIELDS, DEFAULT_TAB_ANCHOR)
        + _chain([EDUCATION_LEVEL_FIELD], EDUCATION_LEVEL_ANCHOR)
        + _chain(STATUTORY_TAB_FIELDS, STATUTORY_TAB_ANCHOR)
    }


def remove_obsolete_fields():
    """Drop empty section breaks that were superseded by custom_pf__esi_details"""
    import frappe

    for fieldname in OBSOLETE_FIELDS:
        name = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": fieldname})
        if name:
            frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
            print(f"   🗑  Removed obsolete Employee field {fieldname}")


def sync_field_positions(fields):
    """Apply insert_after to fields that already exist; nothing else is touched"""
    import frappe

    for field in fields:
        name = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": field["fieldname"]})
        if name and frappe.db.get_value("Custom Field", name, "insert_after") != field["insert_after"]:
            frappe.db.set_value("Custom Field", name, "insert_after", field["insert_after"])
            print(f"   ↕ Moved {field['fieldname']} after {field['insert_after']}")
    frappe.clear_cache(doctype="Employee")


def convert_fields_to_link():
    """Turn existing Data fields into Links; reports values that match no record"""
    import frappe

    for fieldname, target in CONVERT_TO_LINK.items():
        name = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": fieldname})
        if not name or not frappe.db.exists("DocType", target):
            continue
        if frappe.db.get_value("Custom Field", name, "fieldtype") == "Link":
            continue

        frappe.db.set_value("Custom Field", name, {"fieldtype": "Link", "options": target})
        frappe.clear_cache(doctype="Employee")
        print(f"   🔗 Converted Employee.{fieldname} to Link -> {target}")

        unmatched = frappe.db.sql_list(
            f"""select distinct `{fieldname}` from `tabEmployee`
            where ifnull(`{fieldname}`, '') != ''
            and `{fieldname}` not in (select name from `tab{target}`)"""
        )
        if unmatched:
            print(f"   ⚠️  {fieldname} has values not in {target}: {unmatched}")


def hide_replaced_fields():
    """Hide fields superseded by a Link field; the column and its data stay"""
    import frappe

    for fieldname in HIDDEN_FIELDS:
        name = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": fieldname})
        if name and not frappe.db.get_value("Custom Field", name, "hidden"):
            frappe.db.set_value("Custom Field", name, "hidden", 1)
            frappe.clear_cache(doctype="Employee")
            print(f"   🙈 Hid replaced Employee field {fieldname}")


def create_custom_fields():
    """
    Create custom fields for Employee doctype
    Called from install.py
    """
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    fields = []
    skipped = {}  # skipped fieldname -> its insert_after, to keep the chain intact
    employee_meta = frappe.get_meta("Employee")
    for field in get_employee_custom_fields()["Employee"]:
        if field["fieldname"] == "custom_candidate" and employee_meta.has_field(CANDIDATE_PREFERRED_ANCHOR):
            field["insert_after"] = CANDIDATE_PREFERRED_ANCHOR
        target = field.get("options") if field["fieldtype"] in ("Link", "Table") else None
        if target and not frappe.db.exists("DocType", target):
            # Retried on the next migrate once the doctype is available
            print(f"   ⚠️  Skipped {field['fieldname']}: DocType '{target}' not found")
            skipped[field["fieldname"]] = field["insert_after"]
            continue
        while field["insert_after"] in skipped:
            field["insert_after"] = skipped[field["insert_after"]]
        fields.append(field)

    remove_obsolete_fields()
    create_custom_fields({"Employee": fields}, update=False)
    sync_field_positions(fields)
    convert_fields_to_link()
    hide_replaced_fields()

    frappe.db.commit()
    print("✅ Created custom fields for Employee doctype")
