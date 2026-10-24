"""Custom login page for frappe_ticktix.

Reuses Frappe's own login context (redirect handling, provider auth URLs,
logo, app name) so the authentication flow is unchanged; only the template
(login.html) is replaced.
"""

from frappe.www.login import get_context as frappe_login_context

no_cache = True


def get_context(context):
	return frappe_login_context(context)
