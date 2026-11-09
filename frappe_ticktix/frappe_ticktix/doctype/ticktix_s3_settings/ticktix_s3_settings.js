// Copyright (c) 2026, Ticktix Solutions and contributors
// For license information, please see license.txt

const FOLDER_PREFIX = 'attachment/';

frappe.ui.form.on('TickTix S3 Settings', {
	s3_folder_name: function(frm) {
		// the "attachment/" prefix is fixed; the user only types the site name after it
		const value = frm.doc.s3_folder_name || '';
		if (!value.startsWith(FOLDER_PREFIX)) {
			const fixed = FOLDER_PREFIX.startsWith(value)
				? FOLDER_PREFIX
				: FOLDER_PREFIX + value.replace(/^\/+/, '');
			frm.set_value('s3_folder_name', fixed);
		}
	},

	refresh: function(frm) {
		if (!frm.doc.s3_folder_name) {
			frm.set_value('s3_folder_name', FOLDER_PREFIX + (frappe.boot.sitename || ''));
		}

		frm.set_intro(__('Configure S3 attachment storage. Changes take effect immediately for new uploads.'));

		if (frm.doc.s3_enabled && !frm.is_dirty()) {
			frm.add_custom_button(__('Migrate Existing Files to S3'), function() {
				frappe.confirm(
					__('This will upload every local file attachment to S3. Continue?'),
					function() {
						frappe.call({
							method: "frappe_ticktix.plugins.storage.s3_attachment.migrate_existing_files",
							freeze: true,
							freeze_message: __('Migrating files to S3...'),
							callback: function(r) {
								if (r.message && r.message.status === "success") {
									frappe.msgprint({
										title: __('Migration Complete'),
										message: __('Migrated {0} of {1} files.', [r.message.migrated, r.message.total]),
										indicator: 'green'
									});
								}
							}
						});
					}
				);
			}, __('Storage'));
		}
	}
});

