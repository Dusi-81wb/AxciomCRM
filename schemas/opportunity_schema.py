"""
Opportunity Form Schema Validation for AcxiomCRM (Phase 7).

Performs field-level and format validation on incoming opportunity request payloads.
Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md Section 95:
- OpportunityName: Required, 1-100 characters.
- CustomerId: Required positive integer.
- LeadId: Optional integer.
- Amount: Required non-negative Decimal; strictly > 0 for active (Open) opportunities.
- Stage: Valid stage in (Qualification, Proposal, Negotiation, Won, Lost).
- Probability: Integer 0–100 inclusive.
- ExpectedCloseDate: Required YYYY-MM-DD date; not in past for active opportunities (Asia/Kolkata).
- Status: Valid status in (Open, Won, Lost); consistent with stage.
- AssignedTo: User ID integer where provided.
"""

from validation.business_rules import (
    validate_opportunity_stage,
    validate_opportunity_status,
    validate_opportunity_stage_status_consistency,
    validate_opportunity_amount,
    validate_expected_close_date,
    validate_probability,
    OPPORTUNITY_STAGE_QUALIFICATION,
    OPPORTUNITY_STATUS_OPEN,
    OPPORTUNITY_STAGE_WON,
    OPPORTUNITY_STAGE_LOST,
)


def validate_opportunity_form(data, is_edit=False, current_status=None):
    """
    Validate opportunity create or edit form data.

    :param data: Dictionary containing form input fields.
    :param is_edit: Boolean indicating whether this is an edit operation.
    :param current_status: The current status of the opportunity in edit mode.
    :return: Dictionary of errors mapping field names to error messages (empty if valid).
    """
    errors = {}

    # 1. Opportunity Name
    opp_name = (data.get("opportunity_name") or "").strip()
    if not opp_name:
        errors["opportunity_name"] = "Opportunity Name is required."
    elif len(opp_name) > 100:
        errors["opportunity_name"] = "Opportunity Name must not exceed 100 characters."

    # 2. Customer ID
    raw_cust_id = data.get("customer_id")
    if raw_cust_id in (None, ""):
        errors["customer_id"] = "Customer is required."
    else:
        try:
            cid = int(str(raw_cust_id).strip())
            if cid <= 0:
                errors["customer_id"] = "A valid Customer selection is required."
        except (ValueError, TypeError):
            errors["customer_id"] = "Customer ID must be a valid integer."

    # 3. Lead ID (Optional)
    raw_lead_id = data.get("lead_id")
    if raw_lead_id not in (None, ""):
        try:
            lid = int(str(raw_lead_id).strip())
            if lid <= 0:
                errors["lead_id"] = "Lead ID must be a positive integer."
        except (ValueError, TypeError):
            errors["lead_id"] = "Lead ID must be a valid integer."

    # 4. Stage and Status resolution
    stage = (data.get("stage") or (OPPORTUNITY_STAGE_QUALIFICATION if not is_edit else "")).strip()
    is_valid_stage, stage_err = validate_opportunity_stage(stage)
    if not is_valid_stage:
        errors["stage"] = stage_err

    # Determine status
    if not is_edit:
        status = OPPORTUNITY_STATUS_OPEN
        if stage == OPPORTUNITY_STAGE_WON:
            status = "Won"
        elif stage == OPPORTUNITY_STAGE_LOST:
            status = "Lost"
    else:
        raw_status = (data.get("status") or current_status or OPPORTUNITY_STATUS_OPEN).strip()
        is_valid_status, status_err = validate_opportunity_status(raw_status)
        if not is_valid_status:
            errors["status"] = status_err
            status = OPPORTUNITY_STATUS_OPEN
        else:
            status = raw_status

    # Stage / Status Consistency
    if is_valid_stage and "status" not in errors:
        is_consistent, consistency_err = validate_opportunity_stage_status_consistency(stage, status)
        if not is_consistent:
            errors["stage"] = consistency_err

    # 5. Amount
    raw_amount = data.get("amount")
    is_valid_amount, amount_err = validate_opportunity_amount(raw_amount, status=status)
    if not is_valid_amount:
        errors["amount"] = amount_err

    # 6. Probability
    raw_prob = data.get("probability")
    is_valid_prob, prob_err = validate_probability(raw_prob)
    if not is_valid_prob:
        errors["probability"] = prob_err

    # 7. Expected Close Date
    raw_close_date = data.get("expected_close_date")
    is_valid_date, date_err = validate_expected_close_date(raw_close_date, status=status)
    if not is_valid_date:
        errors["expected_close_date"] = date_err

    # 8. Assigned To format check if supplied
    raw_assigned = data.get("assigned_to")
    if raw_assigned not in (None, ""):
        try:
            int(str(raw_assigned).strip())
        except (ValueError, TypeError):
            errors["assigned_to"] = "Assigned user ID must be a valid integer."

    return errors
