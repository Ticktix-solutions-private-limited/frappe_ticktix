// Copyright (c) 2024, Ticktix Solutions private limited and contributors
// For license information, please see license.txt

frappe.ui.form.on('TickTix Settings', {
	refresh: function(frm) {
		// Add custom buttons
		frm.add_custom_button(__('Test JWT Configuration'), function() {
			frappe.call({
				method: "test_jwt_connection",
				doc: frm.doc,
				callback: function(r) {
					if (r.message) {
						if (r.message.status === "success") {
							frappe.msgprint({
								title: __('JWT Test Successful'),
								message: r.message.message,
								indicator: 'green'
							});
						} else {
							frappe.msgprint({
								title: __('JWT Test Failed'),
								message: r.message.message,
								indicator: 'red'
							});
						}
					}
				}
			});
		}, __('JWT'));
		
		frm.add_custom_button(__('Clear JWKS Cache'), function() {
			frappe.call({
				method: "frappe_ticktix.auth.jwt_validator.clear_jwks_cache",
				callback: function(r) {
					frappe.msgprint(__('JWKS cache cleared successfully'));
				}
			});
		}, __('JWT'));
		
		// Add help section
		frm.set_intro(__('Configure TickTix OAuth and JWT authentication settings. Changes take effect immediately.'));
	},
	
	jwt_validation_method: function(frm) {
		// Show/hide relevant sections based on validation method
		frm.refresh_fields();
	},
	
	jwt_role_mapping_json: function(frm) {
		// Validate JSON on blur
		if (frm.doc.jwt_role_mapping_json) {
			try {
				JSON.parse(frm.doc.jwt_role_mapping_json);
			} catch (e) {
				frappe.msgprint({
					title: __('Invalid JSON'),
					message: __('JWT Role Mapping contains invalid JSON: ') + e.message,
					indicator: 'red'
				});
			}
		}
	},
	
	jwt_custom_claims_json: function(frm) {
		// Validate JSON on blur
		if (frm.doc.jwt_custom_claims_json) {
			try {
				JSON.parse(frm.doc.jwt_custom_claims_json);
			} catch (e) {
				frappe.msgprint({
					title: __('Invalid JSON'),
					message: __('Custom Claims Validation contains invalid JSON: ') + e.message,
					indicator: 'red'
				});
			}
		}
	}
});