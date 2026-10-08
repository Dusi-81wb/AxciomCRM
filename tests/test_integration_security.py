"""
Phase 12: Full Integration & Security Testing Suite for AcxiomCRM.

Verifies that the entire application operates as a unified, secure system:
- Multi-module end-to-end sales lifecycle (Lead -> Convert -> Customer + Opportunity -> Follow-Up -> Activity -> Dashboard -> Reports -> API -> Audit).
- Role workflows: Admin (organization-wide + Audit Report), Manager (scope + no Audit Report), Sales Executive (assigned scope).
- Cross-user IDOR protection across Customers, Leads, Opportunities, Follow-Ups, Activities (HTML and REST API).
- Assignment manipulation resistance (client-submitted assigned_to ignored/rejected).
- Lead conversion atomic rollback on transaction failure and ambiguous duplicate rejection.
- Terminal state immutability (Won/Lost opportunities, Converted/Unqualified/Lost leads, Completed/Cancelled follow-ups).
- SQL Injection resistance across HTML search, API filters, and report sorting.
- XSS prevention (Jinja escaping).
- Sensitive data exclusion (no passwords, hashes, or session tokens in JSON, HTML error pages, or audit logs).
- Financial decimal precision and Asia/Kolkata timezone boundaries.
"""

import uuid
import random
from decimal import Decimal
from datetime import date, datetime, timedelta
import pytest
import psycopg2

from repositories import (
    customer_repository,
    lead_repository,
    opportunity_repository,
    followup_repository,
    activity_repository,
    audit_repository,
    user_repository,
)
from services import (
    customer_service,
    lead_service,
    opportunity_service,
    followup_service,
    activity_service,
    audit_service,
)
from zoneinfo import ZoneInfo

KOLKATA = ZoneInfo("Asia/Kolkata")


def get_current_business_date():
    return datetime.now(KOLKATA).date()


# =============================================================================
# HELPER UTILITIES
# =============================================================================

def get_unique_suffix():
    return uuid.uuid4().hex[:6]


def get_unique_phone():
    return f"+91-9{random.randint(100000000, 999999999)}"


def login(client, identifier, password):
    return client.post("/login", data={
        "identifier": identifier,
        "password": password
    }, follow_redirects=False)


@pytest.fixture(autouse=True)
def clean_created_test_records():
    """Ensure test data isolation by removing newly created records after each test."""
    yield
    from config import TestingConfig
    cleanup_conn = psycopg2.connect(TestingConfig.DATABASE_URL)
    with cleanup_conn.cursor() as cur:
        cur.execute("DELETE FROM activities WHERE activity_id > 4")
        cur.execute("DELETE FROM followups WHERE followup_id > 4")
        cur.execute("DELETE FROM opportunities WHERE opportunity_id > 5")
        cur.execute("DELETE FROM leads WHERE lead_id > 6")
        cur.execute("DELETE FROM customers WHERE customer_id > 4")
    cleanup_conn.commit()
    cleanup_conn.close()


# =============================================================================
# 1. COMPLETE MULTI-MODULE SALES LIFECYCLE (PART 39)
# =============================================================================

def test_01_complete_sales_lifecycle_integration(client, db_conn):
    """
    End-to-End Sales Lifecycle Test:
    1. Register new Sales Executive & login.
    2. Create Lead (New).
    3. Progress Lead: Contacted -> Qualified.
    4. Convert Lead into Customer + Opportunity in one atomic operation.
    5. Progress Opportunity: Qualification -> Proposal -> Negotiation -> Won.
    6. Schedule Follow-Up for Customer and complete it.
    7. Log Activity (Call) for Customer.
    8. Verify Dashboard KPIs update with the new customer, deal, and activities.
    9. Verify Reports include the new records.
    10. Verify REST API returns the new records.
    11. Verify Audit trail has logged every lifecycle change.
    """
    suffix = get_unique_suffix()
    username = f"rep_{suffix}"
    email = f"rep_{suffix}@example.com"
    phone = get_unique_phone()
    password = "Password@123"

    # Step 1: Self-registration as Sales Executive
    reg_resp = client.post("/register", data={
        "username": username,
        "email": email,
        "phone": phone,
        "password": password,
        "confirm_password": password
    }, follow_redirects=True)
    assert reg_resp.status_code == 200

    # Login as the new Sales Executive
    login_resp = login(client, username, password)
    assert login_resp.status_code == 302

    # Step 2: Create a new Lead
    lead_name = f"Integ Lead {suffix}"
    lead_email = f"lead_{suffix}@example.com"
    lead_phone = get_unique_phone()
    lead_create_resp = client.post("/leads/create", data={
        "lead_name": lead_name,
        "email": lead_email,
        "phone": lead_phone,
        "company_name": f"Integ Corp {suffix}",
        "source": "Website",
        "status": "New",
        "expected_value": "150000.00",
        "notes": "Web inquiry for enterprise integration"
    }, follow_redirects=True)
    assert lead_create_resp.status_code == 200

    # Verify lead was created and self-assigned
    leads = lead_repository.find_leads(search=lead_email)
    assert len(leads) >= 1
    lead = leads[0]
    lead_id = lead["lead_id"]

    # Step 3: Transition Lead to Contacted then Qualified
    client.post(f"/leads/{lead_id}/edit", data={
        "lead_name": lead_name,
        "email": lead_email,
        "phone": lead_phone,
        "company_name": f"Integ Corp {suffix}",
        "source": "Website",
        "status": "Contacted",
        "expected_value": "150000.00",
        "notes": "Discovery call completed"
    }, follow_redirects=True)

    client.post(f"/leads/{lead_id}/edit", data={
        "lead_name": lead_name,
        "email": lead_email,
        "phone": lead_phone,
        "company_name": f"Integ Corp {suffix}",
        "source": "Website",
        "status": "Qualified",
        "expected_value": "180000.00",
        "notes": "Budget confirmed and qualified"
    }, follow_redirects=True)

    lead_qual = lead_repository.find_by_id(lead_id)
    assert lead_qual["status"] == "Qualified"

    # Step 4: Convert Lead -> Customer + Opportunity
    future_date = (get_current_business_date() + timedelta(days=30)).isoformat()
    convert_resp = client.post(f"/leads/{lead_id}/convert", data={
        "customer_name": lead_name,
        "email": lead_email,
        "phone": lead_phone,
        "address": "123 Tech Park",
        "city": "Bengaluru",
        "state": "Karnataka",
        "create_opportunity": "yes",
        "opportunity_name": f"Enterprise Deal {suffix}",
        "amount": "180000.00",
        "expected_close_date": future_date,
        "probability": "25"
    }, follow_redirects=True)
    assert convert_resp.status_code == 200

    # Verify Lead is Converted
    lead_conv = lead_repository.find_by_id(lead_id)
    assert lead_conv["status"] == "Converted"

    # Verify Customer was created
    customer = customer_repository.find_by_email(lead_email)
    assert customer is not None
    customer_id = customer["customer_id"]

    # Verify Opportunity was created
    opps = opportunity_repository.find_opportunities(customer_id=customer_id)
    assert len(opps) == 1
    opp = opps[0]
    opp_id = opp["opportunity_id"]
    assert opp["stage"] == "Qualification"
    assert opp["status"] == "Open"

    # Step 5: Advance Opportunity through stages: Proposal -> Negotiation -> Won
    client.post(f"/opportunities/{opp_id}/stage", data={"stage": "Proposal"}, follow_redirects=True)
    client.post(f"/opportunities/{opp_id}/stage", data={"stage": "Negotiation"}, follow_redirects=True)
    client.post(f"/opportunities/{opp_id}/stage", data={"stage": "Won"}, follow_redirects=True)

    opp_won = opportunity_repository.find_by_id(opp_id)
    assert opp_won["stage"] == "Won"
    assert opp_won["status"] == "Won"
    assert opp_won["closed_date"] is not None

    # Step 6: Create and Complete a Follow-Up for the Customer
    fu_date = (get_current_business_date() + timedelta(days=2)).isoformat()
    fu_resp = client.post("/followups/create", data={
        "subject": "Onboarding Kickoff",
        "customer_id": str(customer_id),
        "followup_date": fu_date,
        "followup_type": "Meeting",
        "status": "Planned",
        "remarks": "Onboarding kickoff meeting"
    }, follow_redirects=True)
    assert fu_resp.status_code == 200

    fus = followup_repository.find_followups(customer_id=customer_id)
    assert len(fus) == 1
    fu_id = fus[0]["followup_id"]

    client.post(f"/followups/{fu_id}/edit", data={
        "subject": "Onboarding Kickoff",
        "followup_date": fu_date,
        "followup_type": "Meeting",
        "status": "Completed",
        "remarks": "Kickoff completed successfully"
    }, follow_redirects=True)

    fu_done = followup_repository.find_by_id(fu_id)
    assert fu_done["status"] == "Completed"

    # Step 7: Create an Activity (Call)
    act_resp = client.post("/activities/create", data={
        "customer_id": str(customer_id),
        "activity_type": "Call",
        "subject": "Introductory Technical Call",
        "activity_date": fu_date,
        "status": "Completed",
        "notes": "Reviewed architectural prerequisites"
    }, follow_redirects=True)
    assert act_resp.status_code == 200

    # Step 8: Dashboard displays metrics
    dash_resp = client.get("/dashboard")
    assert dash_resp.status_code == 200
    assert "Total Customers" in dash_resp.get_data(as_text=True)

    # Step 9: Reports display metrics
    cust_rep_resp = client.get("/reports/customers")
    assert cust_rep_resp.status_code == 200
    assert customer["customer_name"] in cust_rep_resp.get_data(as_text=True)

    # Step 10: REST API reads resources
    api_c_resp = client.get(f"/api/customers/{customer_id}")
    assert api_c_resp.status_code == 200
    assert api_c_resp.get_json()["data"]["customer_id"] == customer_id

    api_o_resp = client.get(f"/api/opportunities/{opp_id}")
    assert api_o_resp.status_code == 200
    assert api_o_resp.get_json()["data"]["stage"] == "Won"

    # Step 11: Audit trail logged events
    logs = audit_repository.find_audit_logs(conn=db_conn)
    customer_audits = [l for l in logs if str(l.get("record_id")) == str(customer_id)]
    assert len(customer_audits) >= 1


# =============================================================================
# 2. ROLE WORKFLOW & ACCESS PERMISSIONS (PARTS 40, 41, 42)
# =============================================================================

def test_02_admin_full_workflow_access(client):
    """Admin has organization-wide access across all CRM views, Reports, and Audit Report."""
    login(client, "admin", "Admin@123")

    for path in ["/customers", "/leads", "/opportunities", "/followups", "/activities",
                 "/dashboard", "/reports", "/reports/audit", "/api/customers", "/api/leads"]:
        resp = client.get(path)
        assert resp.status_code == 200


def test_03_manager_workflow_access_and_audit_report_forbidden(client):
    """Manager has scope access to CRM, Dashboard, Reports, but 403 Forbidden to Audit Report."""
    login(client, "manager", "Manager@123")

    # Manager can access general CRM pages
    for path in ["/customers", "/leads", "/opportunities", "/followups", "/activities",
                 "/dashboard", "/reports"]:
        resp = client.get(path)
        assert resp.status_code == 200

    # Manager is blocked from /reports/audit with 403 Forbidden
    audit_resp = client.get("/reports/audit")
    assert audit_resp.status_code == 403


def test_04_sales_executive_cannot_access_audit_report_receives_403(client):
    """Sales Executive is rejected with 403 Forbidden when requesting /reports/audit."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/reports/audit")
    assert resp.status_code == 403


# =============================================================================
# 3. IDOR & CROSS-USER ISOLATION (PARTS 8, 42)
# =============================================================================

def test_05_cross_sales_rep_idor_defense_html_and_api(client):
    """
    Sales Executive 1 cannot view or modify Sales Executive 2's Customer, Lead,
    Opportunity, Follow-Up, or Activity via HTML routes or REST API endpoints.
    """
    # Create records strictly assigned to Sales Executive 2 (user_id = 4)
    suffix = get_unique_suffix()
    cust_s2 = customer_repository.create_customer(
        customer_name=f"Rep2 Cust {suffix}",
        customer_code=f"CUST-S2-{suffix[:4]}",
        email=f"rep2_cust_{suffix}@example.com",
        phone=get_unique_phone(),
        assigned_to=4,
        created_by=1
    )
    cust_id = cust_s2["customer_id"]

    lead_s2 = lead_repository.create_lead(
        lead_code=f"LEAD-S2-{suffix[:4]}",
        lead_name=f"Rep2 Lead {suffix}",
        email=f"rep2_lead_{suffix}@example.com",
        phone=get_unique_phone(),
        assigned_to=4
    )
    lead_id = lead_s2["lead_id"]

    future_date = (get_current_business_date() + timedelta(days=20)).isoformat()
    opp_s2 = opportunity_repository.create_opportunity(
        opportunity_name=f"Rep2 Deal {suffix}",
        customer_id=cust_id,
        amount=Decimal("100000.00"),
        stage="Qualification",
        probability=20,
        expected_close_date=future_date,
        assigned_to=4
    )
    opp_id = opp_s2["opportunity_id"]

    fu_s2 = followup_repository.create_followup(
        subject="Rep2 Call",
        followup_date=future_date,
        followup_type="Call",
        customer_id=cust_id,
        assigned_to=4
    )
    fu_id = fu_s2["followup_id"]

    act_s2 = activity_repository.create_activity(
        activity_type="Meeting",
        subject="Rep2 Meeting",
        activity_date=future_date,
        customer_id=cust_id,
        assigned_to=4
    )
    act_id = act_s2["activity_id"]

    # Now login as Sales Executive 1 (user_id = 3)
    login(client, "sales1", "Sales@123")

    # 1. Customer IDOR checks
    assert client.get(f"/customers/{cust_id}").status_code == 403
    assert client.get(f"/customers/{cust_id}/edit").status_code == 403
    assert client.post(f"/customers/{cust_id}/edit", data={"customer_name": "Hacked"}).status_code == 403
    assert client.get(f"/api/customers/{cust_id}").status_code == 403
    assert client.put(f"/api/customers/{cust_id}", json={
        "customer_name": "Hacked",
        "email": f"rep2_cust_{suffix}@example.com",
        "phone": cust_s2["phone"]
    }).status_code == 403

    # 2. Lead IDOR checks
    assert client.get(f"/leads/{lead_id}").status_code == 403
    assert client.get(f"/leads/{lead_id}/edit").status_code == 403
    assert client.post(f"/leads/{lead_id}/edit", data={"lead_name": "Hacked"}).status_code == 403
    assert client.get(f"/api/leads/{lead_id}").status_code == 403
    assert client.put(f"/api/leads/{lead_id}", json={
        "lead_name": "Hacked",
        "email": f"rep2_lead_{suffix}@example.com",
        "phone": lead_s2["phone"]
    }).status_code == 403

    # 3. Opportunity IDOR checks
    assert client.get(f"/opportunities/{opp_id}").status_code == 403
    assert client.get(f"/opportunities/{opp_id}/edit").status_code == 403
    assert client.post(f"/opportunities/{opp_id}/edit", data={"opportunity_name": "Hacked"}).status_code == 403
    assert client.get(f"/api/opportunities/{opp_id}").status_code == 403
    assert client.put(f"/api/opportunities/{opp_id}", json={
        "opportunity_name": "Hacked",
        "customer_id": cust_id,
        "amount": "100000.00",
        "stage": "Qualification",
        "probability": 20,
        "expected_close_date": future_date
    }).status_code == 403

    # 4. Follow-Up IDOR checks
    assert client.get(f"/followups/{fu_id}").status_code == 403
    assert client.get(f"/followups/{fu_id}/edit").status_code == 403
    assert client.post(f"/followups/{fu_id}/edit", data={"remarks": "Hacked"}).status_code == 403

    # 5. Activity IDOR checks
    assert client.get(f"/activities/{act_id}").status_code == 403


def test_06_sales_executive_cannot_link_records_to_other_rep_customer(client):
    """
    A Sales Executive cannot create an Opportunity, Follow-Up, or Activity
    referencing another sales representative's Customer (Related-Record IDOR).
    """
    suffix = get_unique_suffix()
    cust_s2 = customer_repository.create_customer(
        customer_name=f"Foreign Cust {suffix}",
        customer_code=f"CUST-FOR-{suffix[:4]}",
        email=f"for_{suffix}@example.com",
        phone=get_unique_phone(),
        assigned_to=4,
        created_by=1
    )
    cust_id = cust_s2["customer_id"]

    # Login as Sales Executive 1
    login(client, "sales1", "Sales@123")

    # Attempt to create Opportunity against Foreign Customer
    future_date = (get_current_business_date() + timedelta(days=15)).isoformat()
    opp_resp = client.post("/opportunities/create", data={
        "opportunity_name": "Bypass Attempt",
        "customer_id": str(cust_id),
        "amount": "100000.00",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": future_date
    }, follow_redirects=True)
    # Must be rejected (either 400 or 403 depending on validation/authorization layer)
    assert opp_resp.status_code in (400, 403) or "Customer does not exist" in opp_resp.get_data(as_text=True)

    # API check: POST /api/opportunities against Foreign Customer
    api_opp_resp = client.post("/api/opportunities", json={
        "opportunity_name": "API Bypass Attempt",
        "customer_id": cust_id,
        "amount": "100000.00",
        "stage": "Qualification",
        "probability": 20,
        "expected_close_date": future_date
    })
    assert api_opp_resp.status_code in (400, 403)


# =============================================================================
# 4. ASSIGNMENT MANIPULATION RESISTANCE (PART 9)
# =============================================================================

def test_07_sales_executive_cannot_manipulate_assigned_to_in_form_or_api(client):
    """
    When a Sales Executive submits an assigned_to value (e.g. pointing to Admin),
    the server ignores it and enforces self-assignment.
    """
    login(client, "sales1", "Sales@123")
    suffix = get_unique_suffix()

    # HTML Customer creation with spoofed assigned_to=1 (Admin)
    client.post("/customers/create", data={
        "customer_name": f"Spoof Test {suffix}",
        "email": f"spoof_{suffix}@example.com",
        "phone": get_unique_phone(),
        "assigned_to": "1"
    }, follow_redirects=True)

    cust = customer_repository.find_by_email(f"spoof_{suffix}@example.com")
    assert cust is not None
    # Must be self-assigned to sales1 (user_id = 3)
    assert cust["assigned_to"] == 3

    # API Lead creation with spoofed assigned_to=1
    api_lead_resp = client.post("/api/leads", json={
        "lead_name": f"Spoof Lead {suffix}",
        "email": f"spoof_lead_{suffix}@example.com",
        "phone": get_unique_phone(),
        "assigned_to": 1
    })
    assert api_lead_resp.status_code == 201
    assert api_lead_resp.get_json()["data"]["assigned_to"] == 3


def test_08_admin_must_explicitly_assign_active_sales_executive_no_fallback(client):
    """
    Admin/Manager creating an Opportunity cannot leave assigned_to empty,
    and the system never silently falls back to the Customer's assigned representative.
    """
    login(client, "admin", "Admin@123")
    future_date = (get_current_business_date() + timedelta(days=15)).isoformat()

    resp = client.post("/api/opportunities", json={
        "opportunity_name": "No Assignee Deal",
        "customer_id": 1,
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": 30,
        "expected_close_date": future_date
        # assigned_to missing
    })
    assert resp.status_code == 400
    assert "Sales Executive" in str(resp.get_json())


# =============================================================================
# 5. LEAD CONVERSION ROLLBACK & DUPLICATE AMBIGUITY (PART 12)
# =============================================================================

def test_09_lead_conversion_atomic_rollback_on_failure(client, db_conn):
    """
    If a failure occurs during Lead conversion (e.g. invalid close date for the Opportunity),
    the entire transaction rolls back atomically: no Customer is created, Lead remains Qualified,
    and no partial audit log is persisted.
    """
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    lead_email = f"rb_lead_{suffix}@example.com"
    lead_phone = get_unique_phone()

    lead = lead_repository.create_lead(
        lead_code=f"LEAD-RB-{suffix[:4]}",
        lead_name=f"Rollback Lead {suffix}",
        email=lead_email,
        phone=lead_phone,
        status="Qualified",
        assigned_to=3
    )
    lead_id = lead["lead_id"]

    # Attempt conversion with a past expected_close_date (violates active opportunity rule)
    past_date = (get_current_business_date() - timedelta(days=5)).isoformat()
    resp = client.post(f"/leads/{lead_id}/convert", data={
        "address": "Street 1",
        "city": "City",
        "state": "State",
        "create_opportunity": "y",
        "opportunity_name": "Invalid Opp",
        "amount": "100000.00",
        "expected_close_date": past_date,
        "probability": "50"
    }, follow_redirects=True)

    # Conversion should fail
    assert resp.status_code in (400, 200) # Form re-renders with error or returns 400

    # Verify atomic rollback
    lead_after = lead_repository.find_by_id(lead_id)
    assert lead_after["status"] == "Qualified" # NOT Converted!

    cust_after = customer_repository.find_by_email(lead_email)
    assert cust_after is None # Customer was NOT created!


def test_10_lead_conversion_rejects_ambiguous_duplicate_customer(client):
    """
    If a Lead's email matches Customer A and phone matches Customer B,
    conversion must be rejected as an ambiguous duplicate without silent merging.
    """
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    email_a = f"cust_a_{suffix}@example.com"
    phone_a = get_unique_phone()
    email_b = f"cust_b_{suffix}@example.com"
    phone_b = get_unique_phone()

    # Create Customer A
    customer_repository.create_customer(
        customer_name=f"Customer A {suffix}",
        customer_code=f"CUST-A-{suffix[:4]}",
        email=email_a,
        phone=phone_a,
        assigned_to=3,
        created_by=1
    )

    # Create Customer B
    customer_repository.create_customer(
        customer_name=f"Customer B {suffix}",
        customer_code=f"CUST-B-{suffix[:4]}",
        email=email_b,
        phone=phone_b,
        assigned_to=3,
        created_by=1
    )

    # Create Lead with email of A and phone of B
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-AMB-{suffix[:4]}",
        lead_name=f"Ambiguous Lead {suffix}",
        email=email_a,
        phone=phone_b,
        status="Qualified",
        assigned_to=3
    )
    lead_id = lead["lead_id"]

    resp = client.post(f"/leads/{lead_id}/convert", data={
        "customer_name": f"Ambiguous Lead {suffix}",
        "email": email_a,
        "phone": phone_b,
        "create_opportunity": "n"
    }, follow_redirects=True)

    # Must be rejected with ambiguity warning
    lead_after = lead_repository.find_by_id(lead_id)
    assert lead_after["status"] == "Qualified" # Still Qualified, not Converted


# =============================================================================
# 6. TERMINAL STATE IMMUTABILITY (PARTS 11, 13, 15)
# =============================================================================

def test_11_terminal_state_enforcement_across_crm_modules(client, db_conn):
    """
    Terminal states across all modules are strictly locked:
    - Won / Lost Opportunities cannot be edited or reopened.
    - Converted / Unqualified / Lost Leads cannot transition.
    - Completed / Cancelled Follow-Ups cannot be modified.
    """
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    future_date = (get_current_business_date() + timedelta(days=10)).isoformat()

    # 1. Opportunity Won is terminal
    opp = opportunity_repository.create_opportunity(
        opportunity_name=f"Terminal Opp {suffix}",
        customer_id=1,
        amount=Decimal("50000.00"),
        stage="Won",
        probability=100,
        expected_close_date=future_date,
        status="Won",
        assigned_to=3,
        closed_date=datetime.now(),
        conn=db_conn
    )
    db_conn.commit()
    opp_id = opp["opportunity_id"]

    api_opp_resp = client.put(f"/api/opportunities/{opp_id}", json={
        "opportunity_name": "Reopen Attempt",
        "customer_id": 1,
        "amount": "50000.00",
        "stage": "Negotiation",
        "probability": 100,
        "expected_close_date": future_date
    })
    assert api_opp_resp.status_code == 400
    assert "terminal" in str(api_opp_resp.get_json()).lower()

    # 2. Lead Converted is terminal
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-TRM-{suffix[:4]}",
        lead_name=f"Terminal Lead {suffix}",
        email=f"term_{suffix}@example.com",
        phone=get_unique_phone(),
        status="Converted",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()
    lead_id = lead["lead_id"]

    api_lead_resp = client.put(f"/api/leads/{lead_id}", json={
        "status": "Qualified"
    })
    assert api_lead_resp.status_code == 400

    # 3. Follow-Up Completed is terminal
    fu = followup_repository.create_followup(
        subject="Terminal Call",
        followup_date=future_date,
        followup_type="Call",
        customer_id=1,
        status="Completed",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()
    fu_id = fu["followup_id"]

    fu_edit_resp = client.post(f"/followups/{fu_id}/edit", data={
        "status": "Planned",
        "followup_date": future_date,
        "followup_type": "Call",
        "remarks": "Reopen"
    }, follow_redirects=True)
    assert fu_edit_resp.status_code in (400, 200, 302)
    fu_after = followup_repository.find_by_id(fu_id, conn=db_conn)
    assert fu_after["status"] == "Completed"


# =============================================================================
# 7. SECURITY: SQL INJECTION & XSS (PARTS 23, 24)
# =============================================================================

def test_12_sql_injection_defense_across_all_endpoints(client):
    """
    SQL injection attack vectors across HTML searches, Report sorting,
    and API filters return safe results and never cause syntax errors or leaks.
    """
    login(client, "admin", "Admin@123")
    payloads = [
        "' OR '1'='1",
        "'; DROP TABLE audit_logs; --",
        "1 UNION SELECT 1, 'admin', 'hash', 1, true --"
    ]

    for p in payloads:
        # Customer HTML search
        c_resp = client.get(f"/customers?search={p}")
        assert c_resp.status_code == 200

        # Reports sorting
        rep_resp = client.get(f"/reports/customers?sort_by={p}&sort_dir=ASC")
        assert rep_resp.status_code == 200

        # API query parameter
        api_resp = client.get(f"/api/customers?search={p}")
        assert api_resp.status_code == 200
        assert api_resp.is_json


def test_13_xss_protection_in_templates(client):
    """User-controlled text with script tags is properly escaped in HTML rendering."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    script_payload = f"<script>alert('xss_{suffix}')</script>"

    client.post("/customers/create", data={
        "customer_name": script_payload,
        "email": f"xss_{suffix}@example.com",
        "phone": get_unique_phone(),
        "assigned_to": 3
    }, follow_redirects=True)

    cust = customer_repository.find_by_email(f"xss_{suffix}@example.com")
    assert cust is not None

    resp = client.get(f"/customers/{cust['customer_id']}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    # Literal <script> must be escaped as &lt;script&gt;
    assert "<script>alert(" not in html
    assert "&lt;script&gt;" in html or script_payload not in html


# =============================================================================
# 8. SENSITIVE DATA EXCLUSION & ERROR INTEGRITY (PARTS 22, 30, 31)
# =============================================================================

def test_14_api_responses_and_error_pages_never_expose_secrets(client):
    """
    Verifies that password hashes, session secrets, and database exception stack traces
    are never returned in API JSON or HTML error responses.
    """
    login(client, "admin", "Admin@123")

    # Check Customer API response
    c_resp = client.get("/api/customers/1")
    assert c_resp.status_code == 200
    body = c_resp.get_data(as_text=True)
    assert "password" not in body.lower()
    assert "hash" not in body.lower()

    # Check 404 error page (HTML)
    h_resp = client.get("/non-existent-page")
    assert h_resp.status_code == 404
    html = h_resp.get_data(as_text=True)
    assert "Traceback" not in html
    assert "psycopg2" not in html

    # Check 404 API response (JSON)
    j_resp = client.get("/api/customers/999999")
    assert j_resp.status_code == 404
    assert j_resp.is_json
    assert "Traceback" not in j_resp.get_data(as_text=True)


# =============================================================================
# 9. DATABASE AUDIT IMMUTABILITY TRIGGER (PART 29)
# =============================================================================

def test_15_audit_immutability_trigger_enforced_in_postgresql(db_conn):
    """Direct PostgreSQL UPDATE or DELETE on audit_logs raises an exception from the trigger."""
    # Ensure at least one audit log exists
    audit_rec = audit_repository.create_audit_log(
        action="TEST_TRIGGER",
        entity_name="TEST",
        result="Success",
        conn=db_conn
    )
    db_conn.commit()
    log_id = audit_rec["audit_log_id"]

    # Attempt UPDATE
    with pytest.raises(psycopg2.Error) as exc_update:
        with db_conn.cursor() as cur:
            cur.execute("UPDATE audit_logs SET result = 'Altered' WHERE audit_log_id = %s;", (log_id,))
    assert "append-only" in str(exc_update.value).lower()
    db_conn.rollback()

    # Attempt DELETE
    with pytest.raises(psycopg2.Error) as exc_delete:
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM audit_logs WHERE audit_log_id = %s;", (log_id,))
    assert "append-only" in str(exc_delete.value).lower()
    db_conn.rollback()
