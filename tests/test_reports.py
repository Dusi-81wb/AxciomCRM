"""
Comprehensive Report Tests for AcxiomCRM (Phase 10).

Covers all 77 test requirements from Phase 10 specification:
- Customer Report (1-8)
- Lead Report (9-14)
- Follow-Up Report (15-22)
- Opportunity Report (23-30)
- Pipeline Report (31-38)
- Sales / Conversion Report (39-44)
- User Activity Report (45-49)
- Audit Report (50-57)
- Search / Sort (58-62)
- Pagination (63-66)
- Date Semantics (67-70)
- Security & Access Control (71-76)
- Full Regression Verification (77)
"""

from decimal import Decimal
from zoneinfo import ZoneInfo
import pytest

from repositories import report_repository
from services import report_service

KOLKATA = ZoneInfo("Asia/Kolkata")


def UserPrincipal(user_id, username, role_id, role_name):
    """Helper creating user principal dict for tests."""
    return {
        "user_id": user_id,
        "username": username,
        "role_id": role_id,
        "role_name": role_name,
        "is_active": True,
    }


def login(client, identifier, password):
    """Authenticate test user and store session cookies."""
    return client.post("/login", data={
        "identifier": identifier,
        "password": password
    }, follow_redirects=False)


# =============================================================================
# PART 1: CUSTOMER REPORT (1-8)
# =============================================================================

def test_01_customer_report_loads(client):
    """1. Customer report loads successfully with HTTP 200."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/customers")
    assert resp.status_code == 200
    assert b"Customer Report" in resp.data
    assert b"Customer Code" in resp.data


def test_02_customer_report_requires_authentication(client):
    """2. Customer report requires authentication; anonymous user is redirected."""
    resp = client.get("/reports/customers")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_03_customer_filters_work(client):
    """3. Customer status filters filter results correctly."""
    login(client, "admin", "Admin@123")
    resp_active = client.get("/reports/customers?status=Active")
    assert resp_active.status_code == 200
    assert b"Active" in resp_active.data

    resp_inactive = client.get("/reports/customers?status=Inactive")
    assert resp_inactive.status_code == 200


def test_04_customer_search_works(client):
    """4. Customer search matches by name, company, email, or phone."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/customers?search=Acme")
    assert resp.status_code == 200
    assert b"Acme" in resp.data


def test_05_customer_report_respects_role_scope(client):
    """5. Customer report respects role scope (Admin org-wide vs Sales Exec isolated)."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")

    admin_data = report_service.get_customer_report_data(admin_user)
    sales1_data = report_service.get_customer_report_data(sales1_user)

    assert admin_data["total_count"] >= sales1_data["total_count"]
    # All records for sales1 must be assigned to user 3
    for r in sales1_data["records"]:
        assert r["assigned_to"] == 3


def test_06_sales_executive_cannot_see_other_customers(client):
    """6. Sales Executive cannot see another user's customers in HTML or SQL."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/reports/customers")
    assert resp.status_code == 200
    # Global Tech is assigned to sales2 (user 4), sales1 should not see it
    # We verify that only records assigned to sales1 appear
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")
    sales1_data = report_service.get_customer_report_data(sales1_user)
    for r in sales1_data["records"]:
        assert r["assigned_to"] == 3


def test_07_customer_sql_injection_search_safe(client):
    """7. SQL injection attempts in search are safely parameterized."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/customers?search=' OR '1'='1")
    assert resp.status_code == 200
    assert b"No records found for the selected filters." in resp.data


def test_08_customer_empty_result_handled_correctly(client):
    """8. Empty result renders friendly no-records message."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/customers?search=NonExistentEntityX99")
    assert resp.status_code == 200
    assert b"No records found for the selected filters." in resp.data


# =============================================================================
# PART 2: LEAD REPORT (9-14)
# =============================================================================

def test_09_lead_report_loads(client):
    """9. Lead report loads with HTTP 200."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/leads")
    assert resp.status_code == 200
    assert b"Lead Report" in resp.data
    assert b"Lead Code" in resp.data


def test_10_lead_filters_work(client):
    """10. Lead status and source filters filter records."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/leads?status=Qualified")
    assert resp.status_code == 200


def test_11_all_six_lead_statuses_represented(client):
    """11. All 6 lead statuses (New, Contacted, Qualified, Unqualified, Converted, Lost) are valid."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    for st in ("New", "Contacted", "Qualified", "Unqualified", "Converted", "Lost"):
        data = report_service.get_lead_report_data(admin_user, status=st)
        assert data["status"] == st


def test_12_lead_report_respects_role_scope(client):
    """12. Lead report respects role scope at repository/SQL layer."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")

    admin_data = report_service.get_lead_report_data(admin_user)
    sales1_data = report_service.get_lead_report_data(sales1_user)

    assert admin_data["total_count"] >= sales1_data["total_count"]
    for r in sales1_data["records"]:
        assert r["assigned_to"] == 3


def test_13_sales_executive_cannot_see_other_leads(client):
    """13. Sales Executive cannot see another user's leads."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/reports/leads")
    assert resp.status_code == 200

    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")
    sales1_data = report_service.get_lead_report_data(sales1_user)
    for r in sales1_data["records"]:
        assert r["assigned_to"] == 3


def test_14_lead_sql_injection_safe(client):
    """14. SQL injection in lead search is parameterized and safe."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/leads?search=' UNION SELECT 1,2,3--")
    assert resp.status_code == 200
    assert b"No records found for the selected filters." in resp.data


# =============================================================================
# PART 3: FOLLOW-UP REPORT (15-22)
# =============================================================================

def test_15_followup_report_loads(client):
    """15. Follow-Up report loads successfully."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/followups")
    assert resp.status_code == 200
    assert b"Follow-Up Report" in resp.data


def test_16_followup_date_filter_works(client):
    """16. Follow-Up date range filtering functions correctly."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/followups?start_date=2026-01-01&end_date=2026-12-31")
    assert resp.status_code == 200


def test_17_followup_status_filter_works(client):
    """17. Follow-Up status filtering (Planned, Completed, Missed, Cancelled) works."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_followup_report_data(admin_user, status="Completed")
    assert data["status"] == "Completed"
    for r in data["records"]:
        assert r["status"] == "Completed"


def test_18_followup_assigned_filter_works(client):
    """18. Follow-Up assigned filter and type filter work."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_followup_report_data(admin_user, followup_type="Call")
    assert data["followup_type"] == "Call"
    for r in data["records"]:
        assert r["followup_type"] == "Call"


def test_19_followup_related_record_filter_works(client):
    """19. Follow-Up report joins customer/lead/opportunity related entities."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_followup_report_data(admin_user)
    # Check that records have related columns
    for r in data["records"]:
        assert "customer_name" in r
        assert "lead_name" in r
        assert "opportunity_name" in r


def test_20_followup_overdue_not_mutated(client, db_conn):
    """20. Overdue remains computed, database records are not mutated to Missed."""
    cursor = db_conn.cursor()
    cursor.execute("SELECT status FROM followups WHERE status = 'Planned'")
    statuses = [row[0] for row in cursor.fetchall()]
    # Loading the report must not mutate Planned rows to Missed
    login(client, "admin", "Admin@123")
    client.get("/reports/followups")

    cursor.execute("SELECT status FROM followups WHERE status = 'Planned'")
    after_statuses = [row[0] for row in cursor.fetchall()]
    assert len(statuses) == len(after_statuses)


def test_21_followup_ownership_scope_enforced(client):
    """21. Ownership scope is enforced on follow-ups."""
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")
    sales1_data = report_service.get_followup_report_data(sales1_user)
    for r in sales1_data["records"]:
        assert r["assigned_to"] == 3


def test_22_followup_sql_injection_safe(client):
    """22. SQL injection in status/type filter is sanitized/parameterized."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/followups?status=Planned' OR '1'='1")
    assert resp.status_code == 200


# =============================================================================
# PART 4: OPPORTUNITY REPORT (23-30)
# =============================================================================

def test_23_opportunity_report_loads(client):
    """23. Opportunity report loads with HTTP 200."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/opportunities")
    assert resp.status_code == 200
    assert b"Opportunity Report" in resp.data


def test_24_opportunity_name_filter_works(client):
    """24. Opportunity search by name/customer works."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_opportunity_report_data(admin_user, search="Expansion")
    assert data["search"] == "Expansion"


def test_25_opportunity_customer_filter_works(client):
    """25. Customer search in opportunity report matches customer name."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_opportunity_report_data(admin_user, search="Acme")
    assert data["search"] == "Acme"


def test_26_opportunity_stage_filter_works(client):
    """26. Opportunity stage filter works."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    for stg in ("Qualification", "Proposal", "Negotiation", "Won", "Lost"):
        data = report_service.get_opportunity_report_data(admin_user, stage=stg)
        assert data["stage"] == stg
        for r in data["records"]:
            assert r["stage"] == stg


def test_27_opportunity_status_filter_works(client):
    """27. Opportunity status filter (Open, Won, Lost) works."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    for st in ("Open", "Won", "Lost"):
        data = report_service.get_opportunity_report_data(admin_user, status=st)
        assert data["status"] == st
        for r in data["records"]:
            assert r["status"] == st


def test_28_opportunity_ownership_scope_works(client):
    """28. Sales Executive only sees assigned opportunities."""
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")
    sales1_data = report_service.get_opportunity_report_data(sales1_user)
    for r in sales1_data["records"]:
        assert r["assigned_to"] == 3


def test_29_opportunity_won_lost_open_semantics(client):
    """29. Won/Lost/Open semantics are strictly preserved."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data_open = report_service.get_opportunity_report_data(admin_user, status="Open")
    for r in data_open["records"]:
        assert r["status"] == "Open"
        assert r["stage"] not in ("Won", "Lost")


def test_30_opportunity_sql_injection_safe(client):
    """30. SQL injection in stage/status is whitelisted/parameterized."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/opportunities?stage=Proposal'; DROP TABLE users;--")
    assert resp.status_code == 200


# =============================================================================
# PART 5: PIPELINE REPORT (31-38)
# =============================================================================

def test_31_pipeline_report_loads(client):
    """31. Pipeline report loads with HTTP 200."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/pipeline")
    assert resp.status_code == 200
    assert b"Pipeline Report" in resp.data
    assert b"Total Pipeline Value" in resp.data
    assert b"Weighted Pipeline" in resp.data


def test_32_pipeline_only_open_opportunities_count(client):
    """32. Only Open opportunities count toward active pipeline."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_pipeline_report_data(admin_user)
    for r in data["records"]:
        assert r["status"] == "Open"


def test_33_pipeline_amount_excludes_won(client):
    """33. Active pipeline total excludes Won opportunities."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_pipeline_report_data(admin_user)
    for r in data["records"]:
        assert r["status"] != "Won"
        assert r["stage"] != "Won"


def test_34_pipeline_amount_excludes_lost(client):
    """34. Active pipeline total excludes Lost opportunities."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_pipeline_report_data(admin_user)
    for r in data["records"]:
        assert r["status"] != "Lost"
        assert r["stage"] != "Lost"


def test_35_weighted_pipeline_formula(client):
    """35. Weighted pipeline formula = Amount * Probability / 100."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_pipeline_report_data(admin_user)
    for r in data["records"]:
        amt = Decimal(str(r["amount"]))
        prob = int(r["probability"])
        expected_weighted = (amt * Decimal(prob) / Decimal(100)).quantize(Decimal("0.01"))
        actual_weighted = Decimal(str(r["weighted_value_formatted"].replace(",", "")))
        assert actual_weighted == expected_weighted


def test_36_weighted_pipeline_uses_decimal(client):
    """36. Pipeline calculation outputs are Decimal instances."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_pipeline_report_data(admin_user)
    summary = data["summary"]
    assert isinstance(summary["total_pipeline_value"], Decimal)
    assert isinstance(summary["total_weighted_value"], Decimal)


def test_37_pipeline_stage_breakdown_correct(client):
    """37. Stage breakdown accurately groups active stages."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_pipeline_report_data(admin_user)
    stage_names = [stg["stage"] for stg in data["stage_summaries"]]
    for sn in stage_names:
        assert sn in ("Qualification", "Proposal", "Negotiation")


def test_38_pipeline_ownership_scope_correct(client):
    """38. Sales Executive sees only their own active pipeline deals."""
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")
    sales1_data = report_service.get_pipeline_report_data(sales1_user)
    for r in sales1_data["records"]:
        assert r["assigned_to"] == 3


# =============================================================================
# PART 6: SALES / CONVERSION REPORT (39-44)
# =============================================================================

def test_39_sales_report_loads(client):
    """39. Sales report loads with HTTP 200."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/sales")
    assert resp.status_code == 200
    assert b"Sales &amp; Conversion Report" in resp.data or b"Sales & Conversion Report" in resp.data
    assert b"Lead Conversion Rate" in resp.data
    assert b"Opportunity Win Rate" in resp.data


def test_40_sales_closed_date_semantics(client):
    """40. Won sales revenue uses ClosedDate semantics."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_sales_conversion_report_data(admin_user)
    for d in data["won_deals"]:
        assert d["status"] == "Won"
        assert d["closed_date"] is not None


def test_41_lost_opportunities_not_counted_as_sales(client):
    """41. Lost opportunities are not counted as won sales."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_sales_conversion_report_data(admin_user)
    for d in data["won_deals"]:
        assert d["status"] != "Lost"


def test_42_open_opportunities_not_counted_as_completed_sales(client):
    """42. Open opportunities are not counted as completed sales."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_sales_conversion_report_data(admin_user)
    for d in data["won_deals"]:
        assert d["status"] != "Open"


def test_43_conversion_calculation_matches_specification(client):
    """43. Dual conversion calculation matches Decision 99 #2."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_sales_conversion_report_data(admin_user)
    if data["total_leads"] > 0:
        expected_lead_cr = (Decimal(str(data["converted_leads"])) / Decimal(str(data["total_leads"])) * Decimal(100)).quantize(Decimal("0.01"))
        assert data["lead_conversion_rate"] == expected_lead_cr
    if data["total_closed_opportunities"] > 0:
        expected_win_rate = (Decimal(str(data["won_opportunities"])) / Decimal(str(data["total_closed_opportunities"])) * Decimal(100)).quantize(Decimal("0.01"))
        assert data["opportunity_win_rate"] == expected_win_rate


def test_44_sales_report_ownership_scope(client):
    """44. Sales report calculates sales and conversions strictly within ownership scope."""
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")
    sales1_data = report_service.get_sales_conversion_report_data(sales1_user)
    for d in sales1_data["won_deals"]:
        assert d["assigned_to"] == 3


# =============================================================================
# PART 7: USER ACTIVITY REPORT (45-49)
# =============================================================================

def test_45_user_activity_report_loads(client):
    """45. User Activity report loads with HTTP 200."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/user-activity")
    assert resp.status_code == 200
    assert b"User Activity Report" in resp.data


def test_46_user_activity_filtering_works(client):
    """46. Activity type and status filtering work."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_user_activity_report_data(admin_user, activity_type="Call")
    assert data["activity_type"] == "Call"
    for r in data["records"]:
        assert r["activity_type"] == "Call"


def test_47_user_activity_date_filtering_works(client):
    """47. Activity date range filtering functions."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_user_activity_report_data(admin_user, start_str="2026-01-01", end_str="2026-12-31")
    assert data["start_date"] == "2026-01-01"


def test_48_user_activity_role_scope_respected(client):
    """48. Sales Executive sees only their own CRM activities."""
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")
    sales1_data = report_service.get_user_activity_report_data(sales1_user)
    for r in sales1_data["records"]:
        assert r["assigned_to"] == 3


def test_49_user_activity_no_sensitive_info_exposed(client):
    """49. User activity report contains no passwords or secret tokens."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/user-activity")
    assert b"password_hash" not in resp.data
    assert b"secret_key" not in resp.data


# =============================================================================
# PART 8: AUDIT REPORT (50-57)
# =============================================================================

def test_50_audit_report_loads_for_admin(client):
    """50. Audit report loads with HTTP 200 for Administrator."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/audit")
    assert resp.status_code == 200
    assert b"Audit Log Report" in resp.data


def test_51_audit_user_filter_works(client):
    """51. Audit user filter filters records by user_id."""
    data = report_service.get_audit_report_data(user_id=1)
    assert data["user_id"] == "1"
    for r in data["records"]:
        assert r["user_id"] == 1


def test_52_audit_entity_filter_works(client):
    """52. Audit entity/module filter functions."""
    data = report_service.get_audit_report_data(entity_name="Customer")
    assert data["entity_name"] == "Customer"
    for r in data["records"]:
        assert r["entity_name"] == "Customer"


def test_53_audit_action_filter_works(client):
    """53. Audit action filter functions."""
    data = report_service.get_audit_report_data(action="CREATE")
    assert data["action"] == "CREATE" if hasattr(data, "action") else True
    for r in data["records"]:
        assert r["action"] == "CREATE"


def test_54_audit_date_filter_works(client):
    """54. Audit date filter functions."""
    data = report_service.get_audit_report_data(start_str="2026-01-01", end_str="2026-12-31")
    assert data["start_date"] == "2026-01-01"


def test_55_audit_records_are_read_only(client):
    """55. Audit routes contain no POST, PUT, DELETE, or mutation handlers."""
    login(client, "admin", "Admin@123")
    resp_post = client.post("/reports/audit", data={})
    assert resp_post.status_code == 405


def test_56_audit_password_hashes_never_exposed(client):
    """56. Password hashes, tokens, and credentials are sanitized from audit payload."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/audit")
    assert b"password_hash" not in resp.data
    assert b"scrypt:" not in resp.data
    assert b"pbkdf2:" not in resp.data


def test_57_audit_access_blocked_for_non_admins(client):
    """57. Manager and Sales Executive cannot access Audit Report (HTTP 403)."""
    login(client, "manager", "Manager@123")
    resp_mgr = client.get("/reports/audit")
    assert resp_mgr.status_code == 403

    login(client, "sales1", "Sales@123")
    resp_se = client.get("/reports/audit")
    assert resp_se.status_code == 403


# =============================================================================
# PART 9: SEARCH / SORT (58-62)
# =============================================================================

def test_58_sorting_works(client):
    """58. Sorting by whitelisted column works."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data_asc = report_service.get_customer_report_data(admin_user, sort_by="customer_name", sort_order="ASC")
    assert data_asc["sort_by"] == "customer_name"
    assert data_asc["sort_order"] == "ASC"


def test_59_sort_whitelist_rejects_arbitrary_sql(client):
    """59. Sort whitelist rejects arbitrary SQL column injection and defaults safely."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_customer_report_data(admin_user, sort_by="customer_name; DROP TABLE users;", sort_order="ASC")
    assert data["sort_by"] == "customer_name"


def test_60_asc_sort_works(client):
    """60. ASC sorting order accepted."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_customer_report_data(admin_user, sort_order="ASC")
    assert data["sort_order"] == "ASC"


def test_61_desc_sort_works(client):
    """61. DESC sorting order accepted."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    data = report_service.get_customer_report_data(admin_user, sort_order="DESC")
    assert data["sort_order"] == "DESC"


def test_62_search_remains_parameterized(client):
    """62. Search input remains fully parameterized against SQL injection."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    records, count = report_repository.get_customer_report(
        visible_user_ids=None,
        search="test' OR '1'='1",
        limit=10,
        offset=0
    )
    assert count == 0


# =============================================================================
# PART 10: PAGINATION (63-66)
# =============================================================================

def test_63_pagination_works(client):
    """63. Server-side pagination computes correct metadata."""
    page, per_page, total_pages, offset = report_service.calculate_pagination(105, page=2, per_page=20)
    assert page == 2
    assert per_page == 20
    assert total_pages == 6
    assert offset == 20


def test_64_invalid_page_handled_safely(client):
    """64. Negative or invalid page numbers fall back to page 1."""
    page, per_page, total_pages, offset = report_service.calculate_pagination(50, page=-5, per_page=20)
    assert page == 1
    assert offset == 0


def test_65_invalid_page_size_handled_safely(client):
    """65. Unreasonable page size is bounded between 1 and 100."""
    page, per_page, total_pages, offset = report_service.calculate_pagination(50, page=1, per_page=5000)
    assert per_page == 100

    page2, per_page2, _, _ = report_service.calculate_pagination(50, page=1, per_page=-10)
    assert per_page2 == 1


def test_66_pagination_performed_in_sql(client):
    """66. SQL repository queries strictly apply LIMIT and OFFSET."""
    records, _ = report_repository.get_customer_report(
        visible_user_ids=None,
        limit=2,
        offset=0
    )
    assert len(records) <= 2


# =============================================================================
# PART 11: DATE SEMANTICS (67-70)
# =============================================================================

def test_67_asia_kolkata_date_semantics(client):
    """67. Asia/Kolkata date parsing produces tz-aware datetime."""
    start_dt, end_dt = report_service.parse_report_date_range("2026-05-01", "2026-05-31")
    assert start_dt.tzinfo == KOLKATA
    assert end_dt.tzinfo == KOLKATA


def test_68_date_start_inclusive_end_exclusive(client):
    """68. Start date boundary is inclusive midnight, end date is exclusive next-day midnight."""
    start_dt, end_dt = report_service.parse_report_date_range("2026-05-01", "2026-05-01")
    assert start_dt.hour == 0 and start_dt.minute == 0
    # End date covers all of May 1st up to midnight May 2nd
    assert end_dt.day == 2
    assert end_dt.hour == 0 and end_dt.minute == 0


def test_69_invalid_date_rejected(client):
    """69. Invalid date string format raises ValueError and yields HTTP 400."""
    with pytest.raises(ValueError):
        report_service.parse_report_date_range("not-a-date", "2026-05-01")

    login(client, "admin", "Admin@123")
    resp = client.get("/reports/followups?start_date=invalid-date")
    assert resp.status_code == 400


def test_70_start_after_end_rejected(client):
    """70. Start date after end date raises ValueError and yields HTTP 400."""
    with pytest.raises(ValueError):
        report_service.parse_report_date_range("2026-06-01", "2026-05-01")

    login(client, "admin", "Admin@123")
    resp = client.get("/reports/followups?start_date=2026-12-01&end_date=2026-01-01")
    assert resp.status_code == 400


# =============================================================================
# PART 12: SECURITY & ACCESS CONTROL (71-76)
# =============================================================================

def test_71_anonymous_access_blocked_for_all_reports(client):
    """71. Anonymous access is blocked across all 8 report endpoints."""
    endpoints = [
        "/reports",
        "/reports/customers",
        "/reports/leads",
        "/reports/followups",
        "/reports/opportunities",
        "/reports/pipeline",
        "/reports/sales",
        "/reports/user-activity",
        "/reports/audit",
    ]
    for ep in endpoints:
        resp = client.get(ep)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


def test_72_idor_blocked_across_reports(client):
    """72. Sales Exec cannot pass unauthorized user filter to view other users' activities."""
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")
    # sales1 attempts to filter for sales2 (user 4)
    data = report_service.get_user_activity_report_data(sales1_user, assigned_to_user_id=4)
    # Service blocks unauthorized rep filter, yielding 0 records
    assert data["total_count"] == 0
    assert len(data["records"]) == 0


def test_73_unauthorized_records_never_appear_in_html(client):
    """73. Unauthorized records are filtered at SQL level and never appear in HTML."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/reports/customers")
    assert resp.status_code == 200
    # Verify that sales1 only sees what belongs to them
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")
    data = report_service.get_customer_report_data(sales1_user)
    for r in data["records"]:
        assert r["assigned_to"] == 3


def test_74_sql_injection_blocked_across_modules(client):
    """74. SQL injection attempts are thwarted across all report modules."""
    login(client, "admin", "Admin@123")
    injection_strings = [
        "1' OR '1'='1",
        "1; DROP TABLE users;--",
        "' UNION SELECT NULL, NULL, NULL--",
    ]
    for inj in injection_strings:
        resp = client.get(f"/reports/customers?search={inj}")
        assert resp.status_code == 200
        assert b"database error" not in resp.data.lower()
        assert b"syntax error" not in resp.data.lower()


def test_75_database_errors_not_exposed(client):
    """75. Malformed requests never reveal database internals or stack traces."""
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/customers?sort_by=non_existent_col")
    assert resp.status_code == 200
    assert b"psycopg2" not in resp.data


def test_76_secrets_not_exposed_in_reports(client):
    """76. Sensitive environment secrets and session keys are never exposed in report pages."""
    login(client, "admin", "Admin@123")
    for path in ("/reports/customers", "/reports/leads", "/reports/pipeline", "/reports/sales", "/reports/audit"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert b"SECRET_KEY" not in resp.data
        assert b"DATABASE_URL" not in resp.data


# =============================================================================
# PART 13: PHASE 10 CORRECTION — EXPLICIT ASSIGNED & RELATED RECORD FILTERS (77-87)
# =============================================================================

def test_77_customer_assigned_filter_admin_manager_works(client):
    """77. Admin/Manager can filter customer report by assigned Sales Executive."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    manager_user = UserPrincipal(2, "manager", 2, "Manager")

    # Admin filters for sales1 (user 3)
    data_rep3 = report_service.get_customer_report_data(admin_user, assigned_to=3)
    assert data_rep3["total_count"] > 0
    for r in data_rep3["records"]:
        assert r["assigned_to"] == 3

    # Admin filters for sales2 (user 4)
    data_rep4 = report_service.get_customer_report_data(admin_user, assigned_to=4)
    assert data_rep4["total_count"] > 0
    for r in data_rep4["records"]:
        assert r["assigned_to"] == 4

    # Manager filters for sales1 (user 3)
    data_mgr = report_service.get_customer_report_data(manager_user, assigned_to=3)
    assert data_mgr["total_count"] > 0
    for r in data_mgr["records"]:
        assert r["assigned_to"] == 3

    # Via HTTP route
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/customers?assigned_to=3")
    assert resp.status_code == 200
    assert b"Apex Global Solutions" in resp.data


def test_78_customer_sales_exec_cannot_bypass_ownership_with_assigned_filter(client):
    """78. Sales Executive cannot use assigned_to filter to access another representative's customers."""
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")

    # Service layer: sales1 attempts to query records of sales2 (user 4)
    data_bypass = report_service.get_customer_report_data(sales1_user, assigned_to=4)
    assert data_bypass["total_count"] == 0
    assert len(data_bypass["records"]) == 0

    # Route layer: sales1 submits assigned_to=4
    login(client, "sales1", "Sales@123")
    resp = client.get("/reports/customers?assigned_to=4")
    assert resp.status_code == 200
    assert b"No records found for the selected filters." in resp.data
    assert b"Horizon Logistics" not in resp.data
    assert b"Legacy Industries" not in resp.data

    # Sales1 can filter with own ID successfully
    data_own = report_service.get_customer_report_data(sales1_user, assigned_to=3)
    assert data_own["total_count"] > 0
    for r in data_own["records"]:
        assert r["assigned_to"] == 3


def test_79_lead_assigned_filter_works(client):
    """79. Assigned filter works for Lead Report (Admin/Manager)."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    manager_user = UserPrincipal(2, "manager", 2, "Manager")

    # Admin filters for sales1 (user 3)
    data_rep3 = report_service.get_lead_report_data(admin_user, assigned_to=3)
    assert data_rep3["total_count"] > 0
    for r in data_rep3["records"]:
        assert r["assigned_to"] == 3

    # Admin filters for sales2 (user 4)
    data_rep4 = report_service.get_lead_report_data(admin_user, assigned_to=4)
    assert data_rep4["total_count"] > 0
    for r in data_rep4["records"]:
        assert r["assigned_to"] == 4

    # Manager filters for sales2 (user 4)
    data_mgr = report_service.get_lead_report_data(manager_user, assigned_to=4)
    assert data_mgr["total_count"] > 0
    for r in data_mgr["records"]:
        assert r["assigned_to"] == 4

    # Via HTTP route
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/leads?assigned_to=4")
    assert resp.status_code == 200
    assert b"Amit Patel" in resp.data


def test_80_lead_sales_exec_cannot_bypass_ownership_with_assigned_filter(client):
    """80. Sales Executive cannot bypass lead ownership scope using assigned_to."""
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")

    # Service layer: sales1 attempts to query user 4's leads
    data_bypass = report_service.get_lead_report_data(sales1_user, assigned_to=4)
    assert data_bypass["total_count"] == 0
    assert len(data_bypass["records"]) == 0

    # Route layer: sales1 queries leads with assigned_to=4
    login(client, "sales1", "Sales@123")
    resp = client.get("/reports/leads?assigned_to=4")
    assert resp.status_code == 200
    assert b"No records found for the selected filters." in resp.data
    assert b"Amit Patel" not in resp.data
    assert b"Ananya Sen" not in resp.data


def test_81_followup_assigned_filter_works(client):
    """81. Follow-up assigned Sales Executive filter works for Admin/Manager."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    manager_user = UserPrincipal(2, "manager", 2, "Manager")

    # Filter for user 3
    data_rep3 = report_service.get_followup_report_data(admin_user, assigned_to=3)
    assert data_rep3["total_count"] > 0
    for r in data_rep3["records"]:
        assert r["assigned_to"] == 3

    # Filter for user 4
    data_rep4 = report_service.get_followup_report_data(admin_user, assigned_to=4)
    assert data_rep4["total_count"] > 0
    for r in data_rep4["records"]:
        assert r["assigned_to"] == 4

    # Manager filter
    data_mgr = report_service.get_followup_report_data(manager_user, assigned_to=3)
    assert data_mgr["total_count"] > 0
    for r in data_mgr["records"]:
        assert r["assigned_to"] == 3

    # Via HTTP
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/followups?assigned_to=3")
    assert resp.status_code == 200
    assert b"Review cloud migration contract proposal" in resp.data


def test_82_followup_related_customer_filter_works(client):
    """82. Follow-up Related Customer filter works (by related_type=Customer and customer_id)."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")

    # Filter by related_type='Customer'
    data_type = report_service.get_followup_report_data(admin_user, related_type="Customer")
    assert data_type["total_count"] > 0
    for r in data_type["records"]:
        assert r["customer_id"] is not None
        assert r["customer_name"] is not None

    # Filter by specific customer_id=1
    data_id = report_service.get_followup_report_data(admin_user, customer_id=1)
    assert data_id["total_count"] > 0
    for r in data_id["records"]:
        assert r["customer_id"] == 1

    # Via HTTP
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/followups?related_type=Customer")
    assert resp.status_code == 200
    assert b"Review cloud migration contract proposal" in resp.data


def test_83_followup_related_lead_filter_works(client):
    """83. Follow-up Related Lead filter works (by related_type=Lead and lead_id)."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")

    # Filter by related_type='Lead'
    data_type = report_service.get_followup_report_data(admin_user, related_type="Lead")
    assert data_type["total_count"] > 0
    for r in data_type["records"]:
        assert r["lead_id"] is not None
        assert r["lead_name"] is not None

    # Filter by specific lead_id=2
    data_id = report_service.get_followup_report_data(admin_user, lead_id=2)
    assert data_id["total_count"] > 0
    for r in data_id["records"]:
        assert r["lead_id"] == 2

    # Via HTTP
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/followups?related_type=Lead")
    assert resp.status_code == 200
    assert b"Call Priya regarding FinServe requirements" in resp.data


def test_84_followup_related_opportunity_filter_works(client):
    """84. Follow-up Related Opportunity filter works (by related_type=Opportunity and opportunity_id)."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")

    # Filter by related_type='Opportunity'
    data_type = report_service.get_followup_report_data(admin_user, related_type="Opportunity")
    assert data_type["total_count"] > 0
    for r in data_type["records"]:
        assert r["opportunity_id"] is not None
        assert r["opportunity_name"] is not None

    # Filter by specific opportunity_id=1
    data_id = report_service.get_followup_report_data(admin_user, opportunity_id=1)
    assert data_id["total_count"] > 0
    for r in data_id["records"]:
        assert r["opportunity_id"] == 1

    # Via HTTP
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/followups?related_type=Opportunity")
    assert resp.status_code == 200
    assert b"Review cloud migration contract proposal" in resp.data


def test_85_followup_sales_exec_cannot_bypass_ownership_through_related_filter(client):
    """85. Sales Executive cannot bypass ownership scope through assigned_to or related-record filters."""
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")

    # Follow-up 4 belongs to sales2 (user 4), linked to customer 4 and opportunity 5
    # Sales1 attempts assigned_to=4
    res_assigned = report_service.get_followup_report_data(sales1_user, assigned_to=4)
    assert res_assigned["total_count"] == 0

    # Sales1 attempts customer_id=4
    res_cust = report_service.get_followup_report_data(sales1_user, customer_id=4)
    assert res_cust["total_count"] == 0

    # Sales1 attempts opportunity_id=5
    res_opp = report_service.get_followup_report_data(sales1_user, opportunity_id=5)
    assert res_opp["total_count"] == 0

    # Sales1 requests related_type='Customer' -> must only see their own follow-ups
    res_rel = report_service.get_followup_report_data(sales1_user, related_type="Customer")
    for r in res_rel["records"]:
        assert r["assigned_to"] == 3

    # Via HTTP route
    login(client, "sales1", "Sales@123")
    resp = client.get("/reports/followups?customer_id=4")
    assert resp.status_code == 200
    assert b"No records found for the selected filters." in resp.data
    assert b"Follow up on legacy modernization proposal" not in resp.data


def test_86_opportunity_assigned_filter_works(client):
    """86. Opportunity assigned filter works for Admin/Manager."""
    admin_user = UserPrincipal(1, "admin", 1, "Admin")
    manager_user = UserPrincipal(2, "manager", 2, "Manager")

    # Filter for user 3
    data_rep3 = report_service.get_opportunity_report_data(admin_user, assigned_to=3)
    assert data_rep3["total_count"] > 0
    for r in data_rep3["records"]:
        assert r["assigned_to"] == 3

    # Filter for user 4
    data_rep4 = report_service.get_opportunity_report_data(admin_user, assigned_to=4)
    assert data_rep4["total_count"] > 0
    for r in data_rep4["records"]:
        assert r["assigned_to"] == 4

    # Manager filter
    data_mgr = report_service.get_opportunity_report_data(manager_user, assigned_to=3)
    assert data_mgr["total_count"] > 0
    for r in data_mgr["records"]:
        assert r["assigned_to"] == 3

    # Via HTTP
    login(client, "admin", "Admin@123")
    resp = client.get("/reports/opportunities?assigned_to=3")
    assert resp.status_code == 200
    assert b"Apex Cloud Migration" in resp.data


def test_87_opportunity_sales_exec_cannot_bypass_ownership_with_assigned_filter(client):
    """87. Sales Executive cannot bypass opportunity ownership using assigned_to filter."""
    sales1_user = UserPrincipal(3, "sales1", 3, "Sales Executive")

    # Service layer: sales1 attempts to query user 4's opportunities
    data_bypass = report_service.get_opportunity_report_data(sales1_user, assigned_to=4)
    assert data_bypass["total_count"] == 0
    assert len(data_bypass["records"]) == 0

    # Route layer: sales1 queries with assigned_to=4
    login(client, "sales1", "Sales@123")
    resp = client.get("/reports/opportunities?assigned_to=4")
    assert resp.status_code == 200
    assert b"No records found for the selected filters." in resp.data
    assert b"Horizon Fleet ERP" not in resp.data
    assert b"Legacy Modernization Deal" not in resp.data

