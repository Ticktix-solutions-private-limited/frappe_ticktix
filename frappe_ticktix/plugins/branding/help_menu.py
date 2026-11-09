"""Help dropdown customisation for the desk navbar.

The Help menu lives in the Navbar Settings single doctype. Frappe builds the
desk's `navbar_settings` boot data after all boot hooks have run, so it cannot be
adjusted at boot time; instead this updates the Navbar Settings record itself.
It is called from after_install and after_migrate (see install.py) and is
idempotent, so every site that has frappe_ticktix gets the same Help menu.

Standard items are hidden rather than deleted, as Frappe requires.

Defaults below can be overridden per site in site_config.json:

	"ticktix": {
		"help_menu": {
			"links": {"Documentation": "https://example.com/docs"},
			"remove": ["User Forum"]
		}
	}
"""

import frappe

from ...config.config_manager import get_config_manager

# menu label -> URL (external links open in a new tab, see public/js/help_menu.bundle.js)
DEFAULT_LINKS = {
	"Documentation": "https://www.ticktix.com/docs",
	"Report an Issue": "https://www.ticktix.com/report-issue",
	"About": "https://www.ticktix.com/about",
}

# menu labels to hide
DEFAULT_REMOVE = ["User Forum", "Frappe School", "Frappe Support"]


def _settings():
	links = dict(DEFAULT_LINKS)
	remove = list(DEFAULT_REMOVE)
	cfg = (get_config_manager().get_config_value("ticktix", {}) or {}).get("help_menu") or {}
	links.update(cfg.get("links") or {})
	if "remove" in cfg:
		remove = list(cfg.get("remove") or [])
	return links, remove


def apply_help_menu():
	"""Hide unwanted Help items and point the rest at the Ticktix pages."""
	try:
		if not frappe.db.exists("DocType", "Navbar Settings"):
			return

		links, remove = _settings()
		remove_labels = {r.strip().lower() for r in remove}
		link_by_label = {k.strip().lower(): v for k, v in links.items()}

		doc = frappe.get_doc("Navbar Settings")
		changed = False

		for row in doc.help_dropdown:
			label = (row.item_label or "").strip().lower()

			if label in remove_labels:
				if not row.hidden:
					row.hidden = 1
					changed = True
				continue

			url = link_by_label.get(label)
			if url:
				# a real link (so the browser shows the URL on hover); the new-tab
				# behaviour comes from public/js/help_menu.bundle.js
				if row.item_type != "Route" or row.route != url or row.action or row.hidden:
					row.item_type = "Route"
					row.route = url
					row.action = None
					row.hidden = 0
					changed = True

		if changed:
			doc.save(ignore_permissions=True)
			frappe.clear_cache(doctype="Navbar Settings")
			print("FRAPPE_TICKTIX: Help menu updated")
	except Exception:
		# never block install / migrate because of the help menu
		frappe.log_error(title="Help menu customisation failed", message=frappe.get_traceback())
