"""
Activity Form Schema Validation for AcxiomCRM (Phase 8).

Validates format, fields, and constraints on incoming activity payloads.
Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md Section 97:
- ActivityType: Required, in ('Call', 'Meeting', 'Email', 'Task').
- Subject: Required, 1-150 characters.
- Description: Optional text.
- ActivityDate: Required date or timestamp.
- Relationship: At least one of customer_id or lead_id must be provided (no opportunity_id in schema).
- Status: In ('Completed', 'Planned'), defaults to 'Completed'.
- AssignedTo: Positive integer format where supplied.
"""

from validation.business_rules import (
    validate_activity_type,
    validate_activity_status,
    validate_activity_date,
    ACTIVITY_STATUS_COMPLETED,
)


def validate_activity_form(data, is_edit=False, current_status=None):
    """
    Validate activity create or edit form data.

    :param data: Dictionary containing form input fields.
    :param is_edit: Boolean indicating whether this is an edit operation.
    :param current_status: The current status of the activity in edit mode.
    :return: Dictionary of errors mapping field names to error messages (empty if valid).
    """
    errors = {}

    # 1. Activity Type (Required, in ('Call', 'Meeting', 'Email', 'Task'))
    atype = (data.get("activity_type") or "").strip()
    is_valid_type, type_err = validate_activity_type(atype)
    if not is_valid_type:
        errors["activity_type"] = type_err

    # 2. Subject (Required, max 150)
    subject = (data.get("subject") or "").strip()
    if not subject:
        errors["subject"] = "Subject is required."
    elif len(subject) > 150:
        errors["subject"] = "Subject must not exceed 150 characters."

    # 3. Activity Date (Required)
    raw_date = data.get("activity_date")
    is_valid_date, date_err = validate_activity_date(raw_date)
    if not is_valid_date:
        errors["activity_date"] = date_err

    # 4. Status Validation
    raw_status = (data.get("status") or current_status or ACTIVITY_STATUS_COMPLETED).strip()
    is_valid_status, status_err = validate_activity_status(raw_status)
    if not is_valid_status:
        errors["status"] = status_err

    # 5. Relationship Cardinality (Decision 97 #5: At least one of customer_id or lead_id)
    if not is_edit:
        raw_cust_id = data.get("customer_id")
        raw_lead_id = data.get("lead_id")

        has_cust = raw_cust_id not in (None, "", "0")
        has_lead = raw_lead_id not in (None, "", "0")

        if not (has_cust or has_lead):
            errors["relationship"] = "At least one related entity (Customer or Lead) must be selected."

        if has_cust:
            try:
                cid = int(str(raw_cust_id).strip())
                if cid <= 0:
                    errors["customer_id"] = "Customer ID must be a positive integer."
            except (ValueError, TypeError):
                errors["customer_id"] = "Customer ID must be a valid integer."

        if has_lead:
            try:
                lid = int(str(raw_lead_id).strip())
                if lid <= 0:
                    errors["lead_id"] = "Lead ID must be a positive integer."
            except (ValueError, TypeError):
                errors["lead_id"] = "Lead ID must be a valid integer."

    # 6. Assigned To format check if supplied
    raw_assigned = data.get("assigned_to")
    if raw_assigned not in (None, ""):
        try:
            int(str(raw_assigned).strip())
        except (ValueError, TypeError):
            errors["assigned_to"] = "Assigned user ID must be a valid integer."

    return errors
