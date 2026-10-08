"""
Dashboard Routes for AcxiomCRM (Phase 9).

Handles HTTP request reception, date filter parameter extraction, and template rendering
for the Role-Based Read-Only CRM Dashboard.

Adheres strictly to layered architecture:
- Contains no SQL queries (all data access is in repositories/dashboard_repository.py).
- Contains no business or aggregation logic (all orchestration in services/dashboard_service.py).
- Read-only: uses GET method exclusively.
- Protected by @login_required; anonymous access redirects to /login.
"""

from flask import Blueprint, render_template, request, abort
from security.authentication import get_current_user, login_required
from services import dashboard_service

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("", methods=["GET"])
@dashboard_bp.route("/", methods=["GET"])
@login_required
def index():
    """
    Render role-aware read-only dashboard with KPI cards, date filters, and Chart.js datasets.
    """
    current_user = get_current_user()
    filter_type = request.args.get("range", "this_month").strip()
    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None

    try:
        dashboard_data = dashboard_service.get_dashboard_data(
            current_user=current_user,
            filter_type=filter_type,
            start_str=start_date,
            end_str=end_date,
        )
    except ValueError:
        # Reject malformed custom date ranges or start > end with HTTP 400 Bad Request
        abort(400)

    return render_template(
        "dashboard/index.html",
        kpis=dashboard_data["kpis"],
        chart_data=dashboard_data["chart_data"],
        chart_data_json=dashboard_data["chart_data_json"],
        active_filter=dashboard_data["filter"]
    )
