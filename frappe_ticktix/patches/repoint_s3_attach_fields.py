import frappe

from frappe_ticktix.plugins.storage.s3_attachment import (
    local_url_variants,
    repoint_attach_fields,
    s3_file_regex_match,
)


def execute():
    """Files migrated to S3 before child-table Attach fields were repointed
    still hold their old local url there. Rebuild that url from the file name
    and update the fields."""
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": ["not in", ["", "File"]]},
        fields=["file_url", "file_name", "is_private", "attached_to_doctype", "attached_to_name"],
    )
    for f in files:
        if not f.file_name or not f.attached_to_name or not s3_file_regex_match(f.file_url):
            continue
        folder = "/private/files/" if f.is_private else "/files/"
        try:
            repoint_attach_fields(
                f.attached_to_doctype,
                f.attached_to_name,
                local_url_variants(folder + f.file_name),
                f.file_url,
            )
        except Exception:
            frappe.log_error(title="repoint_s3_attach_fields")
    frappe.db.commit()
