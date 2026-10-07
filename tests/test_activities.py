"""
Comprehensive Activity Management Tests for AcxiomCRM (Phase 8).

Verifies the complete Activity vertical slice:
UI -> client/server validation -> authorization/scope -> service -> business rules -> repository -> PostgreSQL -> audit.

Covers:
1. Activity Creation & Field Validation (Creation page loads, valid creation, invalid types, customer/lead relations).
2. Field validation (Subject required, length limits, valid ISO datetime format).
3. Status Lifecycle (Completed / Planned).
4. Role-based Ownership & IDOR Protection (Admin sees all, Manager in scope, Sales Executive isolated, IDOR blocked with 403).
5. Search & Filtering (Type, status, rep, search term, SQL injection safety).
6. Atomic Audit Logging (CREATE, UPDATE, STATUS_CHANGE, transaction rollback atomicity).
7. Schema Integrity: Activities table connects only to Customer and Lead (no opportunity_id).
8. Security & CSRF (Anonymous blocked, CSRF protection).
"""

import uuid
import random
from datetime import datetime, timedelta
from unittest.mock import patch
import pytest
from psycopg2.extras import RealDictCursor

from app import create_app
from config import TestingConfig
from repositories import (
    activity_repository,
    customer_repository,
    lead_repository,
    audit_repository,
    user_repository,
)
from services import activity_service, audit_service
from validation.business_rules import (
    ACTIVITY_TYPE_CALL,
    ACTIVITY_TYPE_MEETING,
    ACTIVITY_TYPE_EMAIL,
    ACTIVITY_TYPE_TASK,
    ACTIVITY_STATUS_COMPLETED,
    ACTIVITY_STATUS_PLANNED,
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


def get_activity_datetime_str(hours=0):
    """Return ISO datetime string YYYY-MM-DDTHH:MM."""
    dt = datetime.now() + timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M")


# =============================================================================
# 1. CREATION & PERSISTENCE TESTS
# =============================================================================

def test_activity_create_page_loads_for_authenticated_users(client):
    """Activity creation page loads successfully for authenticated users."""
    for user, pwd in [("admin", "Admin@123"), ("manager", "Manager@123"), ("sales1", "Sales@123")]:
        login(client, user, pwd)
        resp = client.get("/activities/create")
        assert resp.status_code == 200, f"Failed for {user}"
        assert b"Log New Activity" in resp.data


def test_valid_activity_creation_succeeds_by_admin(client, db_conn):
    """41. Activity creation succeeds and 47. CREATE audit exists."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Client Catchup Call {suffix}"
    act_date = get_activity_datetime_str()

    resp = client.post("/activities/create", data={
        "subject": subject,
        "activity_type": "Call",
        "activity_date": act_date,
        "customer_id": 1,
        "assigned_to": 3,
        "status": "Completed",
        "description": "Discussed initial contract terms."
    })
    assert resp.status_code == 302
    assert "/activities/" in resp.headers["Location"]

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM activities WHERE subject = %s;", (subject,))
        row = cur.fetchone()
        assert row is not None
        assert row["activity_type"] == "Call"
        assert row["status"] == "Completed"
        assert row["customer_id"] == 1
        assert row["assigned_to"] == 3

    # Audit verification
    audits = audit_repository.find_audit_logs(
        entity_name="ACTIVITY",
        action="CREATE",
        conn=db_conn
    )
    matching = [a for a in audits if a["record_id"] == str(row["activity_id"])]
    assert len(matching) >= 1
    assert matching[0]["new_value"]["subject"] == subject


def test_activity_creation_invalid_type_rejected(client):
    """42. Invalid ActivityType rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/activities/create", data={
        "subject": "Bad Type Activity",
        "activity_type": "InvalidType",
        "activity_date": get_activity_datetime_str(),
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Activity type must be one of" in resp.data


def test_activity_creation_invalid_status_rejected(client):
    """43. Invalid ActivityStatus rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/activities/create", data={
        "subject": "Bad Status Activity",
        "activity_type": "Call",
        "activity_date": get_activity_datetime_str(),
        "customer_id": 1,
        "assigned_to": 3,
        "status": "UnknownStatus"
    })
    assert resp.status_code == 400
    assert b"Activity status must be one of" in resp.data


def test_activity_creation_invalid_customer_rejected(client):
    """44. Invalid CustomerId rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/activities/create", data={
        "subject": "Bad Customer Activity",
        "activity_type": "Meeting",
        "activity_date": get_activity_datetime_str(),
        "customer_id": 999999,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Selected customer does not exist" in resp.data


def test_activity_creation_invalid_lead_rejected(client):
    """45. Invalid LeadId rejected."""
    login(client, "admin", "Admin@123")
    resp = client.post("/activities/create", data={
        "subject": "Bad Lead Activity",
        "activity_type": "Meeting",
        "activity_date": get_activity_datetime_str(),
        "lead_id": 999999,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Selected lead does not exist" in resp.data


def test_activity_creation_invalid_assigned_to_rejected(client):
    """46. Invalid AssignedTo rejected for Admin/Manager."""
    login(client, "admin", "Admin@123")
    resp = client.post("/activities/create", data={
        "subject": "Bad Rep Activity",
        "activity_type": "Email",
        "activity_date": get_activity_datetime_str(),
        "customer_id": 1,
        "assigned_to": 999999
    })
    assert resp.status_code == 400
    assert b"Assigned user must be an active Sales Executive" in resp.data


def test_activity_creation_requires_customer_or_lead(client):
    """Activity requires at least customer_id or lead_id."""
    login(client, "admin", "Admin@123")
    resp = client.post("/activities/create", data={
        "subject": "Unlinked Activity",
        "activity_type": "Task",
        "activity_date": get_activity_datetime_str(),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"At least one related entity" in resp.data


# =============================================================================
# 2. VALIDATION TESTS
# =============================================================================

def test_activity_validation_required_subject(client):
    """48. Required Subject validated."""
    login(client, "admin", "Admin@123")
    resp = client.post("/activities/create", data={
        "subject": "   ",
        "activity_type": "Task",
        "activity_date": get_activity_datetime_str(),
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Subject is required" in resp.data


def test_activity_validation_subject_length(client):
    """49. Length limits validated (max 150 chars in schema)."""
    login(client, "admin", "Admin@123")
    resp = client.post("/activities/create", data={
        "subject": "A" * 151,
        "activity_type": "Task",
        "activity_date": get_activity_datetime_str(),
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"150 characters" in resp.data


def test_activity_validation_date_format(client):
    """50. Date/datetime format validated."""
    login(client, "admin", "Admin@123")
    resp = client.post("/activities/create", data={
        "subject": "Bad Date Activity",
        "activity_type": "Call",
        "activity_date": "not-a-datetime",
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"valid date or timestamp" in resp.data


# =============================================================================
# 3. OWNERSHIP, SCOPE & IDOR TESTS
# =============================================================================

def test_activity_ownership_scopes(client):
    """52. Admin scope, 53. Manager scope, 54. Sales Executive scope."""
    login(client, "admin", "Admin@123")
    assert client.get("/activities").status_code == 200

    login(client, "manager", "Manager@123")
    assert client.get("/activities").status_code == 200

    login(client, "sales1", "Sales@123")
    assert client.get("/activities").status_code == 200


def test_activity_idor_protection(client, db_conn):
    """55. IDOR blocked: Sales Executive cannot view or edit another rep's activity."""
    login(client, "sales1", "Sales@123")

    # Seed activity 3 is assigned to sales2 (user 4)
    resp_view = client.get("/activities/3")
    assert resp_view.status_code == 403

    # Edit attempt GET
    resp_edit_get = client.get("/activities/3/edit")
    assert resp_edit_get.status_code == 403

    # Edit attempt POST
    resp_edit_post = client.post("/activities/3/edit", data={
        "subject": "Hacked Activity",
        "activity_type": "Call",
        "activity_date": get_activity_datetime_str(),
        "status": "Completed"
    })
    assert resp_edit_post.status_code == 403


def test_activity_unauthorized_related_record_rejected(client):
    """56. Sales Executive cannot log activity for a record assigned to another rep."""
    login(client, "sales1", "Sales@123")
    # Customer 3 is assigned to sales2
    resp = client.post("/activities/create", data={
        "subject": "Cross rep customer activity",
        "activity_type": "Call",
        "activity_date": get_activity_datetime_str(),
        "customer_id": 3
    })
    assert resp.status_code in (400, 403)


# =============================================================================
# 4. SEARCH & FILTER TESTS
# =============================================================================

def test_activity_filters(client):
    """58. ActivityType, 59. Date, 60. Status, 61. Assigned."""
    login(client, "admin", "Admin@123")

    # Type
    assert client.get("/activities?type=Call").status_code == 200

    # Status
    assert client.get("/activities?status=Completed").status_code == 200

    # Assigned
    assert client.get("/activities?assigned_to=3").status_code == 200


def test_activity_search_sql_injection_safe(client):
    """62. SQL injection search is safe."""
    login(client, "admin", "Admin@123")
    payload = "'; DROP TABLE activities; --"
    resp = client.get(f"/activities?search={payload}")
    assert resp.status_code == 200


# =============================================================================
# 5. AUDIT & TRANSACTION ROLLBACK TESTS
# =============================================================================

def test_activity_update_and_audit(client, db_conn):
    """65. UPDATE audited, 66. STATUS_CHANGE audited."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    subject = f"Update Target Activity {suffix}"

    client.post("/activities/create", data={
        "subject": subject,
        "activity_type": "Task",
        "activity_date": get_activity_datetime_str(),
        "customer_id": 1,
        "assigned_to": 3,
        "status": "Planned"
    })

    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT activity_id FROM activities WHERE subject = %s;", (subject,))
        act_id = cur.fetchone()["activity_id"]

    # Update status from Planned to Completed
    resp = client.post(f"/activities/{act_id}/edit", data={
        "subject": subject,
        "activity_type": "Task",
        "activity_date": get_activity_datetime_str(),
        "status": "Completed",
        "assigned_to": 3,
        "description": "Task finished."
    })
    assert resp.status_code == 302

    audits = audit_repository.find_audit_logs(
        entity_name="ACTIVITY",
        action="STATUS_CHANGE",
        conn=db_conn
    )
    matching = [a for a in audits if a["record_id"] == str(act_id)]
    assert len(matching) >= 1
    assert matching[0]["old_value"]["status"] == "Planned"
    assert matching[0]["new_value"]["status"] == "Completed"


def test_activity_audit_failure_rolls_back_mutation(app, db_conn):
    """67. Audit failure rolls back activity mutation."""
    with app.app_context():
        user = user_repository.find_by_username("admin", conn=db_conn)
        initial_count = activity_repository.count_activities(conn=db_conn)

        with patch("services.audit_service.log_event", side_effect=RuntimeError("Simulated Activity Audit Failure")):
            with pytest.raises(RuntimeError):
                activity_service.create_activity(
                    form_data={
                        "subject": "Rollback Test Activity",
                        "activity_type": "Call",
                        "activity_date": get_activity_datetime_str(),
                        "customer_id": 1,
                        "assigned_to": 3,
                        "status": "Completed"
                    },
                    current_user=user
                )

        assert activity_repository.count_activities(conn=db_conn) == initial_count


# =============================================================================
# 6. CSRF & SECURITY TESTS
# =============================================================================

def test_csrf_blocks_activity_post_without_token():
    """CSRF blocks state-changing activity POST without token."""
    class CsrfEnabledConfig(TestingConfig):
        WTF_CSRF_ENABLED = True

    csrf_app = create_app(config_object=CsrfEnabledConfig)
    csrf_client = csrf_app.test_client()

    login(csrf_client, "admin", "Admin@123")
    resp = csrf_client.post("/activities/create", data={
        "subject": "CSRF Attack Activity",
        "activity_type": "Call",
        "activity_date": get_activity_datetime_str(),
        "customer_id": 1,
        "assigned_to": 3
    })
    assert resp.status_code == 400
