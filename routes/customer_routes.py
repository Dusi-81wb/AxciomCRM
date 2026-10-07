"""
Customer Routes for AcxiomCRM.

Handles HTTP request reception, parameter parsing, template rendering, and redirects
for Customer Management CRUD workflows.
Adheres strictly to layered architecture:
- Contains no SQL queries (all data access is in repositories/customer_repository.py).
- Contains no business or duplicate checking logic (all domain orchestration is in services/customer_service.py).
- All state-changing requests require POST method and CSRF protection.
- Authorization enforced server-side using Phase 3 decorators.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from security.authentication import get_current_user, login_required
from security.decorators import role_required, ROLE_ADMIN, ROLE_MANAGER
from repositories import customer_repository
from services import customer_service

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


@customers_bp.route("", methods=["GET"])
@login_required
def customer_list():
    """
    Display paginated list of customers scoped by actor role and ownership.
    Supports search across Name, Email, Phone, Company.
    """
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    status = request.args.get("status", "").strip() or None
    sort_by = request.args.get("sort_by", "created_date")
    sort_order = request.args.get("sort_order", "DESC")
    page = request.args.get("page", 1, type=int)

    customers, total_count, total_pages = customer_service.get_customers_list(
        current_user=current_user,
        search=search,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=10
    )

    return render_template(
        "customers/list.html",
        customers=customers,
        total_count=total_count,
        total_pages=total_pages,
        current_page=page,
        search=search or "",
        status=status or "",
        sort_by=sort_by,
        sort_order=sort_order
    )


@customers_bp.route("/create", methods=["GET", "POST"])
@login_required
def customer_create():
    """
    Handle customer creation form display (GET) and submission (POST).
    Sales Executive creations are automatically self-assigned.
    """
    current_user = get_current_user()
    is_admin_or_mgr = current_user.get("role_name") in (ROLE_ADMIN, ROLE_MANAGER)
    active_sales_reps = customer_repository.get_active_sales_executives() if is_admin_or_mgr else []

    if request.method == "POST":
        success, customer, errors = customer_service.create_customer(request.form, current_user)
        if success:
            flash(f"Customer '{customer['customer_name']}' created successfully ({customer['customer_code']}).", "success")
            return redirect(url_for("customers.customer_detail", customer_id=customer["customer_id"]))

        return render_template(
            "customers/create.html",
            form_data=request.form,
            errors=errors,
            sales_reps=active_sales_reps,
            active_sales_reps=active_sales_reps,
            is_admin_or_mgr=is_admin_or_mgr
        ), 400

    return render_template(
        "customers/create.html",
        form_data={},
        errors={},
        sales_reps=active_sales_reps,
        active_sales_reps=active_sales_reps,
        is_admin_or_mgr=is_admin_or_mgr
    )


@customers_bp.route("/<int:customer_id>", methods=["GET"])
@login_required
def customer_detail(customer_id):
    """
    Display customer detail page with server-side ownership verification.
    """
    current_user = get_current_user()
    customer, error_code = customer_service.get_customer_detail(customer_id, current_user)

    if error_code == 404:
        abort(404)
    elif error_code == 403:
        abort(403)

    return render_template(
        "customers/detail.html",
        customer=customer
    )


@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def customer_edit(customer_id):
    """
    Handle customer edit form display (GET) and update submission (POST).
    """
    current_user = get_current_user()
    existing_customer, error_code = customer_service.get_customer_detail(customer_id, current_user)

    if error_code == 404:
        abort(404)
    elif error_code == 403:
        abort(403)

    is_admin_or_mgr = current_user.get("role_name") in (ROLE_ADMIN, ROLE_MANAGER)
    active_sales_reps = customer_repository.get_active_sales_executives() if is_admin_or_mgr else []

    if request.method == "POST":
        success, updated_customer, errors, status_code = customer_service.update_customer(
            customer_id=customer_id,
            form_data=request.form,
            current_user=current_user
        )

        if success:
            flash(f"Customer '{updated_customer['customer_name']}' updated successfully.", "success")
            return redirect(url_for("customers.customer_detail", customer_id=customer_id))

        if status_code in (403, 404):
            abort(status_code)

        return render_template(
            "customers/edit.html",
            customer=existing_customer,
            form_data=request.form,
            errors=errors,
            sales_reps=active_sales_reps,
            active_sales_reps=active_sales_reps,
            is_admin_or_mgr=is_admin_or_mgr
        ), 400

    return render_template(
        "customers/edit.html",
        customer=existing_customer,
        form_data=existing_customer,
        errors={},
        sales_reps=active_sales_reps,
        active_sales_reps=active_sales_reps,
        is_admin_or_mgr=is_admin_or_mgr
    )


@customers_bp.route("/<int:customer_id>/deactivate", methods=["POST"])
@login_required
@role_required(ROLE_ADMIN, ROLE_MANAGER)
def customer_deactivate(customer_id):
    """
    Deactivate a customer (sets status to 'Inactive').
    Protected strictly for Admin and Manager roles.
    """
    current_user = get_current_user()
    success, error_msg, status_code = customer_service.deactivate_customer(customer_id, current_user)

    if not success:
        abort(status_code)

    flash("Customer has been deactivated successfully.", "info")
    return redirect(url_for("customers.customer_detail", customer_id=customer_id))
