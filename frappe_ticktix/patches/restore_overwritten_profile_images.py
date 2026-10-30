"""
Repair profile images overwritten by the S3 upload hook.

Before the fix in plugins/storage/s3_attachment.py, attaching any file to a
document whose doctype has an image_field (e.g. Employee) replaced that image
with the uploaded file's url, so a PDF in the Documents table became the
employee's profile picture.

For every document whose image points at a File attached through some other
field (or at a non-image file whose File record is gone), restore the most recent file attached through the image field itself.
When there is none the image is left as is and reported, so nothing is guessed.

Not listed in patches.txt: review the output of a run first.

Run: bench --site <sitename> execute frappe_ticktix.patches.restore_overwritten_profile_images.execute
"""

from urllib.parse import parse_qs, urlparse

import frappe

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico", ".tif", ".tiff")


def points_at_non_image(file_url):
    """True when an S3 file_url names a file that cannot be a profile picture"""
    file_name = (parse_qs(urlparse(file_url).query).get("file_name") or [""])[0]
    return bool(file_name) and not file_name.lower().endswith(IMAGE_EXTENSIONS)


def execute():
    restored, unresolved = [], []

    for doctype in frappe.get_all("DocType", filters={"image_field": ["!=", ""]}, pluck="name"):
        image_field = frappe.get_meta(doctype).image_field
        if not image_field or not frappe.db.has_column(doctype, image_field):
            continue

        for doc in frappe.get_all(
            doctype, filters={image_field: ["like", "%generate_file%"]}, fields=["name", image_field]
        ):
            current = doc[image_field]
            overwriting = frappe.db.exists(
                "File",
                {
                    "attached_to_doctype": doctype,
                    "attached_to_name": doc.name,
                    "file_url": current,
                    "attached_to_field": ["not in", [image_field, ""]],
                },
            )
            if not overwriting and not points_at_non_image(current):
                continue

            genuine = frappe.db.get_value(
                "File",
                {
                    "attached_to_doctype": doctype,
                    "attached_to_name": doc.name,
                    "attached_to_field": image_field,
                },
                "file_url",
                order_by="creation desc",
            )
            if genuine:
                frappe.db.set_value(doctype, doc.name, image_field, genuine, update_modified=False)
                restored.append((doctype, doc.name))
            else:
                unresolved.append((doctype, doc.name, current))

    frappe.db.commit()
    print(f"Restored {len(restored)} profile image(s): {restored}")
    if unresolved:
        print(f"No earlier image to restore for {len(unresolved)} document(s), left unchanged:")
        for row in unresolved:
            print("  ", row)
