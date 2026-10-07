"""
Phase 1 Database Integration Tests for AcxiomCRM.

Validates the PostgreSQL database foundation against MASTER_BLUEPRINT.md:
1. Database connectivity.
2. Table creation for all 8 entities.
3. Role verification and constraints.
4. Foreign key integrity.
5. Unique constraint enforcement (CustomerCode, LeadCode, Email, Phone, Username).
6. Business domain constraints (Opportunity probability 0-100, amount >= 0, statuses).
7. Seed data retrieval and password hash verification.
8. Performance and search indexes presence.
9. Audit log immutability (append-only enforcement via database trigger).
"""

import pytest
import psycopg2
from werkzeug.security import check_password_hash
from database import init_db, seed_db


def test_database_connection(db_conn):
    """Verify that direct connection to PostgreSQL works."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT 1;")
        result = cur.fetchone()
        assert result == (1,)


def test_schema_and_seed_idempotency(app):
    """Verify that schema.sql and seed.sql can be executed cleanly via database helpers."""
    db_url = app.config["DATABASE_URL"]
    init_db(db_url=db_url)
    seed_db(db_url=db_url)


def test_required_tables_exist(db_conn):
    """Verify that all 8 core entities exist in the public schema."""
    expected_tables = {
        "roles",
        "users",
        "customers",
        "leads",
        "opportunities",
        "followups",
        "activities",
        "audit_logs",
    }
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """)
        existing_tables = {row[0] for row in cur.fetchall()}

    assert expected_tables.issubset(existing_tables)


def test_required_roles_and_constraint(db_conn):
    """Verify that the 3 approved roles exist and CHECK constraint blocks invalid roles."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT role_name FROM roles ORDER BY role_id;")
        roles = [row[0] for row in cur.fetchall()]
        assert roles == ["Admin", "Manager", "Sales Executive"]

        # Attempt to insert an unauthorized role name
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("INSERT INTO roles (role_name) VALUES ('Superuser');")
    db_conn.rollback()


def test_foreign_keys_present(db_conn):
    """Verify that foreign key constraints exist on dependent entities."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public';
        """)
        fks = [(row[0], row[1], row[2]) for row in cur.fetchall()]

    # Verify key structural relationships
    assert ("users", "role_id", "roles") in fks
    assert ("customers", "assigned_to", "users") in fks
    assert ("leads", "assigned_to", "users") in fks
    assert ("opportunities", "customer_id", "customers") in fks
    assert ("opportunities", "assigned_to", "users") in fks
    assert ("followups", "customer_id", "customers") in fks
    assert ("activities", "assigned_to", "users") in fks
    assert ("audit_logs", "user_id", "users") in fks


def test_unique_constraints(db_conn):
    """Verify that unique constraints are strictly enforced."""
    with db_conn.cursor() as cur:
        # Duplicate customer_code
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO customers (customer_code, customer_name, email, phone, status)
                VALUES ('CUST-001', 'Duplicate Code Corp', 'other@corp.example', '+91-9999999991', 'Active');
            """)
        db_conn.rollback()

        # Duplicate customer email
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO customers (customer_code, customer_name, email, phone, status)
                VALUES ('CUST-999', 'Duplicate Email Corp', 'contact@apexsolutions.example', '+91-9999999992', 'Active');
            """)
        db_conn.rollback()

        # Duplicate customer phone
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO customers (customer_code, customer_name, email, phone, status)
                VALUES ('CUST-998', 'Duplicate Phone Corp', 'unique@phone.example', '+91-9876543210', 'Active');
            """)
        db_conn.rollback()

        # Duplicate lead_code
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO leads (lead_code, lead_name, email, status)
                VALUES ('LEAD-001', 'Duplicate Lead', 'lead@test.example', 'New');
            """)
        db_conn.rollback()

        # Duplicate username in users
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO users (username, email, password_hash, role_id)
                VALUES ('admin', 'unique_email@test.example', 'hash123', 1);
            """)
        db_conn.rollback()


def test_opportunity_probability_constraint(db_conn):
    """Verify that opportunity probability is bounded between 0 and 100."""
    with db_conn.cursor() as cur:
        # Probability > 100
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO opportunities (opportunity_name, amount, stage, probability, expected_close_date, status)
                VALUES ('Invalid High Prob', 1000.00, 'Proposal', 105, '2026-12-31', 'Open');
            """)
        db_conn.rollback()

        # Probability < 0
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO opportunities (opportunity_name, amount, stage, probability, expected_close_date, status)
                VALUES ('Invalid Negative Prob', 1000.00, 'Proposal', -5, '2026-12-31', 'Open');
            """)
        db_conn.rollback()


def test_opportunity_amount_constraint(db_conn):
    """Verify that opportunity amount must be >= 0 (NUMERIC(14,2))."""
    with db_conn.cursor() as cur:
        # Amount < 0
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO opportunities (opportunity_name, amount, stage, probability, expected_close_date, status)
                VALUES ('Negative Amount Deal', -50.00, 'Proposal', 50, '2026-12-31', 'Open');
            """)
        db_conn.rollback()

        # Amount = 0 is accepted by the database schema (service layer handles business rule)
        cur.execute("""
            INSERT INTO opportunities (opportunity_name, amount, stage, probability, expected_close_date, status)
            VALUES ('Zero Amount Deal', 0.00, 'Qualification', 10, '2026-12-31', 'Open')
            RETURNING opportunity_id;
        """)
        opp_id = cur.fetchone()[0]
        assert opp_id > 0
    db_conn.rollback()


def test_lead_statuses_constraint(db_conn):
    """Verify that lead status enforces the 6 canonical values."""
    with db_conn.cursor() as cur:
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO leads (lead_code, lead_name, email, status)
                VALUES ('LEAD-BAD', 'Invalid Status Lead', 'bad@test.example', 'PendingReview');
            """)
    db_conn.rollback()


def test_opportunity_stage_and_status_constraints(db_conn):
    """Verify that opportunity stages and statuses enforce the blueprint enumeration."""
    with db_conn.cursor() as cur:
        # Invalid stage
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO opportunities (opportunity_name, amount, stage, probability, expected_close_date, status)
                VALUES ('Bad Stage', 100.00, 'Discussion', 50, '2026-12-31', 'Open');
            """)
        db_conn.rollback()

        # Invalid status
        with pytest.raises(psycopg2.IntegrityError):
            cur.execute("""
                INSERT INTO opportunities (opportunity_name, amount, stage, probability, expected_close_date, status)
                VALUES ('Bad Status', 100.00, 'Proposal', 50, '2026-12-31', 'Pending');
            """)
        db_conn.rollback()


def test_seed_data_and_password_hashing(db_conn):
    """Verify seeded demo records and valid Werkzeug password hashes."""
    with db_conn.cursor() as cur:
        # Verify users
        cur.execute("SELECT username, email, password_hash, role_id, is_active FROM users ORDER BY user_id;")
        users = cur.fetchall()
        assert len(users) >= 3

        admin = next(u for u in users if u[0] == "admin")
        assert admin[1] == "admin@acxiomcrm.com"
        assert admin[3] == 1  # Admin role_id
        assert admin[4] is True  # is_active
        # Verify Werkzeug scrypt hash passes verification against documented demo password
        assert check_password_hash(admin[2], "Admin@123") is True

        manager = next(u for u in users if u[0] == "manager")
        assert check_password_hash(manager[2], "Manager@123") is True

        sales1 = next(u for u in users if u[0] == "sales1")
        assert check_password_hash(sales1[2], "Sales@123") is True

        # Verify customers
        cur.execute("SELECT COUNT(*) FROM customers;")
        assert cur.fetchone()[0] >= 4

        # Verify leads across multiple statuses
        cur.execute("SELECT DISTINCT status FROM leads;")
        lead_statuses = {row[0] for row in cur.fetchall()}
        assert {"New", "Contacted", "Qualified", "Unqualified", "Converted", "Lost"}.issubset(lead_statuses)

        # Verify opportunities across stages and numeric amount
        cur.execute("SELECT opportunity_name, amount, stage, status FROM opportunities WHERE stage = 'Won';")
        won_opp = cur.fetchone()
        assert won_opp is not None
        assert won_opp[1] == 500000.00
        assert won_opp[3] == "Won"


def test_indexes_exist(db_conn):
    """Verify that expected performance and lookup indexes are created."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public';
        """)
        indexes = {row[0] for row in cur.fetchall()}

    expected_indexes = {
        "idx_users_username",
        "idx_users_email",
        "idx_users_role_id",
        "idx_users_is_active",
        "idx_customers_email",
        "idx_customers_phone",
        "idx_customers_assigned_to",
        "idx_leads_status",
        "idx_opportunities_stage",
        "idx_opportunities_status",
        "idx_followups_followup_date",
        "idx_activities_activity_date",
        "idx_audit_logs_created_date",
    }
    assert expected_indexes.issubset(indexes)


def test_audit_log_append_only_protection(db_conn):
    """Verify that AuditLog permits INSERTs but rejects UPDATE and DELETE operations."""
    with db_conn.cursor() as cur:
        # Append operation succeeds
        cur.execute("""
            INSERT INTO audit_logs (user_id, action, entity_name, record_id, result)
            VALUES (1, 'TEST_APPEND', 'Customer', '99', 'Success')
            RETURNING audit_log_id;
        """)
        new_id = cur.fetchone()[0]
        assert new_id > 0

        # Attempt UPDATE on audit_logs must be blocked by trigger
        with pytest.raises(psycopg2.InternalError) as exc_update:
            cur.execute("""
                UPDATE audit_logs SET action = 'MODIFIED_ACTION' WHERE audit_log_id = %s;
            """, (new_id,))
        assert "Audit logs are append-only" in str(exc_update.value)
        db_conn.rollback()

        # Attempt DELETE on audit_logs must be blocked by trigger
        with pytest.raises(psycopg2.InternalError) as exc_delete:
            cur.execute("""
                DELETE FROM audit_logs WHERE audit_log_id = 1;
            """)
        assert "Audit logs are append-only" in str(exc_delete.value)
        db_conn.rollback()
