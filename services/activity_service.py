"""
Activity Application Service for AcxiomCRM (Phase 8).

Coordinates domain business logic, authorization scope checks, multi-entity validations,
audit logging, and atomic database transaction boundaries for the activities table.
Adheres strictly to:
- Services own database transaction boundaries (BEGIN / COMMIT / ROLLBACK).
- Repositories never commit.
- Strict ownership verification before mutations (can_access_record).
- Scope-aware SQL retrieval via get_visible_user_ids.
- Atomic audit logging in the same database transaction.
- Schema compliance: activities table links only to customers and leads (no opportunity_id).
"""

from datetime import datetime

import database
from repositories import (
    activity_repository,
    customer_repository,
    lead_repository,
    user_repository,
)
from schemas.activity_schema import validate_activity_form
from security.authorization import (
    can_access_record,
    get_visible_user_ids,
    has_role,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES_EXECUTIVE,
)
from services import audit_service
from validation.business_rules import ACTIVITY_STATUS_COMPLETED


def create_activity(form_data, current_user, ip_address=None):
    """
    Validate and create a new activity atomically within a database transaction.

    :param form_data: Dictionary containing incoming request fields.
    :param current_user: Dictionary representing the authenticated actor.
    :param ip_address: Remote client IP address for auditing.
    :return: (success: bool, activity: dict | None, errors: dict, status_code: int)
    """
    # 1. Schema validation
    errors = validate_activity_form(form_data, is_edit=False)
    if errors:
        return False, None, errors, 400

    # 2. Relationship Validation and Authorization (Decision 97 #5)
    customer_id = None
    lead_id = None

    raw_cust_id = form_data.get("customer_id")
    raw_lead_id = form_data.get("lead_id")

    if raw_cust_id not in (None, "", "0"):
        customer_id = int(str(raw_cust_id).strip())
        customer = customer_repository.find_by_id(customer_id)
        if not customer:
            errors["customer_id"] = "Selected customer does not exist."
            return False, None, errors, 400
        if customer.get("status") != "Active":
            errors["customer_id"] = "Inactive customers cannot receive new activities."
            return False, None, errors, 400
        if not can_access_record(current_user, customer.get("assigned_to")):
            errors["customer_id"] = "You are not authorized to create an activity for this customer."
            return False, None, errors, 403

    if raw_lead_id not in (None, "", "0"):
        lead_id = int(str(raw_lead_id).strip())
        lead = lead_repository.find_by_id(lead_id)
        if not lead:
            errors["lead_id"] = "Selected lead does not exist."
            return False, None, errors, 400
        if not can_access_record(current_user, lead.get("assigned_to")):
            errors["lead_id"] = "You are not authorized to create an activity for this lead."
            return False, None, errors, 403

    if not (customer_id or lead_id):
        errors["relationship"] = "At least one related entity (Customer or Lead) must be selected."
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

    activity_type = form_data["activity_type"].strip()
    subject = form_data["subject"].strip()
    activity_date = str(form_data["activity_date"]).strip()
    description = (form_data.get("description") or "").strip() or None
    status = (form_data.get("status") or ACTIVITY_STATUS_COMPLETED).strip()

    # 4. Atomic Transaction: Insert Activity + Insert CREATE Audit Log
    conn = database.get_db_connection()
    try:
        new_activity = activity_repository.create_activity(
            activity_type=activity_type,
            subject=subject,
            activity_date=activity_date,
            customer_id=customer_id,
            lead_id=lead_id,
            description=description,
            assigned_to=assigned_to,
            status=status,
            conn=conn,
        )

        audit_payload = {
            "activity_type": activity_type,
            "subject": subject,
            "activity_date": activity_date,
            "customer_id": customer_id,
            "lead_id": lead_id,
            "status": status,
            "assigned_to": assigned_to,
        }

        audit_service.log_event(
            action="CREATE",
            entity_name="ACTIVITY",
            record_id=new_activity["activity_id"],
            new_value=audit_payload,
            user_id=current_user["user_id"],
            ip_address=ip_address,
            conn=conn,
        )

        conn.commit()
        return True, new_activity, {}, 201

    except Exception as e:
        conn.rollback()
        raise e


def get_activities_list(
    current_user,
    search=None,
    activity_type=None,
    status=None,
    assigned_to=None,
    customer_id=None,
    lead_id=None,
    page=1,
    per_page=20,
):
    """
    Retrieve activities visible to current user with SQL-level scoping.
    """
    visible_user_ids = get_visible_user_ids(current_user)

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

    activities = activity_repository.find_activities(
        visible_user_ids=visible_user_ids,
        search=search,
        activity_type=activity_type,
        status=status,
        assigned_to=filter_assigned,
        customer_id=customer_id,
        lead_id=lead_id,
        limit=per_page,
        offset=offset,
    )

    total_count = activity_repository.count_activities(
        visible_user_ids=visible_user_ids,
        search=search,
        activity_type=activity_type,
        status=status,
        assigned_to=filter_assigned,
        customer_id=customer_id,
        lead_id=lead_id,
    )

    metrics = activity_repository.get_activity_metrics(visible_user_ids=visible_user_ids)

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

    return activities, pagination, metrics


def get_activity_detail(activity_id, current_user):
    """
    Retrieve activity by primary key with strict IDOR access control.

    :return: (activity: dict | None, status_code: int)
    """
    activity = activity_repository.find_by_id(activity_id)
    if not activity:
        return None, 404

    if not can_access_record(current_user, activity["assigned_to"]):
        return None, 403

    return activity, 200


def update_activity(activity_id, form_data, current_user, ip_address=None):
    """
    Update an existing activity within an atomic transaction.
    """
    conn = database.get_db_connection()
    try:
        existing = activity_repository.find_by_id(activity_id, conn=conn, for_update=True)
        if not existing:
            conn.rollback()
            return False, None, {"general": "Activity not found."}, 404

        if not can_access_record(current_user, existing["assigned_to"]):
            conn.rollback()
            return False, None, {"general": "You are not authorized to edit this activity."}, 403

        errors = validate_activity_form(form_data, is_edit=True, current_status=existing["status"])
        if errors:
            conn.rollback()
            return False, None, errors, 400

        # Assignment rules
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

        activity_type = form_data["activity_type"].strip()
        subject = form_data["subject"].strip()
        activity_date = str(form_data["activity_date"]).strip()
        description = (form_data.get("description") or "").strip() or None
        target_status = form_data.get("status", existing["status"]).strip()

        updated = activity_repository.update_activity(
            activity_id=activity_id,
            activity_type=activity_type,
            subject=subject,
            activity_date=activity_date,
            description=description,
            status=target_status,
            assigned_to=assigned_to,
            customer_id=existing["customer_id"],
            lead_id=existing["lead_id"],
            conn=conn,
        )

        old_val = {
            "activity_type": existing["activity_type"],
            "subject": existing["subject"],
            "activity_date": str(existing["activity_date"]),
            "status": existing["status"],
            "assigned_to": existing["assigned_to"],
        }
        new_val = {
            "activity_type": activity_type,
            "subject": subject,
            "activity_date": activity_date,
            "status": target_status,
            "assigned_to": assigned_to,
        }

        audit_action = "STATUS_CHANGE" if target_status != existing["status"] else "UPDATE"

        audit_service.log_event(
            action=audit_action,
            entity_name="ACTIVITY",
            record_id=activity_id,
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
