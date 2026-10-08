"""
Dashboard Service for AcxiomCRM (Phase 9).

Orchestrates date range resolution, role-aware query parameters,
KPI metric computation, and Chart.js visualization preparation.

Adheres strictly to architectural requirements:
- READ-ONLY: Never modifies database records or CRM states.
- Server-side scope: Computes aggregates strictly within the actor's authorized scope.
- Timezone: Asia/Kolkata timezone used for all business date calculations.
- Decimal precision: Monetary values maintained as Decimal throughout.
- JSON-safe: Serializes safe numeric primitives for Chart.js rendering.
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from security.authorization import visible_user_ids
from repositories import dashboard_repository

TIMEZONE_KOLKATA = ZoneInfo("Asia/Kolkata")

FILTER_TODAY = "today"
FILTER_THIS_WEEK = "this_week"
FILTER_THIS_MONTH = "this_month"
FILTER_CUSTOM = "custom"
FILTER_ALL = "all"

VALID_FILTERS = (FILTER_TODAY, FILTER_THIS_WEEK, FILTER_THIS_MONTH, FILTER_CUSTOM, FILTER_ALL)


def resolve_date_range(filter_type="this_month", start_str=None, end_str=None, now=None):
    """
    Resolve date filter type to start and end datetime boundaries in Asia/Kolkata timezone.

    :param filter_type: One of 'today', 'this_week' (or 'week'), 'this_month' (or 'month'), 'custom', 'all'.
    :param start_str: Optional string 'YYYY-MM-DD' for custom range.
    :param end_str: Optional string 'YYYY-MM-DD' for custom range.
    :param now: Optional datetime for deterministic testing.
    :return: Tuple of (start_dt, end_dt, canonical_filter_name)
    :raises ValueError: If custom dates are invalid or start_date > end_date.
    """
    if now is None:
        now = datetime.now(TIMEZONE_KOLKATA)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TIMEZONE_KOLKATA)
    else:
        now = now.astimezone(TIMEZONE_KOLKATA)

    normalized_filter = (filter_type or "").strip().lower()
    if normalized_filter in ("week", "this_week"):
        normalized_filter = FILTER_THIS_WEEK
    elif normalized_filter in ("month", "this_month"):
        normalized_filter = FILTER_THIS_MONTH
    elif normalized_filter not in VALID_FILTERS:
        normalized_filter = FILTER_THIS_MONTH

    today_date = now.date()

    if normalized_filter == FILTER_TODAY:
        start_dt = datetime(today_date.year, today_date.month, today_date.day, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA)
        end_dt = start_dt + timedelta(days=1)
        return start_dt, end_dt, FILTER_TODAY

    elif normalized_filter == FILTER_THIS_WEEK:
        # ISO 8601 week starts on Monday (weekday() == 0)
        monday = today_date - timedelta(days=today_date.weekday())
        start_dt = datetime(monday.year, monday.month, monday.day, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA)
        end_dt = start_dt + timedelta(days=7)
        return start_dt, end_dt, FILTER_THIS_WEEK

    elif normalized_filter == FILTER_THIS_MONTH:
        start_dt = datetime(today_date.year, today_date.month, 1, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA)
        if today_date.month == 12:
            end_dt = datetime(today_date.year + 1, 1, 1, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA)
        else:
            end_dt = datetime(today_date.year, today_date.month + 1, 1, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA)
        return start_dt, end_dt, FILTER_THIS_MONTH

    elif normalized_filter == FILTER_CUSTOM:
        if not start_str or not end_str:
            raise ValueError("Both start date and end date are required for custom range.")
        try:
            start_date = datetime.strptime(start_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("Invalid start date format. Please use YYYY-MM-DD.")

        try:
            end_date = datetime.strptime(end_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("Invalid end date format. Please use YYYY-MM-DD.")

        if start_date > end_date:
            raise ValueError("Start date cannot be after end date.")

        start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA)
        # End datetime covers entire end_date through 23:59:59.999999 by adding 1 day exclusive
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA) + timedelta(days=1)
        return start_dt, end_dt, FILTER_CUSTOM

    elif normalized_filter == FILTER_ALL:
        return None, None, FILTER_ALL

    return None, None, FILTER_THIS_MONTH


def get_monthly_sales_window(now=None, months_count=12):
    """
    Generate the 12-month rolling window (month keys and human labels) ending at the current month in Asia/Kolkata.

    :param now: Optional datetime for testing.
    :param months_count: Number of historical months to display (default 12).
    :return: Tuple of (start_dt, end_dt, month_keys, display_labels)
    """
    if now is None:
        now = datetime.now(TIMEZONE_KOLKATA)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=TIMEZONE_KOLKATA)
    else:
        now = now.astimezone(TIMEZONE_KOLKATA)

    current_year = now.year
    current_month = now.month

    # End boundary: start of next month
    if current_month == 12:
        end_dt = datetime(current_year + 1, 1, 1, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA)
    else:
        end_dt = datetime(current_year, current_month + 1, 1, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA)

    # Generate sequence of months
    month_keys = []
    display_labels = []

    # Calculate past months starting (months_count - 1) months ago up to current month
    for i in range(months_count - 1, -1, -1):
        # Target month offset
        total_months = (current_year * 12 + current_month - 1) - i
        y = total_months // 12
        m = (total_months % 12) + 1
        key = f"{y:04d}-{m:02d}"
        dt = datetime(y, m, 1, tzinfo=TIMEZONE_KOLKATA)
        label = dt.strftime("%b %Y")
        month_keys.append(key)
        display_labels.append(label)

    # Start boundary: 1st of the earliest month in the window
    first_y = ( (current_year * 12 + current_month - 1) - (months_count - 1) ) // 12
    first_m = ( (current_year * 12 + current_month - 1) - (months_count - 1) ) % 12 + 1
    start_dt = datetime(first_y, first_m, 1, 0, 0, 0, tzinfo=TIMEZONE_KOLKATA)

    return start_dt, end_dt, month_keys, display_labels


def get_dashboard_data(current_user, filter_type="this_month", start_str=None, end_str=None, now=None):
    """
    Retrieve all authorized KPI metrics and Chart.js datasets for the authenticated user.

    :param current_user: Authenticated user dictionary from session.
    :param filter_type: Date filter selection ('today', 'this_week', 'this_month', 'custom', 'all').
    :param start_str: Optional 'YYYY-MM-DD' for custom range.
    :param end_str: Optional 'YYYY-MM-DD' for custom range.
    :param now: Optional current datetime reference for testing.
    :return: Dictionary containing KPIs, Chart data structures, and active filter info.
    """
    visible_ids = visible_user_ids(current_user)

    start_dt, end_dt, resolved_filter = resolve_date_range(
        filter_type=filter_type,
        start_str=start_str,
        end_str=end_str,
        now=now
    )

    # 1. Total Customers KPI (CreatedDate)
    total_customers = dashboard_repository.get_customer_kpi(
        visible_user_ids=visible_ids,
        start_dt=start_dt,
        end_dt=end_dt
    )

    # 2 & 3. Total Leads & Open Leads KPIs (CreatedDate)
    lead_kpis = dashboard_repository.get_lead_kpis(
        visible_user_ids=visible_ids,
        start_dt=start_dt,
        end_dt=end_dt
    )
    total_leads = lead_kpis["total_leads"]
    open_leads = lead_kpis["open_leads"]

    # 4 & 5 & 8. Total Opportunities, Open Opportunities, Total Pipeline Value (CreatedDate)
    opp_kpis = dashboard_repository.get_opportunity_kpis(
        visible_user_ids=visible_ids,
        start_dt=start_dt,
        end_dt=end_dt
    )
    total_opportunities = opp_kpis["total_opportunities"]
    open_opportunities = opp_kpis["open_opportunities"]
    total_pipeline_value = opp_kpis["total_pipeline_value"]

    # 6 & 7. Won and Lost KPIs (ClosedDate)
    won_lost_kpis = dashboard_repository.get_won_lost_kpis(
        visible_user_ids=visible_ids,
        start_dt=start_dt,
        end_dt=end_dt
    )
    won_count = won_lost_kpis["won_count"]
    lost_count = won_lost_kpis["lost_count"]

    # -------------------------------------------------------------------------
    # Chart 1: Lead Status Chart
    # Categories: 'New', 'Contacted', 'Qualified', 'Converted', 'Lost'
    # -------------------------------------------------------------------------
    lead_status_categories = ["New", "Contacted", "Qualified", "Converted", "Lost"]
    raw_lead_counts = dashboard_repository.get_lead_status_chart_counts(
        visible_user_ids=visible_ids,
        start_dt=start_dt,
        end_dt=end_dt
    )
    lead_status_values = [raw_lead_counts.get(cat, 0) for cat in lead_status_categories]
    lead_status_total = sum(lead_status_values)

    # -------------------------------------------------------------------------
    # Chart 2: Opportunity Pipeline by Stage Chart
    # Categories: 'Qualification', 'Proposal', 'Negotiation', 'Won', 'Lost'
    # -------------------------------------------------------------------------
    pipeline_stages = ["Qualification", "Proposal", "Negotiation", "Won", "Lost"]
    raw_opp_counts = dashboard_repository.get_opportunity_pipeline_chart_counts(
        visible_user_ids=visible_ids,
        start_dt=start_dt,
        end_dt=end_dt
    )
    pipeline_values = [raw_opp_counts.get(stg, 0) for stg in pipeline_stages]
    pipeline_total = sum(pipeline_values)

    # -------------------------------------------------------------------------
    # Chart 3: Monthly Sales Trend (12 Months, Won Opportunities by ClosedDate)
    # -------------------------------------------------------------------------
    start_12m, end_12m, month_keys, display_month_labels = get_monthly_sales_window(now=now, months_count=12)
    raw_monthly_sales = dashboard_repository.get_monthly_sales_chart_data(
        visible_user_ids=visible_ids,
        start_dt=start_12m,
        end_dt=end_12m
    )
    monthly_sales_values = [float(raw_monthly_sales.get(key, Decimal("0.00"))) for key in month_keys]
    monthly_sales_total = sum(monthly_sales_values)

    # Safe JSON-serializable chart data bundle
    chart_data = {
        "lead_status": {
            "labels": lead_status_categories,
            "values": lead_status_values,
            "total": lead_status_total,
            "has_data": lead_status_total > 0
        },
        "opportunity_pipeline": {
            "labels": pipeline_stages,
            "values": pipeline_values,
            "total": pipeline_total,
            "has_data": pipeline_total > 0
        },
        "monthly_sales": {
            "labels": display_month_labels,
            "month_keys": month_keys,
            "values": monthly_sales_values,
            "total": monthly_sales_total,
            "has_data": monthly_sales_total > 0
        }
    }

    return {
        "kpis": {
            "total_customers": total_customers,
            "total_leads": total_leads,
            "open_leads": open_leads,
            "total_opportunities": total_opportunities,
            "open_opportunities": open_opportunities,
            "won_count": won_count,
            "lost_count": lost_count,
            "total_pipeline_value": total_pipeline_value,
            "total_pipeline_value_formatted": f"{total_pipeline_value:,.2f}"
        },
        "chart_data": chart_data,
        "chart_data_json": json.dumps(chart_data),
        "filter": {
            "type": resolved_filter,
            "start_date": start_str if resolved_filter == FILTER_CUSTOM else (start_dt.strftime("%Y-%m-%d") if start_dt else ""),
            "end_date": end_str if resolved_filter == FILTER_CUSTOM else ((end_dt - timedelta(days=1)).strftime("%Y-%m-%d") if end_dt else ""),
            "start_dt": start_dt,
            "end_dt": end_dt
        }
    }
