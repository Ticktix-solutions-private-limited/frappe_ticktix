"""
Validation Module

Pattern validation and employee ID uniqueness checking
"""

import frappe
import re
from typing import Tuple, List, Dict, Any


def validate_pattern(pattern: str) -> Tuple[bool, List[str]]:
    """
    Validate an employee ID pattern
    
    Args:
        pattern: Pattern string to validate
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check if pattern is empty
    if not pattern or not pattern.strip():
        errors.append("Pattern cannot be empty")
        return False, errors
    
    # Check for at least one counter token
    if not re.search(r'\{#+\}', pattern):
        errors.append("Pattern must include at least one counter token (e.g., {####})")
    
    # Check for valid tokens only
    valid_tokens = {
        "YYYY", "YY", "MM", "DD",
        "COMPANY", "COMPANY_ABBR",
        "DEPARTMENT", "DEPARTMENT_ABBR",
        "BRANCH", "BRANCH_ABBR",
        "EMPLOYMENT_TYPE", "EMPLOYMENT_TYPE_ABBR",
    }
    
    # Find all tokens
    tokens = re.findall(r'\{([^}]+)\}', pattern)
    
    for token in tokens:
        # Skip counter tokens
        if re.match(r'^#+$', token):
            continue
        
        # Check if token is valid
        if token not in valid_tokens:
            errors.append(f"Unknown token: {{{token}}}")
    
    # Check for multiple counter tokens (not allowed)
    counter_tokens = re.findall(r'\{#+\}', pattern)
    if len(counter_tokens) > 1:
        errors.append("Pattern cannot have multiple counter tokens")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def validate_employee_id(employee_doc) -> None:
    """
    Validate employee ID uniqueness
    
    Args:
        employee_doc: Employee document
    
    Raises:
        frappe.ValidationError if duplicate found
    """
    if not employee_doc.employee_number:
        return
    
    # Check if another employee has this ID
    filters = {
        "employee_number": employee_doc.employee_number,
        "name": ["!=", employee_doc.name] if employee_doc.name else ["is", "set"]
    }
    
    existing = frappe.db.exists("Employee", filters)
    
    if existing:
        frappe.throw(
            f"Employee ID '{employee_doc.employee_number}' already exists for employee {existing}",
            frappe.DuplicateEntryError
        )


def validate_settings(settings: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate hr_employee_id_settings configuration
    
    Args:
        settings: Settings dict from config
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check required fields
    if not settings.get("pattern"):
        errors.append("Pattern is required when enabled=true")
    
    # Validate pattern if provided
    if settings.get("pattern"):
        is_valid, pattern_errors = validate_pattern(settings["pattern"])
        errors.extend(pattern_errors)
    
    # Validate case_format
    case_format = settings.get("case_format", "upper")
    if case_format not in ["upper", "lower", "preserve"]:
        errors.append(f"Invalid case_format: {case_format}. Must be 'upper', 'lower', or 'preserve'")
    
    # Validate reset_counter
    reset_counter = settings.get("reset_counter")
    if reset_counter and reset_counter not in ["never", "yearly", "monthly"]:
        errors.append(f"Invalid reset_counter: {reset_counter}. Must be 'never', 'yearly', or 'monthly'")
    
    # Validate counter_padding
    counter_padding = settings.get("counter_padding")
    if counter_padding is not None:
        if not isinstance(counter_padding, int) or counter_padding < 1 or counter_padding > 10:
            errors.append("counter_padding must be an integer between 1 and 10")
    
    is_valid = len(errors) == 0
    return is_valid, errors


def check_required_fields(employee_doc, pattern: str) -> List[str]:
    """
    Check if employee has all required fields for the pattern
    
    Args:
        employee_doc: Employee document
        pattern: Pattern string
    
    Returns:
        List of missing field warnings
    """
    warnings = []
    
    # Map tokens to employee fields
    token_field_map = {
        "COMPANY": "company",
        "COMPANY_ABBR": "company",
        "DEPARTMENT": "department",
        "DEPARTMENT_ABBR": "department",
        "BRANCH": "branch",
        "BRANCH_ABBR": "branch",
        "EMPLOYMENT_TYPE": "employment_type",
        "EMPLOYMENT_TYPE_ABBR": "employment_type",
    }
    
    # Check each token
    for token, field in token_field_map.items():
        if f"{{{token}}}" in pattern:
            if not employee_doc.get(field):
                warnings.append(f"Field '{field}' is required for token {{{token}}} but is not set")
    
    return warnings
