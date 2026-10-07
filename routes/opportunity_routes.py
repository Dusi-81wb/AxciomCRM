"""
Opportunity Routes for AcxiomCRM (Phase 7).

Handles HTTP requests, parameter extraction, and template rendering
for Opportunity Management workflows.
Adheres strictly to architecture:
- Routes contain no SQL queries or business calculation algorithms.
- All state mutations require POST method and CSRF protection.
- Scope-aware authorization enforced server-side.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from security.authentication import get_current_user, login_required
from security.decorators import ROLE_ADMIN, ROLE_MANAGER
from repositories import opportunity_repository
from services import opportunity_service

opportunities_bp = Blueprint("opportunities", __name__, url_prefix="/opportunities")


@opportunities_bp.route("", methods=["GET"])
@login_required
def opportunity_list():
    """
    Display paginated list of opportunities scoped by actor role and ownership.
    Includes active pipeline summary, search, and multidimensional filters.
    """
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    customer_id = request.args.get("customer_id", "").strip() or None
    stage = request.args.get("stage", "").strip() or None
    status = request.args.get("status", "").strip() or None
    assigned_to = request.args.get("assigned_to", "").strip() or None
    sort_by = request.args.get("sort_by", "created_date")
    sort_order = request.args.get("sort_order", "DESC")
    page = request.args.get("page", 1, type=int)

    is_admin_or_mgr = current_user.get("role_name") in (ROLE_ADMIN, ROLE_MANAGER)
    active_sales_reps = opportunity_repository.get_active_sales_executives() if is_admin_or_mgr else []
    active_customers = opportunity_repository.get_active_customers()

    opportunities, total_count, total_pages, pipeline_summary = opportunity_service.get_opportunities_list(
        current_user=current_user,
        search=search,
        customer_id=customer_id,
        stage=stage,
        status=status,
        assigned_to=assigned_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=10
    )

    return render_template(
        "opportunities/list.html",
        opportunities=opportunities,
        total_count=total_count,
        total_pages=total_pages,
        current_page=page,
        pipeline_summary=pipeline_summary,
        search=search or "",
        customer_id=customer_id or "",
        stage=stage or "",
        status=status or "",
        assigned_to=assigned_to or "",
        sort_by=sort_by,
        sort_order=sort_order,
        active_sales_reps=active_sales_reps,
        active_customers=active_customers
    )


@opportunities_bp.route("/create", methods=["GET", "POST"])
@login_required
def opportunity_create():
    """
    Handle opportunity creation form rendering (GET) and submission (POST).
    """
    current_user = get_current_user()
    is_admin_or_mgr = current_user.get("role_name") in (ROLE_ADMIN, ROLE_MANAGER)
    active_sales_reps = opportunity_repository.get_active_sales_executives() if is_admin_or_mgr else []
    active_customers = opportunity_repository.get_active_customers()

    if request.method == "POST":
        success, opp, errors, status_code = opportunity_service.create_opportunity(
            form_data=request.form,
            current_user=current_user,
            ip_address=request.remote_addr
        )

        if success:
            flash(f"Opportunity '{opp['opportunity_name']}' created successfully.", "success")
            return redirect(url_for("opportunities.opportunity_detail", opp_id=opp["opportunity_id"]))

        return render_template(
            "opportunities/create.html",
            form_data=request.form,
            errors=errors,
            active_sales_reps=active_sales_reps,
            active_customers=active_customers
        ), status_code

    # Pre-select customer if customer_id passed in query string (e.g. from customer detail)
    initial_form = {}
    pre_cid = request.args.get("customer_id")
    if pre_cid:
        initial_form["customer_id"] = pre_cid

    return render_template(
        "opportunities/create.html",
        form_data=initial_form,
        errors={},
        active_sales_reps=active_sales_reps,
        active_customers=active_customers
    )


@opportunities_bp.route("/<int:opp_id>", methods=["GET"])
@login_required
def opportunity_detail(opp_id):
    """
    Display comprehensive opportunity detail view with authorization enforcement.
    """
    current_user = get_current_user()
    opp, status_code = opportunity_service.get_opportunity_detail(opp_id, current_user)

    if status_code == 404:
        abort(404)
    elif status_code == 403:
        abort(403)

    return render_template(
        "opportunities/detail.html",
        opportunity=opp
    )


@opportunities_bp.route("/<int:opp_id>/edit", methods=["GET", "POST"])
@login_required
def opportunity_edit(opp_id):
    """
    Handle opportunity edit form display (GET) and update submission (POST).
    """
    current_user = get_current_user()
    existing_opp, status_code = opportunity_service.get_opportunity_detail(opp_id, current_user)

    if status_code == 404:
        abort(404)
    elif status_code == 403:
        abort(403)

    if existing_opp["status"] in ("Won", "Lost"):
        flash("Won and Lost opportunities are terminal and cannot be edited.", "warning")
        return redirect(url_for("opportunities.opportunity_detail", opp_id=opp_id))

    is_admin_or_mgr = current_user.get("role_name") in (ROLE_ADMIN, ROLE_MANAGER)
    active_sales_reps = opportunity_repository.get_active_sales_executives() if is_admin_or_mgr else []
    active_customers = opportunity_repository.get_active_customers()

    if request.method == "POST":
        success, updated_opp, errors, status_code = opportunity_service.update_opportunity(
            opportunity_id=opp_id,
            form_data=request.form,
            current_user=current_user,
            ip_address=request.remote_addr
        )

        if success:
            flash(f"Opportunity '{updated_opp['opportunity_name']}' updated successfully.", "success")
            return redirect(url_for("opportunities.opportunity_detail", opp_id=opp_id))

        if status_code in (403, 404):
            abort(status_code)

        return render_template(
            "opportunities/edit.html",
            opportunity=existing_opp,
            form_data=request.form,
            errors=errors,
            active_sales_reps=active_sales_reps,
            active_customers=active_customers
        ), status_code

    return render_template(
        "opportunities/edit.html",
        opportunity=existing_opp,
        form_data=existing_opp,
        errors={},
        active_sales_reps=active_sales_reps,
        active_customers=active_customers
    )


@opportunities_bp.route("/<int:opp_id>/stage", methods=["POST"])
@login_required
def opportunity_stage(opp_id):
    """
    Handle state-changing stage transition POST requests (Progression, Won, Lost).
    """
    current_user = get_current_user()
    target_stage = request.form.get("stage", "").strip()

    success, error_msg, status_code = opportunity_service.update_opportunity_stage(
        opportunity_id=opp_id,
        target_stage=target_stage,
        current_user=current_user,
        ip_address=request.remote_addr
    )

    if not success:
        if status_code in (403, 404):
            abort(status_code)
        flash(error_msg or "Failed to update opportunity stage.", "danger")
    else:
        flash(f"Opportunity stage updated to '{target_stage}'.", "success")

    return redirect(url_for("opportunities.opportunity_detail", opp_id=opp_id))
