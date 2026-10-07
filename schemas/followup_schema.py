"""
Follow-Up Form Schema Validation for AcxiomCRM (Phase 8).

Validates format, fields, and initial constraints on incoming follow-up payloads.
Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md Section 97:
- Subject: Required, 1-150 characters.
- FollowUpDate: Required date YYYY-MM-DD; cannot be in past (Asia/Kolkata).
- FollowUpType: Required in ('Call', 'Meeting', 'Email').
- Status: Valid status in ('Planned', 'Completed', 'Missed', 'Cancelled').
- Relationship: At least one of customer_id, lead_id, or opportunity_id must be provided.
- AssignedTo: Positive integer format where supplied.
- Remarks: Optional text.
"""

from validation.business_rules import (
    validate_followup_status,
    validate_followup_type,
    validate_followup_date,
    FOLLOWUP_STATUS_PLANNED,
)


def validate_followup_form(data, is_edit=False, current_status=None, is_reschedule=False):
    """
    Validate follow-up create, edit, or reschedule form data.

    :param data: Dictionary containing form input fields.
    :param is_edit: Boolean indicating whether this is an edit operation.
    :param current_status: The current status of the follow-up in edit mode.
    :param is_reschedule: Boolean indicating if this is a date rescheduling action.
    :return: Dictionary of errors mapping field names to error messages (empty if valid).
    """
    errors = {}

    # 1. Subject (Required, max 150)
    if not is_reschedule:
        subject = (data.get("subject") or "").strip()
        if not subject:
            errors["subject"] = "Subject is required."
        elif len(subject) > 150:
            errors["subject"] = "Subject must not exceed 150 characters."

    # 2. Follow-Up Date (Required, cannot be before today in Asia/Kolkata)
    raw_date = data.get("followup_date")
    is_valid_date, date_err = validate_followup_date(raw_date)
    if not is_valid_date:
        errors["followup_date"] = date_err

    # 3. Follow-Up Type
    if not is_reschedule:
        ftype = (data.get("followup_type") or "").strip()
        is_valid_type, type_err = validate_followup_type(ftype)
        if not is_valid_type:
            errors["followup_type"] = type_err

    # 4. Status Validation
    if is_edit and not is_reschedule:
        raw_status = (data.get("status") or current_status or FOLLOWUP_STATUS_PLANNED).strip()
        is_valid_status, status_err = validate_followup_status(raw_status)
        if not is_valid_status:
            errors["status"] = status_err

    # 5. Relationship Cardinality (Decision 97 #1: At least one relationship required)
    if not is_reschedule and not is_edit:
        raw_cust_id = data.get("customer_id")
        raw_lead_id = data.get("lead_id")
        raw_opp_id = data.get("opportunity_id")

        has_cust = raw_cust_id not in (None, "", "0")
        has_lead = raw_lead_id not in (None, "", "0")
        has_opp = raw_opp_id not in (None, "", "0")

        if not (has_cust or has_lead or has_opp):
            errors["relationship"] = "At least one related entity (Customer, Lead, or Opportunity) must be selected."

        # Validate integer formats if supplied
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

        if has_opp:
            try:
                oid = int(str(raw_opp_id).strip())
                if oid <= 0:
                    errors["opportunity_id"] = "Opportunity ID must be a positive integer."
            except (ValueError, TypeError):
                errors["opportunity_id"] = "Opportunity ID must be a valid integer."

    # 6. Assigned To format check if supplied
    raw_assigned = data.get("assigned_to")
    if raw_assigned not in (None, ""):
        try:
            int(str(raw_assigned).strip())
        except (ValueError, TypeError):
            errors["assigned_to"] = "Assigned user ID must be a valid integer."

    return errors
