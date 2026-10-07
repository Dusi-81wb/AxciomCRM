"""
Lead Form and Conversion Schemas for AcxiomCRM.

Validates incoming Lead creation, edit, and conversion payloads.
Adheres strictly to MASTER_BLUEPRINT.md, SPECIFICATION_NOTES.md, and sql/schema.sql:
- LeadName: Required, 2-100 characters.
- Email: Required, valid email format, max 100 characters.
- Phone: Optional on Lead, max 20 characters, 10-15 digits if present.
- CompanyName: Optional, max 100 characters.
- Source: Optional, max 50 characters.
- ExpectedValue: Optional non-negative decimal currency amount.
- Status: One of 6 canonical statuses (New, Contacted, Qualified, Unqualified, Converted, Lost).
- Conversion: Validates Customer details and optional Opportunity details.
"""

from datetime import datetime
from validation.business_rules import (
    validate_email_format,
    validate_phone_format,
    validate_lead_status,
    validate_expected_value,
    validate_probability,
)


def validate_lead_form(data, is_edit=False):
    """
    Validate Lead create or edit form data.

    :param data: Mapping of form input fields.
    :param is_edit: True if update operation.
    :return: Dict mapping field names to error messages (empty if valid).
    """
    errors = {}

    # 1. Lead Name
    lead_name = (data.get("lead_name") or "").strip()
    if not lead_name:
        errors["lead_name"] = "Lead Name is required."
    elif len(lead_name) < 2 or len(lead_name) > 100:
        errors["lead_name"] = "Lead Name must be between 2 and 100 characters."

    # 2. Email Address
    email = (data.get("email") or "").strip()
    is_valid_email, email_err = validate_email_format(email)
    if not is_valid_email:
        errors["email"] = email_err

    # 3. Phone Number (Optional on leads table, but format validated if provided)
    phone = (data.get("phone") or "").strip()
    if phone:
        is_valid_phone, phone_err = validate_phone_format(phone)
        if not is_valid_phone:
            errors["phone"] = phone_err

    # 4. Company Name (Optional)
    company_name = (data.get("company_name") or "").strip()
    if company_name and len(company_name) > 100:
        errors["company_name"] = "Company Name must not exceed 100 characters."

    # 5. Lead Source (Optional)
    source = (data.get("source") or "").strip()
    if source and len(source) > 50:
        errors["source"] = "Source must not exceed 50 characters."

    # 6. Expected Value (Optional non-negative numeric)
    expected_value = data.get("expected_value")
    if expected_value not in (None, ""):
        is_valid_ev, ev_err = validate_expected_value(expected_value)
        if not is_valid_ev:
            errors["expected_value"] = ev_err

    # 7. Status (Only validated if provided in payload)
    status = data.get("status")
    if status:
        is_valid_status, status_err = validate_lead_status(status)
        if not is_valid_status:
            errors["status"] = status_err

    # 8. Assigned User (Optional integer check)
    assigned_to = data.get("assigned_to")
    if assigned_to not in (None, ""):
        try:
            int(assigned_to)
        except (ValueError, TypeError):
            errors["assigned_to"] = "Assigned user ID must be a valid integer."

    return errors


def validate_lead_conversion_form(data):
    """
    Validate Lead-to-Customer (and optional Opportunity) conversion form data.

    :param data: Mapping of conversion form inputs.
    :return: Dict mapping field names to error messages (empty if valid).
    """
    errors = {}

    # 1. Customer Name
    customer_name = (data.get("customer_name") or "").strip()
    if not customer_name:
        errors["customer_name"] = "Customer Name is required."
    elif len(customer_name) < 2 or len(customer_name) > 100:
        errors["customer_name"] = "Customer Name must be between 2 and 100 characters."

    # 2. Email Address
    email = (data.get("email") or "").strip()
    is_valid_email, email_err = validate_email_format(email)
    if not is_valid_email:
        errors["email"] = email_err

    # 3. Phone Number (Mandatory for customers table: phone VARCHAR(20) NOT NULL UNIQUE)
    phone = (data.get("phone") or "").strip()
    if not phone:
        errors["phone"] = "Phone number is required to create a Customer."
    else:
        is_valid_phone, phone_err = validate_phone_format(phone)
        if not is_valid_phone:
            errors["phone"] = phone_err

    # 4. Company Name
    company_name = (data.get("company_name") or "").strip()
    if company_name and len(company_name) > 100:
        errors["company_name"] = "Company Name must not exceed 100 characters."

    # 5. Address, City, State
    city = (data.get("city") or "").strip()
    if city and len(city) > 50:
        errors["city"] = "City must not exceed 50 characters."

    state = (data.get("state") or "").strip()
    if state and len(state) > 50:
        errors["state"] = "State must not exceed 50 characters."

    address = (data.get("address") or "").strip()
    if address and len(address) > 255:
        errors["address"] = "Address must not exceed 255 characters."

    # 6. Optional Opportunity Details
    create_opportunity = data.get("create_opportunity") in (True, "true", "1", "on", "yes")
    if create_opportunity:
        opp_name = (data.get("opportunity_name") or "").strip()
        if not opp_name:
            errors["opportunity_name"] = "Opportunity Name is required when creating an Opportunity."
        elif len(opp_name) < 2 or len(opp_name) > 100:
            errors["opportunity_name"] = "Opportunity Name must be between 2 and 100 characters."

        # Expected Close Date (DATE NOT NULL in opportunities table)
        close_date = (data.get("expected_close_date") or "").strip()
        if not close_date:
            errors["expected_close_date"] = "Expected Close Date is required."
        else:
            try:
                datetime.strptime(close_date, "%Y-%m-%d")
            except ValueError:
                errors["expected_close_date"] = "Expected Close Date must be formatted as YYYY-MM-DD."

        # Opportunity Amount (defaults to Lead expected value or 0.00)
        amount = data.get("amount")
        if amount not in (None, ""):
            is_valid_amt, amt_err = validate_expected_value(amount)
            if not is_valid_amt:
                errors["amount"] = amt_err

        # Probability (0 to 100)
        prob = data.get("probability")
        if prob in (None, ""):
            errors["probability"] = "Probability is required (0 to 100)."
        else:
            is_valid_prob, prob_err = validate_probability(prob)
            if not is_valid_prob:
                errors["probability"] = prob_err

    return errors
