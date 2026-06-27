# Services package — geo travel distance & time processing pipeline.
#
# Layer responsibilities:
#   geo_utils.py          — Pure Python helpers (no Frappe imports).
#   distance_calculator.py — Pure math: Haversine, noise filters, aggregation.
#   geo_processing.py     — Frappe orchestration: DB fetch, dispatch, upsert.
