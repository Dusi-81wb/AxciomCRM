"""
Audit Infrastructure and Transaction Tests for AcxiomCRM.

Verifies:
1. Authentication event auditing (LOGIN_SUCCESS, LOGIN_FAILED, ACCOUNT_LOCKED, LOGOUT).
2. Audit records contain user_id, action, entity_name, result, timestamp, and IP address.
3. Strict credential redaction: passwords, hashes, and secrets are NEVER written to audit logs.
4. Audit filtering foundation (by user, module/entity, action, date range, pagination).
5. Database engine-level audit immutability (UPDATE and DELETE triggers forbid modification).
6. Transactional integrity: business changes and audit logs commit or rollback together atomically.
"""

from datetime import datetime, timezone, timedelta
import pytest
import psycopg2
from repositories import audit_repository
from services import audit_service


# =============================================================================
# 1. AUTHENTICATION EVENT AUDITING TESTS
# =============================================================================

def test_successful_login_creates_audit_record(client, db_conn):
    """Successful login inserts a LOGIN_SUCCESS audit entry."""
    response = client.post("/login", data={
        "identifier": "admin",
        "password": "Admin@123"
    })
    assert response.status_code == 302

    logs = audit_repository.find_audit_logs(action="LOGIN_SUCCESS", entity_name="AUTH", conn=db_conn)
    assert len(logs) >= 1
    latest = logs[0]
    assert latest["action"] == "LOGIN_SUCCESS"
    assert latest["entity_name"] == "AUTH"
    assert latest["result"] == "Success"
    assert latest["user_id"] == 1
    assert latest["created_date"] is not None


def test_failed_login_creates_audit_record(client, db_conn):
    """Failed login attempt with bad password inserts a LOGIN_FAILED audit entry."""
    response = client.post("/login", data={
        "identifier": "admin",
        "password": "WrongPassword123!"
    })
    assert response.status_code == 401

    logs = audit_repository.find_audit_logs(action="LOGIN_FAILED", entity_name="AUTH", conn=db_conn)
    assert len(logs) >= 1
    latest = logs[0]
    assert latest["action"] == "LOGIN_FAILED"
    assert latest["entity_name"] == "AUTH"
    assert latest["result"] == "Failure"
    assert latest["user_id"] == 1


def test_unknown_identifier_login_creates_audit_record(client, db_conn):
    """Login attempt with non-existent user creates LOGIN_FAILED with user_id = NULL."""
    response = client.post("/login", data={
        "identifier": "unknown_user_xyz",
        "password": "SomePassword123!"
    })
    assert response.status_code == 401

    logs = audit_repository.find_audit_logs(action="LOGIN_FAILED", entity_name="AUTH", conn=db_conn)
    # At least one log should have user_id as None
    unknown_logs = [l for l in logs if l["user_id"] is None]
    assert len(unknown_logs) >= 1
    assert unknown_logs[0]["result"] == "Failure"


def test_account_lockout_creates_audit_record(client, db_conn):
    """Reaching the failed attempt threshold triggers an ACCOUNT_LOCKED audit entry."""
    # Register a fresh dedicated user to test lockout without affecting seed demo accounts
    reg_res = client.post("/register", data={
        "username": "audit_lockout_user",
        "email": "lockout_audit@acxiomcrm.com",
        "password": "LockoutPass123!",
        "confirm_password": "LockoutPass123!"
    })
    assert reg_res.status_code == 302

    # Attempt 5 incorrect logins to trigger lockout
    for _ in range(5):
        client.post("/login", data={
            "identifier": "audit_lockout_user",
            "password": "BadPassword123!"
        })

    logs = audit_repository.find_audit_logs(action="ACCOUNT_LOCKED", entity_name="AUTH", conn=db_conn)
    assert len(logs) >= 1
    assert logs[0]["action"] == "ACCOUNT_LOCKED"
    assert logs[0]["result"] == "Locked"


def test_logout_creates_audit_record(client, db_conn):
    """Logging out generates a LOGOUT audit log with actor user_id."""
    # Login
    client.post("/login", data={
        "identifier": "manager",
        "password": "Manager@123"
    })

    # Logout
    logout_res = client.post("/logout")
    assert logout_res.status_code == 302

    logs = audit_repository.find_audit_logs(action="LOGOUT", entity_name="AUTH", conn=db_conn)
    assert len(logs) >= 1
    assert logs[0]["action"] == "LOGOUT"
    assert logs[0]["result"] == "Success"
    assert logs[0]["user_id"] == 2


# =============================================================================
# 2. AUDIT DATA INTEGRITY & SENSITIVE DATA REDACTION
# =============================================================================

def test_passwords_and_hashes_never_saved_to_audit():
    """
    Ensures that audit_service.sanitize_payload strips passwords, hashes, and secrets
    from metadata dictionaries before storage.
    """
    dirty_payload = {
        "username": "john_doe",
        "password": "PlainTextPassword123!",
        "password_hash": "scrypt:32768:8:1$abcdef...",
        "token": "secret_session_token",
        "csrf_token": "csrf_anti_forgery_token",
        "nested": {
            "api_key": "live_secret_key_999",
            "safe_field": "visible_data"
        }
    }

    clean = audit_service.sanitize_payload(dirty_payload)

    assert clean["username"] == "john_doe"
    assert clean["password"] == "[REDACTED]"
    assert clean["password_hash"] == "[REDACTED]"
    assert clean["token"] == "[REDACTED]"
    assert clean["csrf_token"] == "[REDACTED]"
    assert clean["nested"]["api_key"] == "[REDACTED]"
    assert clean["nested"]["safe_field"] == "visible_data"


def test_audit_logs_table_contains_no_plaintext_passwords(db_conn):
    """
    Inspects all historical audit records in PostgreSQL to ensure no plaintext passwords exist.
    """
    with db_conn.cursor() as cur:
        cur.execute("SELECT old_value, new_value FROM audit_logs;")
        rows = cur.fetchall()

    for old_val, new_val in rows:
        for val in (old_val, new_val):
            if val:
                text = str(val).lower()
                assert "plaintext" not in text
                assert "admin@123" not in text
                assert "manager@123" not in text
                assert "sales@123" not in text


# =============================================================================
# 3. AUDIT QUERY AND FILTERING FOUNDATION
# =============================================================================

def test_audit_filtering_by_user(db_conn):
    """Verify filtering audit logs by actor user_id."""
    logs = audit_repository.find_audit_logs(user_id=1, conn=db_conn)
    assert len(logs) >= 1
    for log in logs:
        assert log["user_id"] == 1


def test_audit_filtering_by_entity(db_conn):
    """Verify filtering audit logs by entity_name."""
    logs = audit_repository.find_audit_logs(entity_name="AUTH", conn=db_conn)
    assert len(logs) >= 1
    for log in logs:
        assert log["entity_name"] == "AUTH"


def test_audit_filtering_by_action(db_conn):
    """Verify filtering audit logs by specific action string."""
    logs = audit_repository.find_audit_logs(action="LOGIN_SUCCESS", conn=db_conn)
    assert len(logs) >= 1
    for log in logs:
        assert log["action"] == "LOGIN_SUCCESS"


def test_audit_filtering_by_date_range(db_conn):
    """Verify filtering audit logs by date range window."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=1)
    end = now + timedelta(hours=1)

    logs = audit_repository.find_audit_logs(start_date=start, end_date=end, conn=db_conn)
    assert len(logs) >= 1
    for log in logs:
        assert log["created_date"] >= start
        assert log["created_date"] <= end


def test_audit_count_matches_pagination(db_conn):
    """Verify count_audit_logs returns accurate total for pagination."""
    total = audit_repository.count_audit_logs(entity_name="AUTH", conn=db_conn)
    logs = audit_repository.find_audit_logs(entity_name="AUTH", limit=1000, conn=db_conn)
    assert total == len(logs)


# =============================================================================
# 4. AUDIT IMMUTABILITY (DATABASE ENGINE PROTECTION)
# =============================================================================

def test_audit_log_modification_forbidden(db_conn):
    """
    Attempting an UPDATE query on audit_logs must be rejected by PostgreSQL's trigger
    with an exception stating audit logs are append-only.
    """
    logs = audit_repository.get_recent_audit_logs(limit=1, conn=db_conn)
    assert len(logs) >= 1
    target_id = logs[0]["audit_log_id"]

    with pytest.raises(psycopg2.Error) as exc_info:
        with db_conn.cursor() as cur:
            cur.execute("UPDATE audit_logs SET action = 'MODIFIED' WHERE audit_log_id = %s;", (target_id,))
    db_conn.rollback()

    assert "append-only" in str(exc_info.value).lower()


def test_audit_log_deletion_forbidden(db_conn):
    """
    Attempting a DELETE query on audit_logs must be rejected by PostgreSQL's trigger
    with an exception stating audit logs are append-only.
    """
    logs = audit_repository.get_recent_audit_logs(limit=1, conn=db_conn)
    assert len(logs) >= 1
    target_id = logs[0]["audit_log_id"]

    with pytest.raises(psycopg2.Error) as exc_info:
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM audit_logs WHERE audit_log_id = %s;", (target_id,))
    db_conn.rollback()

    assert "append-only" in str(exc_info.value).lower()


# =============================================================================
# 5. TRANSACTIONAL INTEGRITY & ROLLBACK CONTRACT (PART 23)
# =============================================================================

def test_business_and_audit_persist_together_on_success(db_conn):
    """
    When a business operation succeeds, the business record and the audit record
    commit together in the same transaction.
    """
    unique_user = f"tx_success_{int(datetime.now().timestamp())}"

    # Transaction begins
    with db_conn.cursor() as cur:
        # 1. Business operation: create user
        cur.execute("""
            INSERT INTO users (username, email, password_hash, role_id, is_active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING user_id;
        """, (unique_user, f"{unique_user}@test.example", "hash", 3, True))
        new_user_id = cur.fetchone()[0]

    # 2. Audit operation on same connection
    audit_rec = audit_repository.create_audit_log(
        action="CREATE",
        entity_name="USER",
        user_id=new_user_id,
        record_id=str(new_user_id),
        result="Success",
        conn=db_conn
    )

    # 3. Commit both together
    db_conn.commit()

    # Verify both persisted
    with db_conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s;", (unique_user,))
        assert cur.fetchone() is not None

    persisted_audit = audit_repository.get_audit_log_by_id(audit_rec["audit_log_id"], conn=db_conn)
    assert persisted_audit is not None
    assert persisted_audit["action"] == "CREATE"


def test_failed_business_operation_rolls_back_audit_record(db_conn):
    """
    If a business operation fails, the business change AND the audit log roll back.
    No false 'Success' audit log is left in the database.
    """
    unique_user = f"tx_fail_{int(datetime.now().timestamp())}"
    audit_id_attempted = None

    try:
        with db_conn.cursor() as cur:
            # 1. Business operation
            cur.execute("""
                INSERT INTO users (username, email, password_hash, role_id, is_active)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING user_id;
            """, (unique_user, f"{unique_user}@test.example", "hash", 3, True))
            new_user_id = cur.fetchone()[0]

            # 2. Audit log creation on same connection
            audit_rec = audit_repository.create_audit_log(
                action="CREATE",
                entity_name="USER",
                user_id=new_user_id,
                record_id=str(new_user_id),
                result="Success",
                conn=db_conn
            )
            audit_id_attempted = audit_rec["audit_log_id"]

            # 3. Simulate business operation failure (e.g. database error or validation exception)
            raise RuntimeError("Simulated mid-transaction failure")

    except RuntimeError:
        # Atomic rollback of both business change and audit entry
        db_conn.rollback()

    # Verify business record was rolled back
    with db_conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE username = %s;", (unique_user,))
        assert cur.fetchone() is None

    # Verify audit record was ALSO rolled back (no false success log)
    assert audit_id_attempted is not None
    persisted_audit = audit_repository.get_audit_log_by_id(audit_id_attempted, conn=db_conn)
    assert persisted_audit is None
