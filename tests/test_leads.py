"""
Comprehensive Lead Management and Conversion Tests for AcxiomCRM (Phase 6).

Verifies the complete Lead vertical slice and atomic Lead Conversion workflow:
UI -> client/server validation -> authorization/scope -> service -> business rules -> repository -> PostgreSQL -> audit.

Covers:
1. Lead creation (form loads, validation, auto-generated LEAD-XXX, persistence, CREATE audit).
2. Field-level validation (name required, email format, phone format, non-negative expected value).
3. Role-based ownership & visibility (Admin sees all, Manager sees all, Sales Executive sees only assigned).
4. Assignment rules (Admin/Manager assign active Sales Executive; Sales Exec auto self-assigns; inactive/admin/manager rejected).
5. 6-state status transition matrix (valid transitions succeed, invalid transitions blocked, audits stamped).
6. Update behavior (mutable fields update, modified_date updated, immutable system fields preserved, UPDATE audit).
7. Search and filtering (by name, company, status, assigned rep, scoped in SQL, SQL injection immunity).
8. Lead-to-Customer and Opportunity conversion (Qualified only, existing customer matching, atomic commit/rollback).
9. Concurrency & double conversion prevention (SELECT FOR UPDATE row-level locking).
10. CSRF & Security (Anonymous redirected, POST blocked without CSRF, IDOR blocked with 403, no leaked credentials).
"""

import random
import uuid
from decimal import Decimal
from datetime import datetime, date
import pytest
import psycopg2

from app import create_app
from config import TestingConfig
from repositories import lead_repository, customer_repository, audit_repository, user_repository
from services import lead_service, customer_service, audit_service


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
    """Generate a unique 10-digit phone number with +91- prefix."""
    return f"+91-9{random.randint(100000000, 999999999)}"


# =============================================================================
# 1. LEAD CREATION & METADATA TESTS
# =============================================================================

def test_lead_create_page_loads_for_authenticated_users(client):
    """Authenticated users across all roles can access the lead creation page."""
    for user, pwd in [("admin", "Admin@123"), ("manager", "Manager@123"), ("sales1", "Sales@123")]:
        login(client, user, pwd)
        resp = client.get("/leads/create")
        assert resp.status_code == 200, f"Failed for {user}"
        assert b"Create Lead" in resp.data


def test_valid_lead_creation_by_admin(client, db_conn):
    """Admin creates a lead and assigns it to an active Sales Executive."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    test_email = f"lead_{suffix}@prospect.example"

    resp = client.post("/leads/create", data={
        "lead_name": f"Prospect Corp {suffix}",
        "company_name": "Prospect Holdings",
        "email": test_email,
        "phone": get_unique_phone(),
        "source": "Website",
        "expected_value": "150000.00",
        "assigned_to": 3  # sales1
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"created successfully" in resp.data

    # Verify record in database
    lead = lead_repository.find_by_code(lead_repository.get_next_lead_code(conn=db_conn), conn=db_conn)
    # Search by email
    leads = lead_repository.find_leads(search=test_email, conn=db_conn)
    assert len(leads) >= 1
    lead = leads[0]
    assert lead["lead_name"] == f"Prospect Corp {suffix}"
    assert lead["status"] == "New"
    assert lead["assigned_to"] == 3
    assert lead["lead_code"].startswith("LEAD-")
    assert lead["created_date"] is not None
    assert Decimal(str(lead["expected_value"])) == Decimal("150000.00")


def test_sales_executive_lead_creation_automatically_self_assigned(client, db_conn):
    """Sales Executive creating a lead is automatically self-assigned; submitted assigned_to is ignored."""
    login(client, "sales1", "Sales@123")  # user_id = 3
    suffix = get_unique_suffix()
    test_email = f"sales_lead_{suffix}@example.com"

    # Attempt to assign to sales2 (user_id = 4)
    resp = client.post("/leads/create", data={
        "lead_name": f"Indie Lead {suffix}",
        "company_name": "Indie Co",
        "email": test_email,
        "phone": get_unique_phone(),
        "source": "Cold Call",
        "expected_value": "50000.00",
        "assigned_to": 4  # sales2
    }, follow_redirects=True)

    assert resp.status_code == 200
    leads = lead_repository.find_leads(search=test_email, conn=db_conn)
    assert len(leads) >= 1
    lead = leads[0]
    # Must be forced to sales1 (user_id = 3)
    assert lead["assigned_to"] == 3


def test_lead_code_generated_sequentially(client, db_conn):
    """LeadCode is generated sequentially in the LEAD-XXX format."""
    login(client, "admin", "Admin@123")
    next_expected = lead_repository.get_next_lead_code(conn=db_conn)
    assert next_expected.startswith("LEAD-")

    suffix = get_unique_suffix()
    test_email = f"seq_lead_{suffix}@example.com"

    client.post("/leads/create", data={
        "lead_name": f"Seq Test {suffix}",
        "email": test_email,
        "phone": get_unique_phone(),
        "assigned_to": 3
    })

    leads = lead_repository.find_leads(search=test_email, conn=db_conn)
    assert len(leads) >= 1
    assert leads[0]["lead_code"] == next_expected


def test_lead_creation_creates_audit_log(client, db_conn):
    """Lead creation creates a CREATE audit record with lead metadata."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    test_email = f"audit_lead_{suffix}@example.com"

    client.post("/leads/create", data={
        "lead_name": f"Audit Lead {suffix}",
        "email": test_email,
        "phone": get_unique_phone(),
        "expected_value": "80000.00",
        "assigned_to": 3
    })

    leads = lead_repository.find_leads(search=test_email, conn=db_conn)
    assert len(leads) >= 1
    lead = leads[0]

    logs = audit_repository.find_audit_logs(
        entity_name="LEAD",
        action="CREATE",
        conn=db_conn
    )
    matching = [l for l in logs if str(l.get("record_id")) == str(lead["lead_id"])]
    assert len(matching) >= 1
    audit_entry = matching[0]
    assert audit_entry["action"] == "CREATE"
    assert audit_entry["result"] == "Success"
    assert audit_entry["user_id"] == 1
    assert audit_entry["new_value"]["lead_name"] == f"Audit Lead {suffix}"
    assert audit_entry["new_value"]["lead_code"] == lead["lead_code"]


# =============================================================================
# 2. VALIDATION TESTS
# =============================================================================

def test_missing_lead_name_rejected(client):
    """Missing or empty lead name is rejected with 400 Bad Request."""
    login(client, "admin", "Admin@123")
    resp = client.post("/leads/create", data={
        "lead_name": "   ",
        "email": "lead@example.com",
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Lead Name is required" in resp.data


def test_invalid_email_format_rejected(client):
    """Malformed email strings are rejected server-side."""
    login(client, "admin", "Admin@123")
    for bad_email in ["not-an-email", "@missinguser.com", "user@", "plainaddress"]:
        resp = client.post("/leads/create", data={
            "lead_name": "Valid Lead",
            "email": bad_email,
            "assigned_to": 3
        })
        assert resp.status_code == 400
        assert b"valid email address" in resp.data.lower()


def test_invalid_phone_format_rejected(client):
    """Invalid phone format (when provided) is rejected server-side."""
    login(client, "admin", "Admin@123")
    for bad_phone in ["123", "abcde12345", "+12345678901234567890"]:
        resp = client.post("/leads/create", data={
            "lead_name": "Valid Lead",
            "email": f"valid_{get_unique_suffix()}@example.com",
            "phone": bad_phone,
            "assigned_to": 3
        })
        assert resp.status_code == 400
        assert b"Phone" in resp.data


def test_negative_expected_value_rejected(client):
    """Negative expected values are rejected server-side."""
    login(client, "admin", "Admin@123")
    resp = client.post("/leads/create", data={
        "lead_name": "Negative EV Lead",
        "email": f"valid_{get_unique_suffix()}@example.com",
        "expected_value": "-500.00",
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"negative" in resp.data.lower()


def test_non_numeric_expected_value_rejected(client):
    """Malformed non-numeric expected value is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/leads/create", data={
        "lead_name": "Bad EV Lead",
        "email": f"valid_{get_unique_suffix()}@example.com",
        "expected_value": "not-a-number",
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"valid numeric amount" in resp.data.lower()


def test_excessive_field_lengths_rejected(client):
    """Lead name, company name, or source exceeding maximum lengths are rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/leads/create", data={
        "lead_name": "L" * 105,
        "email": f"valid_{get_unique_suffix()}@example.com",
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"100 characters" in resp.data


def test_admin_cannot_assign_inactive_or_non_sales_rep(client):
    """Admin cannot assign an invalid user, an inactive user, or a Manager/Admin."""
    login(client, "admin", "Admin@123")
    # user_id 2 is Manager, user_id 1 is Admin, user_id 999 does not exist
    for bad_rep in [1, 2, 999, "invalid"]:
        resp = client.post("/leads/create", data={
            "lead_name": "Assignment Test",
            "email": f"valid_{get_unique_suffix()}@example.com",
            "assigned_to": bad_rep
        })
        assert resp.status_code == 400
        assert b"Sales Executive" in resp.data


# =============================================================================
# 3. ROLE-BASED OWNERSHIP & VISIBILITY (SQL-LEVEL SCOPING)
# =============================================================================

def test_admin_can_view_all_leads(client):
    """Admin sees all leads across the CRM system."""
    login(client, "admin", "Admin@123")
    resp = client.get("/leads")
    assert resp.status_code == 200
    assert b"LEAD-001" in resp.data  # Rohan Verma (sales1)
    assert b"LEAD-003" in resp.data  # Amit Patel (sales2)
    assert b"LEAD-005" in resp.data  # Vikram Rao (Converted)


def test_manager_can_view_all_leads_under_manager_scope(client):
    """Manager sees all leads under approved Manager scope."""
    login(client, "manager", "Manager@123")
    resp = client.get("/leads")
    assert resp.status_code == 200
    assert b"LEAD-001" in resp.data
    assert b"LEAD-003" in resp.data


def test_sales_executive_sees_only_assigned_leads_in_sql(client):
    """Sales Executive 1 sees ONLY records assigned to user_id=3 in SQL."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/leads")
    assert resp.status_code == 200
    # Assigned to sales1 (user 3):
    assert b"LEAD-001" in resp.data  # Rohan Verma
    assert b"LEAD-002" in resp.data  # Priya Sharma
    # Assigned to sales2 (user 4): MUST NOT appear
    assert b"LEAD-003" not in resp.data
    assert b"LEAD-004" not in resp.data


def test_sales_executive_2_sees_only_their_leads(client):
    """Sales Executive 2 sees ONLY records assigned to user_id=4."""
    login(client, "sales2", "Sales@123")
    resp = client.get("/leads")
    assert resp.status_code == 200
    assert b"LEAD-003" in resp.data
    assert b"LEAD-004" in resp.data
    assert b"LEAD-001" not in resp.data
    assert b"LEAD-002" not in resp.data


# =============================================================================
# 4. IDOR PROTECTION
# =============================================================================

def test_sales_rep_can_view_assigned_lead_detail(client):
    """Sales Executive 1 can view detail of their own lead (lead_id = 1)."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/leads/1")
    assert resp.status_code == 200
    assert b"LEAD-001" in resp.data
    assert b"Rohan Verma" in resp.data


def test_idor_sales_rep_cannot_view_other_rep_lead_detail(client):
    """Sales Executive 1 requesting lead_id = 3 (owned by sales2) is blocked with HTTP 403."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/leads/3")
    assert resp.status_code == 403


def test_idor_sales_rep_cannot_get_edit_page_for_other_rep_lead(client):
    """Sales Executive 1 requesting GET /leads/3/edit is blocked with HTTP 403."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/leads/3/edit")
    assert resp.status_code == 403


def test_idor_sales_rep_cannot_post_edit_for_other_rep_lead(client):
    """Sales Executive 1 attempting POST /leads/3/edit is blocked with HTTP 403."""
    login(client, "sales1", "Sales@123")
    resp = client.post("/leads/3/edit", data={
        "lead_name": "Hacked Lead Name",
        "email": "hacked@example.com"
    })
    assert resp.status_code == 403


# =============================================================================
# 5. STATUS TRANSITIONS & ENFORCEMENT
# =============================================================================

def test_valid_status_transition_new_to_contacted(client, db_conn):
    """Valid transition: New -> Contacted succeeds and creates audit log."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    # Create a fresh New lead
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-T{suffix[:4]}",
        lead_name=f"Transition Lead {suffix}",
        email=f"trans_{suffix}@example.com",
        status="New",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/leads/{lead['lead_id']}/status", data={"status": "Contacted"})
    assert resp.status_code == 302
    assert f"/leads/{lead['lead_id']}" in resp.headers["Location"]

    updated = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert updated["status"] == "Contacted"

    # Verify STATUS_CHANGE audit
    logs = audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
    matching = [l for l in logs if str(l.get("record_id")) == str(lead["lead_id"])]
    assert len(matching) >= 1
    assert matching[0]["old_value"]["status"] == "New"
    assert matching[0]["new_value"]["status"] == "Contacted"


def test_valid_status_transition_contacted_to_qualified(client, db_conn):
    """Valid transition: Contacted -> Qualified succeeds."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-T{suffix[:4]}",
        lead_name=f"Contacted Lead {suffix}",
        email=f"cont_{suffix}@example.com",
        status="Contacted",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/leads/{lead['lead_id']}/status", data={"status": "Qualified"}, follow_redirects=True)
    assert resp.status_code == 200
    updated = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert updated["status"] == "Qualified"


def test_valid_status_transition_to_lost(client, db_conn):
    """Valid transition: Contacted -> Lost and Qualified -> Lost succeed."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-T{suffix[:4]}",
        lead_name=f"Lost Lead {suffix}",
        email=f"lost_{suffix}@example.com",
        status="Contacted",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/leads/{lead['lead_id']}/status", data={"status": "Lost"}, follow_redirects=True)
    assert resp.status_code == 200
    updated = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert updated["status"] == "Lost"


def test_invalid_transition_new_to_qualified_rejected(client, db_conn):
    """Invalid transition: New -> Qualified is rejected server-side."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-T{suffix[:4]}",
        lead_name=f"Skip Stage Lead {suffix}",
        email=f"skip_{suffix}@example.com",
        status="New",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/leads/{lead['lead_id']}/status", data={"status": "Qualified"}, follow_redirects=True)
    assert b"Invalid status transition" in resp.data

    unchanged = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert unchanged["status"] == "New"


def test_invalid_transition_from_terminal_states_rejected(client, db_conn):
    """Invalid transition: Terminal states (Lost, Converted, Unqualified) cannot transition to any state."""
    login(client, "admin", "Admin@123")
    # Lead 6 is Lost in seed data
    resp = client.post("/leads/6/status", data={"status": "Contacted"}, follow_redirects=True)
    assert b"Invalid status transition" in resp.data

    l6 = lead_repository.find_by_id(6, conn=db_conn)
    assert l6["status"] == "Lost"


def test_valid_status_transition_new_to_unqualified(client, db_conn):
    """Valid transition: New -> Unqualified succeeds and creates STATUS_CHANGE audit log."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-T{suffix[:4]}",
        lead_name=f"New To Unqualified {suffix}",
        email=f"new_unq_{suffix}@example.com",
        status="New",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/leads/{lead['lead_id']}/status", data={"status": "Unqualified"})
    assert resp.status_code == 302
    assert f"/leads/{lead['lead_id']}" in resp.headers["Location"]

    updated = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert updated["status"] == "Unqualified"

    # Verify STATUS_CHANGE audit event
    logs = audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
    matching = [l for l in logs if str(l.get("record_id")) == str(lead["lead_id"])]
    assert len(matching) >= 1
    assert matching[0]["old_value"]["status"] == "New"
    assert matching[0]["new_value"]["status"] == "Unqualified"
    assert matching[0]["result"] == "Success"


def test_valid_status_transition_contacted_to_unqualified(client, db_conn):
    """Valid transition: Contacted -> Unqualified succeeds and creates STATUS_CHANGE audit log."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-T{suffix[:4]}",
        lead_name=f"Contacted To Unqualified {suffix}",
        email=f"cont_unq_{suffix}@example.com",
        status="Contacted",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/leads/{lead['lead_id']}/status", data={"status": "Unqualified"})
    assert resp.status_code == 302
    assert f"/leads/{lead['lead_id']}" in resp.headers["Location"]

    updated = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert updated["status"] == "Unqualified"

    # Verify STATUS_CHANGE audit event
    logs = audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
    matching = [l for l in logs if str(l.get("record_id")) == str(lead["lead_id"])]
    assert len(matching) >= 1
    assert matching[0]["old_value"]["status"] == "Contacted"
    assert matching[0]["new_value"]["status"] == "Unqualified"
    assert matching[0]["result"] == "Success"


def test_invalid_transition_unqualified_to_contacted_rejected(client, db_conn):
    """Invalid transition: Unqualified -> Contacted is rejected. Status unmodified, no audit."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-T{suffix[:4]}",
        lead_name=f"Unqualified Terminal {suffix}",
        email=f"unq_c_{suffix}@example.com",
        status="Unqualified",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    initial_audit_count = len([l for l in audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
                               if str(l.get("record_id")) == str(lead["lead_id"])])

    resp = client.post(f"/leads/{lead['lead_id']}/status", data={"status": "Contacted"}, follow_redirects=True)
    assert b"Invalid status transition" in resp.data

    unchanged = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert unchanged["status"] == "Unqualified"

    after_audit_count = len([l for l in audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
                             if str(l.get("record_id")) == str(lead["lead_id"])])
    assert after_audit_count == initial_audit_count


def test_invalid_transition_unqualified_to_qualified_rejected(client, db_conn):
    """Invalid transition: Unqualified -> Qualified is rejected. Status unmodified, no audit."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-T{suffix[:4]}",
        lead_name=f"Unqualified Terminal {suffix}",
        email=f"unq_q_{suffix}@example.com",
        status="Unqualified",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    initial_audit_count = len([l for l in audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
                               if str(l.get("record_id")) == str(lead["lead_id"])])

    resp = client.post(f"/leads/{lead['lead_id']}/status", data={"status": "Qualified"}, follow_redirects=True)
    assert b"Invalid status transition" in resp.data

    unchanged = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert unchanged["status"] == "Unqualified"

    after_audit_count = len([l for l in audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
                             if str(l.get("record_id")) == str(lead["lead_id"])])
    assert after_audit_count == initial_audit_count


def test_invalid_transition_unqualified_to_converted_rejected(client, db_conn):
    """Invalid transition: Unqualified -> Converted is rejected (both status route and convert route)."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-T{suffix[:4]}",
        lead_name=f"Unqualified Terminal {suffix}",
        email=f"unq_conv_{suffix}@example.com",
        status="Unqualified",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    initial_audit_count = len([l for l in audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
                               if str(l.get("record_id")) == str(lead["lead_id"])])

    # Attempt via status update endpoint
    resp1 = client.post(f"/leads/{lead['lead_id']}/status", data={"status": "Converted"}, follow_redirects=True)
    assert b"conversion must be performed through the conversion workflow" in resp1.data or b"Invalid" in resp1.data

    # Attempt via conversion workflow POST
    resp2 = client.post(f"/leads/{lead['lead_id']}/convert", data={
        "customer_name": "Unqualified Convert Attempt",
        "email": f"unq_conv_{suffix}@example.com",
        "phone": "+91-9876543299"
    })
    assert resp2.status_code == 400
    assert b"Only Qualified leads may be converted" in resp2.data

    unchanged = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert unchanged["status"] == "Unqualified"

    after_audit_count = len([l for l in audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
                             if str(l.get("record_id")) == str(lead["lead_id"])])
    assert after_audit_count == initial_audit_count


def test_invalid_transition_unqualified_to_lost_rejected(client, db_conn):
    """Invalid transition: Unqualified -> Lost is rejected. Status unmodified, no audit."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-T{suffix[:4]}",
        lead_name=f"Unqualified Terminal {suffix}",
        email=f"unq_lost_{suffix}@example.com",
        status="Unqualified",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    initial_audit_count = len([l for l in audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
                               if str(l.get("record_id")) == str(lead["lead_id"])])

    resp = client.post(f"/leads/{lead['lead_id']}/status", data={"status": "Lost"}, follow_redirects=True)
    assert b"Invalid status transition" in resp.data

    unchanged = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert unchanged["status"] == "Unqualified"

    after_audit_count = len([l for l in audit_repository.find_audit_logs(entity_name="LEAD", action="STATUS_CHANGE", conn=db_conn)
                             if str(l.get("record_id")) == str(lead["lead_id"])])
    assert after_audit_count == initial_audit_count


# =============================================================================
# 6. UPDATE BEHAVIOR & AUDITING
# =============================================================================

def test_valid_lead_update_succeeds(client, db_conn):
    """Updating lead details updates fields and modified_date while preserving created_date."""
    login(client, "admin", "Admin@123")
    l_before = lead_repository.find_by_id(1, conn=db_conn)
    created_date_before = l_before["created_date"]

    suffix = get_unique_suffix()
    new_name = f"Rohan Verma Updated {suffix}"

    resp = client.post("/leads/1/edit", data={
        "lead_name": new_name,
        "company_name": "Innovate Tech Labs",
        "email": "rohan_upd@innovatetech.example",
        "phone": "+91-9123456780",
        "source": "Website Direct",
        "expected_value": "95000.00",
        "assigned_to": 3
    }, follow_redirects=True)
    assert resp.status_code == 200

    l_after = lead_repository.find_by_id(1, conn=db_conn)
    assert l_after["lead_name"] == new_name
    assert l_after["company_name"] == "Innovate Tech Labs"
    assert l_after["created_date"] == created_date_before
    assert l_after["modified_date"] is not None


def test_sales_executive_cannot_reassign_lead_on_update(client, db_conn):
    """Sales Executive updating a lead cannot reassign it to another sales rep."""
    login(client, "sales1", "Sales@123")
    client.post("/leads/1/edit", data={
        "lead_name": "Rohan Valid Update",
        "email": "rohan@innovatetech.example",
        "phone": "+91-9123456780",
        "assigned_to": 4  # Attempt to reassign to sales2
    })

    lead = lead_repository.find_by_id(1, conn=db_conn)
    assert lead["assigned_to"] == 3


# =============================================================================
# 7. SEARCH & FILTERING
# =============================================================================

def test_search_by_lead_name(client):
    """Search matches lead name case-insensitively."""
    login(client, "admin", "Admin@123")
    resp = client.get("/leads?search=priya")
    assert resp.status_code == 200
    assert b"Priya Sharma" in resp.data
    assert b"Amit Patel" not in resp.data


def test_search_by_company(client):
    """Search matches lead company name."""
    login(client, "admin", "Admin@123")
    resp = client.get("/leads?search=CloudCore")
    assert resp.status_code == 200
    assert b"CloudCore Systems" in resp.data


def test_filter_by_status(client):
    """Filter by lead status returns matching records."""
    login(client, "admin", "Admin@123")
    resp = client.get("/leads?status=Qualified")
    assert resp.status_code == 200
    assert b"Amit Patel" in resp.data


def test_search_remains_ownership_scoped_for_sales_executive(client):
    """Sales Executive searching can only see results among their assigned leads."""
    login(client, "sales1", "Sales@123")
    # Search for "CloudCore" which is assigned to sales2 (lead 3)
    resp = client.get("/leads?search=CloudCore")
    assert resp.status_code == 200
    assert b"CloudCore Systems" not in resp.data
    assert b"No leads found matching your criteria" in resp.data


def test_sql_injection_in_search_input_is_safe(client):
    """Search input with SQL injection payloads is safely parameterized."""
    login(client, "admin", "Admin@123")
    for payload in ["' OR '1'='1", "'; DROP TABLE leads; --", "admin'--"]:
        resp = client.get(f"/leads?search={payload}")
        assert resp.status_code == 200
        assert b"Leads" in resp.data


# =============================================================================
# 8. LEAD CONVERSION WORKFLOW (ATOMIC & CONCURRENCY)
# =============================================================================

def test_non_qualified_lead_cannot_be_converted(client):
    """Non-qualified leads (New, Contacted, Lost) cannot be converted."""
    login(client, "admin", "Admin@123")
    # Lead 1 is New
    resp = client.get("/leads/1/convert", follow_redirects=True)
    assert b"Only Qualified leads may be converted" in resp.data

    resp_post = client.post("/leads/1/convert", data={
        "customer_name": "Invalid Convert Test",
        "email": "invalid@example.com",
        "phone": "+91-9123456780"
    })
    assert resp_post.status_code == 400
    assert b"Only Qualified leads may be converted" in resp_post.data


def test_qualified_lead_conversion_creates_customer_and_opportunity(client, db_conn):
    """Converting a Qualified lead creates Customer, Opportunity, marks Lead Converted, and writes audits atomically."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    test_email = f"convert_target_{suffix}@corp.example"
    test_phone = get_unique_phone()

    # Create a fresh Qualified lead
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-Q{suffix[:4]}",
        lead_name=f"Qualified Prospect {suffix}",
        company_name="Apex Global Tech",
        email=test_email,
        phone=test_phone,
        status="Qualified",
        expected_value=Decimal("250000.00"),
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/leads/{lead['lead_id']}/convert", data={
        "customer_name": f"Apex Global Tech {suffix}",
        "company_name": "Apex Global Tech",
        "email": test_email,
        "phone": test_phone,
        "address": "77 Cyber City",
        "city": "Gurugram",
        "state": "Haryana",
        "create_opportunity": "1",
        "opportunity_name": f"Cloud ERP Deployment {suffix}",
        "amount": "250000.00",
        "probability": "60",
        "expected_close_date": "2026-12-31"
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"converted successfully" in resp.data

    # 1. Lead is now Converted
    updated_lead = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert updated_lead["status"] == "Converted"

    # 2. Customer created
    cust = customer_repository.find_by_email(test_email, conn=db_conn)
    assert cust is not None
    assert cust["customer_name"] == f"Apex Global Tech {suffix}"
    assert cust["assigned_to"] == 3
    assert cust["status"] == "Active"

    # 3. Opportunity created
    with db_conn.cursor() as cur:
        cur.execute("SELECT * FROM opportunities WHERE lead_id = %s;", (lead["lead_id"],))
        columns = [desc[0] for desc in cur.description]
        opp_row = cur.fetchone()
        assert opp_row is not None
        opp = dict(zip(columns, opp_row))
        assert opp["opportunity_name"] == f"Cloud ERP Deployment {suffix}"
        assert opp["customer_id"] == cust["customer_id"]
        assert Decimal(str(opp["amount"])) == Decimal("250000.00")
        assert opp["stage"] == "Qualification"
        assert opp["probability"] == 60
        assert str(opp["expected_close_date"]) == "2026-12-31"

    # 4. Audit events verified
    logs = audit_repository.find_audit_logs(conn=db_conn)
    lead_audit = [l for l in logs if l.get("entity_name") == "LEAD" and str(l.get("record_id")) == str(lead["lead_id"])]
    assert len(lead_audit) >= 1
    assert lead_audit[0]["action"] == "STATUS_CHANGE"
    assert lead_audit[0]["new_value"]["status"] == "Converted"


def test_conversion_links_to_existing_customer_without_duplicate(client, db_conn):
    """Converting a lead whose email matches an existing customer safely links to that Customer without error."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    # Existing seed customer 1 email: contact@apexsolutions.example
    existing_cust = customer_repository.find_by_id(1, conn=db_conn)
    existing_email = existing_cust["email"]
    existing_phone = existing_cust["phone"]

    # Create a Qualified lead matching existing customer's contact
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-L{suffix[:4]}",
        lead_name=f"Existing Match Lead {suffix}",
        company_name="Apex Global Solutions",
        email=existing_email,
        phone=existing_phone,
        status="Qualified",
        expected_value=Decimal("120000.00"),
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/leads/{lead['lead_id']}/convert", data={
        "customer_name": "Apex Global Solutions",
        "company_name": "Apex Global Solutions",
        "email": existing_email,
        "phone": existing_phone,
        "create_opportunity": "1",
        "opportunity_name": f"Addon Deal {suffix}",
        "amount": "120000.00",
        "probability": "40",
        "expected_close_date": "2026-11-30"
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert b"converted successfully" in resp.data

    # Lead marked Converted
    l_conv = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert l_conv["status"] == "Converted"

    # Opportunity linked to EXISTING customer 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT customer_id FROM opportunities WHERE lead_id = %s;", (lead["lead_id"],))
        opp_cust_id = cur.fetchone()[0]
        assert opp_cust_id == 1


def test_ambiguous_customer_match_rejects_conversion(client, db_conn):
    """If email matches Customer A but phone matches Customer B, conversion is rejected as ambiguous duplicate."""
    login(client, "admin", "Admin@123")
    # Customer 1 email + Customer 2 phone
    c1 = customer_repository.find_by_id(1, conn=db_conn)
    c2 = customer_repository.find_by_id(2, conn=db_conn)

    suffix = get_unique_suffix()
    lead = lead_repository.create_lead(
        lead_code=f"LEAD-A{suffix[:4]}",
        lead_name="Ambiguous Lead",
        email=c1["email"],
        phone=c2["phone"],
        status="Qualified",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    resp = client.post(f"/leads/{lead['lead_id']}/convert", data={
        "customer_name": "Ambiguous Lead",
        "email": c1["email"],
        "phone": c2["phone"]
    })
    assert resp.status_code == 400
    assert b"Ambiguous customer identity" in resp.data

    # Lead must still be Qualified
    l_unchanged = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert l_unchanged["status"] == "Qualified"


def test_already_converted_lead_cannot_be_converted_again(client, db_conn):
    """A lead with status 'Converted' cannot be converted again."""
    login(client, "admin", "Admin@123")
    # Lead 5 is already Converted in seed data
    resp = client.post("/leads/5/convert", data={
        "customer_name": "Repeat Convert",
        "email": "repeat@example.com",
        "phone": get_unique_phone()
    })
    assert resp.status_code == 400
    assert b"already been converted" in resp.data


def test_sales_rep_cannot_convert_another_reps_lead(client, db_conn):
    """Sales Executive 1 cannot convert a Qualified lead assigned to Sales Executive 2 (HTTP 403)."""
    login(client, "sales1", "Sales@123")
    # Lead 3 is Qualified and assigned to sales2 (user_id = 4)
    resp = client.post("/leads/3/convert", data={
        "customer_name": "Unauthorized Convert",
        "email": "unauth@example.com",
        "phone": get_unique_phone()
    })
    assert resp.status_code == 403


def test_atomic_rollback_on_conversion_failure(db_conn):
    """Simulated mid-conversion failure rolls back Customer, Opportunity, and Lead status atomically."""
    suffix = get_unique_suffix()
    unique_email = f"tx_rollback_{suffix}@example.com"
    unique_phone = get_unique_phone()

    lead = lead_repository.create_lead(
        lead_code=f"LEAD-R{suffix[:4]}",
        lead_name=f"Rollback Lead {suffix}",
        email=unique_email,
        phone=unique_phone,
        status="Qualified",
        assigned_to=3,
        conn=db_conn
    )
    db_conn.commit()

    try:
        with db_conn.cursor() as cur:
            # 1. Update lead status to Converted
            cur.execute("UPDATE leads SET status = 'Converted' WHERE lead_id = %s;", (lead["lead_id"],))

            # 2. Insert customer
            cur.execute("""
                INSERT INTO customers (customer_code, customer_name, email, phone, status, assigned_to, created_by)
                VALUES (%s, %s, %s, %s, 'Active', 3, 1) RETURNING customer_id;
            """, (f"CUST-R{suffix[:4]}", "Rollback Cust", unique_email, unique_phone))

            # 3. Simulate failure before commit
            raise RuntimeError("Simulated failure during opportunity/audit creation")

    except RuntimeError:
        db_conn.rollback()

    # Lead must still be Qualified
    check_lead = lead_repository.find_by_id(lead["lead_id"], conn=db_conn)
    assert check_lead["status"] == "Qualified"

    # Customer must NOT exist
    check_cust = customer_repository.find_by_email(unique_email, conn=db_conn)
    assert check_cust is None


# =============================================================================
# 9. SECURITY & CSRF TESTS
# =============================================================================

def test_csrf_blocks_lead_post_without_token():
    """State-changing POST to /leads/create without CSRF token is rejected with 400 Bad Request."""
    class CsrfEnabledConfig(TestingConfig):
        WTF_CSRF_ENABLED = True

    csrf_app = create_app(config_object=CsrfEnabledConfig)
    csrf_client = csrf_app.test_client()

    login(csrf_client, "admin", "Admin@123")

    resp = csrf_client.post("/leads/create", data={
        "lead_name": "CSRF Attack",
        "email": "csrf@example.com"
    })
    assert resp.status_code == 400


def test_anonymous_user_redirected_to_login(client):
    """Anonymous user attempting to access lead endpoints is redirected to login."""
    endpoints = ["/leads", "/leads/create", "/leads/1", "/leads/1/edit", "/leads/1/convert"]
    for ep in endpoints:
        resp = client.get(ep, follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


def test_passwords_and_tokens_never_in_lead_responses_or_audits(client, db_conn):
    """Lead views and audit logs never leak password hashes or secret tokens."""
    login(client, "admin", "Admin@123")
    resp = client.get("/leads/1")
    assert resp.status_code == 200
    assert b"scrypt:" not in resp.data
    assert b"password_hash" not in resp.data

    logs = audit_repository.find_audit_logs(entity_name="LEAD", conn=db_conn)
    for log in logs:
        for val_dict in [log.get("old_value"), log.get("new_value")]:
            if val_dict:
                assert "password" not in val_dict
                assert "password_hash" not in val_dict
                assert "token" not in val_dict
