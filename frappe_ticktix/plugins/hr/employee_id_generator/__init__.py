"""
Employee ID Auto-Generation Plugin

Automatically generates unique employee IDs when new employees are created.
Uses a flexible pattern-based system with auto-detected counter scoping.
"""

from .id_generator import generate_employee_id, preview_employee_id
from .validators import validate_pattern, validate_employee_id

__all__ = [
    "generate_employee_id",
    "preview_employee_id",
    "validate_pattern",
    "validate_employee_id",
]
