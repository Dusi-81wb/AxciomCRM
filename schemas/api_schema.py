"""
API Schemas and Data Transfer Objects (DTOs) for AcxiomCRM (Phase 11).

Provides input validation and output serialization for the REST API.
Adheres strictly to MASTER_BLUEPRINT.md Section 95 and SPECIFICATION_NOTES.md:
- Never exposes internal password hashes, authentication tokens, session objects, or database internals.
- Enforces strict type casting and presence checks on incoming JSON payloads.
- Formats monetary values as exact Decimal strings (e.g. "12500.00") without float precision loss.
- Formats dates and timestamps in ISO 8601 representation.
- Business rule logic and transactions remain entirely in the existing service layer.
"""

from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import re

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-\.]+$")
PHONE_REGEX = re.compile(r"^\+?[0-9\s\-\(\)]{10,15}$")


# =============================================================================
# HELPER SERIALIZERS
# =============================================================================

def format_datetime(dt):
    """Serialize datetime/date to ISO 8601 string or None."""
    if dt is None:
        return None
    if isinstance(dt, (datetime, date)):
        return dt.isoformat()
    return str(dt)


def format_decimal(val):
    """Serialize Decimal currency without IEEE 754 floating-point precision loss."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return f"{val:.2f}"
    try:
        d = Decimal(str(val))
        return f"{d:.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return str(val)


# =============================================================================
# 1. CUSTOMER DTOs
# =============================================================================

def serialize_customer(customer):
    """
    Transform internal Customer entity into public output DTO.
    Excludes any internal or sensitive attributes.
    """
    if not customer:
        return None
    return {
        "customer_id": customer.get("customer_id"),
        "customer_code": customer.get("customer_code"),
        "customer_name": customer.get("customer_name"),
        "email": customer.get("email"),
        "phone": customer.get("phone"),
        "company_name": customer.get("company_name"),
        "address": customer.get("address"),
        "city": customer.get("city"),
        "state": customer.get("state"),
        "status": customer.get("status"),
        "assigned_to": customer.get("assigned_to"),
        "assigned_to_name": customer.get("assigned_to_name"),
        "created_date": format_datetime(customer.get("created_date")),
    }


def validate_customer_input(payload, is_edit=False):
    """
    Validate incoming JSON payload for Customer create/update.
    Returns (cleaned_dict, errors_dict).
    """
    errors = {}
    cleaned = {}

    if not isinstance(payload, dict):
        return {}, {"general": "JSON body must be an object."}

    # Customer Name
    customer_name = payload.get("customer_name")
    if not customer_name or not str(customer_name).strip():
        errors["customer_name"] = "Customer name is required."
    elif len(str(customer_name).strip()) > 100:
        errors["customer_name"] = "Customer name cannot exceed 100 characters."
    else:
        cleaned["customer_name"] = str(customer_name).strip()

    # Email
    email = payload.get("email")
    if not email or not str(email).strip():
        errors["email"] = "Email address is required."
    elif len(str(email).strip()) > 100:
        errors["email"] = "Email cannot exceed 100 characters."
    elif not EMAIL_REGEX.match(str(email).strip()):
        errors["email"] = "Invalid email address format."
    else:
        cleaned["email"] = str(email).strip().lower()

    # Phone
    phone = payload.get("phone")
    if not phone or not str(phone).strip():
        errors["phone"] = "Phone number is required."
    else:
        phone_clean = re.sub(r"[\s\-\(\)]", "", str(phone).strip())
        digits_only = re.sub(r"^\+", "", phone_clean)
        if not (10 <= len(digits_only) <= 15 and digits_only.isdigit()):
            errors["phone"] = "Phone number must contain between 10 and 15 digits."
        else:
            cleaned["phone"] = str(phone).strip()

    # Optional string fields
    for field, max_len in [("company_name", 100), ("address", 255), ("city", 50), ("state", 50)]:
        val = payload.get(field)
        if val is not None and str(val).strip():
            if len(str(val).strip()) > max_len:
                errors[field] = f"{field.replace('_', ' ').capitalize()} cannot exceed {max_len} characters."
            else:
                cleaned[field] = str(val).strip()
        else:
            cleaned[field] = None

    # Status
    status = payload.get("status")
    if status is not None and str(status).strip():
        if str(status).strip() not in ("Active", "Inactive"):
            errors["status"] = "Status must be either 'Active' or 'Inactive'."
        else:
            cleaned["status"] = str(status).strip()
    else:
        cleaned["status"] = "Active" if not is_edit else None

    # Assigned To
    raw_assigned = payload.get("assigned_to")
    if raw_assigned not in (None, ""):
        try:
            cleaned["assigned_to"] = int(raw_assigned)
        except (ValueError, TypeError):
            errors["assigned_to"] = "Assigned user ID must be an integer."
    else:
        cleaned["assigned_to"] = None

    return cleaned, errors


# =============================================================================
# 2. LEAD DTOs
# =============================================================================

def serialize_lead(lead):
    """
    Transform internal Lead entity into public output DTO.
    Excludes sensitive/internal fields.
    """
    if not lead:
        return None
    return {
        "lead_id": lead.get("lead_id"),
        "lead_code": lead.get("lead_code"),
        "lead_name": lead.get("lead_name"),
        "email": lead.get("email"),
        "phone": lead.get("phone"),
        "company_name": lead.get("company_name"),
        "source": lead.get("source"),
        "status": lead.get("status"),
        "expected_value": format_decimal(lead.get("expected_value")),
        "assigned_to": lead.get("assigned_to"),
        "assigned_to_name": lead.get("assigned_to_name"),
        "created_date": format_datetime(lead.get("created_date")),
    }


def validate_lead_input(payload, is_edit=False):
    """
    Validate incoming JSON payload for Lead create/update.
    Returns (cleaned_dict, errors_dict).
    """
    errors = {}
    cleaned = {}

    if not isinstance(payload, dict):
        return {}, {"general": "JSON body must be an object."}

    # Lead Name
    lead_name = payload.get("lead_name")
    if not lead_name or not str(lead_name).strip():
        errors["lead_name"] = "Lead name is required."
    elif len(str(lead_name).strip()) > 100:
        errors["lead_name"] = "Lead name cannot exceed 100 characters."
    else:
        cleaned["lead_name"] = str(lead_name).strip()

    # Email
    email = payload.get("email")
    if not email or not str(email).strip():
        errors["email"] = "Email address is required."
    elif len(str(email).strip()) > 100:
        errors["email"] = "Email cannot exceed 100 characters."
    elif not EMAIL_REGEX.match(str(email).strip()):
        errors["email"] = "Invalid email address format."
    else:
        cleaned["email"] = str(email).strip().lower()

    # Phone (Optional for leads)
    phone = payload.get("phone")
    if phone is not None and str(phone).strip():
        phone_clean = re.sub(r"[\s\-\(\)]", "", str(phone).strip())
        digits_only = re.sub(r"^\+", "", phone_clean)
        if not (10 <= len(digits_only) <= 15 and digits_only.isdigit()):
            errors["phone"] = "Phone number must contain between 10 and 15 digits."
        else:
            cleaned["phone"] = str(phone).strip()
    else:
        cleaned["phone"] = None

    # Company Name
    comp = payload.get("company_name")
    if comp is not None and str(comp).strip():
        if len(str(comp).strip()) > 100:
            errors["company_name"] = "Company name cannot exceed 100 characters."
        else:
            cleaned["company_name"] = str(comp).strip()
    else:
        cleaned["company_name"] = None

    # Source
    valid_sources = ("Website", "Referral", "Cold Call", "Advertisement", "Partner", "Other")
    source = payload.get("source")
    if source is not None and str(source).strip():
        if str(source).strip() not in valid_sources:
            errors["source"] = f"Source must be one of: {', '.join(valid_sources)}."
        else:
            cleaned["source"] = str(source).strip()
    else:
        cleaned["source"] = None

    # Status
    valid_statuses = ("New", "Contacted", "Qualified", "Unqualified", "Converted", "Lost")
    status = payload.get("status")
    if status is not None and str(status).strip():
        if str(status).strip() not in valid_statuses:
            errors["status"] = f"Status must be one of: {', '.join(valid_statuses)}."
        else:
            cleaned["status"] = str(status).strip()
    else:
        cleaned["status"] = "New" if not is_edit else None

    # Expected Value
    raw_ev = payload.get("expected_value")
    if raw_ev not in (None, ""):
        try:
            ev = Decimal(str(raw_ev).strip())
            if ev < 0:
                errors["expected_value"] = "Expected value cannot be negative."
            else:
                cleaned["expected_value"] = ev
        except (InvalidOperation, TypeError, ValueError):
            errors["expected_value"] = "Expected value must be a valid numeric amount."
    else:
        cleaned["expected_value"] = None

    # Assigned To
    raw_assigned = payload.get("assigned_to")
    if raw_assigned not in (None, ""):
        try:
            cleaned["assigned_to"] = int(raw_assigned)
        except (ValueError, TypeError):
            errors["assigned_to"] = "Assigned user ID must be an integer."
    else:
        cleaned["assigned_to"] = None

    return cleaned, errors


# =============================================================================
# 3. OPPORTUNITY DTOs
# =============================================================================

def serialize_opportunity(opp):
    """
    Transform internal Opportunity entity into public output DTO.
    Excludes sensitive/internal fields.
    """
    if not opp:
        return None
    return {
        "opportunity_id": opp.get("opportunity_id"),
        "opportunity_name": opp.get("opportunity_name"),
        "customer_id": opp.get("customer_id"),
        "customer_name": opp.get("customer_name"),
        "lead_id": opp.get("lead_id"),
        "lead_name": opp.get("lead_name"),
        "amount": format_decimal(opp.get("amount")),
        "stage": opp.get("stage"),
        "probability": opp.get("probability"),
        "expected_close_date": format_datetime(opp.get("expected_close_date")),
        "status": opp.get("status"),
        "closed_date": format_datetime(opp.get("closed_date")),
        "assigned_to": opp.get("assigned_to"),
        "assigned_to_name": opp.get("assigned_to_name"),
        "created_date": format_datetime(opp.get("created_date")),
    }


def validate_opportunity_input(payload, is_edit=False):
    """
    Validate incoming JSON payload for Opportunity create/update.
    Returns (cleaned_dict, errors_dict).
    """
    errors = {}
    cleaned = {}

    if not isinstance(payload, dict):
        return {}, {"general": "JSON body must be an object."}

    # Opportunity Name
    opp_name = payload.get("opportunity_name")
    if not opp_name or not str(opp_name).strip():
        errors["opportunity_name"] = "Opportunity name is required."
    elif len(str(opp_name).strip()) > 100:
        errors["opportunity_name"] = "Opportunity name cannot exceed 100 characters."
    else:
        cleaned["opportunity_name"] = str(opp_name).strip()

    # Customer ID
    raw_cust = payload.get("customer_id")
    if raw_cust in (None, ""):
        errors["customer_id"] = "Customer ID is required."
    else:
        try:
            cleaned["customer_id"] = int(raw_cust)
        except (ValueError, TypeError):
            errors["customer_id"] = "Customer ID must be a valid integer."

    # Lead ID (Optional)
    raw_lead = payload.get("lead_id")
    if raw_lead not in (None, ""):
        try:
            cleaned["lead_id"] = int(raw_lead)
        except (ValueError, TypeError):
            errors["lead_id"] = "Lead ID must be a valid integer."
    else:
        cleaned["lead_id"] = None

    # Amount
    raw_amount = payload.get("amount")
    if raw_amount in (None, ""):
        errors["amount"] = "Amount is required."
    else:
        try:
            amt = Decimal(str(raw_amount).strip())
            if amt <= 0:
                errors["amount"] = "Amount must be greater than zero."
            else:
                cleaned["amount"] = amt
        except (InvalidOperation, TypeError, ValueError):
            errors["amount"] = "Amount must be a valid numeric amount."

    # Stage
    valid_stages = ("Qualification", "Proposal", "Negotiation", "Won", "Lost")
    stage = payload.get("stage")
    if stage is not None and str(stage).strip():
        if str(stage).strip() not in valid_stages:
            errors["stage"] = f"Stage must be one of: {', '.join(valid_stages)}."
        else:
            cleaned["stage"] = str(stage).strip()
    else:
        cleaned["stage"] = "Qualification" if not is_edit else None

    # Probability
    raw_prob = payload.get("probability")
    if raw_prob in (None, ""):
        errors["probability"] = "Probability is required."
    else:
        try:
            prob = int(raw_prob)
            if not (0 <= prob <= 100):
                errors["probability"] = "Probability must be an integer between 0 and 100."
            else:
                cleaned["probability"] = prob
        except (ValueError, TypeError):
            errors["probability"] = "Probability must be an integer."

    # Expected Close Date
    close_date = payload.get("expected_close_date")
    if not close_date or not str(close_date).strip():
        errors["expected_close_date"] = "Expected close date is required."
    else:
        try:
            datetime.strptime(str(close_date).strip(), "%Y-%m-%d")
            cleaned["expected_close_date"] = str(close_date).strip()
        except ValueError:
            errors["expected_close_date"] = "Expected close date must be in YYYY-MM-DD format."

    # Assigned To
    raw_assigned = payload.get("assigned_to")
    if raw_assigned not in (None, ""):
        try:
            cleaned["assigned_to"] = int(raw_assigned)
        except (ValueError, TypeError):
            errors["assigned_to"] = "Assigned user ID must be an integer."
    else:
        cleaned["assigned_to"] = None

    return cleaned, errors
