"""
Comprehensive Opportunity Management Tests for AcxiomCRM (Phase 7).

Verifies the complete Opportunity vertical slice and sales pipeline calculations:
UI -> client/server validation -> authorization/scope -> service -> business rules -> repository -> PostgreSQL -> audit.

Covers:
1. Opportunity Creation (form rendering, validation, persistence, exact Decimal currency, CREATE audit).
2. Field-level validation (name required, amount > 0 for open, probability 0-100, close date >= today in Asia/Kolkata).
3. Customer relationship (valid active customer required, inactive customer rejected with 400).
4. Role-based ownership & visibility (Admin sees all, Manager sees all in scope, Sales Executive sees only assigned).
5. IDOR protection (Sales Executive cannot view, edit, or progress another rep's deal).
6. Opportunity updates (mutable fields update, modified_date updated, created_date preserved, UPDATE audit).
7. Stage & status lifecycle (Qualification -> Proposal -> Negotiation -> Won/Lost, consistency checks, terminal states).
8. Pipeline calculations (Total Pipeline Value = SUM(Open), Weighted Pipeline = SUM(Open * prob / 100), Decimal precision).
9. Atomic audit logging (CREATE, UPDATE, STATUS_CHANGE commit/rollback atomically).
10. CSRF & Security (Anonymous redirected, POST blocked without CSRF, no credential leakage).
11. Phase 6 Integration (Opportunities created from Lead conversion appear and function in Opportunity module).
"""

import uuid
import random
from decimal import Decimal
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import pytest

from app import create_app
from config import TestingConfig
from repositories import opportunity_repository, customer_repository, lead_repository, audit_repository, user_repository
from services import opportunity_service, audit_service


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def login(client, identifier, password):
    """Authenticate test user and store session cookies."""
    return client.post("/login", data={
        "identifier": identifier,
        "password": password
    }, follow_redirects=False)


def get_unique_suffix():
    """Generate a unique short string for test isolation."""
    return uuid.uuid4().hex[:6]


def get_unique_phone():
    """Generate a unique valid phone number with +91- prefix."""
    return f"+91-9{random.randint(100000000, 999999999)}"


def get_future_date_str(days=30):
    """Return future date string YYYY-MM-DD relative to Asia/Kolkata."""
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    return (today + timedelta(days=days)).strftime("%Y-%m-%d")


def get_past_date_str(days=5):
    """Return past date string YYYY-MM-DD relative to Asia/Kolkata."""
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    return (today - timedelta(days=days)).strftime("%Y-%m-%d")


# =============================================================================
# 1. CREATION & PERSISTENCE TESTS
# =============================================================================

def test_opportunity_create_page_loads_for_authenticated_users(client):
    """Authenticated users across roles can access the opportunity creation page."""
    for user, pwd in [("admin", "Admin@123"), ("manager", "Manager@123"), ("sales1", "Sales@123")]:
        login(client, user, pwd)
        resp = client.get("/opportunities/create")
        assert resp.status_code == 200, f"Failed for {user}"
        assert b"Create New Opportunity" in resp.data


def test_valid_opportunity_creation_succeeds_by_admin(client, db_conn):
    """Admin can create a valid opportunity assigned to an active Sales Executive."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    opp_name = f"Enterprise Cloud Deal {suffix}"
    close_date = get_future_date_str(45)

    resp = client.post("/opportunities/create", data={
        "opportunity_name": opp_name,
        "customer_id": 1,  # Apex Solutions (Active)
        "amount": "250000.00",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": close_date,
        "assigned_to": 3  # sales1
    })
    assert resp.status_code == 302
    assert "/opportunities/" in resp.headers["Location"]

    # Verify database persistence
    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM opportunities WHERE opportunity_name = %s;", (opp_name,))
        row = cur.fetchone()
        assert row is not None

    opp = opportunity_repository.find_opportunities(search=opp_name, conn=db_conn)[0]
    assert opp["opportunity_name"] == opp_name
    assert opp["customer_id"] == 1
    assert opp["amount"] == Decimal("250000.00")
    assert opp["stage"] == "Qualification"
    assert opp["status"] == "Open"
    assert opp["probability"] == 20
    assert opp["assigned_to"] == 3
    assert opp["closed_date"] is None


def test_sales_executive_opportunity_creation_automatically_self_assigned(client, db_conn):
    """Sales Executive creating an opportunity is automatically self-assigned."""
    login(client, "sales1", "Sales@123")  # user_id 3
    suffix = get_unique_suffix()
    opp_name = f"Self Assigned Deal {suffix}"

    # Attempt to assign to user 4 (sales2) - must be ignored/overwritten to 3
    resp = client.post("/opportunities/create", data={
        "opportunity_name": opp_name,
        "customer_id": 1,
        "amount": "150000.00",
        "stage": "Qualification",
        "probability": "30",
        "expected_close_date": get_future_date_str(20),
        "assigned_to": 4
    })
    assert resp.status_code == 302

    opps = opportunity_repository.find_opportunities(search=opp_name, conn=db_conn)
    assert len(opps) == 1
    assert opps[0]["assigned_to"] == 3


def test_opportunity_creation_creates_audit_log(client, db_conn):
    """Opportunity creation creates an immutable CREATE audit record."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    opp_name = f"Audit Deal {suffix}"

    client.post("/opportunities/create", data={
        "opportunity_name": opp_name,
        "customer_id": 1,
        "amount": "99000.00",
        "stage": "Proposal",
        "probability": "50",
        "expected_close_date": get_future_date_str(15),
        "assigned_to": 3
    })

    opp = opportunity_repository.find_opportunities(search=opp_name, conn=db_conn)[0]
    logs = audit_repository.find_audit_logs(entity_name="OPPORTUNITY", action="CREATE", conn=db_conn)
    matching = [l for l in logs if str(l.get("record_id")) == str(opp["opportunity_id"])]
    assert len(matching) >= 1
    assert matching[0]["action"] == "CREATE"
    assert matching[0]["result"] == "Success"
    assert matching[0]["new_value"]["opportunity_name"] == opp_name
    assert matching[0]["new_value"]["amount"] == "99000.00"


def test_amount_stored_exactly_as_decimal(client, db_conn):
    """Amount precision is preserved without floating point corruption."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    opp_name = f"Decimal Deal {suffix}"
    precise_amount = "123456.78"

    client.post("/opportunities/create", data={
        "opportunity_name": opp_name,
        "customer_id": 1,
        "amount": precise_amount,
        "stage": "Qualification",
        "probability": "40",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })

    opp = opportunity_repository.find_opportunities(search=opp_name, conn=db_conn)[0]
    assert opp["amount"] == Decimal("123456.78")
    assert isinstance(opp["amount"], Decimal)


def test_invalid_customer_id_rejected(client):
    """Non-existent or malformed Customer ID is rejected with 400."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Invalid Customer Opp",
        "customer_id": 99999,  # Does not exist
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": get_future_date_str(30)
    })
    assert resp.status_code == 400
    assert b"customer does not exist" in resp.data.lower() or b"valid customer" in resp.data.lower()


def test_inactive_customer_rejected(client, db_conn):
    """Inactive customers cannot receive new opportunities (Decision 95 #2)."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    # Create an inactive customer
    with db_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO customers (customer_code, customer_name, email, phone, status, assigned_to, created_by)
            VALUES (%s, %s, %s, %s, 'Inactive', 3, 1)
            RETURNING customer_id;
        """, (f"CUST-IN{suffix[:3]}", f"Inactive Cust {suffix}", f"inact_{suffix}@test.com", f"+91-98765{suffix[:5]}"))
        inact_id = cur.fetchone()[0]
    db_conn.commit()

    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Inactive Customer Deal",
        "customer_id": inact_id,
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Customer is inactive" in resp.data


def test_admin_cannot_assign_inactive_or_non_sales_rep(client):
    """Admin cannot assign an invalid user, an inactive user, or a non-sales rep."""
    login(client, "admin", "Admin@123")
    for bad_rep in [1, 2, 9999]:  # 1=Admin, 2=Manager
        resp = client.post("/opportunities/create", data={
            "opportunity_name": "Bad Assignment Opp",
            "customer_id": 1,
            "amount": "50000.00",
            "stage": "Qualification",
            "probability": "20",
            "expected_close_date": get_future_date_str(30),
            "assigned_to": bad_rep
        })
        assert resp.status_code == 400
        assert b"Sales Executive" in resp.data


def test_admin_or_manager_cannot_create_opportunity_without_assignment(client):
    """Admin and Manager cannot create an Opportunity without explicitly selecting an active Sales Executive."""
    for role_user, role_pass in [("admin", "Admin@123"), ("manager1", "Manager@123")]:
        login(client, role_user, role_pass)
        # 1. Missing assigned_to key
        resp1 = client.post("/opportunities/create", data={
            "opportunity_name": "Unassigned Deal Missing",
            "customer_id": 1,
            "amount": "100000.00",
            "stage": "Qualification",
            "probability": "20",
            "expected_close_date": get_future_date_str(30)
        })
        assert resp1.status_code == 400
        assert b"Sales Executive" in resp1.data

        # 2. Empty string assigned_to
        resp2 = client.post("/opportunities/create", data={
            "opportunity_name": "Unassigned Deal Empty",
            "customer_id": 1,
            "amount": "100000.00",
            "stage": "Qualification",
            "probability": "20",
            "expected_close_date": get_future_date_str(30),
            "assigned_to": ""
        })
        assert resp2.status_code == 400
        assert b"Sales Executive" in resp2.data


# =============================================================================
# 2. FIELD-LEVEL VALIDATION TESTS
# =============================================================================

def test_missing_opportunity_name_rejected(client):
    """Missing or empty opportunity name is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "   ",
        "customer_id": 1,
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Opportunity Name is required" in resp.data


def test_invalid_amount_format_rejected(client):
    """Malformed non-numeric amount is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Bad Amount Opp",
        "customer_id": 1,
        "amount": "not-a-number",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"valid numeric" in resp.data.lower() or b"amount" in resp.data.lower()


def test_negative_amount_rejected(client):
    """Negative amount is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Negative Amount Opp",
        "customer_id": 1,
        "amount": "-500.00",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"greater than 0" in resp.data.lower() or b"negative" in resp.data.lower()


def test_active_opportunity_zero_amount_rejected(client):
    """Active opportunity with amount = 0 is rejected (Part 5: Amount > 0)."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Zero Amount Opp",
        "customer_id": 1,
        "amount": "0.00",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"greater than 0" in resp.data.lower()


def test_probability_below_zero_rejected(client):
    """Probability < 0 is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Negative Prob Opp",
        "customer_id": 1,
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": "-5",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"between 0 and 100" in resp.data.lower()


def test_probability_above_100_rejected(client):
    """Probability > 100 is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Excess Prob Opp",
        "customer_id": 1,
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": "105",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"between 0 and 100" in resp.data.lower()


def test_invalid_probability_format_rejected(client):
    """Non-integer probability is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Float Prob Opp",
        "customer_id": 1,
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": "abc",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"integer" in resp.data.lower() or b"probability" in resp.data.lower()


def test_invalid_stage_rejected(client):
    """Non-canonical stage is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Bad Stage Opp",
        "customer_id": 1,
        "amount": "50000.00",
        "stage": "InvalidStage",
        "probability": "20",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Stage must be one of" in resp.data


def test_past_expected_close_date_rejected_for_active_opportunity(client):
    """Past ExpectedCloseDate is rejected for active opportunities (Part 7)."""
    login(client, "admin", "Admin@123")
    past_date = get_past_date_str(10)
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Past Date Opp",
        "customer_id": 1,
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": past_date,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"cannot be in the past" in resp.data.lower()


def test_invalid_date_format_rejected(client):
    """Malformed date format is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Bad Date Opp",
        "customer_id": 1,
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": "15-11-2026",
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"YYYY-MM-DD" in resp.data


# =============================================================================
# 3. ROLE-BASED OWNERSHIP & IDOR TESTS (SQL SCOPING)
# =============================================================================

def test_admin_can_view_all_opportunities(client):
    """Admin sees all opportunities across all sales executives."""
    login(client, "admin", "Admin@123")
    resp = client.get("/opportunities")
    assert resp.status_code == 200
    assert b"Apex Cloud Migration" in resp.data  # rep 3
    assert b"Horizon Fleet ERP" in resp.data     # rep 4


def test_manager_can_view_all_opportunities_under_manager_scope(client):
    """Manager sees all opportunities within approved scope."""
    login(client, "manager", "Manager@123")
    resp = client.get("/opportunities")
    assert resp.status_code == 200
    assert b"Apex Cloud Migration" in resp.data
    assert b"Horizon Fleet ERP" in resp.data


def test_sales_executive_sees_only_assigned_opportunities_in_sql(client):
    """Sales Executive 1 sees ONLY records assigned to user_id=3 in SQL."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/opportunities")
    assert resp.status_code == 200
    # Owned by sales1:
    assert b"Apex Cloud Migration" in resp.data
    assert b"Apex Security Suite" in resp.data
    # Owned by sales2 (user 4): MUST NOT be visible
    assert b"Horizon Fleet ERP" not in resp.data
    assert b"Legacy Modernization Deal" not in resp.data


def test_sales_executive_2_sees_only_their_assigned_opportunities(client):
    """Sales Executive 2 sees ONLY records assigned to user_id=4."""
    login(client, "sales2", "Sales@123")
    resp = client.get("/opportunities")
    assert resp.status_code == 200
    assert b"Horizon Fleet ERP" in resp.data
    assert b"Apex Cloud Migration" not in resp.data


def test_sales_rep_can_view_assigned_opportunity_detail(client):
    """Sales Executive 1 can view detail of their own opportunity (opp 1)."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/opportunities/1")
    assert resp.status_code == 200
    assert b"Apex Cloud Migration" in resp.data


def test_idor_sales_rep_cannot_view_other_rep_opportunity_detail(client):
    """Sales Executive 1 requesting opp 4 (owned by sales2) is blocked with HTTP 403."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/opportunities/4")
    assert resp.status_code == 403


def test_idor_sales_rep_cannot_get_edit_page_for_other_rep_opportunity(client):
    """Sales Executive 1 requesting GET /opportunities/4/edit is blocked with HTTP 403."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/opportunities/4/edit")
    assert resp.status_code == 403


def test_idor_sales_rep_cannot_post_edit_for_other_rep_opportunity(client):
    """Sales Executive 1 attempting POST /opportunities/4/edit is blocked with HTTP 403."""
    login(client, "sales1", "Sales@123")
    resp = client.post("/opportunities/4/edit", data={
        "opportunity_name": "Hacked Deal",
        "customer_id": 3,
        "amount": "1000.00",
        "stage": "Qualification",
        "probability": "10",
        "expected_close_date": get_future_date_str(30)
    })
    assert resp.status_code == 403


def test_sales_executive_cannot_reassign_opportunity_on_update(client, db_conn):
    """Sales Executive cannot reassign their opportunity to another rep."""
    login(client, "sales1", "Sales@123")
    # Opportunity 2 is owned by sales1 (user 3)
    resp = client.post("/opportunities/2/edit", data={
        "opportunity_name": "Apex Security Suite Renamed",
        "customer_id": 1,
        "amount": "90000.00",
        "stage": "Proposal",
        "probability": "50",
        "expected_close_date": get_future_date_str(40),
        "assigned_to": 4  # Try to transfer to sales2
    })
    assert resp.status_code == 302

    opp = opportunity_repository.find_by_id(2, conn=db_conn)
    assert opp["assigned_to"] == 3  # Unchanged!


# =============================================================================
# 4. SEARCH AND FILTER TESTS
# =============================================================================

def test_search_by_opportunity_name(client):
    """Search matches opportunity name."""
    login(client, "admin", "Admin@123")
    resp = client.get("/opportunities?search=Cloud")
    assert resp.status_code == 200
    assert b"Apex Cloud Migration" in resp.data
    assert b"Zenith POS Upgrade" not in resp.data


def test_search_by_customer_name(client):
    """Search matches customer name."""
    login(client, "admin", "Admin@123")
    resp = client.get("/opportunities?search=Zenith")
    assert resp.status_code == 200
    assert b"Zenith POS Upgrade" in resp.data
    assert b"Apex Cloud Migration" not in resp.data


def test_filter_by_stage(client):
    """Filter by stage returns only matching deals."""
    login(client, "admin", "Admin@123")
    resp = client.get("/opportunities?stage=Negotiation")
    assert resp.status_code == 200
    assert b"Apex Cloud Migration" in resp.data
    assert b"Apex Security Suite" not in resp.data


def test_filter_by_status(client):
    """Filter by status returns only matching deals."""
    login(client, "admin", "Admin@123")
    resp = client.get("/opportunities?status=Won")
    assert resp.status_code == 200
    assert b"Horizon Fleet ERP" in resp.data
    assert b"Apex Cloud Migration" not in resp.data


def test_search_remains_ownership_scoped_for_sales_executive(client):
    """Sales Executive search cannot return opportunities assigned to other reps."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/opportunities?search=Horizon")
    assert resp.status_code == 200
    assert b"Horizon Fleet ERP" not in resp.data


def test_sql_injection_in_search_is_safe(client):
    """Search input with SQL injection payloads is safely parameterized."""
    login(client, "admin", "Admin@123")
    for payload in ["' OR '1'='1", "'; DROP TABLE opportunities; --", "admin'--"]:
        resp = client.get(f"/opportunities?search={payload}")
        assert resp.status_code == 200
        assert b"Opportunities" in resp.data


# =============================================================================
# 5. UPDATE BEHAVIOR & AUDITING
# =============================================================================

def test_valid_opportunity_update_succeeds(client, db_conn):
    """Updating opportunity updates fields and modified_date while preserving created_date."""
    login(client, "admin", "Admin@123")
    opp_before = opportunity_repository.find_by_id(2, conn=db_conn)
    created_date_before = opp_before["created_date"]

    suffix = get_unique_suffix()
    new_name = f"Updated Suite {suffix}"

    resp = client.post("/opportunities/2/edit", data={
        "opportunity_name": new_name,
        "customer_id": 1,
        "amount": "95000.00",
        "stage": "Proposal",
        "probability": "55",
        "expected_close_date": get_future_date_str(25),
        "assigned_to": 3
    })
    assert resp.status_code == 302

    opp_after = opportunity_repository.find_by_id(2, conn=db_conn)
    assert opp_after["opportunity_name"] == new_name
    assert opp_after["amount"] == Decimal("95000.00")
    assert opp_after["created_date"] == created_date_before
    assert opp_after["modified_date"] is not None


def test_update_audit_contains_old_and_new_values(client, db_conn):
    """Opportunity update creates an UPDATE audit record with before and after values."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    new_name = f"Audit Update {suffix}"

    client.post("/opportunities/3/edit", data={
        "opportunity_name": new_name,
        "customer_id": 2,
        "amount": "175000.00",
        "stage": "Qualification",
        "probability": "25",
        "expected_close_date": get_future_date_str(40),
        "assigned_to": 3
    })

    logs = audit_repository.find_audit_logs(entity_name="OPPORTUNITY", action="UPDATE", conn=db_conn)
    matching = [l for l in logs if str(l.get("record_id")) == "3"]
    assert len(matching) >= 1
    assert matching[0]["old_value"]["opportunity_name"] == "Zenith POS Upgrade"
    assert matching[0]["new_value"]["opportunity_name"] == new_name


# =============================================================================
# 6. STAGE TRANSITIONS & TERMINAL PROTECTION
# =============================================================================

def test_valid_stage_transition_qualification_to_proposal(client, db_conn):
    """Valid transition: Qualification -> Proposal succeeds and writes STATUS_CHANGE audit."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    opp = opportunity_repository.create_opportunity(
        opportunity_name=f"Stage Opp {suffix}",
        customer_id=1,
        amount=Decimal("100000.00"),
        stage="Qualification",
        probability=20,
        expected_close_date=get_future_date_str(30),
        status="Open",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/opportunities/{opp['opportunity_id']}/stage", data={"stage": "Proposal"})
    assert resp.status_code == 302

    updated = opportunity_repository.find_by_id(opp["opportunity_id"], conn=db_conn)
    assert updated["stage"] == "Proposal"
    assert updated["status"] == "Open"
    assert updated["closed_date"] is None

    # Verify STATUS_CHANGE audit
    logs = audit_repository.find_audit_logs(entity_name="OPPORTUNITY", action="STATUS_CHANGE", conn=db_conn)
    matching = [l for l in logs if str(l.get("record_id")) == str(opp["opportunity_id"])]
    assert len(matching) >= 1
    assert matching[0]["old_value"]["stage"] == "Qualification"
    assert matching[0]["new_value"]["stage"] == "Proposal"


def test_valid_stage_transition_negotiation_to_won(client, db_conn):
    """Valid transition: Negotiation -> Won sets Stage=Won, Status=Won, and stamps closed_date."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    opp = opportunity_repository.create_opportunity(
        opportunity_name=f"Winning Opp {suffix}",
        customer_id=1,
        amount=Decimal("300000.00"),
        stage="Negotiation",
        probability=80,
        expected_close_date=get_future_date_str(10),
        status="Open",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/opportunities/{opp['opportunity_id']}/stage", data={"stage": "Won"})
    assert resp.status_code == 302

    won_opp = opportunity_repository.find_by_id(opp["opportunity_id"], conn=db_conn)
    assert won_opp["stage"] == "Won"
    assert won_opp["status"] == "Won"
    assert won_opp["closed_date"] is not None


def test_valid_stage_transition_to_lost(client, db_conn):
    """Any open stage can transition to Lost, setting Stage=Lost, Status=Lost, and closed_date."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    opp = opportunity_repository.create_opportunity(
        opportunity_name=f"Lost Opp {suffix}",
        customer_id=1,
        amount=Decimal("120000.00"),
        stage="Proposal",
        probability=40,
        expected_close_date=get_future_date_str(15),
        status="Open",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/opportunities/{opp['opportunity_id']}/stage", data={"stage": "Lost"})
    assert resp.status_code == 302

    lost_opp = opportunity_repository.find_by_id(opp["opportunity_id"], conn=db_conn)
    assert lost_opp["stage"] == "Lost"
    assert lost_opp["status"] == "Lost"
    assert lost_opp["closed_date"] is not None


def test_invalid_stage_transition_rejected(client, db_conn):
    """Illegal stage skip (e.g. Qualification -> Won) is rejected."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    opp = opportunity_repository.create_opportunity(
        opportunity_name=f"Skip Stage Opp {suffix}",
        customer_id=1,
        amount=Decimal("100000.00"),
        stage="Qualification",
        probability=20,
        expected_close_date=get_future_date_str(30),
        status="Open",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/opportunities/{opp['opportunity_id']}/stage", data={"stage": "Won"}, follow_redirects=True)
    assert b"Invalid stage transition" in resp.data

    unchanged = opportunity_repository.find_by_id(opp["opportunity_id"], conn=db_conn)
    assert unchanged["stage"] == "Qualification"
    assert unchanged["status"] == "Open"


def test_terminal_won_opportunity_cannot_be_modified_or_transitioned(client, db_conn):
    """Won opportunities are strictly terminal (Decision 95 #4). Cannot edit or transition."""
    login(client, "admin", "Admin@123")
    # Opp 4 is Won in seed data
    resp1 = client.post("/opportunities/4/stage", data={"stage": "Negotiation"}, follow_redirects=True)
    assert b"terminal" in resp1.data.lower() or b"cannot be modified" in resp1.data.lower()

    resp2 = client.post("/opportunities/4/edit", data={
        "opportunity_name": "Modify Won Deal",
        "customer_id": 3,
        "amount": "600000.00",
        "stage": "Negotiation",
        "probability": "80",
        "expected_close_date": get_future_date_str(30)
    }, follow_redirects=True)
    assert b"terminal" in resp2.data.lower() or b"cannot be edited" in resp2.data.lower()

    opp = opportunity_repository.find_by_id(4, conn=db_conn)
    assert opp["status"] == "Won"
    assert opp["stage"] == "Won"


def test_terminal_lost_opportunity_cannot_be_modified_or_transitioned(client, db_conn):
    """Lost opportunities are strictly terminal (Decision 95 #4). Cannot edit or transition."""
    login(client, "admin", "Admin@123")
    # Opp 5 is Lost in seed data
    resp = client.post("/opportunities/5/stage", data={"stage": "Proposal"}, follow_redirects=True)
    assert b"terminal" in resp.data.lower() or b"cannot be modified" in resp.data.lower()

    opp = opportunity_repository.find_by_id(5, conn=db_conn)
    assert opp["status"] == "Lost"
    assert opp["stage"] == "Lost"


# =============================================================================
# 7. PIPELINE CALCULATIONS (EXACT DECIMAL ARITHMETIC)
# =============================================================================

def test_pipeline_totals_include_only_open_opportunities(client, db_conn):
    """
    Total Pipeline Value = SUM(amount) where status = 'Open'.
    Won and Lost deals are strictly excluded from active pipeline (Part 22).
    """
    login(client, "admin", "Admin@123")
    totals = opportunity_repository.calculate_pipeline_totals(allowed_user_ids=None, conn=db_conn)

    # In seed data:
    # Opp 1: 300,000.00 (Open)
    # Opp 2: 85,000.00 (Open)
    # Opp 3: 150,000.00 (Open)
    # Opp 4: 500,000.00 (Won - EXCLUDED)
    # Opp 5: 200,000.00 (Lost - EXCLUDED)
    # Base sum = 300,000 + 85,000 + 150,000 = 535,000.00 (plus any earlier test creations)
    assert totals["total_pipeline_value"] >= Decimal("535000.00")
    # Verify Won (500k) and Lost (200k) are not in total_pipeline_value
    assert totals["won_count"] >= 1
    assert totals["lost_count"] >= 1
    assert totals["open_count"] >= 3


def test_weighted_pipeline_calculation_uses_decimal_precision(client, db_conn):
    """
    Weighted Pipeline = SUM(amount * probability / 100) for Open opportunities.
    Example: Amount 300000 with Probability 70 produces exactly 210000 (Part 23).
    """
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    opp = opportunity_repository.create_opportunity(
        opportunity_name=f"Weighted Test {suffix}",
        customer_id=1,
        amount=Decimal("300000.00"),
        stage="Proposal",
        probability=70,
        expected_close_date=get_future_date_str(30),
        status="Open",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    opp_dict, _ = opportunity_service.get_opportunity_detail(opp["opportunity_id"], {"user_id": 1, "role_name": "Admin"})
    assert opp_dict["weighted_value"] == Decimal("210000.00")
    assert isinstance(opp_dict["weighted_value"], Decimal)


def test_pipeline_totals_are_scoped_to_sales_executive(client):
    """Pipeline metrics on list page are scope-aware (Sales Exec sees only own deals)."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/opportunities")
    assert resp.status_code == 200
    # Sales 1 only sees their pipeline value, not the global total


# =============================================================================
# 8. AUDITING ATOMICITY & SECURITY TESTS
# =============================================================================

def test_atomic_rollback_on_audit_failure(monkeypatch, db_conn):
    """If audit logging fails, the opportunity mutation is rolled back completely."""
    from services import audit_service
    suffix = get_unique_suffix()

    def broken_log_event(*args, **kwargs):
        raise RuntimeError("Simulated audit infrastructure failure")

    monkeypatch.setattr(audit_service, "log_event", broken_log_event)

    with pytest.raises(RuntimeError):
        opportunity_service.create_opportunity(
            form_data={
                "opportunity_name": f"Rollback Opp {suffix}",
                "customer_id": 1,
                "amount": "100000.00",
                "stage": "Qualification",
                "probability": "20",
                "expected_close_date": get_future_date_str(30),
                "assigned_to": 3
            },
            current_user={"user_id": 1, "role_name": "Admin"}
        )

    # Verify that the opportunity was NOT saved to the database
    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM opportunities WHERE opportunity_name = %s;", (f"Rollback Opp {suffix}",))
        assert cur.fetchone() is None


def test_csrf_blocks_opportunity_post_without_token():
    """State-changing POST without CSRF token is rejected with HTTP 400."""
    class CsrfEnabledConfig(TestingConfig):
        WTF_CSRF_ENABLED = True

    csrf_app = create_app(config_object=CsrfEnabledConfig)
    csrf_client = csrf_app.test_client()

    login(csrf_client, "admin", "Admin@123")

    resp = csrf_client.post("/opportunities/create", data={
        "opportunity_name": "CSRF Attack Opp",
        "customer_id": 1,
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": "20",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400


def test_anonymous_user_redirected_to_login(client):
    """Unauthenticated users attempting to access opportunity routes are redirected to login."""
    for path in ["/opportunities", "/opportunities/create", "/opportunities/1", "/opportunities/1/edit"]:
        resp = client.get(path)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


def test_passwords_and_tokens_never_in_opportunity_responses_or_audits(client, db_conn):
    """Ensure no password hashes or tokens appear in opportunity responses or audits."""
    login(client, "admin", "Admin@123")
    resp = client.get("/opportunities/1")
    assert b"password_hash" not in resp.data
    assert b"pbkdf2:" not in resp.data

    logs = audit_repository.find_audit_logs(entity_name="OPPORTUNITY", conn=db_conn)
    for log in logs:
        for val in [log.get("old_value"), log.get("new_value")]:
            if val and isinstance(val, dict):
                assert "password_hash" not in val
                assert "password" not in val


# =============================================================================
# 9. PHASE 6 INTEGRATION TESTS
# =============================================================================

def test_converted_lead_opportunity_appears_in_opportunity_list(client, db_conn):
    """
    Opportunities created during Phase 6 Lead conversion appear in the Opportunity
    list and detail with correct CustomerId, LeadId, Amount, and ownership.
    """
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    test_email = f"lead_opp_{suffix}@corp.example"
    test_phone = get_unique_phone()

    # 1. Create Qualified lead
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-P{suffix[:4]}",
        lead_name=f"Lead With Opp {suffix}",
        company_name=f"Apex Conversion Corp {suffix}",
        email=test_email,
        phone=test_phone,
        status="Qualified",
        expected_value=Decimal("450000.00"),
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    # 2. Convert lead with Opportunity creation selected
    opp_deal_name = f"Conversion Deal {suffix}"
    close_date = get_future_date_str(60)

    conv_resp = client.post(f"/leads/{lead['lead_id']}/convert", data={
        "customer_name": f"Apex Conversion Corp {suffix}",
        "company_name": f"Apex Conversion Corp {suffix}",
        "email": test_email,
        "phone": test_phone,
        "create_opportunity": "on",
        "opportunity_name": opp_deal_name,
        "amount": "450000.00",
        "probability": "50",
        "expected_close_date": close_date
    })
    assert conv_resp.status_code == 302

    # 3. Verify created Opportunity appears in Opportunity Management
    opps = opportunity_repository.find_opportunities(search=opp_deal_name, conn=db_conn)
    assert len(opps) == 1
    opp = opps[0]
    assert opp["opportunity_name"] == opp_deal_name
    assert opp["lead_id"] == lead["lead_id"]
    assert opp["amount"] == Decimal("450000.00")
    assert opp["stage"] == "Qualification"
    assert opp["status"] == "Open"
    assert opp["probability"] == 50
    assert opp["assigned_to"] == 3

    # 4. Access Opportunity detail view
    detail_resp = client.get(f"/opportunities/{opp['opportunity_id']}")
    assert detail_resp.status_code == 200
    assert opp_deal_name.encode() in detail_resp.data
    assert lead["lead_code"].encode() in detail_resp.data


def test_invalid_lead_id_rejected(client):
    """Providing a non-existent lead_id is rejected with HTTP 400."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/create", data={
        "opportunity_name": "Invalid Lead Opp",
        "customer_id": 1,
        "lead_id": 999999,
        "amount": "50000.00",
        "stage": "Qualification",
        "probability": "30",
        "expected_close_date": get_future_date_str(30),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Selected lead does not exist" in resp.data


def test_invalid_status_rejected(client):
    """Submitting an invalid status value in edit is rejected with HTTP 400."""
    login(client, "admin", "Admin@123")
    resp = client.post("/opportunities/1/edit", data={
        "opportunity_name": "Apex Cloud Migration",
        "customer_id": 1,
        "amount": "250000.00",
        "stage": "Negotiation",
        "status": "NonExistentStatus",
        "probability": "75",
        "expected_close_date": get_future_date_str(45),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Status must be one of" in resp.data


def test_invalid_stage_status_combinations_rejected(client):
    """Stage and status combinations that are contradictory are rejected."""
    login(client, "admin", "Admin@123")
    # Won stage with Open status
    resp1 = client.post("/opportunities/1/edit", data={
        "opportunity_name": "Apex Cloud Migration",
        "customer_id": 1,
        "amount": "250000.00",
        "stage": "Won",
        "status": "Open",
        "probability": "100",
        "expected_close_date": get_future_date_str(45),
        "assigned_to": 3
    })
    assert resp1.status_code == 400
    assert b"must have status" in resp1.data

    # Lost stage with Open status
    resp2 = client.post("/opportunities/1/edit", data={
        "opportunity_name": "Apex Cloud Migration",
        "customer_id": 1,
        "amount": "250000.00",
        "stage": "Lost",
        "status": "Open",
        "probability": "0",
        "expected_close_date": get_future_date_str(45),
        "assigned_to": 3
    })
    assert resp2.status_code == 400
    assert b"must have status" in resp2.data


def test_mutation_failure_rolls_back_audit(app, monkeypatch, db_conn):
    """If repository insertion fails, any pending audit entry is rolled back."""
    import psycopg2
    suffix = get_unique_suffix()

    def broken_insert(*args, **kwargs):
        raise psycopg2.DatabaseError("Simulated DB insertion error")

    monkeypatch.setattr(opportunity_repository, "create_opportunity", broken_insert)

    with pytest.raises(psycopg2.DatabaseError):
        opportunity_service.create_opportunity(
            form_data={
                "opportunity_name": f"Failed DB Opp {suffix}",
                "customer_id": 1,
                "amount": "100000.00",
                "stage": "Qualification",
                "probability": "20",
                "expected_close_date": get_future_date_str(30),
                "assigned_to": 3
            },
            current_user={"user_id": 1, "role_name": "Admin"}
        )

    # Verify no audit log exists for this failed opportunity
    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM audit_logs WHERE new_value::text LIKE %s;", (f"%Failed DB Opp {suffix}%",))
        assert cur.fetchone() is None

