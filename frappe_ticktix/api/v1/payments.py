"""
Payment Gateway API
===================
Endpoints for creating and verifying payments.

Currently backed by Razorpay, but the API surface is intentionally generic
so the gateway can be swapped without changing client-side integration.

Endpoints
---------
POST /api/method/frappe_ticktix.api.v1.payments.create_order
POST /api/method/frappe_ticktix.api.v1.payments.verify_payment
"""

import hmac
import hashlib

import frappe
import razorpay


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_razorpay_client():
	settings = frappe.get_single("TickTix Settings")
	key_id = settings.razorpay_key_id
	key_secret = settings.get_password("razorpay_key_secret")
	if not key_id or not key_secret:
		frappe.throw("Razorpay keys not configured in TickTix Settings")
	return razorpay.Client(auth=(key_id, key_secret))


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist()
def create_order(so_name: str):
	"""
	Create a payment gateway order.

	Args:
	    so_name: Sales Order name.

	Returns:
	    {"order_id": str, "amount": int}
	"""
	if not frappe.db.exists("Sales Order", so_name):
		frappe.throw(f"Sales Order {so_name} not found")

	so = frappe.get_doc("Sales Order", so_name)

	amount = int(so.grand_total * 100)
	currency = so.price_list_currency

	client = _get_razorpay_client()
	order = client.order.create({
		"amount": amount,
		"currency": currency,
		"receipt": so_name,
		"payment_capture": 1,
	})

	return {
		"order_id": order["id"],
		"amount": order["amount"],
	}


@frappe.whitelist()
def verify_payment(
	payment_gateway_order_id: str,
	payment_gateway_payment_id: str,
	payment_gateway_signature: str,
):
	"""
	Verify a completed payment and update the linked Sales Order.

	Steps:
	  1. Verify the HMAC-SHA256 signature (prevents tampered callbacks).
	  2. Fetch the gateway order to retrieve the SO name (never trust the client).
	  3. Confirm the Sales Order exists in Frappe.
	  4. Cross-check the captured amount against grand_total.
	  5. Confirm payment status is "captured".
	  6. Persist gateway IDs and status on the Sales Order.

	Args:
	    payment_gateway_order_id   : Order ID returned by create_order.
	    payment_gateway_payment_id : Payment ID sent in the gateway callback.
	    payment_gateway_signature  : HMAC signature sent in the gateway callback.

	Returns:
	    {"status": "ok", "so_name": str, "payment_id": str, "amount": int}
	"""
	client = _get_razorpay_client()
	settings = frappe.get_single("TickTix Settings")

	# Step 1: Verify signature cryptographically
	key_secret = settings.get_password("razorpay_key_secret").encode()
	msg = f"{payment_gateway_order_id}|{payment_gateway_payment_id}".encode()
	expected_signature = hmac.new(key_secret, msg, hashlib.sha256).hexdigest()

	if not hmac.compare_digest(expected_signature, payment_gateway_signature):
		frappe.throw("Invalid payment signature", frappe.AuthenticationError)

	# Step 2: Fetch the gateway order to get the SO name — never trust the client
	rzp_order = client.order.fetch(payment_gateway_order_id)
	so_name = rzp_order.get("receipt")
	if not so_name:
		frappe.throw("No Sales Order linked to this payment order")

	# Step 3: Verify the Sales Order exists
	if not frappe.db.exists("Sales Order", so_name):
		frappe.throw(f"Sales Order {so_name} not found")

	# Step 4: Cross-check amount
	rzp_payment = client.payment.fetch(payment_gateway_payment_id)
	so = frappe.get_doc("Sales Order", so_name)
	expected_paise = int(so.grand_total * 100)

	if rzp_payment["amount"] < expected_paise:
		frappe.throw(
			f"Amount mismatch: expected {expected_paise} paise, got {rzp_payment['amount']} paise"
		)

	# Step 5: Confirm capture
	if rzp_payment["status"] != "captured":
		frappe.throw(f"Payment not captured, current status: {rzp_payment['status']}")

	# Step 6: Persist on Sales Order (db_set skips validation/hooks, safe for submitted docs)
	so.db_set("custom_payment_gateway_order_id", payment_gateway_order_id)
	so.db_set("custom_payment_gateway_payment_id", payment_gateway_payment_id)
	so.db_set("custom_payment_gateway_status", "Success")
	so.db_set("custom_payment_gateway_message", rzp_payment.get("description") or "Payment captured successfully")

	return {
		"status": "ok",
		"so_name": so_name,
		"payment_id": payment_gateway_payment_id,
		"amount": rzp_payment["amount"],
	}