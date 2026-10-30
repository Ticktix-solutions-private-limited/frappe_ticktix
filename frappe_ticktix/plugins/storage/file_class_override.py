"""
File class override for S3-stored attachments.

Files on S3 are served through
/api/method/frappe_ticktix.plugins.storage.s3_attachment.generate_file?key=...
Frappe already treats /api/method/ urls as remote files, but File.get_full_path()
still runs its local path safety check on them and throws "Cannot access file
path ...". Anything that builds a File record from such a url then fails, for
example Employee.update_user() copying the employee image to a user that has no
profile image yet, which broke saving the employee.

An S3 url is not a path on disk, so hand it back untouched; validate_file_on_disk()
already accepts urls.
"""

from frappe.core.doctype.file.file import File

from frappe_ticktix.plugins.storage.s3_attachment import s3_file_regex_match


class TickTixFile(File):
    def get_full_path(self):
        if s3_file_regex_match(self.file_url):
            return self.file_url
        return super().get_full_path()
