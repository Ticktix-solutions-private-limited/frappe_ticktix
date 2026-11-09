"""Registry of demo data packs.

A pack is a named, versioned group of steps. Loading runs every pack that is not
yet on the site, or whose version here is higher than the one loaded. Steps must
be idempotent (use `utils.make`), because a version bump re-runs the whole pack.

To add demo data later: write the steps, append a pack here (list the packs it
needs in `requires`), and the next "Load Demo Data" click will top it up.

A step is (label, dotted path of a callable, kwargs).
"""

PACKS = [
	{
		"name": "core",
		"label": "Facilitix core (company, HR, payroll, sales, support, TickTix)",
		"version": 1,
		"expected_steps": 52,  # number of utils.step() calls, for the progress bar
		"requires": [],
		"steps": [
			("Masters", "frappe_ticktix.demo.seed_phase", {"phase": "masters"}),
			("HR & payroll", "frappe_ticktix.demo.seed_phase", {"phase": "hr"}),
			("Transactions", "frappe_ticktix.demo.seed_phase", {"phase": "transactions"}),
			("CRM & support", "frappe_ticktix.demo.seed_phase", {"phase": "crm_support"}),
			("TickTix modules", "frappe_ticktix.demo.seed_phase", {"phase": "ticktix"}),
		],
	},
]


def pack_by_name(name):
	return next((p for p in PACKS if p["name"] == name), None)
