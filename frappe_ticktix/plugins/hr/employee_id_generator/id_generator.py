"""
ID Generator Module

Core employee ID generation engine
"""

import frappe
from typing import Optional, Dict, Any
from .token_resolver import get_token_resolver
from .counter_manager import get_counter_manager
from .validators import validate_employee_id, check_required_fields, validate_settings


def generate_employee_id(employee_doc, method=None) -> Optional[str]:
    """
    Generate employee ID for a new employee

    This is the main entry point called from hooks

    Args:
        employee_doc: Employee document
        method: Hook method (unused, required by Frappe)

    Returns:
        Generated employee ID or None if disabled
    """
    # Get settings from ticktix namespace
    ticktix_config = frappe.conf.get("ticktix", {})
    settings = ticktix_config.get('hr_employee_id_settings', {})

    # Check if enabled
    if not settings.get("enabled", False):
        return None

    # Check if manual override is allowed and ID is already set
    if settings.get("allow_manual_override", False) and employee_doc.employee_number:
        # User manually entered an ID, validate it but don't override
        validate_employee_id(employee_doc)
        return employee_doc.employee_number

    # Validate settings
    is_valid, errors = validate_settings(settings)
    if not is_valid:
        frappe.log_error(
            message=f"Invalid hr_employee_id_settings: {', '.join(errors)}",
            title="Employee ID Generation"
        )
        frappe.throw(f"Employee ID generation failed: Invalid configuration. {errors[0]}")

    pattern = settings.get("pattern")

    # Check required fields
    warnings = check_required_fields(employee_doc, pattern)
    if warnings:
        frappe.log_error(
            message=f"Missing fields for employee ID generation: {', '.join(warnings)}",
            title="Employee ID Generation"
        )
        # Don't throw, just log warning and continue with empty values

    # Generate ID with retry logic for uniqueness
    max_attempts = 100
    for attempt in range(max_attempts):
        try:
            employee_id = _generate_id(employee_doc, settings)

            # Set the ID
            employee_doc.employee_number = employee_id

            # Validate uniqueness
            validate_employee_id(employee_doc)

            # Success!
            return employee_id

        except frappe.DuplicateEntryError:
            # ID already exists, try again with incremented counter
            if attempt == max_attempts - 1:
                frappe.throw(
                    f"Failed to generate unique employee ID after {max_attempts} attempts. "
                    "Please check your pattern configuration."
                )
            continue
        except Exception as e:
            frappe.log_error(message=f"Error generating employee ID: {str(e)}", title="Employee ID Generation")
            raise

    return None


def preview_employee_id(employee_doc) -> str:
    """
    Preview what employee ID would be generated WITHOUT actually generating it

    Args:
        employee_doc: Employee document

    Returns:
        Preview of employee ID
    """
    # Get settings from ticktix namespace
    ticktix_config = frappe.conf.get("ticktix", {})
    settings = ticktix_config.get('hr_employee_id_settings', {})

    if not settings.get("enabled", False):
        return "Employee ID generation is disabled"

    pattern = settings.get("pattern")

    # Get components
    token_resolver = get_token_resolver(employee_doc, settings)
    counter_manager = get_counter_manager(settings)

    # Extract scope
    scope_components = token_resolver.extract_scope_components(pattern)
    component_values = token_resolver.get_scope_key_components()
    scope_key = counter_manager.build_scope_key(scope_components, component_values)

    # Preview counter (without incrementing)
    counter_value = counter_manager.preview_counter(scope_key)

    # Resolve tokens
    employee_id = token_resolver.resolve_tokens(pattern, counter_value)

    return employee_id


def _generate_id(employee_doc, settings: Dict[str, Any]) -> str:
    """
    Internal ID generation logic

    Args:
        employee_doc: Employee document
        settings: hr_employee_id_settings

    Returns:
        Generated employee ID
    """
    pattern = settings.get("pattern")

    # Initialize components
    token_resolver = get_token_resolver(employee_doc, settings)
    counter_manager = get_counter_manager(settings)

    # Extract scope from pattern
    scope_components = token_resolver.extract_scope_components(pattern)

    # Get actual component values from employee
    component_values = token_resolver.get_scope_key_components()

    # Build scope key
    scope_key = counter_manager.build_scope_key(scope_components, component_values)

    # Get next counter
    counter_value = counter_manager.get_next_counter(scope_key)

    # Resolve all tokens
    employee_id = token_resolver.resolve_tokens(pattern, counter_value)

    return employee_id
