"""
Report Routes for AcxiomCRM (Phase 10).

Handles HTTP request reception, parameter parsing, authorization enforcement,
and template rendering for all 8 system reports:
1. Customer Report (/reports/customers)
2. Lead Report (/reports/leads)
3. Follow-Up Report (/reports/followups)
4. Opportunity Report (/reports/opportunities)
5. Pipeline Report (/reports/pipeline)
6. Sales / Conversion Report (/reports/sales)
7. User Activity Report (/reports/user-activity)
8. Audit Report (/reports/audit) - Admin Only

Adheres strictly to layered architecture:
- Routes contain no SQL queries or business aggregation logic.
- Purely read-only GET endpoints.
- Authorization enforced server-side (@login_required, @admin_required).
"""

from flask import Blueprint, render_template, request, abort
from security.authentication import get_current_user, login_required
from security.decorators import admin_required
from services import report_service

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("", methods=["GET"])
@reports_bp.route("/", methods=["GET"])
@login_required
def index():
    """Reports navigation hub displaying available reports based on role."""
    current_user = get_current_user()
    return render_template("reports/index.html", current_user=current_user)


# =============================================================================
# 1. CUSTOMER REPORT
# =============================================================================

@reports_bp.route("/customers", methods=["GET"])
@login_required
def customer_report():
    """Customer Report with search, status filtering, assigned rep filter, and sorting."""
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    status = request.args.get("status", "").strip() or None
    assigned_to = request.args.get("assigned_to", "").strip() or None
    sort_by = request.args.get("sort_by", "customer_name")
    sort_order = request.args.get("sort_order", "ASC")
    page = request.args.get("page", 1, type=int)

    data = report_service.get_customer_report_data(
        current_user=current_user,
        search=search,
        status=status,
        assigned_to=assigned_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=20,
    )
    return render_template("reports/customers.html", **data)


# =============================================================================
# 2. LEAD REPORT
# =============================================================================

@reports_bp.route("/leads", methods=["GET"])
@login_required
def lead_report():
    """Lead Report across all 6 statuses with source/status/assigned rep filtering."""
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    status = request.args.get("status", "").strip() or None
    source = request.args.get("source", "").strip() or None
    assigned_to = request.args.get("assigned_to", "").strip() or None
    sort_by = request.args.get("sort_by", "lead_name")
    sort_order = request.args.get("sort_order", "ASC")
    page = request.args.get("page", 1, type=int)

    data = report_service.get_lead_report_data(
        current_user=current_user,
        search=search,
        status=status,
        source=source,
        assigned_to=assigned_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=20,
    )
    return render_template("reports/leads.html", **data)


# =============================================================================
# 3. FOLLOW-UP REPORT
# =============================================================================

@reports_bp.route("/followups", methods=["GET"])
@login_required
def followup_report():
    """Follow-Up Report with date window, status, communication type, assigned rep, and related entity filters."""
    current_user = get_current_user()
    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None
    status = request.args.get("status", "").strip() or None
    followup_type = request.args.get("type", "").strip() or None
    assigned_to = request.args.get("assigned_to", "").strip() or None
    related_type = request.args.get("related_type", "").strip() or None
    customer_id = request.args.get("customer_id", "").strip() or None
    lead_id = request.args.get("lead_id", "").strip() or None
    opportunity_id = request.args.get("opportunity_id", "").strip() or None
    sort_by = request.args.get("sort_by", "followup_date")
    sort_order = request.args.get("sort_order", "ASC")
    page = request.args.get("page", 1, type=int)

    try:
        data = report_service.get_followup_report_data(
            current_user=current_user,
            start_str=start_date,
            end_str=end_date,
            status=status,
            followup_type=followup_type,
            assigned_to=assigned_to,
            related_type=related_type,
            customer_id=customer_id,
            lead_id=lead_id,
            opportunity_id=opportunity_id,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            per_page=20,
        )
    except ValueError:
        abort(400)

    return render_template("reports/followups.html", **data)


# =============================================================================
# 4. OPPORTUNITY REPORT
# =============================================================================

@reports_bp.route("/opportunities", methods=["GET"])
@login_required
def opportunity_report():
    """Opportunity Report with stage, status, assigned rep, and customer search filtering."""
    current_user = get_current_user()
    search = request.args.get("search", "").strip() or None
    stage = request.args.get("stage", "").strip() or None
    status = request.args.get("status", "").strip() or None
    assigned_to = request.args.get("assigned_to", "").strip() or None
    sort_by = request.args.get("sort_by", "opportunity_name")
    sort_order = request.args.get("sort_order", "ASC")
    page = request.args.get("page", 1, type=int)

    data = report_service.get_opportunity_report_data(
        current_user=current_user,
        search=search,
        stage=stage,
        status=status,
        assigned_to=assigned_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=20,
    )
    return render_template("reports/opportunities.html", **data)


# =============================================================================
# 5. PIPELINE REPORT
# =============================================================================

@reports_bp.route("/pipeline", methods=["GET"])
@login_required
def pipeline_report():
    """Pipeline Report with stage breakdown, weighted value, and exact Decimal totals."""
    current_user = get_current_user()
    stage = request.args.get("stage", "").strip() or None
    sort_by = request.args.get("sort_by", "expected_close_date")
    sort_order = request.args.get("sort_order", "ASC")
    page = request.args.get("page", 1, type=int)

    data = report_service.get_pipeline_report_data(
        current_user=current_user,
        stage=stage,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=20,
    )
    return render_template("reports/pipeline.html", **data)


# =============================================================================
# 6. SALES / CONVERSION REPORT
# =============================================================================

@reports_bp.route("/sales", methods=["GET"])
@login_required
def sales_report():
    """Sales & Conversion Report with dual conversion rates, won revenue, and deal listings."""
    current_user = get_current_user()
    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None

    try:
        data = report_service.get_sales_conversion_report_data(
            current_user=current_user,
            start_str=start_date,
            end_str=end_date,
        )
    except ValueError:
        abort(400)

    return render_template("reports/sales.html", **data)


# =============================================================================
# 7. USER ACTIVITY REPORT
# =============================================================================

@reports_bp.route("/user-activity", methods=["GET"])
@login_required
def user_activity_report():
    """User Activity Report tracking CRM interaction interactions (Calls, Meetings, Emails, Tasks)."""
    current_user = get_current_user()
    rep_id = request.args.get("assigned_to", "").strip() or None
    activity_type = request.args.get("type", "").strip() or None
    status = request.args.get("status", "").strip() or None
    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None
    sort_by = request.args.get("sort_by", "activity_date")
    sort_order = request.args.get("sort_order", "DESC")
    page = request.args.get("page", 1, type=int)

    try:
        data = report_service.get_user_activity_report_data(
            current_user=current_user,
            assigned_to_user_id=rep_id,
            activity_type=activity_type,
            status=status,
            start_str=start_date,
            end_str=end_date,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            per_page=20,
        )
    except ValueError:
        abort(400)

    return render_template("reports/user_activity.html", **data)


# =============================================================================
# 8. AUDIT REPORT (ADMIN ONLY)
# =============================================================================

@reports_bp.route("/audit", methods=["GET"])
@admin_required
def audit_report():
    """Immutable Audit Log Report restricted strictly to Administrators."""
    user_id = request.args.get("user_id", "").strip() or None
    entity_name = request.args.get("entity_name", "").strip() or None
    action = request.args.get("action", "").strip() or None
    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None
    sort_by = request.args.get("sort_by", "created_date")
    sort_order = request.args.get("sort_order", "DESC")
    page = request.args.get("page", 1, type=int)

    try:
        data = report_service.get_audit_report_data(
            user_id=user_id,
            entity_name=entity_name,
            action=action,
            start_str=start_date,
            end_str=end_date,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            per_page=20,
        )
    except ValueError:
        abort(400)

    return render_template("reports/audit.html", **data)
