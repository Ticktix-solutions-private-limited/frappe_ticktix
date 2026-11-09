# Copyright (c) 2026, Ticktix Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


FOLDER_PREFIX = "attachment/"


class TickTixS3Settings(Document):
	"""S3 attachment storage settings, managed from the desk.

	Read by frappe_ticktix.plugins.storage.s3_attachment. Seeded once from the
	ticktix.storage.s3 site config by patches/migrate_s3_settings_to_doctype.py;
	after that this doctype is the source of truth.
	"""

	def validate(self):
		if self.s3_enabled:
			if not self.s3_bucket_name:
				frappe.throw(frappe._("Bucket Name is required when S3 storage is enabled"))
			if not self.s3_aws_key:
				frappe.throw(frappe._("AWS Access Key ID is required when S3 storage is enabled"))
			if not self.s3_aws_secret:
				frappe.throw(frappe._("AWS Secret Access Key is required when S3 storage is enabled"))
			if not self.s3_region_name:
				frappe.throw(frappe._("S3 Bucket Region Name is required when S3 storage is enabled"))
		if self.s3_signed_url_expiry_time is not None and self.s3_signed_url_expiry_time < 0:
			frappe.throw(frappe._("Signed URL Expiry Time cannot be negative"))

		# strip stray whitespace/slashes that would corrupt the object key
		for field in ("s3_bucket_name", "s3_region_name", "s3_aws_key"):
			if self.get(field):
				self.set(field, self.get(field).strip())
		folder = (self.s3_folder_name or "").strip().strip("/")
		if folder == FOLDER_PREFIX.strip("/"):
			folder = ""
		if folder and not folder.startswith(FOLDER_PREFIX):
			frappe.throw(frappe._("Folder Name must start with {0}").format(FOLDER_PREFIX))
		if self.s3_enabled and not folder:
			frappe.throw(frappe._("Folder Name is required: {0}<site name>").format(FOLDER_PREFIX))
		self.s3_folder_name = folder
