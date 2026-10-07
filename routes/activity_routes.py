"""
Activity Routes for AcxiomCRM (Phase 8).

Handles HTTP requests, parameter extraction, and template rendering
for Activity Management workflows.
Adheres strictly to architecture:
- Routes contain no SQL queries or business logic algorithms.
- All state mutations require POST method and CSRF protection.
- Scope-aware authorization enforced server-side.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from security.authentication import get_current_user, login_required
from security.authorization import get_visible_user_ids, has_role, ROLE_ADMIN, ROLE_MANAGER
from repositories import (
    activity_repository,
    opportunity_repository,
    lead_repository,
)
from services import activity_service

activities_bp = Blueprint("activities", __name__, url_prefix="/activities")


@activities_bp.route("", methods=["GET"])
@login_required
def activity_list():
    """
    Display paginated list of activities scoped by actor role and ownership.
    Supports filtering by type, status, assigned rep, and search keywords.
    """
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    activity_type = request.args.get("type", "").strip() or None
    status = request.args.get("status", "").strip() or None
    assigned_to = request.args.get("assigned_to", "").strip() or None
    page = request.args.get("page", 1, type=int)

    is_admin_or_mgr = has_role(current_user, ROLE_ADMIN) or has_role(current_user, ROLE_MANAGER)
    active_sales_reps = opportunity_repository.get_active_sales_executives() if is_admin_or_mgr else []

    activities, pagination, metrics = activity_service.get_activities_list(
        current_user=current_user,
        search=search,
        activity_type=activity_type,
        status=status,
        assigned_to=assigned_to,
        page=page,
        per_page=15,
    )

    return render_template(
        "activities/list.html",
        activities=activities,
        pagination=pagination,
        metrics=metrics,
        search=search or "",
        selected_type=activity_type or "",
        selected_status=status or "",
        selected_assigned=assigned_to or "",
        active_sales_reps=active_sales_reps,
    )


@activities_bp.route("/create", methods=["GET", "POST"])
@login_required
def activity_create():
    """
    Handle activity creation form rendering (GET) and submission (POST).
    """
    current_user = get_current_user()
    is_admin_or_mgr = has_role(current_user, ROLE_ADMIN) or has_role(current_user, ROLE_MANAGER)
    visible_user_ids = get_visible_user_ids(current_user)

    active_sales_reps = opportunity_repository.get_active_sales_executives() if is_admin_or_mgr else []
    active_customers = opportunity_repository.get_active_customers()
    leads = lead_repository.find_leads(allowed_user_ids=visible_user_ids, limit=100)

    if request.method == "POST":
        success, activity, errors, status_code = activity_service.create_activity(
            form_data=request.form,
            current_user=current_user,
            ip_address=request.remote_addr,
        )

        if success:
            flash(f"Activity '{activity['subject']}' logged successfully.", "success")
            return redirect(url_for("activities.activity_detail", activity_id=activity["activity_id"]))

        return render_template(
            "activities/create.html",
            form_data=request.form,
            errors=errors,
            active_sales_reps=active_sales_reps,
            active_customers=active_customers,
            leads=leads,
        ), status_code

    initial_form = {}
    for param in ["customer_id", "lead_id"]:
        val = request.args.get(param)
        if val:
            initial_form[param] = val

    return render_template(
        "activities/create.html",
        form_data=initial_form,
        errors={},
        active_sales_reps=active_sales_reps,
        active_customers=active_customers,
        leads=leads,
    )


@activities_bp.route("/<int:activity_id>", methods=["GET"])
@login_required
def activity_detail(activity_id):
    """
    Display single activity detail with IDOR verification.
    """
    current_user = get_current_user()
    activity, status_code = activity_service.get_activity_detail(activity_id, current_user)

    if status_code == 404:
        abort(404)
    elif status_code == 403:
        abort(403)

    return render_template(
        "activities/detail.html",
        activity=activity,
    )


@activities_bp.route("/<int:activity_id>/edit", methods=["GET", "POST"])
@login_required
def activity_edit(activity_id):
    """
    Display edit form (GET) and handle update submission (POST).
    """
    current_user = get_current_user()
    existing, status_code = activity_service.get_activity_detail(activity_id, current_user)

    if status_code == 404:
        abort(404)
    elif status_code == 403:
        abort(403)

    is_admin_or_mgr = has_role(current_user, ROLE_ADMIN) or has_role(current_user, ROLE_MANAGER)
    active_sales_reps = opportunity_repository.get_active_sales_executives() if is_admin_or_mgr else []

    if request.method == "POST":
        success, updated, errors, status_code = activity_service.update_activity(
            activity_id=activity_id,
            form_data=request.form,
            current_user=current_user,
            ip_address=request.remote_addr,
        )

        if success:
            flash(f"Activity '{updated['subject']}' updated successfully.", "success")
            return redirect(url_for("activities.activity_detail", activity_id=activity_id))

        if status_code in (403, 404):
            abort(status_code)

        return render_template(
            "activities/edit.html",
            activity=existing,
            form_data=request.form,
            errors=errors,
            active_sales_reps=active_sales_reps,
        ), status_code

    return render_template(
        "activities/edit.html",
        activity=existing,
        form_data=existing,
        errors={},
        active_sales_reps=active_sales_reps,
    )
