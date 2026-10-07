"""
Customer Service for AcxiomCRM.

Orchestrates customer business logic, validation, duplicate checking,
ownership/scope enforcement, and atomic transaction audit coordination.
Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md:
- CustomerCode: Generated sequentially (e.g. CUST-005).
- Phone: Validated 10-15 digits.
- Ownership: Sales Executive creations are automatically self-assigned; Admin/Manager can assign.
- Deactivation: Restricted strictly to Admin and Manager (Sales Executive -> 403).
- Audit: Every mutation commits atomically with an audit log in the same PostgreSQL transaction.
- Duplicate checks: Reserve email/phone across both Active and Inactive customers.
"""

import math
import database
from repositories import customer_repository, user_repository
from schemas.customer_schema import validate_customer_form
from security.authorization import (
    visible_user_ids,
    can_access_record,
    has_role,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES_EXECUTIVE,
)
from services import audit_service


def create_customer(form_data, current_user):
    """
    Create a new customer record.

    :param form_data: Dict containing form fields.
    :param current_user: Database-backed current user dict.
    :return: Tuple (success: bool, customer_dict: dict or None, errors: dict).
    """
    errors = validate_customer_form(form_data, is_edit=False)
    if errors:
        return False, None, errors

    customer_name = form_data["customer_name"].strip()
    email = form_data["email"].strip().lower()
    phone = form_data["phone"].strip()
    company_name = (form_data.get("company_name") or "").strip() or None
    address = (form_data.get("address") or "").strip() or None
    city = (form_data.get("city") or "").strip() or None
    state = (form_data.get("state") or "").strip() or None
    status = (form_data.get("status") or "Active").strip()

    # 1. Ownership Assignment Rule (Spec Notes Section 93 #3)
    if has_role(current_user, ROLE_SALES_EXECUTIVE):
        # Sales Executive unconditionally self-assigns created customer
        assigned_to = current_user["user_id"]
    else:
        # Admin / Manager may select an active Sales Executive
        raw_assigned = form_data.get("assigned_to")
        if raw_assigned not in (None, ""):
            assigned_to = int(raw_assigned)
            # Verify target user exists, is active, and is a Sales Executive
            target_user = user_repository.find_by_id(assigned_to)
            if not target_user or not target_user.get("is_active") or target_user.get("role_id") != 3:
                errors["assigned_to"] = "Assigned user must be an active Sales Executive."
        else:
            assigned_to = None

    # 2. Duplicate Check across ALL customers (including Inactive)
    if customer_repository.find_by_email(email):
        errors["email"] = "Email address is already registered to another customer."

    if customer_repository.find_by_phone(phone):
        errors["phone"] = "Phone number is already registered to another customer."

    if errors:
        return False, None, errors

    # 3. Transaction Execution: Insert Customer + Insert Audit Log
    conn = database.get_db_connection()
    try:
        # Generate sequential unique customer code
        customer_code = customer_repository.get_next_customer_code(conn=conn)

        customer = customer_repository.create_customer(
            customer_code=customer_code,
            customer_name=customer_name,
            email=email,
            phone=phone,
            company_name=company_name,
            address=address,
            city=city,
            state=state,
            status=status,
            assigned_to=assigned_to,
            created_by=current_user["user_id"],
            conn=conn
        )

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
                "status": customer["status"],
                "assigned_to": customer["assigned_to"]
            },
            result="Success",
            conn=conn
        )

        conn.commit()
        return True, customer, {}
    except Exception:
        conn.rollback()
        raise


def get_customers_list(current_user, search=None, status=None, sort_by="created_date", sort_order="DESC", page=1, per_page=10):
    """
    Retrieve paginated list of customers filtered by user ownership scope.

    :param current_user: Database-backed current user dict.
    :return: Tuple (customers: list, total_count: int, total_pages: int).
    """
    scope = visible_user_ids(current_user)
    page = max(1, int(page or 1))
    per_page = max(1, min(100, int(per_page or 10)))
    offset = (page - 1) * per_page

    customers = customer_repository.find_customers(
        visible_user_ids=scope,
        search=search,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=per_page,
        offset=offset
    )

    total_count = customer_repository.count_customers(
        visible_user_ids=scope,
        search=search,
        status=status
    )

    total_pages = max(1, math.ceil(total_count / per_page))
    return customers, total_count, total_pages


def get_customer_detail(customer_id, current_user):
    """
    Retrieve single customer detail with server-side authorization check.

    :param customer_id: Customer ID.
    :param current_user: Database-backed current user dict.
    :return: Tuple (customer: dict or None, error_code: int or None).
    """
    customer = customer_repository.find_by_id(customer_id)
    if not customer:
        return None, 404

    # Server-side ownership / scope enforcement
    if not can_access_record(current_user, customer.get("assigned_to")):
        return None, 403

    return customer, None


def update_customer(customer_id, form_data, current_user):
    """
    Update customer details with server-side ownership and authorization checks.

    :param customer_id: Customer ID.
    :param form_data: Submitted form dictionary.
    :param current_user: Current user dict.
    :return: Tuple (success: bool, customer_dict: dict or None, errors: dict, status_code: int).
    """
    # 1. Load existing customer
    existing_customer = customer_repository.find_by_id(customer_id)
    if not existing_customer:
        return False, None, {"general": "Customer not found."}, 404

    # 2. Scope check
    if not can_access_record(current_user, existing_customer.get("assigned_to")):
        return False, None, {"general": "You are not authorized to update this customer."}, 403

    # 3. Schema validation
    errors = validate_customer_form(form_data, is_edit=True)
    if errors:
        return False, None, errors, 400

    customer_name = form_data["customer_name"].strip()
    email = form_data["email"].strip().lower()
    phone = form_data["phone"].strip()
    company_name = (form_data.get("company_name") or "").strip() or None
    address = (form_data.get("address") or "").strip() or None
    city = (form_data.get("city") or "").strip() or None
    state = (form_data.get("state") or "").strip() or None

    # 4. Duplicate checks excluding current customer
    if customer_repository.find_by_email(email, exclude_id=customer_id):
        errors["email"] = "Email address is already registered to another customer."

    if customer_repository.find_by_phone(phone, exclude_id=customer_id):
        errors["phone"] = "Phone number is already registered to another customer."

    # 5. Assignment and Status Authorization Rules
    if has_role(current_user, ROLE_SALES_EXECUTIVE):
        # Sales Executive cannot reassign customer or alter status
        assigned_to = existing_customer["assigned_to"]
        status = existing_customer["status"]
    else:
        # Admin / Manager can change assigned_to
        raw_assigned = form_data.get("assigned_to")
        if raw_assigned not in (None, ""):
            assigned_to = int(raw_assigned)
            target_user = user_repository.find_by_id(assigned_to)
            if not target_user or not target_user.get("is_active") or target_user.get("role_id") != 3:
                errors["assigned_to"] = "Assigned user must be an active Sales Executive."
        else:
            assigned_to = existing_customer["assigned_to"]

        # Admin / Manager can update status
        status = form_data.get("status") or existing_customer["status"]

    if errors:
        return False, None, errors, 400

    # 6. Atomic Transaction: Update Customer + Update Audit Log
    conn = database.get_db_connection()
    try:
        old_value = {
            "customer_name": existing_customer["customer_name"],
            "email": existing_customer["email"],
            "phone": existing_customer["phone"],
            "company_name": existing_customer["company_name"],
            "status": existing_customer["status"],
            "assigned_to": existing_customer["assigned_to"]
        }

        updated_customer = customer_repository.update_customer(
            customer_id=customer_id,
            customer_name=customer_name,
            email=email,
            phone=phone,
            company_name=company_name,
            address=address,
            city=city,
            state=state,
            status=status,
            assigned_to=assigned_to,
            conn=conn
        )

        new_value = {
            "customer_name": updated_customer["customer_name"],
            "email": updated_customer["email"],
            "phone": updated_customer["phone"],
            "company_name": updated_customer["company_name"],
            "status": updated_customer["status"],
            "assigned_to": updated_customer["assigned_to"]
        }

        # If status changed, log STATUS_CHANGE audit
        if existing_customer["status"] != updated_customer["status"]:
            audit_service.log_event(
                action=audit_service.ACTION_STATUS_CHANGE,
                entity_name=audit_service.ENTITY_CUSTOMER,
                user_id=current_user["user_id"],
                record_id=customer_id,
                old_value={"status": existing_customer["status"]},
                new_value={"status": updated_customer["status"]},
                result="Success",
                conn=conn
            )

        # Log UPDATE audit
        audit_service.log_event(
            action=audit_service.ACTION_UPDATE,
            entity_name=audit_service.ENTITY_CUSTOMER,
            user_id=current_user["user_id"],
            record_id=customer_id,
            old_value=old_value,
            new_value=new_value,
            result="Success",
            conn=conn
        )

        conn.commit()
        return True, updated_customer, {}, 200
    except Exception:
        conn.rollback()
        raise


def deactivate_customer(customer_id, current_user):
    """
    Deactivate a customer (Status -> 'Inactive').
    Restricted strictly to Admin and Manager roles (Spec Notes Section 93 #4).

    :param customer_id: Customer ID.
    :param current_user: Current user dict.
    :return: Tuple (success: bool, error_message: str or None, status_code: int).
    """
    # Authorization: Sales Executives are explicitly denied deactivation permission
    if not has_role(current_user, ROLE_ADMIN, ROLE_MANAGER):
        return False, "You do not have permission to deactivate customers.", 403

    customer = customer_repository.find_by_id(customer_id)
    if not customer:
        return False, "Customer not found.", 404

    if not can_access_record(current_user, customer.get("assigned_to")):
        return False, "You do not have permission to access this customer.", 403

    if customer["status"] == "Inactive":
        return True, None, 200

    conn = database.get_db_connection()
    try:
        customer_repository.update_status(customer_id, "Inactive", conn=conn)

        # Audit status change
        audit_service.log_event(
            action=audit_service.ACTION_STATUS_CHANGE,
            entity_name=audit_service.ENTITY_CUSTOMER,
            user_id=current_user["user_id"],
            record_id=customer_id,
            old_value={"status": "Active"},
            new_value={"status": "Inactive"},
            result="Success",
            conn=conn
        )

        conn.commit()
        return True, None, 200
    except Exception:
        conn.rollback()
        raise
