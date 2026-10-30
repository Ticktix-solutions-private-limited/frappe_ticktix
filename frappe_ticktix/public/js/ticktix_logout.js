// Override Frappe's logout so the browser redirects to Zitadel end_session after the server clears the Frappe session.
$(document).ready(function () {
	function attach_logout_override() {
		if (!window.frappe || !window.frappe.app || !window.frappe.call) {
			setTimeout(attach_logout_override, 100);
			return;
		}

		if (frappe.app.logout && frappe.app.logout.__ticktix_override__) {
			return;
		}

		var original_logout = frappe.app.logout;

		frappe.app.logout = function () {
			frappe.dom.freeze("Logging out...");

			return frappe.call({
				method: "frappe_ticktix.api.ticktix_logout",
				callback: function (r) {
					frappe.dom.unfreeze();

					var redirect_url = r && r.message && (r.message.redirect_to || r.message.redirect_url);
					if (redirect_url) {
						window.location.href = redirect_url;
						return;
					}

					if (original_logout) {
						return original_logout.apply(this, arguments);
					}

					window.location.href = "/login";
				}.bind(this),
				error: function () {
					frappe.dom.unfreeze();
					if (original_logout) {
						return original_logout();
					}
					window.location.href = "/login";
				}
			});
		};

		frappe.app.logout.__ticktix_override__ = true;
	}

	attach_logout_override();
});
