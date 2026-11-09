# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt
"""Seed the "TickTix S3 Settings" doctype so existing S3 storage keeps working.

S3 settings used to be read-only fields on TickTix Settings, re-synced from the
ticktix.storage.s3 site config on every migrate. They are now edited in
TickTix S3 Settings. Values come from the site config, falling back to what was
last stored on TickTix Settings. An already configured doctype is never touched.
"""

import frappe
from frappe.utils.password import get_decrypted_password

NEW = "TickTix S3 Settings"
OLD = "TickTix Settings"


def _legacy_values():
    # Singles values stay in tabSingles after the fields leave the doctype
    old = frappe.db.get_singles_dict(OLD) or {}
    values = {k: v for k, v in old.items() if k.startswith("s3_")}
    try:
        secret = get_decrypted_password(OLD, OLD, "s3_aws_secret", raise_exception=False)
    except Exception:
        secret = None
    if secret:
        values["s3_aws_secret"] = secret
    return values


def seed_s3_settings():
    """Returns True if the doctype was seeded."""
    from frappe_ticktix.config.config_manager import get_s3_config

    settings = frappe.get_single(NEW)
    if settings.s3_bucket_name:
        return False  # already configured from the desk

    values = {k: v for k, v in _legacy_values().items() if v not in (None, "")}
    # site config wins - it was the source of truth until now
    values.update({k: v for k, v in get_s3_config().items() if v not in (None, "")})
    if not values.get("s3_bucket_name"):
        return False

    # folder is always "attachment/<site name>"
    folder = (values.get("s3_folder_name") or "").strip().strip("/")
    if not folder.startswith("attachment/") or folder == "attachment/":
        folder = "attachment/" + (folder.removeprefix("attachment").strip("/") or frappe.local.site)
    values["s3_folder_name"] = folder

    for fieldname, value in values.items():
        if settings.meta.has_field(fieldname):
            settings.set(fieldname, value)
    settings.s3_enabled = 1 if frappe.utils.cint(values.get("s3_enabled")) else 0
    settings.s3_delete_file_from_cloud = (
        1 if frappe.utils.cint(values.get("s3_delete_file_from_cloud")) else 0
    )

    settings.flags.ignore_permissions = True
    settings.save()
    frappe.db.commit()
    return True


def execute():
    seed_s3_settings()
