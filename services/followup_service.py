"""
Follow-Up Application Service for AcxiomCRM (Phase 8).

Coordinates domain business logic, authorization scope checks, multi-entity validations,
audit logging, and atomic database transaction boundaries for the followups table.
Adheres strictly to:
- Services own database transaction boundaries (BEGIN / COMMIT / ROLLBACK).
- Repositories never commit.
- Strict ownership verification before mutations (can_access_record).
- Scope-aware SQL retrieval via get_visible_user_ids.
- Atomic audit logging in the same database transaction.
"""

from datetime import datetime, date
from zoneinfo import ZoneInfo

import database
from repositories import (
    followup_repository,
    customer_repository,
    lead_repository,
    opportunity_repository,
    user_repository,
)
from schemas.followup_schema import validate_followup_form
from security.authorization import (
    can_access_record,
    get_visible_user_ids,
    has_role,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES_EXECUTIVE,
)
from services import audit_service
from validation.business_rules import (
    validate_followup_status_transition,
    validate_followup_date,
    FOLLOWUP_STATUS_PLANNED,
    FOLLOWUP_STATUS_COMPLETED,
    FOLLOWUP_STATUS_MISSED,
    FOLLOWUP_STATUS_CANCELLED,
)


def create_followup(form_data, current_user, ip_address=None):
    """
    Validate and create a new follow-up atomically within a database transaction.

    :param form_data: Dictionary containing incoming request fields.
    :param current_user: Dictionary representing the authenticated actor.
    :param ip_address: Remote client IP address for auditing.
    :return: (success: bool, followup: dict | None, errors: dict, status_code: int)
    """
    # 1. Schema-level field validation
    errors = validate_followup_form(form_data, is_edit=False)
    if errors:
        return False, None, errors, 400

    # 2. Relationship Validation and Authorization (Decision 97 #1)
    customer_id = None
    lead_id = None
    opportunity_id = None

    raw_cust_id = form_data.get("customer_id")
    raw_lead_id = form_data.get("lead_id")
    raw_opp_id = form_data.get("opportunity_id")

    # Validate Customer if provided
    if raw_cust_id not in (None, "", "0"):
        customer_id = int(str(raw_cust_id).strip())
        customer = customer_repository.find_by_id(customer_id)
        if not customer:
            errors["customer_id"] = "Selected customer does not exist."
            return False, None, errors, 400
        if customer.get("status") != "Active":
            errors["customer_id"] = "Inactive customers cannot receive new follow-ups."
            return False, None, errors, 400
        if not can_access_record(current_user, customer.get("assigned_to")):
            errors["customer_id"] = "You are not authorized to create a follow-up for this customer."
            return False, None, errors, 403

    # Validate Lead if provided
    if raw_lead_id not in (None, "", "0"):
        lead_id = int(str(raw_lead_id).strip())
        lead = lead_repository.find_by_id(lead_id)
        if not lead:
            errors["lead_id"] = "Selected lead does not exist."
            return False, None, errors, 400
        if lead.get("status") in ("Converted", "Unqualified", "Lost"):
            errors["lead_id"] = f"Cannot schedule a follow-up for a {lead.get('status')} lead."
            return False, None, errors, 400
        if not can_access_record(current_user, lead.get("assigned_to")):
            errors["lead_id"] = "You are not authorized to create a follow-up for this lead."
            return False, None, errors, 403

    # Validate Opportunity if provided
    if raw_opp_id not in (None, "", "0"):
        opportunity_id = int(str(raw_opp_id).strip())
        opp = opportunity_repository.find_by_id(opportunity_id)
        if not opp:
            errors["opportunity_id"] = "Selected opportunity does not exist."
            return False, None, errors, 400
        if not can_access_record(current_user, opp.get("assigned_to")):
            errors["opportunity_id"] = "You are not authorized to create a follow-up for this opportunity."
            return False, None, errors, 403
        # If customer_id was not explicitly passed, auto-link to the opportunity's parent customer
        if not customer_id and opp.get("customer_id"):
            customer_id = opp.get("customer_id")

    # Final check: at least one relation must be present
    if not (customer_id or lead_id or opportunity_id):
        errors["relationship"] = "At least one related entity (Customer, Lead, or Opportunity) must be selected."
        return False, None, errors, 400

    # 3. Ownership Assignment Rule (Decision 97 #6)
    if has_role(current_user, ROLE_SALES_EXECUTIVE):
        assigned_to = current_user["user_id"]
    else:
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

    subject = form_data["subject"].strip()
    followup_date = str(form_data["followup_date"]).strip()
    followup_type = form_data["followup_type"].strip()
    remarks = (form_data.get("remarks") or "").strip() or None
    status = FOLLOWUP_STATUS_PLANNED

    # 4. Atomic Transaction: Insert Follow-Up + Insert CREATE Audit Log
    conn = database.get_db_connection()
    try:
        new_followup = followup_repository.create_followup(
            subject=subject,
            followup_date=followup_date,
            followup_type=followup_type,
            customer_id=customer_id,
            lead_id=lead_id,
            opportunity_id=opportunity_id,
            remarks=remarks,
            status=status,
            assigned_to=assigned_to,
            conn=conn,
        )

        audit_payload = {
            "subject": subject,
            "followup_date": followup_date,
            "followup_type": followup_type,
            "customer_id": customer_id,
            "lead_id": lead_id,
            "opportunity_id": opportunity_id,
            "status": status,
            "assigned_to": assigned_to,
        }

        audit_service.log_event(
            action="CREATE",
            entity_name="FOLLOWUP",
            record_id=new_followup["followup_id"],
            new_value=audit_payload,
            user_id=current_user["user_id"],
            ip_address=ip_address,
            conn=conn,
        )

        conn.commit()
        return True, new_followup, {}, 201

    except Exception as e:
        conn.rollback()
        raise e


def get_followups_list(
    current_user,
    search=None,
    status=None,
    ftype=None,
    assigned_to=None,
    view_filter=None,
    customer_id=None,
    lead_id=None,
    opportunity_id=None,
    page=1,
    per_page=20,
):
    """
    Retrieve follow-ups visible to current user with SQL-level scoping.
    """
    visible_user_ids = get_visible_user_ids(current_user)

    # Restrict rep filter to permitted scope
    filter_assigned = None
    if assigned_to:
        try:
            target_id = int(assigned_to)
            if visible_user_ids is None or target_id in visible_user_ids:
                filter_assigned = target_id
            else:
                return [], {"total": 0, "page": page, "per_page": per_page, "pages": 0}, {}
        except (ValueError, TypeError):
            pass

    offset = (page - 1) * per_page

    followups = followup_repository.find_followups(
        visible_user_ids=visible_user_ids,
        search=search,
        status=status,
        ftype=ftype,
        assigned_to=filter_assigned,
        view_filter=view_filter,
        customer_id=customer_id,
        lead_id=lead_id,
        opportunity_id=opportunity_id,
        limit=per_page,
        offset=offset,
    )

    total_count = followup_repository.count_followups(
        visible_user_ids=visible_user_ids,
        search=search,
        status=status,
        ftype=ftype,
        assigned_to=filter_assigned,
        view_filter=view_filter,
        customer_id=customer_id,
        lead_id=lead_id,
        opportunity_id=opportunity_id,
    )

    metrics = followup_repository.get_followup_metrics(visible_user_ids=visible_user_ids)

    # Annotate computed overdue state for template presentation
    today_kolkata = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    for f in followups:
        f_date = f["followup_date"]
        if isinstance(f_date, datetime):
            f_date = f_date.date()
        f["is_overdue"] = f["status"] == FOLLOWUP_STATUS_PLANNED and f_date < today_kolkata

    total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total_count,
        "pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_num": page - 1,
        "next_num": page + 1,
    }

    return followups, pagination, metrics


def get_followup_detail(followup_id, current_user):
    """
    Retrieve follow-up by primary key with strict IDOR access control.

    :return: (followup: dict | None, status_code: int)
    """
    followup = followup_repository.find_by_id(followup_id)
    if not followup:
        return None, 404

    if not can_access_record(current_user, followup["assigned_to"]):
        return None, 403

    # Add computed overdue flag
    today_kolkata = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    f_date = followup["followup_date"]
    if isinstance(f_date, datetime):
        f_date = f_date.date()
    followup["is_overdue"] = followup["status"] == FOLLOWUP_STATUS_PLANNED and f_date < today_kolkata

    return followup, 200


def update_followup(followup_id, form_data, current_user, ip_address=None):
    """
    Update an existing follow-up within an atomic transaction.
    """
    conn = database.get_db_connection()
    try:
        existing = followup_repository.find_by_id(followup_id, conn=conn, for_update=True)
        if not existing:
            conn.rollback()
            return False, None, {"general": "Follow-up not found."}, 404

        if not can_access_record(current_user, existing["assigned_to"]):
            conn.rollback()
            return False, None, {"general": "You are not authorized to edit this follow-up."}, 403

        # Check terminal state
        if existing["status"] in (FOLLOWUP_STATUS_COMPLETED, FOLLOWUP_STATUS_CANCELLED):
            conn.rollback()
            return False, None, {"general": f"Follow-ups in '{existing['status']}' status are terminal and cannot be edited."}, 400

        # Validate form
        errors = validate_followup_form(form_data, is_edit=True, current_status=existing["status"])
        if errors:
            conn.rollback()
            return False, None, errors, 400

        # Validate target status transition if changing
        target_status = form_data.get("status", existing["status"]).strip()
        if target_status != existing["status"]:
            is_valid_trans, trans_err = validate_followup_status_transition(existing["status"], target_status)
            if not is_valid_trans:
                conn.rollback()
                return False, None, {"status": trans_err}, 400

        # Assignment permissions
        if has_role(current_user, ROLE_SALES_EXECUTIVE):
            assigned_to = existing["assigned_to"]
        else:
            raw_assigned = form_data.get("assigned_to")
            if raw_assigned in (None, ""):
                assigned_to = existing["assigned_to"]
            else:
                try:
                    assigned_to = int(raw_assigned)
                    target_user = user_repository.find_by_id(assigned_to)
                    if not target_user or not target_user.get("is_active") or target_user.get("role_id") != 3:
                        conn.rollback()
                        return False, None, {"assigned_to": "Assigned user must be an active Sales Executive."}, 400
                except (ValueError, TypeError):
                    conn.rollback()
                    return False, None, {"assigned_to": "Assigned user ID must be a valid integer."}, 400

        subject = form_data["subject"].strip()
        followup_date = str(form_data["followup_date"]).strip()
        followup_type = form_data["followup_type"].strip()
        remarks = (form_data.get("remarks") or "").strip() or None

        updated = followup_repository.update_followup(
            followup_id=followup_id,
            subject=subject,
            followup_date=followup_date,
            followup_type=followup_type,
            remarks=remarks,
            status=target_status,
            assigned_to=assigned_to,
            customer_id=existing["customer_id"],
            lead_id=existing["lead_id"],
            opportunity_id=existing["opportunity_id"],
            conn=conn,
        )

        old_val = {
            "subject": existing["subject"],
            "followup_date": str(existing["followup_date"]),
            "followup_type": existing["followup_type"],
            "remarks": existing["remarks"],
            "status": existing["status"],
            "assigned_to": existing["assigned_to"],
        }
        new_val = {
            "subject": subject,
            "followup_date": followup_date,
            "followup_type": followup_type,
            "remarks": remarks,
            "status": target_status,
            "assigned_to": assigned_to,
        }

        audit_action = "STATUS_CHANGE" if target_status != existing["status"] else "UPDATE"

        audit_service.log_event(
            action=audit_action,
            entity_name="FOLLOWUP",
            record_id=followup_id,
            old_value=old_val,
            new_value=new_val,
            user_id=current_user["user_id"],
            ip_address=ip_address,
            conn=conn,
        )

        conn.commit()
        return True, updated, {}, 200

    except Exception as e:
        conn.rollback()
        raise e


def update_followup_status(followup_id, target_status, current_user, ip_address=None):
    """
    Transition a follow-up to Completed, Missed, or Cancelled.
    """
    conn = database.get_db_connection()
    try:
        existing = followup_repository.find_by_id(followup_id, conn=conn, for_update=True)
        if not existing:
            conn.rollback()
            return False, None, {"general": "Follow-up not found."}, 404

        if not can_access_record(current_user, existing["assigned_to"]):
            conn.rollback()
            return False, None, {"general": "You are not authorized to update this follow-up."}, 403

        if existing["status"] in (FOLLOWUP_STATUS_COMPLETED, FOLLOWUP_STATUS_CANCELLED):
            conn.rollback()
            return False, None, {"general": f"Follow-ups in '{existing['status']}' status are terminal."}, 400

        is_valid_trans, trans_err = validate_followup_status_transition(existing["status"], target_status)
        if not is_valid_trans:
            conn.rollback()
            return False, None, {"general": trans_err}, 400

        updated = followup_repository.update_status(followup_id, target_status, conn=conn)

        audit_service.log_event(
            action="STATUS_CHANGE",
            entity_name="FOLLOWUP",
            record_id=followup_id,
            old_value={"status": existing["status"]},
            new_value={"status": target_status},
            user_id=current_user["user_id"],
            ip_address=ip_address,
            conn=conn,
        )

        conn.commit()
        return True, updated, {}, 200

    except Exception as e:
        conn.rollback()
        raise e


def reschedule_followup(followup_id, new_date, current_user, ip_address=None):
    """
    Reschedule follow-up to a new date (Decision 97 #4).
    Must satisfy new_date >= today (Asia/Kolkata).
    If status was Missed, resets status to Planned.
    Audited with RESCHEDULE action recording old and new dates.
    """
    conn = database.get_db_connection()
    try:
        existing = followup_repository.find_by_id(followup_id, conn=conn, for_update=True)
        if not existing:
            conn.rollback()
            return False, None, {"general": "Follow-up not found."}, 404

        if not can_access_record(current_user, existing["assigned_to"]):
            conn.rollback()
            return False, None, {"general": "You are not authorized to reschedule this follow-up."}, 403

        if existing["status"] in (FOLLOWUP_STATUS_COMPLETED, FOLLOWUP_STATUS_CANCELLED):
            conn.rollback()
            return False, None, {"general": f"Completed and Cancelled follow-ups cannot be rescheduled."}, 400

        is_valid_date, date_err = validate_followup_date(new_date)
        if not is_valid_date:
            conn.rollback()
            return False, None, {"followup_date": date_err}, 400

        # If missed, reset to Planned upon rescheduling
        target_status = FOLLOWUP_STATUS_PLANNED

        updated = followup_repository.reschedule_followup(
            followup_id=followup_id,
            new_date=str(new_date).strip(),
            status=target_status,
            conn=conn,
        )

        audit_service.log_event(
            action="RESCHEDULE",
            entity_name="FOLLOWUP",
            record_id=followup_id,
            old_value={
                "followup_date": str(existing["followup_date"]),
                "status": existing["status"],
            },
            new_value={
                "followup_date": str(new_date).strip(),
                "status": target_status,
            },
            user_id=current_user["user_id"],
            ip_address=ip_address,
            conn=conn,
        )

        conn.commit()
        return True, updated, {}, 200

    except Exception as e:
        conn.rollback()
        raise e
