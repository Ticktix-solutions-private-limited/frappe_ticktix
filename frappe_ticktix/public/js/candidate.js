// Loaded via app_include_js: Candidate is a custom doctype, so doctype_js hooks are ignored for it.
frappe.ui.form.on("Candidate", {
	refresh(frm) {
		if (frm.is_new() || frm.is_dirty() || frm.doc.status !== "Ready to Create Employee") return;

		frm.add_custom_button(__("Create Employee"), () => frm.trigger("create_employee")).addClass("btn-primary");
	},

	status(frm) {
		// Button appears once the status change is saved
		frm.remove_custom_button(__("Create Employee"));
	},

	async create_employee(frm) {
		const method = "frappe_ticktix.plugins.hr.candidate.create_employee";
		const { message: fields } = await frappe.call({
			method: `${method}.get_missing_fields`,
			args: { candidate: frm.doc.name },
		});

		const create = (extra) =>
			frappe
				.call({
					method: `${method}.create_employee`,
					args: { candidate: frm.doc.name, extra: extra || {} },
					freeze: true,
					freeze_message: __("Creating Employee..."),
				})
				.then(({ message }) => {
					frappe.show_alert({ message: __("Employee {0} created", [message]), indicator: "green" });
					frappe.set_route("Form", "Employee", message);
				});

		if (!fields || !fields.length) return create();

		frappe.prompt(fields, (values) => create(values), __("Additional details for Employee"), __("Create Employee"));
	},
});
