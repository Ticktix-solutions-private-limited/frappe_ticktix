"""
Custom fields for Customer doctype

Adds three new tabs to the Customer form's tab bar (alongside the
standard Details / Address & Contact / Tax / Accounting tabs):
- Employment
- Financial
- Loan Details
"""


def get_customer_custom_fields():
    """Returns custom field definitions for Customer doctype"""
    return {
        "Customer": [
            # ================================================================
            # EMPLOYMENT TAB
            # ================================================================
            {
                "fieldname": "custom_employment_tab",
                "fieldtype": "Tab Break",
                "insert_after": "portal_users",
                "label": "Employment"
            },
            {
                "fieldname": "custom_employment_type",
                "fieldtype": "Select",
                "insert_after": "custom_employment_tab",
                "label": "Employment Type",
                "options": "\nSalaried\nSelf Employed"
            },
            {
                "fieldname": "custom_column_break_employment_type",
                "fieldtype": "Column Break",
                "insert_after": "custom_employment_type"
            },
            # ---- Salaried section ----
            {
                "fieldname": "custom_salaried_details_section",
                "fieldtype": "Section Break",
                "insert_after": "custom_column_break_employment_type",
                "label": "Salaried Details",
                "depends_on": "eval:doc.custom_employment_type==\"Salaried\""
            },
            {
                "fieldname": "custom_company_name",
                "fieldtype": "Data",
                "insert_after": "custom_salaried_details_section",
                "label": "Company Name"
            },
            {
                "fieldname": "custom_designation",
                "fieldtype": "Data",
                "insert_after": "custom_company_name",
                "label": "Designation"
            },
            {
                "fieldname": "custom_total_work_experience",
                "fieldtype": "Data",
                "insert_after": "custom_designation",
                "label": "Total Work Experience"
            },
            {
                "fieldname": "custom_column_break_salaried",
                "fieldtype": "Column Break",
                "insert_after": "custom_total_work_experience"
            },
            {
                "fieldname": "custom_current_employer_experience",
                "fieldtype": "Data",
                "insert_after": "custom_column_break_salaried",
                "label": "Current Employer Experience"
            },
            {
                "fieldname": "custom_monthly_net_salary",
                "fieldtype": "Currency",
                "insert_after": "custom_current_employer_experience",
                "label": "Monthly Net Salary"
            },
            {
                "fieldname": "custom_salary_account_bank",
                "fieldtype": "Data",
                "insert_after": "custom_monthly_net_salary",
                "label": "Salary Account Bank"
            },
            # ---- Self Employed section ----
            {
                "fieldname": "custom_self_employed_details_section",
                "fieldtype": "Section Break",
                "insert_after": "custom_salary_account_bank",
                "label": "Self Employed Details",
                "depends_on": "eval:doc.custom_employment_type==\"Self Employed\""
            },
            {
                "fieldname": "custom_business_name",
                "fieldtype": "Data",
                "insert_after": "custom_self_employed_details_section",
                "label": "Business Name"
            },
            {
                "fieldname": "custom_business_type",
                "fieldtype": "Data",
                "insert_after": "custom_business_name",
                "label": "Business Type"
            },
            {
                "fieldname": "custom_annual_turnover",
                "fieldtype": "Currency",
                "insert_after": "custom_business_type",
                "label": "Annual Turnover"
            },
            {
                "fieldname": "custom_column_break_self_employed",
                "fieldtype": "Column Break",
                "insert_after": "custom_annual_turnover"
            },
            {
                "fieldname": "custom_annual_income",
                "fieldtype": "Currency",
                "insert_after": "custom_column_break_self_employed",
                "label": "Annual Income"
            },
            {
                "fieldname": "custom_years_in_business",
                "fieldtype": "Float",
                "insert_after": "custom_annual_income",
                "label": "Years in Business"
            },
            {
                "fieldname": "custom_gst_number",
                "fieldtype": "Data",
                "insert_after": "custom_years_in_business",
                "label": "GST Number"
            },

            # ================================================================
            # FINANCIAL TAB
            # ================================================================
            {
                "fieldname": "custom_financial_tab",
                "fieldtype": "Tab Break",
                "insert_after": "custom_gst_number",
                "label": "Financial"
            },
            {
                "fieldname": "custom_existing_emis",
                "fieldtype": "Currency",
                "insert_after": "custom_financial_tab",
                "label": "Existing EMIs (₹/month)"
            },
            {
                "fieldname": "custom_monthly_obligations",
                "fieldtype": "Currency",
                "insert_after": "custom_existing_emis",
                "label": "Monthly Obligations (₹)"
            },
            {
                "fieldname": "custom_primary_bank",
                "fieldtype": "Data",
                "insert_after": "custom_monthly_obligations",
                "label": "Primary Bank"
            },
            {
                "fieldname": "custom_column_break_financial",
                "fieldtype": "Column Break",
                "insert_after": "custom_primary_bank"
            },
            {
                "fieldname": "custom_credit_card_holder",
                "fieldtype": "Select",
                "insert_after": "custom_column_break_financial",
                "label": "Credit Card Holder?",
                "options": "No\nYes",
                "default": "No"
            },
            {
                "fieldname": "custom_number_of_credit_cards",
                "fieldtype": "Int",
                "insert_after": "custom_credit_card_holder",
                "label": "Number of Credit Cards",
                "depends_on": "eval:doc.custom_credit_card_holder==\"Yes\""
            },
            {
                "fieldname": "custom_existing_loan_types_section",
                "fieldtype": "Section Break",
                "insert_after": "custom_number_of_credit_cards",
                "label": "Existing Loan Types"
            },
            {
                "fieldname": "custom_existing_loan_type_personal_loan",
                "fieldtype": "Check",
                "insert_after": "custom_existing_loan_types_section",
                "label": "Personal Loan"
            },
            {
                "fieldname": "custom_existing_loan_type_home_loan",
                "fieldtype": "Check",
                "insert_after": "custom_existing_loan_type_personal_loan",
                "label": "Home Loan"
            },
            {
                "fieldname": "custom_column_break_loan_types",
                "fieldtype": "Column Break",
                "insert_after": "custom_existing_loan_type_home_loan"
            },
            {
                "fieldname": "custom_existing_loan_type_vehicle_loan",
                "fieldtype": "Check",
                "insert_after": "custom_column_break_loan_types",
                "label": "Vehicle Loan"
            },
            {
                "fieldname": "custom_existing_loan_type_business_loan",
                "fieldtype": "Check",
                "insert_after": "custom_existing_loan_type_vehicle_loan",
                "label": "Business Loan"
            },
            {
                "fieldname": "custom_column_break_loan_types_2",
                "fieldtype": "Column Break",
                "insert_after": "custom_existing_loan_type_business_loan"
            },
            {
                "fieldname": "custom_existing_loan_type_gold_loan",
                "fieldtype": "Check",
                "insert_after": "custom_column_break_loan_types_2",
                "label": "Gold Loan"
            },

            # ================================================================
            # LOAN DETAILS TAB
            # ================================================================
            {
                "fieldname": "custom_loan_details_tab",
                "fieldtype": "Tab Break",
                "insert_after": "custom_existing_loan_type_gold_loan",
                "label": "Loan Details"
            },
            {
                "fieldname": "custom_loan_type",
                "fieldtype": "Data",
                "insert_after": "custom_loan_details_tab",
                "label": "Loan Type",
                "options": ""
            },
            {
                "fieldname": "custom_required_loan_amount",
                "fieldtype": "Currency",
                "insert_after": "custom_loan_type",
                "label": "Required Loan Amount"
            },
            {
                "fieldname": "custom_column_break_loan_details",
                "fieldtype": "Column Break",
                "insert_after": "custom_required_loan_amount"
            },
            {
                "fieldname": "custom_preferred_tenure",
                "fieldtype": "Data",
                "insert_after": "custom_column_break_loan_details",
                "label": "Preferred Tenure"
            },
            {
                "fieldname": "custom_loan_purpose",
                "fieldtype": "Small Text",
                "insert_after": "custom_preferred_tenure",
                "label": "Loan Purpose"
            }
        ]
    }


def create_custom_fields():
    """
    Create custom fields for Customer doctype
    Called from install.py
    """
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    custom_fields = get_customer_custom_fields()
    create_custom_fields(custom_fields, update=True)

    frappe.db.commit()
    print("✅ Created custom fields for Customer doctype")
