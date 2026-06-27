# Copyright (c) 2024, Ticktix Solutions private limited and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document


class TickTixSettings(Document):
	"""TickTix Settings DocType for configuring OAuth and JWT authentication."""
	
	def validate(self):
		"""Validate settings before saving."""
		self.validate_jwt_config()
		self.validate_oauth_config()
		self.validate_role_mapping()
		self.validate_custom_claims()
	
	def validate_jwt_config(self):
		"""Validate JWT configuration fields."""
		if self.jwt_enabled:
			# Validate based on validation method
			if self.jwt_validation_method == 'secret':
				if not self.jwt_secret_key:
					frappe.throw("JWT Secret Key is required when using secret validation method")
			
			elif self.jwt_validation_method == 'jwks':
				if not self.jwt_jwks_uri and not self.jwt_issuer:
					frappe.throw("Either JWKS URI or JWT Issuer is required for JWKS validation method")
			
			# Validate issuer format
			if self.jwt_issuer and not (self.jwt_issuer.startswith('http://') or self.jwt_issuer.startswith('https://')):
				frappe.throw("JWT Issuer must be a valid URL starting with http:// or https://")
			
			# Validate JWKS URI format 
			if self.jwt_jwks_uri and not (self.jwt_jwks_uri.startswith('http://') or self.jwt_jwks_uri.startswith('https://')):
				frappe.throw("JWKS URI must be a valid URL starting with http:// or https://")
	
	def validate_oauth_config(self):
		"""Validate OAuth configuration fields."""
		if self.ticktix_base_url:
			if not (self.ticktix_base_url.startswith('http://') or self.ticktix_base_url.startswith('https://')):
				frappe.throw("TickTix Base URL must be a valid URL starting with http:// or https://")
		
		if self.company_logo_url:
			if not (self.company_logo_url.startswith('http://') or self.company_logo_url.startswith('https://') or self.company_logo_url.startswith('/')):
				frappe.throw("Company Logo URL must be a valid URL or absolute path")
	
	def validate_role_mapping(self):
		"""Validate JWT role mapping JSON."""
		if self.jwt_role_mapping_json:
			try:
				role_mapping = json.loads(self.jwt_role_mapping_json)
				if not isinstance(role_mapping, dict):
					frappe.throw("JWT Role Mapping must be a valid JSON object")
				
				# Validate that Frappe roles exist
				for jwt_role, frappe_roles in role_mapping.items():
					if isinstance(frappe_roles, str):
						frappe_roles = [frappe_roles]
					
					for role in frappe_roles:
						if not frappe.db.exists("Role", role):
							frappe.throw(f"Frappe role '{role}' does not exist in role mapping")
			
			except json.JSONDecodeError:
				frappe.throw("JWT Role Mapping must be valid JSON")
	
	def validate_custom_claims(self):
		"""Validate custom claims JSON."""
		if self.jwt_custom_claims_json:
			try:
				custom_claims = json.loads(self.jwt_custom_claims_json)
				if not isinstance(custom_claims, dict):
					frappe.throw("Custom Claims Validation must be a valid JSON object")
			except json.JSONDecodeError:
				frappe.throw("Custom Claims Validation must be valid JSON")
	
	def get_jwt_config(self):
		"""Get JWT configuration as a dictionary."""
		config = {
			'enabled': self.jwt_enabled,
			'validation_method': self.jwt_validation_method or 'jwks',
			'algorithm': self.jwt_algorithm or 'RS256',
			'issuer': self.jwt_issuer,
			'audience': self.jwt_audience,
			'secret_key': self.get_password('jwt_secret_key') if self.jwt_secret_key else None,
			'jwks_uri': self.jwt_jwks_uri,
			'auto_provision_users': self.jwt_auto_provision_users or False,
			'default_user_type': self.jwt_default_user_type or 'System User',
		}
		
		# Parse list fields
		if self.jwt_required_scopes:
			config['required_scopes'] = [s.strip() for s in self.jwt_required_scopes.split(',') if s.strip()]
		else:
			config['required_scopes'] = []
		
		if self.jwt_allowed_email_domains:
			config['allowed_email_domains'] = [d.strip() for d in self.jwt_allowed_email_domains.split(',') if d.strip()]
		else:
			config['allowed_email_domains'] = []
			
		if self.jwt_default_roles:
			config['default_roles'] = [r.strip() for r in self.jwt_default_roles.split(',') if r.strip()]
		else:
			config['default_roles'] = ['Desk User']
		
		# Parse JSON fields
		if self.jwt_role_mapping_json:
			try:
				config['jwt_role_mapping'] = json.loads(self.jwt_role_mapping_json)
			except json.JSONDecodeError:
				config['jwt_role_mapping'] = {}
		else:
			config['jwt_role_mapping'] = {}
		
		if self.jwt_custom_claims_json:
			try:
				config['custom_claims'] = json.loads(self.jwt_custom_claims_json)
			except json.JSONDecodeError:
				config['custom_claims'] = {}
		else:
			config['custom_claims'] = {}
		
		return config
	
	@frappe.whitelist()
	def test_jwt_connection(self):
		"""Test JWT configuration by attempting to fetch JWKS if using JWKS method."""
		if not self.jwt_enabled:
			return {"status": "disabled", "message": "JWT authentication is disabled"}
		
		if self.jwt_validation_method == 'jwks' and self.jwt_jwks_uri:
			try:
				import requests
				response = requests.get(self.jwt_jwks_uri, timeout=10)
				response.raise_for_status()
				
				jwks_data = response.json()
				keys_count = len(jwks_data.get('keys', []))
				
				return {
					"status": "success", 
					"message": f"JWKS endpoint is reachable with {keys_count} keys",
					"keys_count": keys_count
				}
			except Exception as e:
				return {"status": "error", "message": f"Failed to connect to JWKS endpoint: {str(e)}"}
		
		elif self.jwt_validation_method == 'secret':
			if self.jwt_secret_key:
				return {"status": "success", "message": "JWT secret key is configured"}
			else:
				return {"status": "error", "message": "JWT secret key is not configured"}
		
		else:
			return {"status": "error", "message": "JWT validation method not properly configured"}


def get_jwt_config_from_settings():
	"""Helper function to get JWT config from TickTix Settings."""
	try:
		settings = frappe.get_single("TickTix Settings")
		return settings.get_jwt_config()
	except Exception:
		return {
			'enabled': False,
			'validation_method': 'jwks',
			'algorithm': 'RS256'
		}