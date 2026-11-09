import frappe
from frappe.model.rename_doc import rename_doc


def execute() -> None:
    old_name = "Live GEO Tracking"
    new_name = "Live GEO Tracking V2"

    if not frappe.db.exists("DocType", old_name):
        return
    if frappe.db.exists("DocType", new_name):
        return

    doc = frappe.get_doc("DocType", old_name)
    if getattr(doc, "custom", 0):
        return
    if doc.module != "Frappe Ticktix":
        return

    rename_doc("DocType", old_name, new_name, force=True, ignore_if_exists=True)
    frappe.clear_cache()
