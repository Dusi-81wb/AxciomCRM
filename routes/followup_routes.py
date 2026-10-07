"""
Follow-Up Routes for AcxiomCRM (Phase 8).

Handles HTTP requests, parameter extraction, and template rendering
for Follow-Up Management workflows.
Adheres strictly to architecture:
- Routes contain no SQL queries or business logic algorithms.
- All state mutations require POST method and CSRF protection.
- Scope-aware authorization enforced server-side.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from security.authentication import get_current_user, login_required
from security.authorization import get_visible_user_ids, has_role, ROLE_ADMIN, ROLE_MANAGER
from repositories import (
    followup_repository,
    opportunity_repository,
    lead_repository,
    customer_repository,
)
from services import followup_service

followups_bp = Blueprint("followups", __name__, url_prefix="/followups")


@followups_bp.route("", methods=["GET"])
@login_required
def followup_list():
    """
    Display paginated list of follow-ups scoped by actor role and ownership.
    Supports filtering by date, status, follow-up type, assigned rep, and view filter (upcoming/overdue/completed).
    """
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    status = request.args.get("status", "").strip() or None
    ftype = request.args.get("ftype", "").strip() or None
    assigned_to = request.args.get("assigned_to", "").strip() or None
    view_filter = request.args.get("view", "").strip() or None
    page = request.args.get("page", 1, type=int)

    is_admin_or_mgr = has_role(current_user, ROLE_ADMIN) or has_role(current_user, ROLE_MANAGER)
    active_sales_reps = opportunity_repository.get_active_sales_executives() if is_admin_or_mgr else []

    followups, pagination, metrics = followup_service.get_followups_list(
        current_user=current_user,
        search=search,
        status=status,
        ftype=ftype,
        assigned_to=assigned_to,
        view_filter=view_filter,
        page=page,
        per_page=15,
    )

    return render_template(
        "followups/list.html",
        followups=followups,
        pagination=pagination,
        metrics=metrics,
        search=search or "",
        selected_status=status or "",
        selected_ftype=ftype or "",
        selected_assigned=assigned_to or "",
        selected_view=view_filter or "",
        active_sales_reps=active_sales_reps,
    )


@followups_bp.route("/create", methods=["GET", "POST"])
@login_required
def followup_create():
    """
    Handle follow-up creation form rendering (GET) and submission (POST).
    """
    current_user = get_current_user()
    is_admin_or_mgr = has_role(current_user, ROLE_ADMIN) or has_role(current_user, ROLE_MANAGER)
    visible_user_ids = get_visible_user_ids(current_user)

    active_sales_reps = opportunity_repository.get_active_sales_executives() if is_admin_or_mgr else []
    active_customers = opportunity_repository.get_active_customers()
    leads = lead_repository.find_leads(allowed_user_ids=visible_user_ids, limit=100)
    opportunities = opportunity_repository.find_opportunities(allowed_user_ids=visible_user_ids, status="Open", limit=100)

    if request.method == "POST":
        success, followup, errors, status_code = followup_service.create_followup(
            form_data=request.form,
            current_user=current_user,
            ip_address=request.remote_addr,
        )

        if success:
            flash(f"Follow-up '{followup['subject']}' scheduled successfully.", "success")
            return redirect(url_for("followups.followup_detail", followup_id=followup["followup_id"]))

        return render_template(
            "followups/create.html",
            form_data=request.form,
            errors=errors,
            active_sales_reps=active_sales_reps,
            active_customers=active_customers,
            leads=leads,
            opportunities=opportunities,
        ), status_code

    # Pre-populate relations if passed via query params
    initial_form = {}
    for param in ["customer_id", "lead_id", "opportunity_id"]:
        val = request.args.get(param)
        if val:
            initial_form[param] = val

    return render_template(
        "followups/create.html",
        form_data=initial_form,
        errors={},
        active_sales_reps=active_sales_reps,
        active_customers=active_customers,
        leads=leads,
        opportunities=opportunities,
    )


@followups_bp.route("/<int:followup_id>", methods=["GET"])
@login_required
def followup_detail(followup_id):
    """
    Display single follow-up detail with ownership verification and IDOR defense.
    """
    current_user = get_current_user()
    followup, status_code = followup_service.get_followup_detail(followup_id, current_user)

    if status_code == 404:
        abort(404)
    elif status_code == 403:
        abort(403)

    return render_template(
        "followups/detail.html",
        followup=followup,
    )


@followups_bp.route("/<int:followup_id>/edit", methods=["GET", "POST"])
@login_required
def followup_edit(followup_id):
    """
    Display edit form (GET) and handle update submission (POST).
    """
    current_user = get_current_user()
    existing, status_code = followup_service.get_followup_detail(followup_id, current_user)

    if status_code == 404:
        abort(404)
    elif status_code == 403:
        abort(403)

    if existing["status"] in ("Completed", "Cancelled"):
        flash(f"Follow-ups in '{existing['status']}' status are terminal and cannot be modified.", "warning")
        return redirect(url_for("followups.followup_detail", followup_id=followup_id))

    is_admin_or_mgr = has_role(current_user, ROLE_ADMIN) or has_role(current_user, ROLE_MANAGER)
    active_sales_reps = opportunity_repository.get_active_sales_executives() if is_admin_or_mgr else []

    if request.method == "POST":
        success, updated, errors, status_code = followup_service.update_followup(
            followup_id=followup_id,
            form_data=request.form,
            current_user=current_user,
            ip_address=request.remote_addr,
        )

        if success:
            flash(f"Follow-up '{updated['subject']}' updated successfully.", "success")
            return redirect(url_for("followups.followup_detail", followup_id=followup_id))

        if status_code in (403, 404):
            abort(status_code)

        return render_template(
            "followups/edit.html",
            followup=existing,
            form_data=request.form,
            errors=errors,
            active_sales_reps=active_sales_reps,
        ), status_code

    return render_template(
        "followups/edit.html",
        followup=existing,
        form_data=existing,
        errors={},
        active_sales_reps=active_sales_reps,
    )


@followups_bp.route("/<int:followup_id>/status", methods=["POST"])
@login_required
def followup_status_change(followup_id):
    """
    Dedicated state-changing route for completing, marking missed, or cancelling a follow-up.
    """
    current_user = get_current_user()
    target_status = request.form.get("status", "").strip()

    success, updated, errors, status_code = followup_service.update_followup_status(
        followup_id=followup_id,
        target_status=target_status,
        current_user=current_user,
        ip_address=request.remote_addr,
    )

    if success:
        flash(f"Follow-up status marked as '{target_status}'.", "success")
        return redirect(url_for("followups.followup_detail", followup_id=followup_id))

    if status_code in (403, 404):
        abort(status_code)

    flash(errors.get("general", "Could not update status."), "danger")
    return redirect(url_for("followups.followup_detail", followup_id=followup_id))


@followups_bp.route("/<int:followup_id>/reschedule", methods=["POST"])
@login_required
def followup_reschedule(followup_id):
    """
    Dedicated route for rescheduling a follow-up to a new future date.
    """
    current_user = get_current_user()
    new_date = request.form.get("followup_date", "").strip()

    success, updated, errors, status_code = followup_service.reschedule_followup(
        followup_id=followup_id,
        new_date=new_date,
        current_user=current_user,
        ip_address=request.remote_addr,
    )

    if success:
        flash(f"Follow-up rescheduled to {new_date}.", "success")
        return redirect(url_for("followups.followup_detail", followup_id=followup_id))

    if status_code in (403, 404):
        abort(status_code)

    flash(errors.get("followup_date") or errors.get("general", "Could not reschedule follow-up."), "danger")
    return redirect(url_for("followups.followup_detail", followup_id=followup_id))
