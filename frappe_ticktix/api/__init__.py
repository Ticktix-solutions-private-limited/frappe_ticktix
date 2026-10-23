"""
TickTix API Module - Simplified Structure

All API endpoints are available in versioned modules:
- v1: Current stable API version
- Future versions (v2, v3, etc.) can be added as needed

For new integrations, use the versioned endpoints directly:
- /api/method/frappe_ticktix.api.v1.jwt_api.test_jwt_auth
- /api/method/frappe_ticktix.api.v1.ticktix_login
"""

# Import current stable API for convenience
# This allows accessing v1 endpoints without the v1 prefix for simplicity
from .v1.jwt_api import *
from .v1 import *

import frappe
frappe.logger().debug("TickTix API module loaded - all endpoints available via v1")