"""
Frappe Hooks for Employee ID Generation

Hooks into Employee doctype lifecycle
"""

import frappe
from .id_generator import generate_employee_id
from .validators import validate_employee_id


def before_insert_employee(doc, method):
    """
    Hook: before_insert for Employee doctype
    Generates employee ID if auto-generation is enabled

    Args:
        doc: Employee document
        method: Hook method name (unused)
    """
    try:
        generate_employee_id(doc, method)
    except Exception as e:
        frappe.log_error(
            title="Employee ID generation failed",
            message=f"Error generating ID in before_insert: {str(e)}"
        )
        # Re-raise to prevent employee creation if ID generation fails
        raise


def validate_employee(doc, method):
    """
    Hook: validate for Employee doctype
    Validates employee ID uniqueness

    Args:
        doc: Employee document
        method: Hook method name (unused)
    """
    try:
        validate_employee_id(doc)
    except Exception as e:
        frappe.log_error(
            title="Employee ID validation failed",
            message=f"Error validating ID in validate: {str(e)}"
        )
        # Re-raise to show validation error
        raise
