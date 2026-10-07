"""
Customer Form Schema Validation for AcxiomCRM.

Performs field-level and format validation on incoming customer request payloads.
Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md:
- CustomerName: Required, 2-100 characters.
- Email: Required, valid format, max 100 characters.
- Phone: Required, 10-15 digits, max 20 characters.
- CompanyName: Optional, max 100 characters.
- City, State: Optional, max 50 characters.
- Status: Active or Inactive.
"""

from validation.business_rules import (
    validate_email_format,
    validate_phone_format,
    validate_customer_status,
)


def validate_customer_form(data, is_edit=False):
    """
    Validate customer create/edit form data.

    :param data: Dictionary containing form input fields.
    :param is_edit: Boolean indicating whether this is an update operation.
    :return: Dictionary of errors mapping field names to error messages (empty if valid).
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

    # 3. Phone Number
    phone = (data.get("phone") or "").strip()
    is_valid_phone, phone_err = validate_phone_format(phone)
    if not is_valid_phone:
        errors["phone"] = phone_err

    # 4. Company Name (Optional)
    company_name = (data.get("company_name") or "").strip()
    if company_name and len(company_name) > 100:
        errors["company_name"] = "Company Name must not exceed 100 characters."

    # 5. City and State (Optional)
    city = (data.get("city") or "").strip()
    if city and len(city) > 50:
        errors["city"] = "City must not exceed 50 characters."

    state = (data.get("state") or "").strip()
    if state and len(state) > 50:
        errors["state"] = "State must not exceed 50 characters."

    # 6. Status (Only validated if provided in payload)
    status = data.get("status")
    if status:
        is_valid_status, status_err = validate_customer_status(status)
        if not is_valid_status:
            errors["status"] = status_err

    # 7. Assigned Sales Executive (Optional integer check)
    assigned_to = data.get("assigned_to")
    if assigned_to not in (None, ""):
        try:
            int(assigned_to)
        except (ValueError, TypeError):
            errors["assigned_to"] = "Assigned user ID must be a valid integer."

    return errors
