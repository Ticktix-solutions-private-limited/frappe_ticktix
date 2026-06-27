"""
Token Resolution Module

Handles parsing and resolution of pattern tokens like {COMPANY_ABBR}, {YYYY}, {####}
"""

import frappe
import re
from datetime import datetime
from typing import Dict, Any, Optional


class TokenResolver:
    """Resolves tokens in employee ID patterns"""
    
    # Token patterns
    DATE_TOKENS = {
        "YYYY": lambda: datetime.now().strftime("%Y"),
        "YY": lambda: datetime.now().strftime("%y"),
        "MM": lambda: datetime.now().strftime("%m"),
        "DD": lambda: datetime.now().strftime("%d"),
    }
    
    ENTITY_TOKENS = [
        "COMPANY",
        "COMPANY_ABBR",
        "DEPARTMENT",
        "DEPARTMENT_ABBR",
        "BRANCH",
        "BRANCH_ABBR",
        "EMPLOYMENT_TYPE",
        "EMPLOYMENT_TYPE_ABBR",
    ]
    
    FALLBACK_LENGTHS = {
        "Company": 3,
        "Department": 3,
        "Branch": 3,
        "Employment Type": 2,
    }
    
    def __init__(self, employee_doc, settings: Dict[str, Any]):
        """
        Initialize token resolver
        
        Args:
            employee_doc: Employee document
            settings: hr_employee_id_settings from config
        """
        self.employee = employee_doc
        self.settings = settings
        self._cache = {}
    
    def resolve_tokens(self, pattern: str, counter_value: Optional[int] = None) -> str:
        """
        Resolve all tokens in the pattern
        
        Args:
            pattern: Pattern string with tokens
            counter_value: Optional counter value (for preview mode)
        
        Returns:
            Resolved pattern string
        """
        result = pattern
        
        # Resolve date tokens
        for token, resolver in self.DATE_TOKENS.items():
            result = result.replace(f"{{{token}}}", resolver())
        
        # Resolve entity tokens
        for token in self.ENTITY_TOKENS:
            if f"{{{token}}}" in result:
                value = self._resolve_entity_token(token)
                result = result.replace(f"{{{token}}}", value)
        
        # Resolve counter token (if provided)
        if counter_value is not None:
            result = self._resolve_counter_token(result, counter_value)
        
        # Apply case format
        case_format = self.settings.get("case_format", "upper")
        result = self._apply_case_format(result, case_format)
        
        return result
    
    def _resolve_entity_token(self, token: str) -> str:
        """
        Resolve an entity token (COMPANY, DEPARTMENT, etc.)
        
        Args:
            token: Token name
        
        Returns:
            Resolved value
        """
        # Check cache first
        if token in self._cache:
            return self._cache[token]
        
        # Parse token
        is_abbr = token.endswith("_ABBR")
        entity_name = token.replace("_ABBR", "")
        
        # Get entity value from employee
        field_map = {
            "COMPANY": "company",
            "DEPARTMENT": "department",
            "BRANCH": "branch",
            "EMPLOYMENT_TYPE": "employment_type",
        }
        
        field_name = field_map.get(entity_name)
        if not field_name:
            frappe.throw(f"Unknown token: {{{token}}}")
        
        entity_value = self.employee.get(field_name)
        if not entity_value:
            # Return placeholder or empty string if field not set
            return ""
        
        # If not abbreviation, return the value as-is
        if not is_abbr:
            result = entity_value
        else:
            # Get abbreviation
            doctype_map = {
                "COMPANY": "Company",
                "DEPARTMENT": "Department",
                "BRANCH": "Branch",
                "EMPLOYMENT_TYPE": "Employment Type",
            }
            doctype = doctype_map[entity_name]
            result = self._get_abbreviation(doctype, entity_value)
        
        # Cache and return
        self._cache[token] = result
        return result
    
    def _get_abbreviation(self, doctype: str, entity_name: str) -> str:
        """
        Get abbreviation for an entity using hybrid resolution
        
        Priority:
        1. Config override
        2. DocType field (abbr or custom_abbr)
        3. Auto-fallback
        
        Args:
            doctype: DocType name
            entity_name: Entity name
        
        Returns:
            Abbreviation string
        """
        # 1. Check config override
        config_abbr = self._get_config_abbreviation(doctype, entity_name)
        if config_abbr:
            return config_abbr
        
        # 2. Check doctype field
        abbr_field_map = {
            "Company": "abbr",           # Built-in field
            "Department": "custom_abbr", # Custom field
            "Branch": "custom_abbr",     # Custom field
            "Employment Type": "custom_abbr",  # Custom field
        }
        
        abbr_field = abbr_field_map.get(doctype)
        if abbr_field:
            try:
                abbr = frappe.db.get_value(doctype, entity_name, abbr_field)
                if abbr:
                    return abbr
            except Exception:
                # Field might not exist yet (pre-migration)
                pass
        
        # 3. Auto-fallback to first N characters
        fallback_length = self.FALLBACK_LENGTHS.get(doctype, 3)
        return entity_name[:fallback_length].upper()
    
    def _get_config_abbreviation(self, doctype: str, entity_name: str) -> Optional[str]:
        """
        Get abbreviation from config
        
        Args:
            doctype: DocType name
            entity_name: Entity name
        
        Returns:
            Abbreviation if found in config, None otherwise
        """
        abbreviations = self.settings.get("abbreviations", {})
        
        # Map doctype to config key
        config_key_map = {
            "Company": "companies",
            "Department": "departments",
            "Branch": "branches",
            "Employment Type": "employment_types",
        }
        
        config_key = config_key_map.get(doctype)
        if not config_key:
            return None
        
        entity_abbrs = abbreviations.get(config_key, {})
        return entity_abbrs.get(entity_name)
    
    def _resolve_counter_token(self, pattern: str, counter_value: int) -> str:
        """
        Resolve counter token {####}
        
        Args:
            pattern: Pattern string
            counter_value: Counter value
        
        Returns:
            Pattern with counter resolved
        """
        # Find counter token pattern
        counter_match = re.search(r'\{(#+)\}', pattern)
        if not counter_match:
            return pattern
        
        # Get padding from counter_padding setting or auto-detect
        counter_padding = self.settings.get("counter_padding")
        if counter_padding is None:
            # Auto-detect from number of # symbols
            counter_padding = len(counter_match.group(1))
        
        # Format counter with padding
        counter_str = str(counter_value).zfill(counter_padding)
        
        # Replace counter token
        result = pattern.replace(counter_match.group(0), counter_str)
        return result
    
    def _apply_case_format(self, text: str, case_format: str) -> str:
        """
        Apply case formatting
        
        Args:
            text: Input text
            case_format: 'upper', 'lower', or 'preserve'
        
        Returns:
            Formatted text
        """
        if case_format == "upper":
            return text.upper()
        elif case_format == "lower":
            return text.lower()
        else:  # preserve
            return text
    
    def extract_scope_components(self, pattern: str) -> Dict[str, Any]:
        """
        Extract scope components from pattern for counter key generation
        
        Returns dict with detected entity types and temporal scope
        
        Args:
            pattern: Pattern string
        
        Returns:
            Dict with 'entities' list and 'temporal' scope
        """
        entities = []
        temporal = None
        
        # Check for entity tokens
        if "{COMPANY_ABBR}" in pattern or "{COMPANY}" in pattern:
            entities.append("company")
        if "{DEPARTMENT_ABBR}" in pattern or "{DEPARTMENT}" in pattern:
            entities.append("department")
        if "{BRANCH_ABBR}" in pattern or "{BRANCH}" in pattern:
            entities.append("branch")
        if "{EMPLOYMENT_TYPE_ABBR}" in pattern or "{EMPLOYMENT_TYPE}" in pattern:
            entities.append("employment_type")
        
        # Check for temporal tokens
        if "{MM}" in pattern:
            temporal = "monthly"
        elif "{YYYY}" in pattern or "{YY}" in pattern:
            temporal = "yearly"
        
        # Check for reset_counter override
        reset_counter = self.settings.get("reset_counter")
        if reset_counter:
            if reset_counter == "monthly":
                temporal = "monthly"
            elif reset_counter == "yearly":
                temporal = "yearly"
            elif reset_counter == "never":
                temporal = None
        
        return {
            "entities": entities,
            "temporal": temporal,
        }
    
    def get_scope_key_components(self) -> Dict[str, str]:
        """
        Get actual values for scope key components from employee doc
        
        Returns:
            Dict with entity values (company, department, etc.)
        """
        components = {}
        
        if self.employee.get("company"):
            components["company"] = self.employee.company
        if self.employee.get("department"):
            components["department"] = self.employee.department
        if self.employee.get("branch"):
            components["branch"] = self.employee.branch
        if self.employee.get("employment_type"):
            components["employment_type"] = self.employee.employment_type
        
        # Add temporal components
        now = datetime.now()
        components["year"] = now.strftime("%Y")
        components["month"] = now.strftime("%Y%m")
        
        return components


def get_token_resolver(employee_doc, settings: Dict[str, Any]) -> TokenResolver:
    """Factory function to create TokenResolver instance"""
    return TokenResolver(employee_doc, settings)
