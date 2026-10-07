"""
Opportunity Service for AcxiomCRM (Phase 7).

Orchestrates Opportunity business logic, validation, ownership/scope enforcement,
pipeline calculations, and atomic transaction audit coordination.
Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md Section 95:
- Monetary values: Handled strictly with Python Decimal; floats strictly prohibited.
- Active opportunity constraints: Status = Open, Amount > 0, Probability 0-100, ExpectedCloseDate >= today in Asia/Kolkata.
- Customer eligibility: Only Active customers may receive new opportunities.
- Ownership: Sales Executive creations are automatically self-assigned; Admin/Manager can assign active Sales Executives.
- Terminal states: Won and Lost are strictly terminal; reopening is prohibited.
- Pipeline calculations: Scope-aware, exact Decimal arithmetic for Open opportunities only.
- Audit: Every mutation commits atomically with an audit log in the same PostgreSQL transaction.
"""

import math
from datetime import datetime, date
from decimal import Decimal
from zoneinfo import ZoneInfo

import database
from repositories import opportunity_repository, customer_repository, user_repository, lead_repository
from schemas.opportunity_schema import validate_opportunity_form
from validation.business_rules import (
    validate_opportunity_stage,
    validate_opportunity_status,
    validate_opportunity_stage_transition,
    validate_opportunity_stage_status_consistency,
    OPPORTUNITY_STAGE_QUALIFICATION,
    OPPORTUNITY_STAGE_WON,
    OPPORTUNITY_STAGE_LOST,
    OPPORTUNITY_STATUS_OPEN,
    OPPORTUNITY_STATUS_WON,
    OPPORTUNITY_STATUS_LOST,
)
from security.authorization import (
    visible_user_ids,
    can_access_record,
    has_role,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES_EXECUTIVE,
)
from services import audit_service


def create_opportunity(form_data, current_user, ip_address=None):
    """
    Create a new Opportunity record with authorization and atomic audit trail.

    :param form_data: Form data dictionary.
    :param current_user: Authenticated actor.
    :param ip_address: Remote client IP.
    :return: Tuple (success: bool, opportunity_dict: dict or None, errors: dict, status_code: int).
    """
    errors = validate_opportunity_form(form_data, is_edit=False)
    if errors:
        return False, None, errors, 400

    opp_name = form_data["opportunity_name"].strip()
    customer_id = int(str(form_data["customer_id"]).strip())

    # 1. Verify Customer exists and is Active (Decision 95 #2)
    customer = customer_repository.find_by_id(customer_id)
    if not customer:
        errors["customer_id"] = "Selected customer does not exist."
        return False, None, errors, 400

    if customer.get("status") != "Active":
        errors["customer_id"] = "Customer is inactive. Inactive customers cannot receive new opportunities."
        return False, None, errors, 400

    if not can_access_record(current_user, customer.get("assigned_to")):
        errors["customer_id"] = "You are not authorized to create an opportunity for this customer."
        return False, None, errors, 403

    # 2. Verify optional Lead relationship if supplied
    lead_id = None
    raw_lead_id = form_data.get("lead_id")
    if raw_lead_id not in (None, ""):
        lead_id = int(str(raw_lead_id).strip())
        lead = lead_repository.find_by_id(lead_id)
        if not lead:
            errors["lead_id"] = "Selected lead does not exist."
            return False, None, errors, 400
        if not can_access_record(current_user, lead.get("assigned_to")):
            errors["lead_id"] = "You are not authorized to link this lead."
            return False, None, errors, 403

    # 3. Ownership Assignment Rule (Decision 95 #3, Section 96)
    if has_role(current_user, ROLE_SALES_EXECUTIVE):
        # Sales Executive automatically self-assigns created opportunity
        assigned_to = current_user["user_id"]
    else:
        # Admin / Manager must explicitly select an active Sales Executive (No fallback)
        raw_assigned = form_data.get("assigned_to")
        if raw_assigned in (None, ""):
            errors["assigned_to"] = "An active Sales Executive must be explicitly selected."
            return False, None, errors, 400

        try:
            assigned_to = int(str(raw_assigned).strip())
            target_user = user_repository.find_by_id(assigned_to)
            if not target_user or not target_user.get("is_active") or target_user.get("role_id") != 3:
                errors["assigned_to"] = "Assigned user must be an active Sales Executive."
                return False, None, errors, 400
        except (ValueError, TypeError):
            errors["assigned_to"] = "Assigned user ID must be a valid integer."
            return False, None, errors, 400

    # 4. Values formatting (Exact Decimal arithmetic)
    amount = Decimal(str(form_data["amount"]).strip())
    stage = form_data.get("stage", OPPORTUNITY_STAGE_QUALIFICATION).strip()
    probability = int(str(form_data["probability"]).strip())
    expected_close_date = str(form_data["expected_close_date"]).strip()

    # Stage / Status synchronization
    if stage == OPPORTUNITY_STAGE_WON:
        status = OPPORTUNITY_STATUS_WON
        closed_date = datetime.now(ZoneInfo("Asia/Kolkata"))
    elif stage == OPPORTUNITY_STAGE_LOST:
        status = OPPORTUNITY_STATUS_LOST
        closed_date = datetime.now(ZoneInfo("Asia/Kolkata"))
    else:
        status = OPPORTUNITY_STATUS_OPEN
        closed_date = None

    # 5. Atomic Transaction: Insert Opportunity + Insert CREATE Audit Log
    conn = database.get_db_connection()
    try:
        new_opp = opportunity_repository.create_opportunity(
            opportunity_name=opp_name,
            customer_id=customer_id,
            amount=amount,
            stage=stage,
            probability=probability,
            expected_close_date=expected_close_date,
            status=status,
            assigned_to=assigned_to,
            lead_id=lead_id,
            closed_date=closed_date,
            conn=conn
        )

        audit_new_value = {
            "opportunity_id": new_opp["opportunity_id"],
            "opportunity_name": new_opp["opportunity_name"],
            "customer_id": new_opp["customer_id"],
            "lead_id": new_opp["lead_id"],
            "amount": str(new_opp["amount"]),
            "stage": new_opp["stage"],
            "probability": new_opp["probability"],
            "expected_close_date": str(new_opp["expected_close_date"]),
            "status": new_opp["status"],
            "assigned_to": new_opp["assigned_to"],
        }

        audit_service.log_event(
            action=audit_service.ACTION_CREATE,
            entity_name=audit_service.ENTITY_OPPORTUNITY,
            user_id=current_user["user_id"],
            record_id=new_opp["opportunity_id"],
            old_value=None,
            new_value=audit_new_value,
            result="Success",
            ip_address=ip_address,
            conn=conn
        )

        conn.commit()
        return True, new_opp, {}, 201

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_opportunities_list(
    current_user,
    search=None,
    customer_id=None,
    stage=None,
    status=None,
    assigned_to=None,
    sort_by="created_date",
    sort_order="DESC",
    page=1,
    per_page=10
):
    """
    Retrieve paginated opportunities with SQL-level ownership scoping and pipeline metrics.

    :return: Tuple (opportunities: list, total_count: int, total_pages: int, pipeline_summary: dict).
    """
    if has_role(current_user, ROLE_ADMIN):
        allowed_user_ids = None
    elif has_role(current_user, ROLE_MANAGER):
        allowed_user_ids = visible_user_ids(current_user)
    elif has_role(current_user, ROLE_SALES_EXECUTIVE):
        allowed_user_ids = [current_user["user_id"]]
    else:
        allowed_user_ids = []

    # Calculate pipeline aggregate metrics under actor's scope
    pipeline_summary = opportunity_repository.calculate_pipeline_totals(
        allowed_user_ids=allowed_user_ids
    )

    total_count = opportunity_repository.count_opportunities(
        allowed_user_ids=allowed_user_ids,
        search=search,
        customer_id=customer_id,
        stage=stage,
        status=status,
        assigned_to=assigned_to
    )

    total_pages = max(1, math.ceil(total_count / per_page))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    opportunities = opportunity_repository.find_opportunities(
        allowed_user_ids=allowed_user_ids,
        search=search,
        customer_id=customer_id,
        stage=stage,
        status=status,
        assigned_to=assigned_to,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=per_page,
        offset=offset
    )

    # Attach weighted value for display
    for opp in opportunities:
        amt = Decimal(str(opp["amount"]))
        prob = Decimal(str(opp["probability"]))
        opp["weighted_value"] = (amt * prob / Decimal("100.00")).quantize(Decimal("0.01"))

    return opportunities, total_count, total_pages, pipeline_summary


def get_opportunity_detail(opportunity_id, current_user):
    """
    Retrieve opportunity detail and verify IDOR scope.

    :param opportunity_id: Integer primary key.
    :param current_user: Authenticated actor.
    :return: Tuple (opportunity_dict: dict or None, status_code: int).
    """
    opp = opportunity_repository.find_by_id(opportunity_id)
    if not opp:
        return None, 404

    if not can_access_record(current_user, opp.get("assigned_to")):
        return None, 403

    # Calculate weighted value with exact Decimal arithmetic
    amt = Decimal(str(opp["amount"]))
    prob = Decimal(str(opp["probability"]))
    opp["weighted_value"] = (amt * prob / Decimal("100.00")).quantize(Decimal("0.01"))

    return opp, 200


def update_opportunity(opportunity_id, form_data, current_user, ip_address=None):
    """
    Update opportunity details with ownership verification and audit trail.

    :return: Tuple (success: bool, opportunity_dict: dict or None, errors: dict, status_code: int).
    """
    existing_opp = opportunity_repository.find_by_id(opportunity_id)
    if not existing_opp:
        return False, None, {"general": "Opportunity not found."}, 404

    if not can_access_record(current_user, existing_opp.get("assigned_to")):
        return False, None, {"general": "You are not authorized to update this opportunity."}, 403

    # Terminal protection: Won/Lost deals cannot be updated (Decision 95 #4)
    if existing_opp["status"] in (OPPORTUNITY_STATUS_WON, OPPORTUNITY_STATUS_LOST):
        return False, None, {"general": "Won and Lost opportunities are terminal and cannot be modified."}, 400

    errors = validate_opportunity_form(form_data, is_edit=True, current_status=existing_opp["status"])
    if errors:
        return False, None, errors, 400

    opp_name = form_data["opportunity_name"].strip()
    customer_id = int(str(form_data["customer_id"]).strip())

    # Customer check
    customer = customer_repository.find_by_id(customer_id)
    if not customer:
        errors["customer_id"] = "Selected customer does not exist."
        return False, None, errors, 400
    if customer.get("status") != "Active":
        errors["customer_id"] = "Customer is inactive. Inactive customers cannot receive opportunities."
        return False, None, errors, 400

    # Lead check
    lead_id = None
    raw_lead_id = form_data.get("lead_id")
    if raw_lead_id not in (None, ""):
        lead_id = int(str(raw_lead_id).strip())
        lead = lead_repository.find_by_id(lead_id)
        if not lead:
            errors["lead_id"] = "Selected lead does not exist."
            return False, None, errors, 400

    # Ownership reassignment rule
    if has_role(current_user, ROLE_SALES_EXECUTIVE):
        assigned_to = existing_opp["assigned_to"]
    else:
        raw_assigned = form_data.get("assigned_to")
        if raw_assigned in (None, ""):
            assigned_to = existing_opp["assigned_to"]
        else:
            try:
                assigned_to = int(raw_assigned)
                target_user = user_repository.find_by_id(assigned_to)
                if not target_user or not target_user.get("is_active") or target_user.get("role_id") != 3:
                    errors["assigned_to"] = "Assigned user must be an active Sales Executive."
                    return False, None, errors, 400
            except (ValueError, TypeError):
                errors["assigned_to"] = "Assigned user ID must be a valid integer."
                return False, None, errors, 400

    # Stage transition check if stage is changing
    target_stage = form_data.get("stage", existing_opp["stage"]).strip()
    if target_stage != existing_opp["stage"]:
        is_valid_trans, trans_err = validate_opportunity_stage_transition(existing_opp["stage"], target_stage)
        if not is_valid_trans:
            errors["stage"] = trans_err
            return False, None, errors, 400

    amount = Decimal(str(form_data["amount"]).strip())
    probability = int(str(form_data["probability"]).strip())
    expected_close_date = str(form_data["expected_close_date"]).strip()

    # Stage / Status synchronization
    if target_stage == OPPORTUNITY_STAGE_WON:
        status = OPPORTUNITY_STATUS_WON
        closed_date = datetime.now(ZoneInfo("Asia/Kolkata"))
    elif target_stage == OPPORTUNITY_STAGE_LOST:
        status = OPPORTUNITY_STATUS_LOST
        closed_date = datetime.now(ZoneInfo("Asia/Kolkata"))
    else:
        status = OPPORTUNITY_STATUS_OPEN
        closed_date = None

    conn = database.get_db_connection()
    try:
        updated_opp = opportunity_repository.update_opportunity(
            opportunity_id=opportunity_id,
            opportunity_name=opp_name,
            customer_id=customer_id,
            amount=amount,
            stage=target_stage,
            probability=probability,
            expected_close_date=expected_close_date,
            status=status,
            assigned_to=assigned_to,
            lead_id=lead_id,
            closed_date=closed_date,
            conn=conn
        )

        old_val = {
            "opportunity_name": existing_opp["opportunity_name"],
            "customer_id": existing_opp["customer_id"],
            "lead_id": existing_opp["lead_id"],
            "amount": str(existing_opp["amount"]),
            "stage": existing_opp["stage"],
            "probability": existing_opp["probability"],
            "expected_close_date": str(existing_opp["expected_close_date"]),
            "status": existing_opp["status"],
            "assigned_to": existing_opp["assigned_to"],
        }
        new_val = {
            "opportunity_name": updated_opp["opportunity_name"],
            "customer_id": updated_opp["customer_id"],
            "lead_id": updated_opp["lead_id"],
            "amount": str(updated_opp["amount"]),
            "stage": updated_opp["stage"],
            "probability": updated_opp["probability"],
            "expected_close_date": str(updated_opp["expected_close_date"]),
            "status": updated_opp["status"],
            "assigned_to": updated_opp["assigned_to"],
        }

        audit_service.log_event(
            action=audit_service.ACTION_UPDATE,
            entity_name=audit_service.ENTITY_OPPORTUNITY,
            user_id=current_user["user_id"],
            record_id=opportunity_id,
            old_value=old_val,
            new_value=new_val,
            result="Success",
            ip_address=ip_address,
            conn=conn
        )

        conn.commit()
        return True, updated_opp, {}, 200

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_opportunity_stage(opportunity_id, target_stage, current_user, ip_address=None):
    """
    Perform a validated stage and status transition on an Opportunity.

    :param opportunity_id: Integer primary key.
    :param target_stage: Requested new stage.
    :param current_user: Authenticated actor.
    :param ip_address: Remote client IP.
    :return: Tuple (success: bool, error_msg: str or None, status_code: int).
    """
    opp = opportunity_repository.find_by_id(opportunity_id)
    if not opp:
        return False, "Opportunity not found.", 404

    if not can_access_record(current_user, opp.get("assigned_to")):
        return False, "Unauthorized access to this opportunity.", 403

    # Terminal state protection
    if opp["status"] in (OPPORTUNITY_STATUS_WON, OPPORTUNITY_STATUS_LOST):
        return False, "Won and Lost opportunities cannot be modified.", 400

    is_valid_stage, stage_err = validate_opportunity_stage(target_stage)
    if not is_valid_stage:
        return False, stage_err, 400

    is_valid_trans, trans_err = validate_opportunity_stage_transition(opp["stage"], target_stage)
    if not is_valid_trans:
        return False, trans_err, 400

    if target_stage == OPPORTUNITY_STAGE_WON:
        target_status = OPPORTUNITY_STATUS_WON
        closed_date = datetime.now(ZoneInfo("Asia/Kolkata"))
    elif target_stage == OPPORTUNITY_STAGE_LOST:
        target_status = OPPORTUNITY_STATUS_LOST
        closed_date = datetime.now(ZoneInfo("Asia/Kolkata"))
    else:
        target_status = OPPORTUNITY_STATUS_OPEN
        closed_date = None

    conn = database.get_db_connection()
    try:
        opportunity_repository.update_stage_status(
            opportunity_id=opportunity_id,
            stage=target_stage,
            status=target_status,
            closed_date=closed_date,
            conn=conn
        )

        audit_service.log_event(
            action=audit_service.ACTION_STATUS_CHANGE,
            entity_name=audit_service.ENTITY_OPPORTUNITY,
            user_id=current_user["user_id"],
            record_id=opportunity_id,
            old_value={"stage": opp["stage"], "status": opp["status"]},
            new_value={"stage": target_stage, "status": target_status},
            result="Success",
            ip_address=ip_address,
            conn=conn
        )

        conn.commit()
        return True, None, 200

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def calculate_pipeline(current_user):
    """
    Retrieve active pipeline metrics scoped to actor's visibility boundaries.
    """
    if has_role(current_user, ROLE_ADMIN):
        allowed_user_ids = None
    elif has_role(current_user, ROLE_MANAGER):
        allowed_user_ids = visible_user_ids(current_user)
    elif has_role(current_user, ROLE_SALES_EXECUTIVE):
        allowed_user_ids = [current_user["user_id"]]
    else:
        allowed_user_ids = []

    return opportunity_repository.calculate_pipeline_totals(allowed_user_ids=allowed_user_ids)
