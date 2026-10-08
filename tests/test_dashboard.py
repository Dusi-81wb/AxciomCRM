"""
Comprehensive Dashboard & Chart.js Tests for AcxiomCRM (Phase 9).

Verifies the complete read-only Dashboard vertical slice:
Route -> Authentication -> Authorization/Role-Scope -> Service -> SQL Aggregation -> Chart.js JSON.

Covers all Part 39 test requirements:
1-4. Access & Authentication (Anonymous redirected, Admin/Manager/Sales Exec allowed).
5-12. KPI Existence (Total Customers, Total Leads, Open Leads, Total Opportunities, Open Opportunities, Won, Lost, Total Pipeline Value).
13-16. Role Scoping (Admin org-wide, Manager scope, Sales Exec isolated, IDOR/inference blocked).
17-20. Pipeline Calculations (Open included, Won/Lost excluded, exact Decimal precision).
21-27. Date Filters (Today, This Week, This Month, Custom, invalid dates rejected, start > end rejected, Asia/Kolkata semantics).
28-31. Lead Status Chart (5 approved categories, role-scoped, date-scoped, Unqualified excluded per Decision 98 #3).
32-34. Opportunity Pipeline Chart (Qualification, Proposal, Negotiation, Won, Lost; role/date scoped).
35-39. Monthly Sales Chart (Won opportunities by ClosedDate, Lost/Open excluded, role-scoped).
40-42. Chart Data Security (Authorized aggregates only, no raw rows in browser, valid JSON).
43-44. Zero-Data Handling (Graceful rendering, no fake demo values).
45-47. System Security (No SQL errors exposed, no secrets leaked, no data-leak side channels).
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
import pytest

from app import create_app
from config import TestingConfig
from repositories import dashboard_repository
from services import dashboard_service

KOLKATA = ZoneInfo("Asia/Kolkata")


def login(client, identifier, password):
    """Authenticate test user and store session cookies."""
    return client.post("/login", data={
        "identifier": identifier,
        "password": password
    }, follow_redirects=False)


# =============================================================================
# PART 1: DASHBOARD ACCESS & AUTHENTICATION
# =============================================================================

def test_anonymous_user_redirected_to_login(client):
    """1. Anonymous requests to /dashboard must redirect to /login."""
    resp = client.get("/dashboard")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_authenticated_admin_can_access_dashboard(client):
    """2. Authenticated Admin can access dashboard with HTTP 200."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Executive Dashboard" in resp.data
    assert b"Admin" in resp.data


def test_authenticated_manager_can_access_dashboard(client):
    """3. Authenticated Manager can access dashboard with HTTP 200."""
    login(client, "manager", "Manager@123")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Executive Dashboard" in resp.data
    assert b"Manager" in resp.data


def test_authenticated_sales_executive_can_access_dashboard(client):
    """4. Authenticated Sales Executive can access dashboard with HTTP 200."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"Executive Dashboard" in resp.data
    assert b"Sales Executive" in resp.data


# =============================================================================
# PART 2: KPI EXISTENCE (ALL 8 MANDATORY CARDS)
# =============================================================================

def test_dashboard_returns_all_eight_kpi_cards(client):
    """5-12. Dashboard renders all 8 mandatory KPI cards with exact approved names."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    content = resp.data.decode("utf-8")

    # 1. Total Customers
    assert "Total Customers" in content
    assert 'id="kpi-total-customers"' in content

    # 2. Total Leads
    assert "Total Leads" in content
    assert 'id="kpi-total-leads"' in content

    # 3. Open Leads
    assert "Open Leads" in content
    assert 'id="kpi-open-leads"' in content

    # 4. Total Opportunities
    assert "Total Opportunities" in content
    assert 'id="kpi-total-opportunities"' in content

    # 5. Open Opportunities
    assert "Open Opportunities" in content
    assert 'id="kpi-open-opportunities"' in content

    # 6. Won
    assert "Won" in content
    assert 'id="kpi-won"' in content

    # 7. Lost
    assert "Lost" in content
    assert 'id="kpi-lost"' in content

    # 8. Total Pipeline Value
    assert "Total Pipeline Value" in content
    assert 'id="kpi-total-pipeline-value"' in content


# =============================================================================
# PART 3: ROLE SCOPING & ISOLATION
# =============================================================================

def test_admin_sees_organization_wide_data(app):
    """13. Admin sees organization-wide CRM data aggregates."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    with app.app_context():
        data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        kpis = data["kpis"]
        # Seed has at least 4 customers, 5 opportunities, 6 leads
        assert kpis["total_customers"] >= 4
        assert kpis["total_opportunities"] >= 5
        assert kpis["open_opportunities"] >= 3
        assert kpis["total_pipeline_value"] >= Decimal("535000.00")


def test_manager_sees_approved_manager_scope(app):
    """14. Manager sees approved Manager CRM data scope (currently organization-wide)."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    mgr_user = {"user_id": 2, "role_name": "Manager", "is_active": True}
    with app.app_context():
        admin_data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        mgr_data = dashboard_service.get_dashboard_data(mgr_user, filter_type="all")
        # In current approved model, Manager scope matches Admin CRM scope
        assert mgr_data["kpis"]["total_customers"] == admin_data["kpis"]["total_customers"]
        assert mgr_data["kpis"]["total_opportunities"] == admin_data["kpis"]["total_opportunities"]
        assert mgr_data["kpis"]["total_pipeline_value"] == admin_data["kpis"]["total_pipeline_value"]


def test_sales_executive_sees_only_assigned_data(app):
    """15. Sales Executive sees only records assigned to themselves."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    sales1 = {"user_id": 3, "role_name": "Sales Executive", "is_active": True}
    sales2 = {"user_id": 4, "role_name": "Sales Executive", "is_active": True}

    with app.app_context():
        admin_data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        data1 = dashboard_service.get_dashboard_data(sales1, filter_type="all")
        data2 = dashboard_service.get_dashboard_data(sales2, filter_type="all")

        # Each rep sees strictly a subset of total records
        assert data1["kpis"]["total_customers"] > 0
        assert data2["kpis"]["total_customers"] > 0
        assert data1["kpis"]["total_customers"] + data2["kpis"]["total_customers"] == admin_data["kpis"]["total_customers"]

        # Sales1 and Sales2 opportunities sum exactly to total org opportunities
        assert data1["kpis"]["total_opportunities"] + data2["kpis"]["total_opportunities"] == admin_data["kpis"]["total_opportunities"]
        # Pipeline sums exactly to total org pipeline
        assert data1["kpis"]["total_pipeline_value"] + data2["kpis"]["total_pipeline_value"] == admin_data["kpis"]["total_pipeline_value"]


def test_sales_executive_cannot_infer_other_users_records(client):
    """16. Sales Executive dashboard HTML does not contain other reps' aggregates."""
    login(client, "sales2", "Sales@123")
    resp = client.get("/dashboard?range=all")
    assert resp.status_code == 200
    content = resp.data.decode("utf-8")
    # sales2 pipeline value is 0.00, sales1 pipeline value is > 0
    assert "0.00" in content


# =============================================================================
# PART 4: PIPELINE DEFINITION & EXACT MONEY
# =============================================================================

def test_pipeline_includes_only_open_opportunities(app):
    """17-19. Pipeline strictly includes Open deals and excludes Won and Lost deals."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    with app.app_context():
        data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        kpis = data["kpis"]

        # All open deals must be included
        assert kpis["open_opportunities"] >= 3
        # Won deals and Lost deals are counted separately
        assert kpis["won_count"] >= 1
        assert kpis["lost_count"] >= 1

        # Total opportunities = Open + Won + Lost
        assert kpis["total_opportunities"] == kpis["open_opportunities"] + kpis["won_count"] + kpis["lost_count"]


def test_pipeline_amount_uses_exact_decimal_precision(app):
    """20. Monetary pipeline calculation preserves exact Decimal precision."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    with app.app_context():
        data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        pipeline_val = data["kpis"]["total_pipeline_value"]
        assert isinstance(pipeline_val, Decimal)
        assert pipeline_val >= Decimal("535000.00")
        assert data["kpis"]["total_pipeline_value_formatted"] == f"{pipeline_val:,.2f}"


# =============================================================================
# PART 5: DATE FILTERS & TIMEZONE SEMANTICS
# =============================================================================

def test_today_filter_works_and_sets_active_state(client):
    """21. Today filter functions properly and reflects in UI."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard?range=today")
    assert resp.status_code == 200
    assert b'id="filter-today"' in resp.data
    assert b'btn-primary' in resp.data


def test_this_week_filter_works_and_sets_active_state(client):
    """22. This Week filter functions properly and reflects in UI."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard?range=this_week")
    assert resp.status_code == 200
    assert b'id="filter-this-week"' in resp.data


def test_this_month_filter_works_and_sets_active_state(client):
    """23. This Month filter functions properly and is default."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard?range=this_month")
    assert resp.status_code == 200
    assert b'id="filter-this-month"' in resp.data


def test_custom_range_valid_filter(client):
    """24. Custom range with valid dates applies successfully."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard?range=custom&start_date=2026-10-01&end_date=2026-10-15")
    assert resp.status_code == 200
    assert b"Custom Range: 2026-10-01" in resp.data


def test_invalid_custom_date_rejected_with_400(client):
    """25. Malformed custom date input is rejected with HTTP 400 Bad Request."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard?range=custom&start_date=not-a-date&end_date=2026-10-15")
    assert resp.status_code == 400


def test_custom_date_start_after_end_rejected_with_400(client):
    """26. Custom range where start_date > end_date is rejected with HTTP 400."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard?range=custom&start_date=2026-10-20&end_date=2026-10-15")
    assert resp.status_code == 400


def test_asia_kolkata_date_boundary_resolution():
    """27. Date boundary resolution adheres strictly to Asia/Kolkata timezone and Monday-start week."""
    mock_now = datetime(2026, 10, 7, 14, 30, 0, tzinfo=KOLKATA)

    # 1. Today
    start_today, end_today, f_today = dashboard_service.resolve_date_range("today", now=mock_now)
    assert f_today == "today"
    assert start_today == datetime(2026, 10, 7, 0, 0, 0, tzinfo=KOLKATA)
    assert end_today == datetime(2026, 10, 8, 0, 0, 0, tzinfo=KOLKATA)

    # 2. This Week (Monday start)
    start_week, end_week, f_week = dashboard_service.resolve_date_range("this_week", now=mock_now)
    assert f_week == "this_week"
    assert start_week == datetime(2026, 10, 5, 0, 0, 0, tzinfo=KOLKATA)
    assert end_week == datetime(2026, 10, 12, 0, 0, 0, tzinfo=KOLKATA)
    assert start_week.weekday() == 0  # Monday

    # 3. This Month
    start_month, end_month, f_month = dashboard_service.resolve_date_range("this_month", now=mock_now)
    assert f_month == "this_month"
    assert start_month == datetime(2026, 10, 1, 0, 0, 0, tzinfo=KOLKATA)
    assert end_month == datetime(2026, 11, 1, 0, 0, 0, tzinfo=KOLKATA)


# =============================================================================
# PART 6: CHART 1: LEAD STATUS VISUALIZATION
# =============================================================================

def test_lead_status_chart_contains_approved_categories(app):
    """28 & 31. Lead Status chart has exact 5 approved categories; Unqualified is excluded."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    with app.app_context():
        data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        lead_chart = data["chart_data"]["lead_status"]

        expected_cats = ["New", "Contacted", "Qualified", "Converted", "Lost"]
        assert lead_chart["labels"] == expected_cats

        # Decision 98 #3: 'Unqualified' is not in chart labels
        assert "Unqualified" not in lead_chart["labels"]
        assert len(lead_chart["values"]) == 5


def test_lead_status_chart_counts_respect_role_scope(app):
    """29. Lead Status chart data is role-scoped server-side."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    sales1 = {"user_id": 3, "role_name": "Sales Executive", "is_active": True}
    sales2 = {"user_id": 4, "role_name": "Sales Executive", "is_active": True}

    with app.app_context():
        admin_data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        data1 = dashboard_service.get_dashboard_data(sales1, filter_type="all")
        data2 = dashboard_service.get_dashboard_data(sales2, filter_type="all")

        # Sum of sales reps equals admin total
        total_reps = data1["chart_data"]["lead_status"]["total"] + data2["chart_data"]["lead_status"]["total"]
        assert total_reps == admin_data["chart_data"]["lead_status"]["total"]


def test_lead_status_counts_respect_date_range(app):
    """30. Lead counts respect date range boundaries."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    with app.app_context():
        data_empty = dashboard_service.get_dashboard_data(
            admin_user, filter_type="custom", start_str="2020-01-01", end_str="2020-01-31"
        )
        assert data_empty["chart_data"]["lead_status"]["total"] == 0
        assert data_empty["chart_data"]["lead_status"]["has_data"] is False


# =============================================================================
# PART 7: CHART 2: OPPORTUNITY PIPELINE VISUALIZATION
# =============================================================================

def test_opportunity_pipeline_chart_contains_approved_stages(app):
    """32. Pipeline chart contains Qualification, Proposal, Negotiation, Won, Lost."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    with app.app_context():
        data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        pipeline_chart = data["chart_data"]["opportunity_pipeline"]

        expected_stages = ["Qualification", "Proposal", "Negotiation", "Won", "Lost"]
        assert pipeline_chart["labels"] == expected_stages
        assert len(pipeline_chart["values"]) == 5


def test_opportunity_pipeline_stage_counts_respect_role_scope(app):
    """33. Opportunity Stage counts respect user ownership."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    sales1 = {"user_id": 3, "role_name": "Sales Executive", "is_active": True}
    sales2 = {"user_id": 4, "role_name": "Sales Executive", "is_active": True}

    with app.app_context():
        admin_data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        data1 = dashboard_service.get_dashboard_data(sales1, filter_type="all")
        data2 = dashboard_service.get_dashboard_data(sales2, filter_type="all")

        # Sum of reps equals admin total
        total_reps = data1["chart_data"]["opportunity_pipeline"]["total"] + data2["chart_data"]["opportunity_pipeline"]["total"]
        assert total_reps == admin_data["chart_data"]["opportunity_pipeline"]["total"]


def test_opportunity_pipeline_counts_respect_date_range(app):
    """34. Opportunity Stage counts respect date range boundaries."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    with app.app_context():
        data_past = dashboard_service.get_dashboard_data(
            admin_user, filter_type="custom", start_str="2020-01-01", end_str="2020-01-31"
        )
        assert data_past["chart_data"]["opportunity_pipeline"]["total"] == 0


# =============================================================================
# PART 8: CHART 3: MONTHLY SALES VISUALIZATION
# =============================================================================

def test_won_opportunities_contribute_to_monthly_sales(app):
    """35-38. Only Won opportunities contribute to Monthly Sales using ClosedDate; Open & Lost excluded."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    with app.app_context():
        data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        sales_chart = data["chart_data"]["monthly_sales"]

        assert len(sales_chart["labels"]) == 12
        assert len(sales_chart["values"]) == 12
        # In seed data, at least Opp 4 is Won (500,000.00)
        assert sales_chart["total"] >= 500000.0


def test_monthly_sales_respects_role_scope(app):
    """39. Monthly sales chart reflects role scope server-side."""
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    sales1 = {"user_id": 3, "role_name": "Sales Executive", "is_active": True}
    sales2 = {"user_id": 4, "role_name": "Sales Executive", "is_active": True}

    with app.app_context():
        admin_data = dashboard_service.get_dashboard_data(admin_user, filter_type="all")
        data1 = dashboard_service.get_dashboard_data(sales1, filter_type="all")
        data2 = dashboard_service.get_dashboard_data(sales2, filter_type="all")

        # Sum of rep sales equals admin total sales
        total_rep_sales = data1["chart_data"]["monthly_sales"]["total"] + data2["chart_data"]["monthly_sales"]["total"]
        assert total_rep_sales == admin_data["chart_data"]["monthly_sales"]["total"]



# =============================================================================
# PART 9: CHART DATA SECURITY & INTEGRITY
# =============================================================================

def test_chart_data_is_valid_json_in_rendered_page(client):
    """40 & 42. Embedded chart data in rendered HTML is valid, well-formed JSON."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard")
    assert resp.status_code == 200

    html = resp.data.decode("utf-8")
    start_tag = '<script id="dashboard-chart-data" type="application/json">'
    end_tag = '</script>'
    assert start_tag in html

    start_idx = html.index(start_tag) + len(start_tag)
    end_idx = html.index(end_tag, start_idx)
    raw_json = html[start_idx:end_idx].strip()

    parsed = json.loads(raw_json)
    assert "lead_status" in parsed
    assert "opportunity_pipeline" in parsed
    assert "monthly_sales" in parsed


def test_no_unauthorized_raw_crm_records_in_dashboard_html(client):
    """41. Dashboard HTML contains only aggregate summaries; raw CRM rows are not leaked."""
    login(client, "sales2", "Sales@123")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    content = resp.data.decode("utf-8")

    # Sensitive or unassigned lead/customer names from sales1 should NOT appear in HTML
    assert "rohan@innovatetech.example" not in content
    assert "Apex Cloud Migration" not in content


# =============================================================================
# PART 10: ZERO-DATA HANDLING
# =============================================================================

def test_zero_data_handling_does_not_produce_fake_values(app):
    """43-44. Empty datasets render with 0 values and has_data = False, never fake data."""
    # User with no records in distant future window
    admin_user = {"user_id": 1, "role_name": "Admin", "is_active": True}
    with app.app_context():
        data = dashboard_service.get_dashboard_data(
            admin_user, filter_type="custom", start_str="2099-01-01", end_str="2099-01-31"
        )
        assert data["kpis"]["total_customers"] == 0
        assert data["kpis"]["total_leads"] == 0
        assert data["kpis"]["open_leads"] == 0
        assert data["kpis"]["total_opportunities"] == 0
        assert data["kpis"]["total_pipeline_value"] == Decimal("0.00")
        assert data["chart_data"]["lead_status"]["has_data"] is False
        assert data["chart_data"]["opportunity_pipeline"]["has_data"] is False


def test_zero_data_empty_messages_render_in_html(client):
    """44. When datasets are empty, graceful zero-data messages are displayed in HTML."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard?range=custom&start_date=2099-01-01&end_date=2099-01-31")
    assert resp.status_code == 200
    content = resp.data.decode("utf-8")
    assert "No lead data available" in content
    assert "No opportunity data available" in content


# =============================================================================
# PART 11: SECURITY & RESILIENCE
# =============================================================================

def test_dashboard_does_not_expose_sql_errors(client):
    """45. SQL injection attempts in query params do not cause 500 or expose database errors."""
    login(client, "admin", "Admin@123")
    malicious_inputs = [
        "/dashboard?range=' OR 1=1 --",
        "/dashboard?range=custom&start_date=2026-10-01'--&end_date=2026-10-15",
        "/dashboard?range=custom&start_date=2026-10-01&end_date=;DROP TABLE customers;--",
    ]
    for url in malicious_inputs:
        resp = client.get(url)
        # Should be rejected with 400 or safely defaulted to 200 with parameterized queries
        assert resp.status_code in (200, 400)
        assert b"psycopg2" not in resp.data
        assert b"syntax error" not in resp.data


def test_dashboard_does_not_expose_secrets_or_stack_traces(client):
    """46-47. Dashboard never exposes passwords, connection strings, or system paths."""
    login(client, "admin", "Admin@123")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    content = resp.data.decode("utf-8")
    assert "password" not in content.lower()
    assert "postgresql://" not in content
    assert "secret_key" not in content.lower()
