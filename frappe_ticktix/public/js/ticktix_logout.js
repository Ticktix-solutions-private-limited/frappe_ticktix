// Override Frappe's logout to redirect to Zitadel end_session and clear the IdP session.
$(document).ready(function () {
	var _original_call = frappe.call;

	frappe.call = function (opts) {
		if (opts && opts.method === "logout") {
			frappe.dom.freeze("Logging out...");

			var original_callback = opts.callback;
			opts.callback = function (r) {
				var redirect_to =
					r && r.message && r.message.redirect_to;
				if (redirect_to) {
					window.location.href = redirect_to;
					return;
				}
				frappe.dom.unfreeze();
				if (original_callback) original_callback(r);
			};
		}
		return _original_call.call(this, opts);
	};
});
