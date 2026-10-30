"""
S3 Attachment Storage

Uploads File attachments to S3 instead of the local filesystem, driven by
TickTix Settings (fields synced from common_site_config.json/site_config.json
under the "ticktix.storage.s3" key - see config/config_manager.get_s3_config()
and install.setup_s3_attachment_settings()).

Ported from the standalone frappe_s3_attachment app, with the following fixes
folded in from that app's debugging session:
  - explicit endpoint_url so presigned URLs don't mismatch the signing region
  - no ACL param on upload (works with buckets that have ACLs disabled /
    Object Ownership: Bucket owner enforced + Block Public Access ON)
  - every file (public or private) is served through the signed-url redirect,
    since a bucket locked down that way never serves raw object URLs anyway
  - attached_to_doctype falls back to 'File' consistently, including in the
    migration path
"""

import datetime
import os
import random
import re
import string

import boto3
import frappe
from botocore.client import Config
from botocore.exceptions import ClientError

try:
    import magic
except ImportError:  # python-magic / libmagic not installed
    magic = None


def get_s3_settings():
    """Return the TickTix Settings singleton, synced from site config."""
    return frappe.get_single("TickTix Settings")


class S3Operations:
    def __init__(self, settings=None):
        self.settings = settings or get_s3_settings()

        region_name = self.settings.s3_region_name
        endpoint_url = "https://s3.{}.amazonaws.com".format(region_name)

        aws_key = self.settings.s3_aws_key
        aws_secret = (
            self.settings.get_password("s3_aws_secret")
            if self.settings.s3_aws_secret
            else None
        )

        if aws_key and aws_secret:
            self.S3_CLIENT = boto3.client(
                "s3",
                aws_access_key_id=aws_key,
                aws_secret_access_key=aws_secret,
                region_name=region_name,
                endpoint_url=endpoint_url,
                config=Config(signature_version="s3v4"),
            )
        else:
            self.S3_CLIENT = boto3.client(
                "s3",
                region_name=region_name,
                endpoint_url=endpoint_url,
                config=Config(signature_version="s3v4"),
            )

        self.BUCKET = self.settings.s3_bucket_name
        self.folder_name = self.settings.s3_folder_name

    def strip_special_chars(self, file_name):
        regex = re.compile("[^0-9a-zA-Z._-]")
        return regex.sub("", file_name)

    def key_generator(self, file_name, parent_doctype, parent_name):
        file_name = file_name.replace(" ", "_")
        file_name = self.strip_special_chars(file_name)
        key = "".join(
            random.choice(string.ascii_uppercase + string.digits) for _ in range(8)
        )

        today = datetime.datetime.now()
        year = today.strftime("%Y")
        month = today.strftime("%m")
        day = today.strftime("%d")

        if self.folder_name:
            return "{}/{}/{}/{}/{}/{}_{}".format(
                self.folder_name, year, month, day, parent_doctype, key, file_name
            )
        return "{}/{}/{}/{}/{}_{}".format(
            year, month, day, parent_doctype, key, file_name
        )

    def upload_files_to_s3_with_key(
        self, file_path, file_name, is_private, parent_doctype, parent_name
    ):
        if magic:
            mime_type = magic.from_file(file_path, mime=True)
        else:
            import mimetypes

            mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        key = self.key_generator(file_name, parent_doctype, parent_name)

        metadata = {"ContentType": mime_type}
        if is_private:
            metadata["file_name"] = file_name

        try:
            self.S3_CLIENT.upload_file(
                file_path,
                self.BUCKET,
                key,
                ExtraArgs={
                    "ContentType": mime_type,
                    "Metadata": metadata,
                },
            )
        except boto3.exceptions.S3UploadFailedError:
            frappe.throw(frappe._("File Upload Failed. Please try again."))
        return key

    def delete_from_s3(self, key):
        if not self.settings.s3_delete_file_from_cloud:
            return
        try:
            self.S3_CLIENT.delete_object(Bucket=self.BUCKET, Key=key)
        except ClientError:
            frappe.throw(frappe._("Access denied: Could not delete file"))

    def get_url(self, key, file_name=None):
        expiry = self.settings.s3_signed_url_expiry_time or 120
        params = {"Bucket": self.BUCKET, "Key": key}
        if file_name:
            params["ResponseContentDisposition"] = "filename={}".format(file_name)

        return self.S3_CLIENT.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=expiry
        )

    def read_file_from_s3(self, key):
        """Fetch the object body+metadata from S3 (used to proxy file bytes
        through Frappe so the browser never sees the S3 URL)."""
        return self.S3_CLIENT.get_object(Bucket=self.BUCKET, Key=key)


def s3_upload_enabled():
    settings = get_s3_settings()
    return bool(
        settings.s3_enabled
        and settings.s3_bucket_name
        and settings.s3_region_name
    )


def s3_file_regex_match(file_url):
    return re.match(
        r"^/api/method/frappe_ticktix\.plugins\.storage\.s3_attachment\.generate_file",
        file_url or "",
    )


def file_upload_to_s3(doc, method=None):
    """doc_events hook: File.after_insert"""
    if not s3_upload_enabled():
        return

    settings = get_s3_settings()
    s3_upload = S3Operations(settings)

    path = doc.file_url
    site_path = frappe.utils.get_site_path()
    parent_doctype = doc.attached_to_doctype or "File"
    parent_name = doc.attached_to_name

    ignore_doctypes = frappe.local.conf.get("ignore_s3_upload_for_doctype") or [
        "Data Import"
    ]
    if parent_doctype in ignore_doctypes:
        return

    file_path = site_path + ("/public" + path if not doc.is_private else path)
    if not os.path.exists(file_path):
        return

    key = s3_upload.upload_files_to_s3_with_key(
        file_path, doc.file_name, doc.is_private, parent_doctype, parent_name
    )

    method_path = "frappe_ticktix.plugins.storage.s3_attachment.generate_file"
    file_url = "/api/method/{0}?key={1}&file_name={2}".format(
        method_path, key, doc.file_name
    )

    os.remove(file_path)

    frappe.db.sql(
        """UPDATE `tabFile` SET file_url=%s, folder=%s,
        old_parent=%s, content_hash=%s WHERE name=%s""",
        (file_url, "Home/Attachments", "Home/Attachments", key, doc.name),
    )
    doc.file_url = file_url

    # Only the image field itself may be repointed at the S3 url. Every other
    # attachment (child-table Attach fields, sidebar uploads) must leave the
    # parent's profile image alone. update_modified=False keeps the form's
    # timestamp valid, otherwise the next Save fails with "Document has been
    # modified after you have opened it".
    image_field = parent_name and frappe.get_meta(parent_doctype).get("image_field")
    if image_field and doc.attached_to_field == image_field:
        frappe.db.set_value(
            parent_doctype,
            parent_name,
            image_field,
            file_url,
            update_modified=False,
        )

    frappe.db.commit()


def delete_from_cloud(doc, method=None):
    """doc_events hook: File.on_trash"""
    if not s3_upload_enabled():
        return
    if not s3_file_regex_match(doc.file_url):
        return
    S3Operations().delete_from_s3(doc.content_hash)


@frappe.whitelist()
def generate_file(key=None, file_name=None):
    """
    Serve the S3 object's bytes directly through this site instead of
    redirecting to a presigned S3 URL, so the browser's address bar and
    network requests never show the S3 domain.

    Trade-off: the file now passes through the Frappe app server's
    memory/CPU/bandwidth on every view, instead of being served directly
    by S3 - fine for images/documents at moderate traffic, but loses S3's
    native byte-range support (video/audio seeking) and edge caching.
    """
    if not key:
        frappe.throw(frappe._("Key not found."), frappe.DoesNotExistError)

    s3_upload = S3Operations()
    try:
        s3_object = s3_upload.read_file_from_s3(key)
    except ClientError:
        frappe.throw(frappe._("File not found"), frappe.DoesNotExistError)

    frappe.local.response.filename = file_name or key.split("/")[-1]
    frappe.local.response.filecontent = s3_object["Body"].read()
    frappe.local.response.content_type = s3_object.get("ContentType")
    frappe.local.response.display_content_as = "inline"
    frappe.local.response.type = "download"


def upload_existing_file_to_s3(name, s3_upload=None):
    """Migrate a single already-local File doc to S3."""
    if not frappe.db.exists("File", name):
        return

    doc = frappe.get_doc("File", name)
    s3_upload = s3_upload or S3Operations()

    path = doc.file_url
    site_path = frappe.utils.get_site_path()
    parent_doctype = doc.attached_to_doctype or "File"
    parent_name = doc.attached_to_name

    file_path = site_path + ("/public" + path if not doc.is_private else path)
    if not os.path.exists(file_path):
        return

    key = s3_upload.upload_files_to_s3_with_key(
        file_path, doc.file_name, doc.is_private, parent_doctype, parent_name
    )

    method_path = "frappe_ticktix.plugins.storage.s3_attachment.generate_file"
    file_url = "/api/method/{0}?key={1}&file_name={2}".format(
        method_path, key, doc.file_name
    )

    os.remove(file_path)

    frappe.db.sql(
        """UPDATE `tabFile` SET file_url=%s, folder=%s,
        old_parent=%s, content_hash=%s WHERE name=%s""",
        (file_url, "Home/Attachments", "Home/Attachments", key, doc.name),
    )
    frappe.db.commit()


@frappe.whitelist()
def migrate_existing_files():
    """Push every File doc not already on S3 up to S3."""
    if not frappe.has_permission("TickTix Settings", "write"):
        frappe.throw(frappe._("Insufficient permissions"))

    if not s3_upload_enabled():
        frappe.throw(
            frappe._(
                "S3 storage is not enabled/configured in TickTix Settings."
            )
        )

    s3_upload = S3Operations()
    files_list = frappe.get_all("File", fields=["name", "file_url"])
    migrated = 0
    for file in files_list:
        if file["file_url"] and not s3_file_regex_match(file["file_url"]):
            upload_existing_file_to_s3(file["name"], s3_upload)
            migrated += 1

    return {"status": "success", "migrated": migrated, "total": len(files_list)}
