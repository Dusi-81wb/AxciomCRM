"""
Business Rules and Validation for AcxiomCRM.

Contains reusable server-side validation logic including password security policy.
Per MASTER_BLUEPRINT.md Section 36, password policy enforces:
- Minimum length (centralized in configuration, default 8)
- No empty passwords
- Secure character composition (uppercase, lowercase, number, special character).
"""

import re


def validate_password_policy(password, min_length=8):
    """
    Validate a password against the security policy.

    :param password: The candidate plaintext password string.
    :param min_length: The minimum required character length (from config).
    :return: Tuple (is_valid: bool, error_message: str or None).
    """
    if not password:
        return False, "Password cannot be empty."

    if len(password) < min_length:
        return False, f"Password must be at least {min_length} characters long."

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."

    if not re.search(r"\d", password):
        return False, "Password must contain at least one number."

    if not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_+=~`]", password):
        return False, "Password must contain at least one special character."

    return True, None


def validate_username(username):
    """
    Validate username format and length.

    :param username: Candidate username string.
    :return: Tuple (is_valid: bool, error_message: str or None).
    """
    if not username or not username.strip():
        return False, "Username is required."

    username = username.strip()
    if len(username) < 3 or len(username) > 50:
        return False, "Username must be between 3 and 50 characters."

    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username may only contain letters, numbers, and underscores."

    return True, None


def validate_email_format(email):
    """
    Validate email structure format.

    :param email: Candidate email string.
    :return: Tuple (is_valid: bool, error_message: str or None).
    """
    if not email or not email.strip():
        return False, "Email address is required."

    email = email.strip()
    if len(email) > 100:
        return False, "Email address must not exceed 100 characters."

    pattern = r"^[\w\.-]+@([\w-]+\.)+[a-zA-Z]{2,}$"
    if not re.match(pattern, email):
        return False, "Please enter a valid email address."

    return True, None


def validate_phone_format(phone):
    """
    Validate phone number format and length.
    Approved specification: 10 to 15 digits, allowing optional leading '+' and hyphens/spaces.
    Matches seed data format: '+91-9876543210' or standard national format '9876543210'.

    :param phone: Candidate phone string.
    :return: Tuple (is_valid: bool, error_message: str or None).
    """
    if not phone or not phone.strip():
        return False, "Phone number is required."

    phone_str = phone.strip()
    if len(phone_str) > 20:
        return False, "Phone number must not exceed 20 characters."

    # Pattern allows optional leading '+', digits, spaces, and hyphens
    if not re.match(r"^\+?[0-9\s\-]+$", phone_str):
        return False, "Phone number contains invalid characters. Use digits, hyphens, and optional '+'."

    # Extract digits only to verify standard length (10 to 15 digits)
    digits = re.sub(r"\D", "", phone_str)
    if len(digits) < 10 or len(digits) > 15:
        return False, "Phone number must contain between 10 and 15 digits."

    return True, None


def validate_customer_status(status):
    """
    Validate customer status against approved values.

    :param status: Candidate status string.
    :return: Tuple (is_valid: bool, error_message: str or None).
    """
    if not status or status.strip() not in ("Active", "Inactive"):
        return False, "Status must be either 'Active' or 'Inactive'."
    return True, None


# =============================================================================
# LEAD CONSTANTS & TRANSITION MATRIX
# =============================================================================

LEAD_STATUS_NEW = "New"
LEAD_STATUS_CONTACTED = "Contacted"
LEAD_STATUS_QUALIFIED = "Qualified"
LEAD_STATUS_UNQUALIFIED = "Unqualified"
LEAD_STATUS_CONVERTED = "Converted"
LEAD_STATUS_LOST = "Lost"

VALID_LEAD_STATUSES = {
    LEAD_STATUS_NEW,
    LEAD_STATUS_CONTACTED,
    LEAD_STATUS_QUALIFIED,
    LEAD_STATUS_UNQUALIFIED,
    LEAD_STATUS_CONVERTED,
    LEAD_STATUS_LOST,
}

# Approved Transition Matrix (Blueprint Section 62 & Spec Notes Section 5)
LEAD_TRANSITIONS = {
    LEAD_STATUS_NEW: {LEAD_STATUS_CONTACTED, LEAD_STATUS_UNQUALIFIED, LEAD_STATUS_LOST},
    LEAD_STATUS_CONTACTED: {LEAD_STATUS_QUALIFIED, LEAD_STATUS_UNQUALIFIED, LEAD_STATUS_LOST},
    LEAD_STATUS_QUALIFIED: {LEAD_STATUS_CONVERTED, LEAD_STATUS_LOST},
    LEAD_STATUS_UNQUALIFIED: set(),
    LEAD_STATUS_CONVERTED: set(),
    LEAD_STATUS_LOST: set(),
}


def validate_lead_status(status):
    """
    Validate that status is one of the 6 canonical Lead statuses.

    :param status: Candidate status string.
    :return: Tuple (is_valid: bool, error_message: str or None).
    """
    if not status or status.strip() not in VALID_LEAD_STATUSES:
        return False, f"Status must be one of: {', '.join(sorted(VALID_LEAD_STATUSES))}."
    return True, None


def validate_lead_transition(current_status, target_status):
    """
    Enforce server-side Lead status transition matrix.

    :param current_status: Current status in database.
    :param target_status: Requested new status.
    :return: Tuple (is_valid: bool, error_message: str or None).
    """
    if current_status == target_status:
        return True, None

    allowed_targets = LEAD_TRANSITIONS.get(current_status, set())
    if target_status not in allowed_targets:
        return False, f"Invalid status transition from '{current_status}' to '{target_status}'."

    return True, None


def validate_expected_value(value):
    """
    Validate ExpectedValue as a non-negative decimal currency value.

    :param value: Candidate numeric/decimal or string value.
    :return: Tuple (is_valid: bool, error_message: str or None).
    """
    if value in (None, ""):
        return True, None

    from decimal import Decimal, InvalidOperation
    try:
        dec = Decimal(str(value).strip())
        if dec < Decimal("0.00"):
            return False, "Expected value cannot be negative."
        return True, None
    except (InvalidOperation, ValueError, TypeError):
        return False, "Expected value must be a valid numeric amount."


def validate_probability(probability):
    """
    Validate probability as an integer between 0 and 100 inclusive.

    :param probability: Candidate integer or string.
    :return: Tuple (is_valid: bool, error_message: str or None).
    """
    if probability in (None, ""):
        return False, "Probability is required."

    try:
        val = int(probability)
        if val < 0 or val > 100:
            return False, "Probability must be between 0 and 100."
        return True, None
    except (ValueError, TypeError):
        return False, "Probability must be an integer between 0 and 100."


# =============================================================================
# OPPORTUNITY DOMAIN CONSTANTS & TRANSITIONS (Phase 7)
# =============================================================================

OPPORTUNITY_STAGE_QUALIFICATION = "Qualification"
OPPORTUNITY_STAGE_PROPOSAL = "Proposal"
OPPORTUNITY_STAGE_NEGOTIATION = "Negotiation"
OPPORTUNITY_STAGE_WON = "Won"
OPPORTUNITY_STAGE_LOST = "Lost"

VALID_OPPORTUNITY_STAGES = {
    OPPORTUNITY_STAGE_QUALIFICATION,
    OPPORTUNITY_STAGE_PROPOSAL,
    OPPORTUNITY_STAGE_NEGOTIATION,
    OPPORTUNITY_STAGE_WON,
    OPPORTUNITY_STAGE_LOST,
}

OPPORTUNITY_STATUS_OPEN = "Open"
OPPORTUNITY_STATUS_WON = "Won"
OPPORTUNITY_STATUS_LOST = "Lost"

VALID_OPPORTUNITY_STATUSES = {
    OPPORTUNITY_STATUS_OPEN,
    OPPORTUNITY_STATUS_WON,
    OPPORTUNITY_STATUS_LOST,
}

# Approved Phase 7 Stage Transition Matrix (Linear progression with drop to Lost; Won/Lost terminal)
OPPORTUNITY_STAGE_TRANSITIONS = {
    OPPORTUNITY_STAGE_QUALIFICATION: {OPPORTUNITY_STAGE_PROPOSAL, OPPORTUNITY_STAGE_LOST},
    OPPORTUNITY_STAGE_PROPOSAL: {OPPORTUNITY_STAGE_NEGOTIATION, OPPORTUNITY_STAGE_LOST},
    OPPORTUNITY_STAGE_NEGOTIATION: {OPPORTUNITY_STAGE_WON, OPPORTUNITY_STAGE_LOST},
    OPPORTUNITY_STAGE_WON: set(),
    OPPORTUNITY_STAGE_LOST: set(),
}


def validate_opportunity_stage(stage):
    """
    Validate that stage is one of the 5 canonical Opportunity stages.
    """
    if not stage or stage.strip() not in VALID_OPPORTUNITY_STAGES:
        return False, f"Stage must be one of: {', '.join(sorted(VALID_OPPORTUNITY_STAGES))}."
    return True, None


def validate_opportunity_status(status):
    """
    Validate that status is one of the 3 canonical Opportunity statuses.
    """
    if not status or status.strip() not in VALID_OPPORTUNITY_STATUSES:
        return False, f"Status must be one of: {', '.join(sorted(VALID_OPPORTUNITY_STATUSES))}."
    return True, None


def validate_opportunity_stage_transition(current_stage, target_stage):
    """
    Enforce server-side Opportunity stage transition matrix.
    """
    if current_stage == target_stage:
        return True, None

    allowed_targets = OPPORTUNITY_STAGE_TRANSITIONS.get(current_stage, set())
    if target_stage not in allowed_targets:
        return False, f"Invalid stage transition from '{current_stage}' to '{target_stage}'."

    return True, None


def validate_opportunity_stage_status_consistency(stage, status):
    """
    Ensure Stage and Status are logically consistent.
    - Active stages (Qualification, Proposal, Negotiation) require status 'Open'.
    - Stage 'Won' requires status 'Won'.
    - Stage 'Lost' requires status 'Lost'.
    """
    if stage == OPPORTUNITY_STAGE_WON:
        if status != OPPORTUNITY_STATUS_WON:
            return False, "Opportunity in stage 'Won' must have status 'Won'."
    elif stage == OPPORTUNITY_STAGE_LOST:
        if status != OPPORTUNITY_STATUS_LOST:
            return False, "Opportunity in stage 'Lost' must have status 'Lost'."
    elif stage in {OPPORTUNITY_STAGE_QUALIFICATION, OPPORTUNITY_STAGE_PROPOSAL, OPPORTUNITY_STAGE_NEGOTIATION}:
        if status != OPPORTUNITY_STATUS_OPEN:
            return False, f"Active opportunity in stage '{stage}' must have status 'Open'."
    else:
        return False, f"Unknown stage '{stage}'."

    return True, None


def validate_opportunity_amount(amount, status=OPPORTUNITY_STATUS_OPEN):
    """
    Validate Opportunity amount.
    Per Part 5: Active opportunity (Status = Open) amount must be strictly > 0.
    For closed opportunities, amount must be >= 0.
    """
    if amount in (None, ""):
        return False, "Amount is required."

    from decimal import Decimal, InvalidOperation
    try:
        dec = Decimal(str(amount).strip())
        if status == OPPORTUNITY_STATUS_OPEN:
            if dec <= Decimal("0.00"):
                return False, "Active opportunity amount must be greater than 0."
        else:
            if dec < Decimal("0.00"):
                return False, "Opportunity amount cannot be negative."
        return True, None
    except (InvalidOperation, ValueError, TypeError):
        return False, "Amount must be a valid numeric currency amount."


def validate_expected_close_date(close_date_val, status=OPPORTUNITY_STATUS_OPEN):
    """
    Validate ExpectedCloseDate.
    Per Part 7: For active opportunities (Status = Open), close date cannot be in the past
    relative to Asia/Kolkata business date.
    """
    if close_date_val in (None, ""):
        return False, "Expected Close Date is required."

    from datetime import datetime, date
    from zoneinfo import ZoneInfo

    if isinstance(close_date_val, date) and not isinstance(close_date_val, datetime):
        parsed_date = close_date_val
    elif isinstance(close_date_val, datetime):
        parsed_date = close_date_val.date()
    else:
        try:
            parsed_date = datetime.strptime(str(close_date_val).strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return False, "Expected Close Date must be in YYYY-MM-DD format."

    if status == OPPORTUNITY_STATUS_OPEN:
        today_kolkata = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        if parsed_date < today_kolkata:
            return False, "Active opportunity expected close date cannot be in the past."

    return True, None


# =============================================================================
# 6. FOLLOW-UP AND ACTIVITY BUSINESS RULES (PHASE 8)
# =============================================================================

# Follow-Up Statuses
FOLLOWUP_STATUS_PLANNED = "Planned"
FOLLOWUP_STATUS_COMPLETED = "Completed"
FOLLOWUP_STATUS_MISSED = "Missed"
FOLLOWUP_STATUS_CANCELLED = "Cancelled"
VALID_FOLLOWUP_STATUSES = {
    FOLLOWUP_STATUS_PLANNED,
    FOLLOWUP_STATUS_COMPLETED,
    FOLLOWUP_STATUS_MISSED,
    FOLLOWUP_STATUS_CANCELLED,
}

# Follow-Up Types
FOLLOWUP_TYPE_CALL = "Call"
FOLLOWUP_TYPE_MEETING = "Meeting"
FOLLOWUP_TYPE_EMAIL = "Email"
VALID_FOLLOWUP_TYPES = {
    FOLLOWUP_TYPE_CALL,
    FOLLOWUP_TYPE_MEETING,
    FOLLOWUP_TYPE_EMAIL,
}

# Follow-Up Status Transitions (Decision 97 #3)
FOLLOWUP_STATUS_TRANSITIONS = {
    FOLLOWUP_STATUS_PLANNED: {FOLLOWUP_STATUS_COMPLETED, FOLLOWUP_STATUS_MISSED, FOLLOWUP_STATUS_CANCELLED},
    FOLLOWUP_STATUS_MISSED: {FOLLOWUP_STATUS_COMPLETED, FOLLOWUP_STATUS_CANCELLED, FOLLOWUP_STATUS_PLANNED},
    FOLLOWUP_STATUS_COMPLETED: set(),  # Terminal
    FOLLOWUP_STATUS_CANCELLED: set(),  # Terminal
}

# Activity Types (Schema Constraint: Call, Meeting, Email, Task)
ACTIVITY_TYPE_CALL = "Call"
ACTIVITY_TYPE_MEETING = "Meeting"
ACTIVITY_TYPE_EMAIL = "Email"
ACTIVITY_TYPE_TASK = "Task"
VALID_ACTIVITY_TYPES = {
    ACTIVITY_TYPE_CALL,
    ACTIVITY_TYPE_MEETING,
    ACTIVITY_TYPE_EMAIL,
    ACTIVITY_TYPE_TASK,
}

# Activity Statuses
ACTIVITY_STATUS_COMPLETED = "Completed"
ACTIVITY_STATUS_PLANNED = "Planned"
VALID_ACTIVITY_STATUSES = {
    ACTIVITY_STATUS_COMPLETED,
    ACTIVITY_STATUS_PLANNED,
}


def validate_followup_status(status):
    """Validate Follow-Up status is one of Planned, Completed, Missed, Cancelled."""
    if not status or str(status).strip() not in VALID_FOLLOWUP_STATUSES:
        return False, f"Status must be one of: {', '.join(sorted(VALID_FOLLOWUP_STATUSES))}."
    return True, None


def validate_followup_type(ftype):
    """Validate Follow-Up type is one of Call, Meeting, Email."""
    if not ftype or str(ftype).strip() not in VALID_FOLLOWUP_TYPES:
        return False, f"Follow-up type must be one of: {', '.join(sorted(VALID_FOLLOWUP_TYPES))}."
    return True, None


def validate_followup_date(date_val):
    """
    Validate that FollowUpDate is not in the past relative to Asia/Kolkata business date.
    Per Part 4 & Decision 97: A new Follow-Up date cannot be before today.
    """
    if date_val in (None, ""):
        return False, "Follow-up date is required."

    from datetime import datetime, date
    from zoneinfo import ZoneInfo

    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        parsed_date = date_val
    elif isinstance(date_val, datetime):
        parsed_date = date_val.date()
    else:
        try:
            parsed_date = datetime.strptime(str(date_val).strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return False, "Follow-up date must be in YYYY-MM-DD format."

    today_kolkata = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if parsed_date < today_kolkata:
        return False, "Follow-up date cannot be in the past."

    return True, None


def validate_followup_status_transition(current_status, target_status):
    """
    Validate Follow-Up status transitions.
    Planned -> Completed, Missed, Cancelled
    Missed -> Completed, Cancelled, Planned (Rescheduled)
    Completed and Cancelled are terminal.
    """
    if current_status == target_status:
        return True, None

    allowed = FOLLOWUP_STATUS_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        return False, f"Invalid status transition from '{current_status}' to '{target_status}'."

    return True, None


def validate_activity_type(atype):
    """Validate Activity type against schema constraint ('Call', 'Meeting', 'Email', 'Task')."""
    if not atype or str(atype).strip() not in VALID_ACTIVITY_TYPES:
        return False, f"Activity type must be one of: {', '.join(sorted(VALID_ACTIVITY_TYPES))}."
    return True, None


def validate_activity_status(status):
    """Validate Activity status."""
    if not status or str(status).strip() not in VALID_ACTIVITY_STATUSES:
        return False, f"Activity status must be one of: {', '.join(sorted(VALID_ACTIVITY_STATUSES))}."
    return True, None


def validate_activity_date(date_val):
    """
    Validate ActivityDate is a valid date or timestamp.
    Accepts YYYY-MM-DD, YYYY-MM-DD HH:MM, or YYYY-MM-DDTHH:MM format.
    """
    if date_val in (None, ""):
        return False, "Activity date is required."

    from datetime import datetime, date
    if isinstance(date_val, (date, datetime)):
        return True, None

    date_str = str(date_val).strip()
    # Try ISO/standard formats
    formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
    for fmt in formats:
        try:
            datetime.strptime(date_str, fmt)
            return True, None
        except ValueError:
            continue

    return False, "Activity date must be a valid date or timestamp (e.g. YYYY-MM-DD HH:MM)."



