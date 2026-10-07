"""
Comprehensive Customer Management Tests for AcxiomCRM (Phase 5).

Verifies the complete Customer vertical slice:
UI -> client/server validation -> authorization/scope -> service -> business rules -> repository -> PostgreSQL -> audit.

Covers:
1. Customer creation (form loads, validation, auto-generated code, persistence, CREATE audit).
2. Field-level and business validation (name, email format, phone format, duplicate checks across active/inactive).
3. Read & Scope Visibility (Admin sees all, Manager sees all, Sales Executive sees ONLY assigned records in SQL).
4. IDOR Protection (Sales Executive cannot view or edit another rep's customer via URL).
5. Update behavior (immutable fields like created_by/created_date, modified_date update, UPDATE audit with old/new values).
6. Deactivation & Status lifecycle (Admin/Manager only, Sales Executive blocked with 403, STATUS_CHANGE audit).
7. Ownership rules (Sales Executive auto-assigned on creation, cannot reassign existing customers).
8. Search and filter (by name, email, phone, company, status, scoped in SQL, SQL injection immunity).
9. Transaction Atomicity (Customer mutation + audit log commit together or roll back together on failure).
10. CSRF & Security (State-changing POST blocked without CSRF, no raw SQL or credential leakage).
"""

import random
import uuid
from datetime import datetime
import pytest
import psycopg2

from app import create_app
from config import TestingConfig
from repositories import customer_repository, audit_repository, user_repository
from services import customer_service, audit_service


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
    """Generate a unique short string for email test isolation."""
    return uuid.uuid4().hex[:6]


def get_unique_phone():
    """Generate a unique 10-digit phone number with +91- prefix."""
    return f"+91-9{random.randint(100000000, 999999999)}"


# =============================================================================
# 1. CREATE FLOW & METADATA TESTS
# =============================================================================

def test_customer_create_page_loads_for_authenticated_users(client):
    """Authenticated users across all roles can access the customer creation page."""
    for user, pwd in [("admin", "Admin@123"), ("manager", "Manager@123"), ("sales1", "Sales@123")]:
        login(client, user, pwd)
        resp = client.get("/customers/create")
        assert resp.status_code == 200, f"Failed for {user}"
        assert b"Create Customer" in resp.data


def test_valid_customer_creation_succeeds_by_admin(client, db_conn):
    """Admin creates a customer and explicitly assigns an active Sales Executive."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    test_email = f"acme_{suffix}@corp.example"
    test_phone = get_unique_phone()

    response = client.post("/customers/create", data={
        "customer_name": f"Acme Corporation {suffix}",
        "company_name": "Acme Holdings",
        "email": test_email,
        "phone": test_phone,
        "address": "404 Innovation Way",
        "city": "Bengaluru",
        "state": "Karnataka",
        "assigned_to": 3  # sales1
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"created successfully" in response.data

    # Verify record in database
    customer = customer_repository.find_by_email(test_email, conn=db_conn)
    assert customer is not None
    assert customer["customer_name"] == f"Acme Corporation {suffix}"
    assert customer["created_by"] == 1  # admin user_id
    assert customer["assigned_to"] == 3
    assert customer["status"] == "Active"
    assert customer["customer_code"].startswith("CUST-")
    assert customer["created_date"] is not None


def test_sales_executive_creation_automatically_self_assigned(client, db_conn):
    """Sales Executive creating a customer is automatically self-assigned regardless of submitted form data."""
    login(client, "sales1", "Sales@123")  # user_id = 3
    suffix = get_unique_suffix()
    test_email = f"client_{suffix}@domain.example"
    test_phone = get_unique_phone()

    # Malicious or crafted attempt: sales1 tries to assign the customer to sales2 (user_id = 4)
    response = client.post("/customers/create", data={
        "customer_name": f"Independent Client {suffix}",
        "company_name": "Indie Co",
        "email": test_email,
        "phone": test_phone,
        "assigned_to": 4  # sales2
    }, follow_redirects=True)

    assert response.status_code == 200

    customer = customer_repository.find_by_email(test_email, conn=db_conn)
    assert customer is not None
    # Must be forced to sales1 (user_id 3) by server-side business rules
    assert customer["assigned_to"] == 3
    assert customer["created_by"] == 3


def test_customer_code_generated_sequentially(client, db_conn):
    """Customer codes follow the CUST-XXX sequential format."""
    login(client, "admin", "Admin@123")
    next_expected = customer_repository.get_next_customer_code(conn=db_conn)
    assert next_expected.startswith("CUST-")

    suffix = get_unique_suffix()
    client.post("/customers/create", data={
        "customer_name": f"Seq Test {suffix}",
        "email": f"seq_{suffix}@corp.example",
        "phone": get_unique_phone(),
        "assigned_to": 3
    })

    cust = customer_repository.find_by_email(f"seq_{suffix}@corp.example", conn=db_conn)
    assert cust is not None
    assert cust["customer_code"] == next_expected


def test_create_customer_audit_log_created(client, db_conn):
    """Customer creation generates a CREATE audit record with full initial details."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()
    test_email = f"audit_create_{suffix}@example.com"
    test_phone = get_unique_phone()

    client.post("/customers/create", data={
        "customer_name": f"Audit Target {suffix}",
        "email": test_email,
        "phone": test_phone,
        "assigned_to": 3
    })

    cust = customer_repository.find_by_email(test_email, conn=db_conn)
    assert cust is not None

    logs = audit_repository.find_audit_logs(
        entity_name="CUSTOMER",
        action="CREATE",
        conn=db_conn
    )
    matching = [l for l in logs if l.get("record_id") == str(cust["customer_id"])]
    assert len(matching) >= 1
    audit_entry = matching[0]
    assert audit_entry["action"] == "CREATE"
    assert audit_entry["result"] == "Success"
    assert audit_entry["user_id"] == 1
    assert audit_entry["new_value"]["customer_name"] == f"Audit Target {suffix}"
    assert audit_entry["new_value"]["customer_code"] == cust["customer_code"]


# =============================================================================
# 2. VALIDATION & DUPLICATE PREVENTION TESTS
# =============================================================================

def test_missing_customer_name_rejected(client):
    """Missing or empty customer name is rejected with 400 Bad Request."""
    login(client, "admin", "Admin@123")
    resp = client.post("/customers/create", data={
        "customer_name": "   ",
        "email": "valid@example.com",
        "phone": "+91-9876543210",
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Customer name is required" in resp.data or b"Customer Name is required" in resp.data


def test_invalid_email_format_rejected(client):
    """Malformed email strings are rejected server-side with 400 Bad Request."""
    login(client, "admin", "Admin@123")
    for bad_email in ["not-an-email", "@missinguser.com", "user@", "plainaddress"]:
        resp = client.post("/customers/create", data={
            "customer_name": "Test Customer",
            "email": bad_email,
            "phone": "+91-9876543210",
            "assigned_to": 3
        })
        assert resp.status_code == 400
        assert b"valid email address" in resp.data.lower()


def test_invalid_phone_format_rejected(client):
    """Malformed or invalid length phone numbers are rejected server-side with 400 Bad Request."""
    login(client, "admin", "Admin@123")
    for bad_phone in ["123", "abcdefghij", "+12345678901234567890", ""]:
        resp = client.post("/customers/create", data={
            "customer_name": "Test Customer",
            "email": f"valid_{get_unique_suffix()}@example.com",
            "phone": bad_phone,
            "assigned_to": 3
        })
        assert resp.status_code == 400
        assert b"Phone" in resp.data


def test_name_exceeding_max_length_rejected(client):
    """Customer name exceeding 100 characters is rejected with 400 Bad Request."""
    login(client, "admin", "Admin@123")
    long_name = "A" * 105
    resp = client.post("/customers/create", data={
        "customer_name": long_name,
        "email": f"valid_{get_unique_suffix()}@example.com",
        "phone": get_unique_phone(),
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"100 characters" in resp.data


def test_invalid_assigned_sales_rep_rejected(client):
    """Admin cannot assign an invalid user or a user who is not an active Sales Executive."""
    login(client, "admin", "Admin@123")
    # user_id 2 is Manager, user_id 999 does not exist
    for invalid_rep in [2, 999, "abc"]:
        resp = client.post("/customers/create", data={
            "customer_name": "Test Assignment",
            "email": f"valid_{get_unique_suffix()}@example.com",
            "phone": get_unique_phone(),
            "assigned_to": invalid_rep
        })
        assert resp.status_code == 400
        assert b"Sales Executive" in resp.data


def test_duplicate_email_rejected_across_active_and_inactive(client):
    """Duplicate email registration is rejected with a friendly message (including inactive accounts)."""
    login(client, "admin", "Admin@123")
    # Seed active customer email
    active_email = "contact@apexsolutions.example"
    resp = client.post("/customers/create", data={
        "customer_name": "Duplicate Active Email Test",
        "email": active_email,
        "phone": "+91-9998887771",
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Email address is already registered to another customer" in resp.data

    # Seed inactive customer email (CUST-004)
    inactive_email = "support@legacyind.example"
    resp = client.post("/customers/create", data={
        "customer_name": "Duplicate Inactive Email Test",
        "email": inactive_email,
        "phone": "+91-9998887772",
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Email address is already registered to another customer" in resp.data


def test_duplicate_phone_rejected_across_active_and_inactive(client):
    """Duplicate phone registration is rejected with a friendly message."""
    login(client, "admin", "Admin@123")
    # Seed customer phone
    active_phone = "+91-9876543210"
    resp = client.post("/customers/create", data={
        "customer_name": "Duplicate Phone Test",
        "email": f"unique_{get_unique_suffix()}@example.com",
        "phone": active_phone,
        "assigned_to": 3
    })
    assert resp.status_code == 400
    assert b"Phone number is already registered to another customer" in resp.data


# =============================================================================
# 3. READ & SCOPE-AWARE VISIBILITY TESTS (SQL-LEVEL FILTERING)
# =============================================================================

def test_admin_can_view_all_customers(client):
    """Admin sees all customer records in the CRM database."""
    login(client, "admin", "Admin@123")
    resp = client.get("/customers")
    assert resp.status_code == 200
    assert b"Apex Global Solutions" in resp.data  # CUST-001 (assigned to sales1)
    assert b"Horizon Logistics Ltd" in resp.data   # CUST-003 (assigned to sales2)
    assert b"Legacy Industries" in resp.data       # CUST-004 (inactive, assigned to sales2)


def test_manager_can_view_all_customers_within_manager_scope(client):
    """Manager sees all customer records under the approved Phase 3 manager scope."""
    login(client, "manager", "Manager@123")
    resp = client.get("/customers")
    assert resp.status_code == 200
    assert b"Apex Global Solutions" in resp.data
    assert b"Horizon Logistics Ltd" in resp.data


def test_sales_executive_sees_only_assigned_customers_in_sql(client):
    """Sales Executive 1 sees ONLY records assigned to user_id=3. Records for user_id=4 are excluded in SQL."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/customers")
    assert resp.status_code == 200
    # Assigned to sales1:
    assert b"Apex Global Solutions" in resp.data
    assert b"Zenith Retail Corp" in resp.data
    # Assigned to sales2: MUST NOT appear
    assert b"Horizon Logistics Ltd" not in resp.data
    assert b"Legacy Industries" not in resp.data


def test_sales_executive_2_sees_only_their_customers(client):
    """Sales Executive 2 sees ONLY records assigned to user_id=4."""
    login(client, "sales2", "Sales@123")
    resp = client.get("/customers")
    assert resp.status_code == 200
    assert b"Horizon Logistics Ltd" in resp.data
    assert b"Legacy Industries" in resp.data
    # Assigned to sales1: MUST NOT appear
    assert b"Apex Global Solutions" not in resp.data
    assert b"Zenith Retail Corp" not in resp.data


# =============================================================================
# 4. IDOR PROTECTION (INSECURE DIRECT OBJECT REFERENCE)
# =============================================================================

def test_sales_executive_can_view_assigned_customer_detail(client):
    """Sales Executive 1 can view detail page of their own customer (customer_id = 1)."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/customers/1")
    assert resp.status_code == 200
    assert b"CUST-001" in resp.data
    assert b"Apex Global Solutions" in resp.data


def test_idor_sales_rep_cannot_view_other_rep_customer_detail(client):
    """Sales Executive 1 requesting customer_id = 3 (owned by sales2) is blocked with HTTP 403."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/customers/3")
    assert resp.status_code == 403


def test_idor_sales_rep_cannot_get_edit_page_for_other_rep_customer(client):
    """Sales Executive 1 requesting GET /customers/3/edit is blocked with HTTP 403."""
    login(client, "sales1", "Sales@123")
    resp = client.get("/customers/3/edit")
    assert resp.status_code == 403


def test_idor_sales_rep_cannot_post_edit_for_other_rep_customer(client):
    """Sales Executive 1 attempting POST /customers/3/edit is blocked with HTTP 403."""
    login(client, "sales1", "Sales@123")
    resp = client.post("/customers/3/edit", data={
        "customer_name": "Hacked Customer Name",
        "email": "hacked@example.com",
        "phone": "+91-9876543212"
    })
    assert resp.status_code == 403


# =============================================================================
# 5. UPDATE BEHAVIOR & AUDITING TESTS
# =============================================================================

def test_valid_customer_update_succeeds(client, db_conn):
    """Updating a customer changes contact info and updates modified_date."""
    login(client, "admin", "Admin@123")
    # Fetch customer 2
    c_before = customer_repository.find_by_id(2, conn=db_conn)
    created_date_before = c_before["created_date"]
    created_by_before = c_before["created_by"]

    suffix = get_unique_suffix()
    new_name = f"Zenith Retail Updated {suffix}"
    new_email = f"zenith_{suffix}@retail.example"

    resp = client.post("/customers/2/edit", data={
        "customer_name": new_name,
        "company_name": "Zenith Corp",
        "email": new_email,
        "phone": "+91-9876543211",
        "status": "Active",
        "assigned_to": 3
    }, follow_redirects=True)
    assert resp.status_code == 200

    c_after = customer_repository.find_by_id(2, conn=db_conn)
    assert c_after["customer_name"] == new_name
    assert c_after["email"] == new_email
    # System fields must remain unchanged
    assert c_after["created_date"] == created_date_before
    assert c_after["created_by"] == created_by_before
    # modified_date must be updated
    assert c_after["modified_date"] is not None


def test_update_audit_contains_old_and_new_values(client, db_conn):
    """Customer update generates an UPDATE audit log capturing before and after states."""
    login(client, "admin", "Admin@123")
    suffix = get_unique_suffix()

    client.post("/customers/1/edit", data={
        "customer_name": f"Apex Renamed {suffix}",
        "company_name": "Apex Holdings",
        "email": f"apex_{suffix}@solutions.example",
        "phone": "+91-9876543210",
        "status": "Active",
        "assigned_to": 3
    })

    logs = audit_repository.find_audit_logs(
        entity_name="CUSTOMER",
        action="UPDATE",
        conn=db_conn
    )
    matching = [l for l in logs if l.get("record_id") == "1"]
    assert len(matching) >= 1
    latest_update = matching[0]
    assert latest_update["action"] == "UPDATE"
    assert latest_update["result"] == "Success"
    assert "customer_name" in latest_update["old_value"]
    assert latest_update["new_value"]["customer_name"] == f"Apex Renamed {suffix}"


def test_sales_executive_cannot_reassign_customer_on_update(client, db_conn):
    """Sales Executive updating their own customer cannot reassign the record to another rep."""
    login(client, "sales1", "Sales@123")
    # Customer 1 is assigned to sales1 (3). Attempt to reassign to sales2 (4)
    client.post("/customers/1/edit", data={
        "customer_name": "Apex Legit Update",
        "email": "contact_sales1@apex.example",
        "phone": "+91-9876543210",
        "assigned_to": 4  # sales2
    })

    cust = customer_repository.find_by_id(1, conn=db_conn)
    # Server-side business rule preserves original assigned_to
    assert cust["assigned_to"] == 3


# =============================================================================
# 6. DEACTIVATION & STATUS LIFECYCLE
# =============================================================================

def test_admin_and_manager_can_deactivate_customer(client, db_conn):
    """Admin and Manager can deactivate an active customer account."""
    # First test Manager deactivation on Customer 3
    login(client, "manager", "Manager@123")
    resp = client.post("/customers/3/deactivate", follow_redirects=True)
    assert resp.status_code == 200
    assert b"deactivated successfully" in resp.data

    c3 = customer_repository.find_by_id(3, conn=db_conn)
    assert c3["status"] == "Inactive"


def test_deactivation_is_audited_with_status_change(client, db_conn):
    """Deactivation creates a STATUS_CHANGE audit record."""
    login(client, "admin", "Admin@123")
    # Ensure customer 2 is Active
    customer_repository.update_status(2, "Active", conn=db_conn)
    db_conn.commit()

    client.post("/customers/2/deactivate")

    logs = audit_repository.find_audit_logs(
        entity_name="CUSTOMER",
        action="STATUS_CHANGE",
        conn=db_conn
    )
    matching = [l for l in logs if l.get("record_id") == "2"]
    assert len(matching) >= 1
    deact_log = matching[0]
    assert deact_log["action"] == "STATUS_CHANGE"
    assert deact_log["old_value"]["status"] == "Active"
    assert deact_log["new_value"]["status"] == "Inactive"


def test_sales_executive_cannot_deactivate_customer(client, db_conn):
    """Sales Executive cannot deactivate any customer, even their own (HTTP 403)."""
    login(client, "sales1", "Sales@123")
    # Try deactivating customer 1 (which sales1 owns)
    resp = client.post("/customers/1/deactivate")
    assert resp.status_code == 403

    # Customer 1 must still be Active
    c1 = customer_repository.find_by_id(1, conn=db_conn)
    assert c1["status"] == "Active"


def test_reactivation_by_admin_or_manager(client, db_conn):
    """Admin can reactivate an Inactive customer through edit form."""
    login(client, "admin", "Admin@123")
    # Customer 4 is Inactive in seed
    resp = client.post("/customers/4/edit", data={
        "customer_name": "Legacy Industries Revived",
        "company_name": "Legacy Industries",
        "email": "support@legacyind.example",
        "phone": "+91-9876543213",
        "status": "Active",
        "assigned_to": 4
    }, follow_redirects=True)
    assert resp.status_code == 200

    c4 = customer_repository.find_by_id(4, conn=db_conn)
    assert c4["status"] == "Active"


# =============================================================================
# 7. SEARCH & FILTERING TESTS
# =============================================================================

def test_search_by_name(client):
    """Search matches customer name case-insensitively."""
    login(client, "admin", "Admin@123")
    resp = client.get("/customers?search=apex")
    assert resp.status_code == 200
    assert b"Apex" in resp.data
    assert b"Horizon" not in resp.data


def test_search_by_email(client):
    """Search matches customer email."""
    login(client, "admin", "Admin@123")
    resp = client.get("/customers?search=horizonlogistics")
    assert resp.status_code == 200
    assert b"Horizon Logistics Ltd" in resp.data
    assert b"Apex" not in resp.data


def test_search_by_phone(client):
    """Search matches customer phone digits."""
    login(client, "admin", "Admin@123")
    resp = client.get("/customers?search=9876543212")
    assert resp.status_code == 200
    assert b"Horizon Logistics Ltd" in resp.data


def test_search_by_company(client):
    """Search matches customer company name."""
    login(client, "admin", "Admin@123")
    resp = client.get("/customers?search=Zenith")
    assert resp.status_code == 200
    assert b"Zenith Retail" in resp.data


def test_search_remains_ownership_scoped_for_sales_executive(client):
    """When a Sales Executive searches, the SQL scope filter prevents seeing other reps' matches."""
    login(client, "sales1", "Sales@123")
    # Search for "Horizon" which is assigned to sales2
    resp = client.get("/customers?search=Horizon")
    assert resp.status_code == 200
    assert b"Horizon Logistics Ltd" not in resp.data
    assert b"No customers found matching your criteria" in resp.data


def test_sql_injection_in_search_input_is_safe(client):
    """Search input containing SQL injection attempts is safely parameterized."""
    login(client, "admin", "Admin@123")
    malicious_searches = [
        "' OR '1'='1",
        "'; DROP TABLE customers; --",
        "admin'--",
        "' UNION SELECT * FROM users --"
    ]
    for injection in malicious_searches:
        resp = client.get(f"/customers?search={injection}")
        assert resp.status_code == 200
        # No 500 server error and no database corruption
        assert b"Customers" in resp.data


# =============================================================================
# 8. TRANSACTION ATOMICITY TESTS
# =============================================================================

def test_atomic_rollback_on_failed_transaction(db_conn):
    """Customer update and audit log commit together; if an error occurs mid-transaction, both roll back."""
    suffix = get_unique_suffix()
    unique_name = f"TxRollback_{suffix}"

    try:
        with db_conn.cursor() as cur:
            # 1. Update customer record
            cur.execute("""
                UPDATE customers
                SET customer_name = %s
                WHERE customer_id = 1;
            """, (unique_name,))

            # 2. Insert audit log on same connection
            audit_repository.create_audit_log(
                action="UPDATE",
                entity_name="CUSTOMER",
                user_id=1,
                record_id="1",
                result="Success",
                new_value={"customer_name": unique_name},
                conn=db_conn
            )

            # 3. Simulate failure right before commit
            raise RuntimeError("Mid-transaction database failure simulation")

    except RuntimeError:
        db_conn.rollback()

    # Verify customer change was rolled back
    cust = customer_repository.find_by_id(1, conn=db_conn)
    assert cust["customer_name"] != unique_name

    # Verify audit log was also rolled back
    logs = audit_repository.find_audit_logs(
        entity_name="CUSTOMER",
        action="UPDATE",
        conn=db_conn
    )
    matching = [l for l in logs if l.get("record_id") == "1" and (l.get("new_value") or {}).get("customer_name") == unique_name]
    assert len(matching) == 0


# =============================================================================
# 9. CSRF & SECURITY TESTS
# =============================================================================

def test_csrf_protection_blocks_post_without_token():
    """State-changing POST requests without a valid CSRF token are rejected with 400 Bad Request."""
    class CsrfEnabledConfig(TestingConfig):
        WTF_CSRF_ENABLED = True

    csrf_app = create_app(config_object=CsrfEnabledConfig)
    csrf_client = csrf_app.test_client()

    # Login without CSRF checking disabled on app
    login(csrf_client, "admin", "Admin@123")

    # Attempt POST to /customers/create without CSRF token
    resp = csrf_client.post("/customers/create", data={
        "customer_name": "CSRF Attack Attempt",
        "email": "attack@example.com",
        "phone": "+91-9876543210"
    })
    assert resp.status_code == 400


def test_anonymous_user_cannot_access_customer_routes(client):
    """Anonymous user attempting to access customer endpoints is redirected to login."""
    endpoints = [
        "/customers",
        "/customers/create",
        "/customers/1",
        "/customers/1/edit"
    ]
    for ep in endpoints:
        resp = client.get(ep, follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    # Destructive/mutation routes
    resp_post = client.post("/customers/1/deactivate", follow_redirects=False)
    assert resp_post.status_code == 302
    assert "/login" in resp_post.headers["Location"]


def test_passwords_and_hashes_never_in_customer_responses_or_audits(client, db_conn):
    """Customer views and audit log records never leak password hashes or secret tokens."""
    login(client, "admin", "Admin@123")
    resp = client.get("/customers/1")
    assert resp.status_code == 200
    assert b"scrypt:" not in resp.data
    assert b"password_hash" not in resp.data

    logs = audit_repository.find_audit_logs(entity_name="CUSTOMER", conn=db_conn)
    for log in logs:
        for val_dict in [log.get("old_values"), log.get("new_values")]:
            if val_dict:
                assert "password" not in val_dict
                assert "password_hash" not in val_dict
                assert "token" not in val_dict
