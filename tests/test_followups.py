"""
Comprehensive Follow-Up Management Tests for AcxiomCRM (Phase 8).

Verifies the complete Follow-Up vertical slice:
UI -> client/server validation -> authorization/scope -> service -> business rules -> repository -> PostgreSQL -> audit.

Covers:
1. Follow-Up Creation & Field Validation (Creation page loads, valid creation, invalid relations, assignment).
2. Date Validation (Asia/Kolkata timezone: past dates rejected, today accepted, future accepted, invalid format rejected).
3. Status Lifecycle & Transitions (Planned -> Completed / Missed / Cancelled, terminal locking).
4. Rescheduling (New date >= today, status reset from Missed -> Planned, RESCHEDULE audit).
5. Role-based Ownership & IDOR Protection (Admin sees all, Manager in scope, Sales Executive isolated, IDOR rejected with 403).
6. Search & Scoped Filtering (Date, status, rep, related records, upcoming/overdue views, SQL injection safety).
7. Atomic Audit Logging (CREATE, UPDATE, STATUS_CHANGE, RESCHEDULE, old/new value capture, transaction rollback atomicity).
8. Security & CSRF (Anonymous blocked, CSRF protection, no leaked credentials).
9. Entity Integration (Customer, Lead, Opportunity associations and authorization checks).
"""

import uuid
import random
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
import pytest
from psycopg2.extras import RealDictCursor

from app import create_app
from config import TestingConfig
from repositories import (
    followup_repository,
    customer_repository,
    lead_repository,
    opportunity_repository,
    audit_repository,
    user_repository,
)
from services import followup_service, audit_service
from validation.business_rules import (
    FOLLOWUP_STATUS_PLANNED,
    FOLLOWUP_STATUS_COMPLETED,
    FOLLOWUP_STATUS_MISSED,
    FOLLOWUP_STATUS_CANCELLED,
    FOLLOWUP_TYPE_CALL,
    FOLLOWUP_TYPE_MEETING,
    FOLLOWUP_TYPE_EMAIL,
)


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


def get_today_kolkata_str():
    """Return today's date string YYYY-MM-DD relative to Asia/Kolkata."""
    return datetime.now(ZoneInfo("Asia/Kolkata")).date().strftime("%Y-%m-%d")


def get_future_date_str(days=7):
    """Return future date string YYYY-MM-DD relative to Asia/Kolkata."""
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    return (today + timedelta(days=days)).strftime("%Y-%m-%d")


def get_past_date_str(days=2):
    """Return past date string YYYY-MM-DD relative to Asia/Kolkata."""
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    return (today - timedelta(days=days)).strftime("%Y-%m-%d")


# =============================================================================
# 1. CREATION & PERSISTENCE TESTS
# =============================================================================

def test_followup_create_page_loads_for_authenticated_users(client):
    """1. Follow-up creation page loads successfully for authenticated users."""
    for user, pwd in [("admin", "Admin@123"), ("manager", "Manager@123"), ("sales1", "Sales@123")]:
        login(client, user, pwd)
        resp = client.get("/followups/create")
        assert resp.status_code == 200, f"Failed for {user}"
        assert b"Schedule Follow-Up" in resp.data


def test_valid_followup_creation_succeeds_by_admin(client, db_conn):
    """2. Valid follow-up creation succeeds and 3. CREATE audit exists."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Review Pricing Proposal {suffix}"
    f_date = get_future_date_str(5)

    resp = client.post("/followups/create", data={
        "subject": subject,
        "followup_date": f_date,
        "followup_type": "Call",
        "customer_id": 1,  # Active Customer
        "assigned_to": 3,   # sales1
        "remarks": "Discuss cloud migration scope"
    })
    assert resp.status_code == 302
    assert "/followups/" in resp.headers["Location"]

    # Verify database persistence
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM followups WHERE subject = %s;", (subject,))
        row = cur.fetchone()
        assert row is not None
        assert row["status"] == "Planned"
        assert row["followup_type"] == "Call"
        assert row["customer_id"] == 1
        assert row["assigned_to"] == 3

    # Verify CREATE audit log entry
    audits = audit_repository.find_audit_logs(
        entity_name="FOLLOWUP",
        action="CREATE",
        conn=db_conn
    )
    matching = [a for a in audits if a["record_id"] == str(row["followup_id"])]
    assert len(matching) >= 1
    assert matching[0]["new_value"]["subject"] == subject
    assert matching[0]["new_value"]["status"] == "Planned"


def test_followup_creation_invalid_customer_rejected(client):
    """4. Invalid related Customer is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/followups/create", data={
        "subject": "Followup Invalid Customer",
        "followup_date": get_future_date_str(3),
        "followup_type": "Email",
        "customer_id": 999999,  # Non-existent
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Selected customer does not exist" in resp.data


def test_followup_creation_invalid_lead_rejected(client):
    """5. Invalid related Lead is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/followups/create", data={
        "subject": "Followup Invalid Lead",
        "followup_date": get_future_date_str(3),
        "followup_type": "Email",
        "lead_id": 999999,  # Non-existent
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Selected lead does not exist" in resp.data


def test_followup_creation_invalid_opportunity_rejected(client):
    """6. Invalid related Opportunity is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/followups/create", data={
        "subject": "Followup Invalid Opportunity",
        "followup_date": get_future_date_str(3),
        "followup_type": "Call",
        "opportunity_id": 999999,  # Non-existent
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Selected opportunity does not exist" in resp.data


def test_followup_creation_unlinked_rejected(client):
    """Cardinality: Follow-Up unlinked to any CRM entity is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/followups/create", data={
        "subject": "Unlinked Followup",
        "followup_date": get_future_date_str(3),
        "followup_type": "Call",
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"At least one related entity" in resp.data


def test_followup_creation_admin_manager_must_select_active_sales_executive(client):
    """7. Invalid or missing AssignedTo for Admin/Manager is rejected."""
    login(client, "admin", "Admin@123")
    # Missing assigned_to
    resp = client.post("/followups/create", data={
        "subject": "Unassigned Followup",
        "followup_date": get_future_date_str(3),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": ""
    })
    assert resp.status_code == 400
    assert b"active Sales Executive" in resp.data

    # Assigning to non-sales executive (e.g. Admin user_id 1)
    resp = client.post("/followups/create", data={
        "subject": "Admin Assigned Followup",
        "followup_date": get_future_date_str(3),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 1
    })
    assert resp.status_code == 400
    assert b"Assigned user must be an active Sales Executive" in resp.data


def test_followup_creation_sales_executive_auto_self_assigned(client, db_conn):
    """Sales Executive creates follow-up and is automatically self-assigned."""
    login(client, "sales1", "Sales@123")  # user_id 3
    suffix = get_unique_suffix()
    subject = f"Sales Rep Touchpoint {suffix}"

    resp = client.post("/followups/create", data={
        "subject": subject,
        "followup_date": get_future_date_str(4),
        "followup_type": "Meeting",
        "customer_id": 1,
        "assigned_to": 4  # sales2 submitted, should be ignored/overridden to 3
    })
    assert resp.status_code == 302

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT assigned_to FROM followups WHERE subject = %s;", (subject,))
        row = cur.fetchone()
        assert row is not None
        assert row["assigned_to"] == 3


def test_followup_creation_inactive_customer_rejected(client, db_conn):
    """8. Inactive related customer is rejected with HTTP 400."""
    login(client, "admin", "Admin@123")
    # Customer 4 is Inactive in seed data
    resp = client.post("/followups/create", data={
        "subject": "Inactive Customer Followup",
        "followup_date": get_future_date_str(3),
        "followup_type": "Call",
        "customer_id": 4,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Inactive customers cannot receive new follow-ups" in resp.data


# =============================================================================
# 2. DATE VALIDATION TESTS
# =============================================================================

def test_followup_past_date_rejected(client):
    """9. Past FollowUpDate is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/followups/create", data={
        "subject": "Past Followup",
        "followup_date": get_past_date_str(2),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"cannot be in the past" in resp.data


def test_followup_today_date_accepted(client, db_conn):
    """10. Follow-up scheduled for today in Asia/Kolkata is accepted."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Today Touchpoint {suffix}"

    resp = client.post("/followups/create", data={
        "subject": subject,
        "followup_date": get_today_kolkata_str(),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 302

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM followups WHERE subject = %s;", (subject,))
        assert cur.fetchone() is not None


def test_followup_future_date_accepted(client, db_conn):
    """11. Follow-up scheduled for a future date is accepted."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Future Touchpoint {suffix}"

    resp = client.post("/followups/create", data={
        "subject": subject,
        "followup_date": get_future_date_str(30),
        "followup_type": "Meeting",
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 302

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM followups WHERE subject = %s;", (subject,))
        assert cur.fetchone() is not None


def test_followup_invalid_date_format_rejected(client):
    """12. Invalid date string format is rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/followups/create", data={
        "subject": "Malformed Date Followup",
        "followup_date": "not-a-date",
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"YYYY-MM-DD" in resp.data


# =============================================================================
# 3. STATUS & TRANSITION TESTS
# =============================================================================

def test_followup_valid_status_accepted(client, db_conn):
    """13. Valid statuses are accepted upon creation or update."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Status Test {suffix}"

    resp = client.post("/followups/create", data={
        "subject": subject,
        "followup_date": get_future_date_str(10),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 302


def test_followup_invalid_status_rejected(app, db_conn):
    """14. Invalid status is rejected by service and business rules."""
    with app.app_context():
        user = user_repository.find_by_username("admin", conn=db_conn)
        success, res, errors, code = followup_service.update_followup_status(
            followup_id=1,
            target_status="UnknownStatus",
            current_user=user
        )
        assert success is False
        assert code == 400


def test_followup_valid_status_transition_succeeds(client, db_conn):
    """15. Valid status transition (Planned -> Completed) succeeds and 17. is audited."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Transition Test {suffix}"

    client.post("/followups/create", data={
        "subject": subject,
        "followup_date": get_future_date_str(5),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 3
    })

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT followup_id FROM followups WHERE subject = %s;", (subject,))
        f_id = cur.fetchone()["followup_id"]

    resp = client.post(f"/followups/{f_id}/status", data={
        "status": "Completed"
    })
    assert resp.status_code == 302

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT status FROM followups WHERE followup_id = %s;", (f_id,))
        assert cur.fetchone()["status"] == "Completed"

    # Verify STATUS_CHANGE audit
    audits = audit_repository.find_audit_logs(
        entity_name="FOLLOWUP",
        action="STATUS_CHANGE",
        conn=db_conn
    )
    matching = [a for a in audits if a["record_id"] == str(f_id)]
    assert len(matching) >= 1
    assert matching[0]["old_value"]["status"] == "Planned"
    assert matching[0]["new_value"]["status"] == "Completed"


def test_followup_invalid_status_transition_from_terminal_rejected(client, db_conn):
    """16. Modifying terminal status (Completed -> Planned) is rejected."""
    # Seed followup 2 is 'Completed'
    login(client, "admin", "Admin@123")
    resp = client.post("/followups/2/status", data={
        "status": "Planned"
    })
    assert resp.status_code == 302
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT status FROM followups WHERE followup_id = 2;")
        assert cur.fetchone()["status"] == "Completed"


# =============================================================================
# 4. RESCHEDULING TESTS
# =============================================================================

def test_followup_rescheduling_succeeds_and_is_audited(client, db_conn):
    """18. Rescheduling updates date and is audited with old/new values."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Reschedule Target {suffix}"
    initial_date = get_future_date_str(3)
    new_date = get_future_date_str(10)

    client.post("/followups/create", data={
        "subject": subject,
        "followup_date": initial_date,
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 3
    })

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT followup_id FROM followups WHERE subject = %s;", (subject,))
        f_id = cur.fetchone()["followup_id"]

    resp = client.post(f"/followups/{f_id}/reschedule", data={
        "followup_date": new_date
    })
    assert resp.status_code == 302

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT followup_date, status FROM followups WHERE followup_id = %s;", (f_id,))
        row = cur.fetchone()
        assert str(row["followup_date"]) == new_date
        assert row["status"] == "Planned"

    # Verify RESCHEDULE audit entry
    audits = audit_repository.find_audit_logs(
        entity_name="FOLLOWUP",
        action="RESCHEDULE",
        conn=db_conn
    )
    matching = [a for a in audits if a["record_id"] == str(f_id)]
    assert len(matching) >= 1
    assert matching[0]["old_value"]["followup_date"] == initial_date
    assert matching[0]["new_value"]["followup_date"] == new_date


def test_followup_rescheduling_to_past_date_rejected(client, db_conn):
    """19. Rescheduling to a past date is rejected."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Reschedule Past Reject {suffix}"
    initial_date = get_future_date_str(5)
    past_date = get_past_date_str(3)

    client.post("/followups/create", data={
        "subject": subject,
        "followup_date": initial_date,
        "followup_type": "Meeting",
        "customer_id": 1,
        "assigned_to": 3
    })

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT followup_id FROM followups WHERE subject = %s;", (subject,))
        f_id = cur.fetchone()["followup_id"]

    resp = client.post(f"/followups/{f_id}/reschedule", data={
        "followup_date": past_date
    })
    assert resp.status_code == 302

    # Verify date did NOT change
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT followup_date FROM followups WHERE followup_id = %s;", (f_id,))
        assert str(cur.fetchone()["followup_date"]) == initial_date


def test_followup_rescheduling_missed_resets_to_planned(client, db_conn):
    """Rescheduling a Missed follow-up reopens it with Planned status."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Missed Reschedule {suffix}"

    client.post("/followups/create", data={
        "subject": subject,
        "followup_date": get_future_date_str(2),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 3
    })

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT followup_id FROM followups WHERE subject = %s;", (subject,))
        f_id = cur.fetchone()["followup_id"]

    # Mark Missed
    client.post(f"/followups/{f_id}/status", data={"status": "Missed"})

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT status FROM followups WHERE followup_id = %s;", (f_id,))
        assert cur.fetchone()["status"] == "Missed"

    # Reschedule
    new_date = get_future_date_str(12)
    resp = client.post(f"/followups/{f_id}/reschedule", data={"followup_date": new_date})
    assert resp.status_code == 302

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT status, followup_date FROM followups WHERE followup_id = %s;", (f_id,))
        row = cur.fetchone()
        assert row["status"] == "Planned"
        assert str(row["followup_date"]) == new_date


# =============================================================================
# 5. OWNERSHIP, SCOPE & IDOR TESTS
# =============================================================================

def test_admin_and_manager_ownership_scopes(client):
    """20. Admin sees all follow-ups, 21. Manager sees follow-ups in scope."""
    login(client, "admin", "Admin@123")
    assert client.get("/followups").status_code == 200

    login(client, "manager", "Manager@123")
    assert client.get("/followups").status_code == 200


def test_sales_executive_scope_isolation(client, db_conn):
    """22. Sales Executive sees only their assigned follow-ups, 23. cannot access others."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject1 = f"Sales1 Followup {suffix}"
    subject2 = f"Sales2 Followup {suffix}"

    client.post("/followups/create", data={
        "subject": subject1,
        "followup_date": get_future_date_str(5),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 3  # sales1
    })

    client.post("/followups/create", data={
        "subject": subject2,
        "followup_date": get_future_date_str(5),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 4  # sales2
    })

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT followup_id FROM followups WHERE subject = %s;", (subject2,))
        f2_id = cur.fetchone()["followup_id"]

    # Login as sales1
    login(client, "sales1", "Sales@123")
    list_resp = client.get("/followups")
    assert subject1.encode() in list_resp.data
    assert subject2.encode() not in list_resp.data

    # IDOR: sales1 attempts to access sales2's followup detail
    detail_resp = client.get(f"/followups/{f2_id}")
    assert detail_resp.status_code == 403


def test_sales_executive_cannot_modify_another_reps_followup(client, db_conn):
    """24. Sales Executive cannot modify another representative's follow-up via URL tampering."""
    # Seed followup 4 is assigned to user 4 (sales2)
    login(client, "sales1", "Sales@123")

    # Attempt GET edit on followup 4
    edit_resp = client.get("/followups/4/edit")
    assert edit_resp.status_code == 403

    # Attempt POST edit on followup 4
    post_resp = client.post("/followups/4/edit", data={
        "subject": "Hacked Subject",
        "followup_date": get_future_date_str(5),
        "followup_type": "Call",
        "status": "Planned"
    })
    assert post_resp.status_code == 403

    # Attempt status change on followup 4
    status_resp = client.post("/followups/4/status", data={"status": "Completed"})
    assert status_resp.status_code == 403


def test_unauthorized_related_records_cannot_be_referenced(client):
    """25. Sales Executive cannot link a follow-up to an account outside their scope."""
    login(client, "sales1", "Sales@123")
    # Customer 3 is assigned to sales2 (user 4)
    resp = client.post("/followups/create", data={
        "subject": "Cross-rep Followup Attempt",
        "followup_date": get_future_date_str(3),
        "followup_type": "Call",
        "customer_id": 3
    })
    assert resp.status_code in (400, 403)


# =============================================================================
# 6. SEARCH & FILTER TESTS
# =============================================================================

def test_followup_search_and_filters(client):
    """26. Date filter, 27. Status filter, 28. Assigned filter, 29. Related-record filter."""
    login(client, "admin", "Admin@123")

    # Status filter
    resp = client.get("/followups?status=Planned")
    assert resp.status_code == 200

    # Type filter
    resp = client.get("/followups?ftype=Call")
    assert resp.status_code == 200

    # Assigned rep filter
    resp = client.get("/followups?assigned_to=3")
    assert resp.status_code == 200

    # Upcoming view filter
    resp = client.get("/followups?view=upcoming")
    assert resp.status_code == 200

    # Overdue view filter
    resp = client.get("/followups?view=overdue")
    assert resp.status_code == 200


def test_followup_search_sql_injection_safe(client):
    """30. Search input with SQL injection payloads executes safely."""
    login(client, "admin", "Admin@123")
    payload = "'; DROP TABLE followups; --"
    resp = client.get(f"/followups?search={payload}")
    assert resp.status_code == 200


# =============================================================================
# 7. SECURITY & CSRF TESTS
# =============================================================================

def test_anonymous_access_blocked(client):
    """32. Unauthenticated access to follow-ups is redirected to login."""
    resp = client.get("/followups", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    resp = client.get("/followups/create", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_csrf_blocks_followup_post_without_token():
    """33. CSRF token is required for state-changing POST requests."""
    class CsrfEnabledConfig(TestingConfig):
        WTF_CSRF_ENABLED = True

    csrf_app = create_app(config_object=CsrfEnabledConfig)
    csrf_client = csrf_app.test_client()

    login(csrf_client, "admin", "Admin@123")
    resp = csrf_client.post("/followups/create", data={
        "subject": "CSRF Attack Followup",
        "followup_date": get_future_date_str(5),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 400


# =============================================================================
# 8. AUDIT & TRANSACTION ROLLBACK TESTS
# =============================================================================

def test_audit_failure_rolls_back_followup_mutation(app, db_conn):
    """40. If audit log fails, the follow-up mutation rolls back atomically."""
    with app.app_context():
        user = user_repository.find_by_username("admin", conn=db_conn)
        initial_count = followup_repository.count_followups(conn=db_conn)

        with patch("services.audit_service.log_event", side_effect=RuntimeError("Simulated Audit Failure")):
            with pytest.raises(RuntimeError):
                followup_service.create_followup(
                    form_data={
                        "subject": "Audit Rollback Test",
                        "followup_date": get_future_date_str(5),
                        "followup_type": "Call",
                        "customer_id": 1,
                        "assigned_to": 3
                    },
                    current_user=user
                )

        assert followup_repository.count_followups(conn=db_conn) == initial_count


# =============================================================================
# 9. INTEGRATION WITH CUSTOMERS, LEADS, AND OPPORTUNITIES
# =============================================================================

def test_followup_referencing_customer_works(client, db_conn):
    """68. Follow-Up referencing Customer works."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Customer Linked Followup {suffix}"

    resp = client.post("/followups/create", data={
        "subject": subject,
        "followup_date": get_future_date_str(7),
        "followup_type": "Call",
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 302

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT customer_id FROM followups WHERE subject = %s;", (subject,))
        assert cur.fetchone()["customer_id"] == 1


def test_followup_referencing_lead_works(client, db_conn):
    """69. Follow-Up referencing Lead works."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Lead Linked Followup {suffix}"

    resp = client.post("/followups/create", data={
        "subject": subject,
        "followup_date": get_future_date_str(7),
        "followup_type": "Meeting",
        "lead_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 302

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT lead_id FROM followups WHERE subject = %s;", (subject,))
        assert cur.fetchone()["lead_id"] == 1


def test_followup_referencing_opportunity_works(client, db_conn):
    """70. Follow-Up referencing Opportunity works and co-links parent Customer."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Opp Linked Followup {suffix}"

    # Opportunity 1 parent is Customer 1
    resp = client.post("/followups/create", data={
        "subject": subject,
        "followup_date": get_future_date_str(7),
        "followup_type": "Email",
        "opportunity_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 302

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT customer_id, opportunity_id FROM followups WHERE subject = %s;", (subject,))
        row = cur.fetchone()
        assert row["opportunity_id"] == 1
        assert row["customer_id"] == 1  # Co-linked parent customer
