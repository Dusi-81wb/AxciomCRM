"""
Lead Routes for AcxiomCRM.

Handles HTTP requests, parameter extraction, and template rendering
for Lead Management and Conversion workflows.
Adheres strictly to architecture:
- Routes contain no SQL queries or business transition rules.
- All state mutations require POST method and CSRF protection.
- Scope-aware authorization enforced server-side.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from security.authentication import get_current_user, login_required
from security.decorators import ROLE_ADMIN, ROLE_MANAGER
from repositories import lead_repository
from services import lead_service

leads_bp = Blueprint("leads", __name__, url_prefix="/leads")


@leads_bp.route("", methods=["GET"])
@login_required
def lead_list():
    """
    Display paginated list of leads scoped by actor role and ownership.
    Supports search across Name, Company, Email, Phone, Status, and Assigned user.
    """
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    status = request.args.get("status", "").strip() or None
    assigned_to = request.args.get("assigned_to", "").strip() or None
    sort_by = request.args.get("sort_by", "created_date")
    sort_order = request.args.get("sort_order", "DESC")
    page = request.args.get("page", 1, type=int)

    is_admin_or_mgr = current_user.get("role_name") in (ROLE_ADMIN, ROLE_MANAGER)
    active_sales_reps = lead_repository.get_active_sales_executives() if is_admin_or_mgr else []

    leads, total_count, total_pages = lead_service.get_leads_list(
        current_user=current_user,
        search=search,
        status=status,
        assigned_to=assigned_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=10
    )

    return render_template(
        "leads/list.html",
        leads=leads,
        total_count=total_count,
        total_pages=total_pages,
        current_page=page,
        search=search or "",
        status=status or "",
        assigned_to=assigned_to or "",
        sort_by=sort_by,
        sort_order=sort_order,
        sales_reps=active_sales_reps,
        is_admin_or_mgr=is_admin_or_mgr
    )


@leads_bp.route("/create", methods=["GET", "POST"])
@login_required
def lead_create():
    """
    Handle lead creation form display (GET) and submission (POST).
    Sales Executive creations are automatically self-assigned.
    """
    current_user = get_current_user()
    is_admin_or_mgr = current_user.get("role_name") in (ROLE_ADMIN, ROLE_MANAGER)
    active_sales_reps = lead_repository.get_active_sales_executives() if is_admin_or_mgr else []

    if request.method == "POST":
        success, lead, errors = lead_service.create_lead(
            form_data=request.form,
            current_user=current_user,
            ip_address=request.remote_addr
        )

        if success:
            flash(f"Lead '{lead['lead_name']}' created successfully ({lead['lead_code']}).", "success")
            return redirect(url_for("leads.lead_detail", lead_id=lead["lead_id"]))

        return render_template(
            "leads/create.html",
            form_data=request.form,
            errors=errors,
            sales_reps=active_sales_reps,
            active_sales_reps=active_sales_reps,
            is_admin_or_mgr=is_admin_or_mgr
        ), 400

    return render_template(
        "leads/create.html",
        form_data={},
        errors={},
        sales_reps=active_sales_reps,
        active_sales_reps=active_sales_reps,
        is_admin_or_mgr=is_admin_or_mgr
    )


@leads_bp.route("/<int:lead_id>", methods=["GET"])
@login_required
def lead_detail(lead_id):
    """
    Display lead detail page with server-side ownership verification.
    """
    current_user = get_current_user()
    lead, status_code = lead_service.get_lead_detail(lead_id, current_user)

    if status_code == 404:
        abort(404)
    elif status_code == 403:
        abort(403)

    return render_template(
        "leads/detail.html",
        lead=lead
    )


@leads_bp.route("/<int:lead_id>/edit", methods=["GET", "POST"])
@login_required
def lead_edit(lead_id):
    """
    Handle lead edit form display (GET) and update submission (POST).
    """
    current_user = get_current_user()
    existing_lead, status_code = lead_service.get_lead_detail(lead_id, current_user)

    if status_code == 404:
        abort(404)
    elif status_code == 403:
        abort(403)

    is_admin_or_mgr = current_user.get("role_name") in (ROLE_ADMIN, ROLE_MANAGER)
    active_sales_reps = lead_repository.get_active_sales_executives() if is_admin_or_mgr else []

    if request.method == "POST":
        success, updated_lead, errors, status_code = lead_service.update_lead(
            lead_id=lead_id,
            form_data=request.form,
            current_user=current_user,
            ip_address=request.remote_addr
        )

        if success:
            flash(f"Lead '{updated_lead['lead_name']}' updated successfully.", "success")
            return redirect(url_for("leads.lead_detail", lead_id=lead_id))

        if status_code in (403, 404):
            abort(status_code)

        return render_template(
            "leads/edit.html",
            lead=existing_lead,
            form_data=request.form,
            errors=errors,
            sales_reps=active_sales_reps,
            active_sales_reps=active_sales_reps,
            is_admin_or_mgr=is_admin_or_mgr
        ), 400

    return render_template(
        "leads/edit.html",
        lead=existing_lead,
        form_data=existing_lead,
        errors={},
        sales_reps=active_sales_reps,
        active_sales_reps=active_sales_reps,
        is_admin_or_mgr=is_admin_or_mgr
    )


@leads_bp.route("/<int:lead_id>/status", methods=["POST"])
@login_required
def lead_status(lead_id):
    """
    Update lead status following approved transition rules.
    """
    current_user = get_current_user()
    target_status = request.form.get("status", "").strip()

    success, error_msg, status_code = lead_service.update_lead_status(
        lead_id=lead_id,
        target_status=target_status,
        current_user=current_user,
        ip_address=request.remote_addr
    )

    if not success:
        if status_code in (403, 404):
            abort(status_code)
        flash(error_msg or "Failed to update lead status.", "danger")
    else:
        flash(f"Lead status updated to '{target_status}'.", "success")

    return redirect(url_for("leads.lead_detail", lead_id=lead_id))


@leads_bp.route("/<int:lead_id>/convert", methods=["GET", "POST"])
@login_required
def lead_convert(lead_id):
    """
    Handle Lead conversion confirmation (GET) and atomic conversion execution (POST).
    """
    current_user = get_current_user()
    lead, status_code = lead_service.get_lead_detail(lead_id, current_user)

    if status_code == 404:
        abort(404)
    elif status_code == 403:
        abort(403)

    if request.method == "GET" and lead["status"] != "Qualified":
        flash(f"Only Qualified leads may be converted. Current status is '{lead['status']}'.", "warning")
        return redirect(url_for("leads.lead_detail", lead_id=lead_id))

    if request.method == "POST":
        success, result, errors, status_code = lead_service.convert_lead(
            lead_id=lead_id,
            form_data=request.form,
            current_user=current_user,
            ip_address=request.remote_addr
        )

        if success:
            cust = result["customer"]
            opp = result.get("opportunity")
            flash(
                f"Lead '{lead['lead_code']}' converted successfully into Customer '{cust['customer_name']}'"
                + (f" and Opportunity '{opp['opportunity_name']}'." if opp else "."),
                "success"
            )
            return redirect(url_for("customers.customer_detail", customer_id=cust["customer_id"]))

        if status_code in (403, 404):
            abort(status_code)

        return render_template(
            "leads/convert.html",
            lead=lead,
            form_data=request.form,
            errors=errors
        ), 400

    # Default form values for GET
    default_form = {
        "customer_name": lead["lead_name"],
        "company_name": lead["company_name"] or "",
        "email": lead["email"],
        "phone": lead["phone"] or "",
        "opportunity_name": f"{lead['company_name'] or lead['lead_name']} Deal",
        "amount": str(lead["expected_value"]) if lead["expected_value"] is not None else "",
        "probability": "50",
        "create_opportunity": True
    }

    return render_template(
        "leads/convert.html",
        lead=lead,
        form_data=default_form,
        errors={}
    )
