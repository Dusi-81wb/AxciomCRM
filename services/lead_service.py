"""
Lead Service for AcxiomCRM.

Coordinates Lead business logic, validation, ownership/scope enforcement,
status transition validation, atomic conversion workflow, and transaction audit coordination.
Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md (including Section 94 approved decisions):
- LeadCode: Sequential format LEAD-001, LEAD-002, ... based on next lead_id.
- Ownership: Sales Executive creations are automatically self-assigned; Admin/Manager may assign active Sales Executives.
- Status Transitions: Strictly enforced per approved 6-state transition matrix.
- Conversion: Only Qualified Leads can be converted; atomic transaction creates/links Customer, creates Opportunity if requested, marks Lead Converted, and writes all audits.
"""

from decimal import Decimal
import math
import database
from repositories import lead_repository, customer_repository, user_repository
from schemas.lead_schema import validate_lead_form, validate_lead_conversion_form
from validation.business_rules import (
    validate_lead_transition,
    LEAD_STATUS_NEW,
    LEAD_STATUS_QUALIFIED,
    LEAD_STATUS_CONVERTED,
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


def create_lead(form_data, current_user, ip_address=None):
    """
    Create a new lead record.

    :param form_data: Dict containing form input fields.
    :param current_user: Database-backed current user dict.
    :param ip_address: Remote client IP address.
    :return: Tuple (success: bool, lead_dict: dict or None, errors: dict).
    """
    errors = validate_lead_form(form_data, is_edit=False)
    if errors:
        return False, None, errors

    lead_name = form_data["lead_name"].strip()
    email = form_data["email"].strip().lower()
    phone = (form_data.get("phone") or "").strip() or None
    company_name = (form_data.get("company_name") or "").strip() or None
    source = (form_data.get("source") or "").strip() or None
    status = (form_data.get("status") or LEAD_STATUS_NEW).strip()

    raw_ev = form_data.get("expected_value")
    expected_value = Decimal(str(raw_ev).strip()) if raw_ev not in (None, "") else None

    # 1. Ownership Assignment Rule (Spec Notes Section 94 #2)
    if has_role(current_user, ROLE_SALES_EXECUTIVE):
        # Sales Executive unconditionally self-assigns created lead
        assigned_to = current_user["user_id"]
    else:
        # Admin / Manager selects an active Sales Executive
        raw_assigned = form_data.get("assigned_to")
        if raw_assigned in (None, ""):
            errors["assigned_to"] = "Assigned Sales Executive is required."
        else:
            try:
                assigned_to = int(raw_assigned)
                target_user = user_repository.find_by_id(assigned_to)
                if not target_user or not target_user.get("is_active") or target_user.get("role_id") != 3:
                    errors["assigned_to"] = "Assigned user must be an active Sales Executive."
            except (ValueError, TypeError):
                errors["assigned_to"] = "Assigned user ID must be a valid integer."

    if errors:
        return False, None, errors

    # 2. Transaction Execution: Insert Lead + Insert Audit Log
    conn = database.get_db_connection()
    try:
        lead_code = lead_repository.get_next_lead_code(conn=conn)

        lead = lead_repository.create_lead(
            lead_code=lead_code,
            lead_name=lead_name,
            email=email,
            phone=phone,
            company_name=company_name,
            source=source,
            status=status,
            expected_value=expected_value,
            assigned_to=assigned_to,
            conn=conn
        )

        audit_service.log_event(
            action=audit_service.ACTION_CREATE,
            entity_name=audit_service.ENTITY_LEAD,
            user_id=current_user["user_id"],
            record_id=lead["lead_id"],
            new_value={
                "lead_code": lead["lead_code"],
                "lead_name": lead["lead_name"],
                "email": lead["email"],
                "phone": lead["phone"],
                "company_name": lead["company_name"],
                "source": lead["source"],
                "status": lead["status"],
                "expected_value": str(lead["expected_value"]) if lead["expected_value"] is not None else None,
                "assigned_to": lead["assigned_to"]
            },
            result="Success",
            ip_address=ip_address,
            conn=conn
        )

        conn.commit()
        return True, lead, {}

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_leads_list(
    current_user,
    search=None,
    status=None,
    assigned_to=None,
    sort_by="created_date",
    sort_order="DESC",
    page=1,
    per_page=10
):
    """
    Retrieve paginated leads list strictly constrained by SQL ownership scope.
    """
    allowed_user_ids = visible_user_ids(current_user)

    total_count = lead_repository.count_leads(
        allowed_user_ids=allowed_user_ids,
        search=search,
        status=status,
        assigned_to=assigned_to
    )

    total_pages = max(1, math.ceil(total_count / per_page))
    current_page = max(1, min(page, total_pages))
    offset = (current_page - 1) * per_page

    leads = lead_repository.find_leads(
        allowed_user_ids=allowed_user_ids,
        search=search,
        status=status,
        assigned_to=assigned_to,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=per_page,
        offset=offset
    )

    return leads, total_count, total_pages


def get_lead_detail(lead_id, current_user):
    """
    Retrieve lead detail with server-side ownership authorization.

    :param lead_id: Integer primary key.
    :param current_user: Authenticated user dict.
    :return: Tuple (lead_dict: dict or None, status_code: int).
    """
    lead = lead_repository.find_by_id(lead_id)
    if not lead:
        return None, 404

    if not can_access_record(current_user, lead.get("assigned_to")):
        return None, 403

    return lead, 200


def update_lead(lead_id, form_data, current_user, ip_address=None):
    """
    Update lead contact and business details with authorization and audit trail.

    :param lead_id: Primary key of lead.
    :param form_data: Form data dictionary.
    :param current_user: Authenticated actor.
    :param ip_address: Remote client IP.
    :return: Tuple (success: bool, lead_dict: dict or None, errors: dict, status_code: int).
    """
    existing_lead = lead_repository.find_by_id(lead_id)
    if not existing_lead:
        return False, None, {"general": "Lead not found."}, 404

    if not can_access_record(current_user, existing_lead.get("assigned_to")):
        return False, None, {"general": "You are not authorized to update this lead."}, 403

    errors = validate_lead_form(form_data, is_edit=True)
    if errors:
        return False, None, errors, 400

    lead_name = form_data["lead_name"].strip()
    email = form_data["email"].strip().lower()
    phone = (form_data.get("phone") or "").strip() or None
    company_name = (form_data.get("company_name") or "").strip() or None
    source = (form_data.get("source") or "").strip() or None

    raw_ev = form_data.get("expected_value")
    expected_value = Decimal(str(raw_ev).strip()) if raw_ev not in (None, "") else None

    # Ownership rules
    if has_role(current_user, ROLE_SALES_EXECUTIVE):
        assigned_to = existing_lead["assigned_to"]
    else:
        raw_assigned = form_data.get("assigned_to")
        if raw_assigned in (None, ""):
            assigned_to = existing_lead["assigned_to"]
        else:
            try:
                assigned_to = int(raw_assigned)
                target_user = user_repository.find_by_id(assigned_to)
                if not target_user or not target_user.get("is_active") or target_user.get("role_id") != 3:
                    errors["assigned_to"] = "Assigned user must be an active Sales Executive."
            except (ValueError, TypeError):
                errors["assigned_to"] = "Assigned user ID must be a valid integer."

    # Status transition rules (conversion has dedicated route)
    status_candidate = form_data.get("status")
    if status_candidate and status_candidate != existing_lead["status"]:
        if status_candidate == LEAD_STATUS_CONVERTED:
            errors["status"] = "Lead conversion must be completed using the dedicated conversion workflow."
        else:
            is_valid_trans, trans_err = validate_lead_transition(existing_lead["status"], status_candidate)
            if not is_valid_trans:
                errors["status"] = trans_err

    if errors:
        return False, None, errors, 400

    conn = database.get_db_connection()
    try:
        old_value = {
            "lead_name": existing_lead["lead_name"],
            "email": existing_lead["email"],
            "phone": existing_lead["phone"],
            "company_name": existing_lead["company_name"],
            "source": existing_lead["source"],
            "expected_value": str(existing_lead["expected_value"]) if existing_lead["expected_value"] is not None else None,
            "status": existing_lead["status"],
            "assigned_to": existing_lead["assigned_to"]
        }

        updated_lead = lead_repository.update_lead(
            lead_id=lead_id,
            lead_name=lead_name,
            email=email,
            phone=phone,
            company_name=company_name,
            source=source,
            expected_value=expected_value,
            assigned_to=assigned_to,
            conn=conn
        )

        if status_candidate and status_candidate != existing_lead["status"]:
            updated_lead = lead_repository.update_status(lead_id, status_candidate, conn=conn)

        new_value = {
            "lead_name": updated_lead["lead_name"],
            "email": updated_lead["email"],
            "phone": updated_lead["phone"],
            "company_name": updated_lead["company_name"],
            "source": updated_lead["source"],
            "expected_value": str(updated_lead["expected_value"]) if updated_lead["expected_value"] is not None else None,
            "status": updated_lead["status"],
            "assigned_to": updated_lead["assigned_to"]
        }

        audit_service.log_event(
            action=audit_service.ACTION_UPDATE,
            entity_name=audit_service.ENTITY_LEAD,
            user_id=current_user["user_id"],
            record_id=lead_id,
            old_value=old_value,
            new_value=new_value,
            result="Success",
            ip_address=ip_address,
            conn=conn
        )

        conn.commit()
        return True, updated_lead, {}, 200

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_lead_status(lead_id, target_status, current_user, ip_address=None):
    """
    Perform a validated status change on a Lead.

    :param lead_id: Integer primary key.
    :param target_status: Requested canonical status.
    :param current_user: Authenticated actor.
    :param ip_address: Remote client IP.
    :return: Tuple (success: bool, error_msg: str or None, status_code: int).
    """
    lead = lead_repository.find_by_id(lead_id)
    if not lead:
        return False, "Lead not found.", 404

    if not can_access_record(current_user, lead.get("assigned_to")):
        return False, "Unauthorized access to this lead.", 403

    if target_status == LEAD_STATUS_CONVERTED:
        return False, "Lead conversion must be performed through the conversion workflow.", 400

    is_valid_trans, trans_err = validate_lead_transition(lead["status"], target_status)
    if not is_valid_trans:
        return False, trans_err, 400

    conn = database.get_db_connection()
    try:
        lead_repository.update_status(lead_id, target_status, conn=conn)

        audit_service.log_event(
            action=audit_service.ACTION_STATUS_CHANGE,
            entity_name=audit_service.ENTITY_LEAD,
            user_id=current_user["user_id"],
            record_id=lead_id,
            old_value={"status": lead["status"]},
            new_value={"status": target_status},
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


def convert_lead(lead_id, form_data, current_user, ip_address=None):
    """
    Execute Lead-to-Customer (and optional Opportunity) conversion in ONE atomic transaction.

    Concurrency: Uses SELECT ... FOR UPDATE on the lead row to prevent double-conversion.

    :param lead_id: Integer primary key of Qualified lead.
    :param form_data: Mapping of conversion form inputs.
    :param current_user: Authenticated actor.
    :param ip_address: Remote client IP.
    :return: Tuple (success: bool, result_dict: dict or None, errors: dict, status_code: int).
    """
    conn = database.get_db_connection()
    try:
        # 1. Row-level locking to prevent concurrent double-conversion race condition
        lead = lead_repository.find_by_id(lead_id, conn=conn, for_update=True)
        if not lead:
            conn.rollback()
            return False, None, {"general": "Lead not found."}, 404

        # 2. Authorization verification
        if not can_access_record(current_user, lead.get("assigned_to")):
            conn.rollback()
            return False, None, {"general": "You are not authorized to convert this lead."}, 403

        # 3. Conversion eligibility
        if lead["status"] == LEAD_STATUS_CONVERTED:
            conn.rollback()
            return False, None, {"general": "This lead has already been converted."}, 400

        if lead["status"] != LEAD_STATUS_QUALIFIED:
            conn.rollback()
            return False, None, {"general": f"Only Qualified leads may be converted. Current status is '{lead['status']}'."}, 400

        # 4. Form validation
        errors = validate_lead_conversion_form(form_data)
        if errors:
            conn.rollback()
            return False, None, errors, 400

        email = form_data["email"].strip().lower()
        phone = form_data["phone"].strip()

        # 5. Existing Customer Matching (Spec Notes Section 94 #5)
        existing_by_email = customer_repository.find_by_email(email, conn=conn)
        existing_by_phone = customer_repository.find_by_phone(phone, conn=conn)

        customer = None
        is_new_customer = False

        if existing_by_email and existing_by_phone:
            if existing_by_email["customer_id"] == existing_by_phone["customer_id"]:
                customer = existing_by_email
            else:
                conn.rollback()
                return False, None, {
                    "general": "Ambiguous customer identity: Email matches one existing customer while phone matches a different existing customer. Cannot safely link."
                }, 400
        elif existing_by_email:
            customer = existing_by_email
        elif existing_by_phone:
            customer = existing_by_phone
        else:
            # Create new customer record
            is_new_customer = True
            customer_code = customer_repository.get_next_customer_code(conn=conn)
            customer = customer_repository.create_customer(
                customer_code=customer_code,
                customer_name=form_data["customer_name"].strip(),
                email=email,
                phone=phone,
                company_name=(form_data.get("company_name") or "").strip() or None,
                address=(form_data.get("address") or "").strip() or None,
                city=(form_data.get("city") or "").strip() or None,
                state=(form_data.get("state") or "").strip() or None,
                status="Active",
                assigned_to=lead["assigned_to"],
                created_by=current_user["user_id"],
                conn=conn
            )

            # Audit Customer creation
            audit_service.log_event(
                action=audit_service.ACTION_CREATE,
                entity_name=audit_service.ENTITY_CUSTOMER,
                user_id=current_user["user_id"],
                record_id=customer["customer_id"],
                new_value={
                    "customer_code": customer["customer_code"],
                    "customer_name": customer["customer_name"],
                    "email": customer["email"],
                    "phone": customer["phone"],
                    "company_name": customer["company_name"],
                    "source": "LEAD_CONVERSION",
                    "converted_from_lead_id": lead_id,
                    "status": "Active",
                    "assigned_to": customer["assigned_to"]
                },
                result="Success",
                ip_address=ip_address,
                conn=conn
            )

        # 6. Optional Opportunity Creation
        opportunity = None
        create_opp = form_data.get("create_opportunity") in (True, "true", "1", "on", "yes")
        if create_opp:
            raw_amt = form_data.get("amount")
            opp_amount = Decimal(str(raw_amt).strip()) if raw_amt not in (None, "") else (lead["expected_value"] or Decimal("0.00"))
            opp_prob = int(form_data["probability"])
            opp_close_date = form_data["expected_close_date"].strip()
            opp_name = form_data["opportunity_name"].strip()

            opportunity = lead_repository.create_opportunity(
                opportunity_name=opp_name,
                customer_id=customer["customer_id"],
                lead_id=lead["lead_id"],
                amount=opp_amount,
                stage="Qualification",
                probability=opp_prob,
                expected_close_date=opp_close_date,
                status="Open",
                assigned_to=lead["assigned_to"],
                conn=conn
            )

            # Audit Opportunity creation
            audit_service.log_event(
                action=audit_service.ACTION_CREATE,
                entity_name=audit_service.ENTITY_OPPORTUNITY,
                user_id=current_user["user_id"],
                record_id=opportunity["opportunity_id"],
                new_value={
                    "opportunity_name": opportunity["opportunity_name"],
                    "customer_id": customer["customer_id"],
                    "lead_id": lead["lead_id"],
                    "amount": str(opp_amount),
                    "stage": "Qualification",
                    "probability": opp_prob,
                    "expected_close_date": opp_close_date,
                    "status": "Open",
                    "assigned_to": opportunity["assigned_to"]
                },
                result="Success",
                ip_address=ip_address,
                conn=conn
            )

        # 7. Update Lead status to 'Converted'
        updated_lead = lead_repository.update_status(lead_id, LEAD_STATUS_CONVERTED, conn=conn)

        # Audit Lead conversion status change
        audit_service.log_event(
            action=audit_service.ACTION_STATUS_CHANGE,
            entity_name=audit_service.ENTITY_LEAD,
            user_id=current_user["user_id"],
            record_id=lead_id,
            old_value={"status": LEAD_STATUS_QUALIFIED},
            new_value={
                "status": LEAD_STATUS_CONVERTED,
                "customer_id": customer["customer_id"],
                "opportunity_id": opportunity["opportunity_id"] if opportunity else None,
                "is_new_customer": is_new_customer
            },
            result="Success",
            ip_address=ip_address,
            conn=conn
        )

        # 8. Single Atomic Commit
        conn.commit()
        return True, {
            "lead": updated_lead,
            "customer": customer,
            "opportunity": opportunity,
            "is_new_customer": is_new_customer
        }, {}, 200

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
