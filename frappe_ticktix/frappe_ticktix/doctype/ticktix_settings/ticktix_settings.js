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

		ticktix_demo.setup(frm);

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

// Demo data: load, top-up and clear, run as a background job with a progress dialog
const ticktix_demo = {
	api: "frappe_ticktix.demo.api.",
	dialog: null,

	setup(frm) {
		if (!frappe.user.has_role("System Manager")) return;
		frappe.call({ method: this.api + "get_status" }).then((r) => {
			const s = r.message;
			if (!s) return;
			if (s.busy) {
				this.show_progress(frm, s);
				return;
			}
			if (s.pending.length) {
				const label = s.has_data ? __("Load New Demo Data") : __("Load Demo Data");
				frm.add_custom_button(label, () => this.confirm_load(frm, s), __("Demo Data"));
			}
			if (s.has_data) {
				frm.add_custom_button(__("Clear Demo Data"), () => this.confirm_clear(frm, s), __("Demo Data"));
			}
			if (s.status === "Failed" && s.error) {
				frm.dashboard.set_headline_alert(
					__("The last demo data run stopped with errors. Click the Demo Data button to continue.") +
						"<pre style='max-height:120px;overflow:auto'>" + frappe.utils.escape_html(s.error) + "</pre>",
					"red"
				);
			} else if (s.status === "Loaded") {
				frm.dashboard.set_headline_alert(
					__("Demo data for {0} is loaded (as of {1}).", [s.company, s.anchor_date]),
					"blue"
				);
			}
		});
	},

	confirm_load(frm, s) {
		frappe.confirm(
			__("This adds sample data ({0}) to this site under the company {1}. It takes a few minutes and runs in the background. Continue?", [
				s.pending.join(", "),
				s.company,
			]),
			() => frappe.call({ method: this.api + "load_demo_data" }).then((r) => this.show_progress(frm, r.message))
		);
	},

	confirm_clear(frm, s) {
		frappe.call({ method: this.api + "check_clear", freeze: true, freeze_message: __("Checking what depends on the demo data…") }).then((r) => {
			const c = r.message || {};
			if (c.blockers && c.blockers.length) {
				const rows = c.blockers
					.slice(0, 50)
					.map((b) => `<li>${frappe.utils.get_form_link(b.doctype, b.name, true)} <span class="text-muted">(${__("uses demo")} ${b.uses.join(", ")})</span></li>`)
					.join("");
				frappe.msgprint({
					title: __("Demo data is in use"),
					indicator: "red",
					message: `<p>${__("These records are not part of the demo, but they use demo data. Delete them or point them at your own data, then try again.")}</p><ul>${rows}</ul>${c.blockers.length > 50 ? "<p>… " + __("and {0} more", [c.blockers.length - 50]) + "</p>" : ""}`,
				});
				return;
			}
			let msg = __("This permanently deletes the demo company {0} and its {1} demo records. Your own data is not touched.", [c.company, c.demo_records]);
			const extra = Object.entries(c.own_in_company || {});
			if (extra.length) {
				msg += "<br><br><b>" + __("Also deleted, because they belong to the demo company:") + "</b><ul>" +
					extra.map(([dt, n]) => `<li>${n} × ${__(dt)}</li>`).join("") + "</ul>";
			}
			msg += "<br>" + __("Continue?");
			frappe.confirm(msg, () => frappe.call({ method: this.api + "clear_demo_data" }).then((r2) => this.show_progress(frm, r2.message)));
		});
	},

	show_progress(frm, s) {
		// already showing: the form refreshes often, never rebuild the dialog
		if (this.dialog) return;

		const d = new frappe.ui.Dialog({
			title: s.status === "Clearing" ? __("Clearing Demo Data") : __("Loading Demo Data"),
			static: true,
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
		});
		d.$wrapper.find(".modal-header .btn-modal-close").hide();
		d.fields_dict.body.$wrapper.html(`
			<div class="progress" style="height: 12px">
				<div class="progress-bar" role="progressbar" style="width: 0%; transition: width .6s ease"></div>
			</div>
			<p class="demo-msg text-muted" style="margin-top: 12px"></p>
			<p class="text-muted small">${__("You can close this page. The job keeps running and this screen returns when you reopen TickTix Settings.")}</p>`);
		const $bar = d.fields_dict.body.$wrapper.find(".progress-bar");
		const $msg = d.fields_dict.body.$wrapper.find(".demo-msg");

		// update in place, never go backwards, ignore updates without a percent
		let shown = 0;
		const render = (percent, message) => {
			if (percent != null && percent > shown) {
				shown = percent;
				$bar.css("width", shown + "%");
			}
			if (message) $msg.text(message);
		};
		render(s.percent, s.message || __("Starting…"));
		d.show();
		this.dialog = d;

		let finished = false;
		const finish = () => {
			if (finished) return;
			finished = true;
			frappe.realtime.off("ticktix_demo_progress");
			clearInterval(this.timer);
			render(100);
			frappe.call({ method: this.api + "get_status" }).then((r) => {
				const st = r.message || {};
				setTimeout(() => {
					d.hide();
					this.dialog = null;
					frappe.msgprint({
						title: st.status === "Failed" ? __("Stopped with errors") : __("Done"),
						message: st.status === "Failed" ? frappe.utils.escape_html(st.error || "") : st.message,
						indicator: st.status === "Failed" ? "red" : "green",
					});
					frm.reload_doc();
				}, 700);
			});
		};

		frappe.realtime.off("ticktix_demo_progress");
		frappe.realtime.on("ticktix_demo_progress", (data) => {
			if (data.done) return finish();
			render(data.percent, data.message);
		});
		// realtime can be missed (socket drop); poll as a safety net
		this.timer = setInterval(() => {
			frappe.call({ method: this.api + "get_status", freeze: false }).then((r) => {
				const st = r.message;
				if (!st) return;
				if (st.status !== "Loading" && st.status !== "Clearing") return finish();
				render(st.percent, st.message);
			});
		}, 4000);
	},
};
