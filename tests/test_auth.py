"""
Phase 2 Authentication, Password Security, Sessions, and Lockout Tests.

Validates:
1. Registration flow, validation, and role assignment.
2. Password hashing and security policy enforcement.
3. Login flow, generic error messages (anti-enumeration).
4. Failed login tracking and account lockout at threshold.
5. Inactive user rejection.
6. Session security and logout behavior.
7. CSRF protection verification.
"""

from datetime import datetime, timezone, timedelta
import pytest
from werkzeug.security import check_password_hash
from app import create_app
from config import TestingConfig
from repositories import user_repository


def test_login_page_loads(client):
    """Verify GET /login returns 200 and renders the sign-in form."""
    response = client.get("/login")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Sign In" in html
    assert 'name="identifier"' in html
    assert 'name="password"' in html


def test_registration_page_loads(client):
    """Verify GET /register returns 200 and renders the registration form."""
    response = client.get("/register")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Create Account" in html
    assert 'name="username"' in html
    assert 'name="email"' in html
    assert 'name="password"' in html
    assert 'name="confirm_password"' in html
    # Ensure client form does not present role selection
    assert 'name="role"' not in html
    assert 'name="role_id"' not in html


def test_valid_registration_succeeds(client, db_conn):
    """Verify registering with valid details succeeds and redirects to login."""
    response = client.post("/register", data={
        "username": "new_sales_user",
        "email": "newsales@example.com",
        "password": "ValidPassword@123",
        "confirm_password": "ValidPassword@123"
    })
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    # Verify user in database
    user = user_repository.find_by_username("new_sales_user", conn=db_conn)
    assert user is not None
    assert user["email"] == "newsales@example.com"
    assert user["role_id"] == 3  # Sales Executive


def test_registration_automatically_creates_sales_executive(client, db_conn):
    """Verify that public registration always assigns role_id = 3 (Sales Executive)."""
    client.post("/register", data={
        "username": "auto_sales_rep",
        "email": "rep@example.com",
        "password": "Password#2026",
        "confirm_password": "Password#2026"
    })
    user = user_repository.find_by_username("auto_sales_rep", conn=db_conn)
    assert user is not None
    assert user["role_id"] == 3


def test_registration_cannot_choose_admin_or_manager(client, db_conn):
    """Verify that tampering with request parameters cannot grant Admin or Manager roles."""
    # Attempt to inject role_id = 1 (Admin)
    client.post("/register", data={
        "username": "hacker_admin",
        "email": "hacker1@example.com",
        "password": "Password#2026",
        "confirm_password": "Password#2026",
        "role_id": "1",
        "role": "Admin"
    })
    user = user_repository.find_by_username("hacker_admin", conn=db_conn)
    assert user is not None
    assert user["role_id"] == 3  # Still Sales Executive!

    # Attempt to inject role_id = 2 (Manager)
    client.post("/register", data={
        "username": "hacker_manager",
        "email": "hacker2@example.com",
        "password": "Password#2026",
        "confirm_password": "Password#2026",
        "role_id": "2",
        "role": "Manager"
    })
    user2 = user_repository.find_by_username("hacker_manager", conn=db_conn)
    assert user2 is not None
    assert user2["role_id"] == 3  # Still Sales Executive!


def test_duplicate_username_rejected(client):
    """Verify duplicate username submission is rejected with 400 Bad Request."""
    response = client.post("/register", data={
        "username": "admin",  # Already exists from seed
        "email": "different_email@example.com",
        "password": "ValidPassword@123",
        "confirm_password": "ValidPassword@123"
    })
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Username is already taken" in html


def test_duplicate_email_rejected(client):
    """Verify duplicate email submission is rejected with 400 Bad Request."""
    response = client.post("/register", data={
        "username": "unique_username_99",
        "email": "admin@acxiomcrm.com",  # Already exists from seed
        "password": "ValidPassword@123",
        "confirm_password": "ValidPassword@123"
    })
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Email address is already registered" in html


def test_invalid_email_format_rejected(client):
    """Verify poorly formatted email address is rejected."""
    response = client.post("/register", data={
        "username": "test_bad_email",
        "email": "not-an-email",
        "password": "ValidPassword@123",
        "confirm_password": "ValidPassword@123"
    })
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "valid email address" in html


@pytest.mark.parametrize("weak_pass,expected_err", [
    ("Short1!", "at least 8 characters"),
    ("nouppercase1!", "at least one uppercase letter"),
    ("NOLOWERCASE1!", "at least one lowercase letter"),
    ("NoNumber!Pass", "at least one number"),
    ("NoSpecialChar123", "at least one special character"),
])
def test_password_policy_enforcement(client, weak_pass, expected_err):
    """Verify password policy rules reject non-compliant passwords."""
    response = client.post("/register", data={
        "username": f"user_{weak_pass[:4]}",
        "email": f"user_{weak_pass[:4]}@example.com",
        "password": weak_pass,
        "confirm_password": weak_pass
    })
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert expected_err in html


def test_password_stored_hashed_never_plaintext(client, db_conn):
    """Verify that passwords are cryptographically hashed using Werkzeug and never plaintext."""
    raw_pass = "UltraSecretPass#999"
    client.post("/register", data={
        "username": "hashed_user_test",
        "email": "hashed@example.com",
        "password": raw_pass,
        "confirm_password": raw_pass
    })
    user = user_repository.find_by_username("hashed_user_test", conn=db_conn)
    assert user is not None

    stored_hash = user["password_hash"]
    # Stored value must not match plaintext
    assert stored_hash != raw_pass
    # Must use Werkzeug hashing format
    assert stored_hash.startswith("scrypt:") or stored_hash.startswith("pbkdf2:")
    # Must verify via check_password_hash
    assert check_password_hash(stored_hash, raw_pass) is True


def test_valid_login_succeeds_with_username(client):
    """Verify logging in with valid username and password establishes session."""
    response = client.post("/login", data={
        "identifier": "admin",
        "password": "Admin@123"
    })
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("user_id") == 1
        assert sess.get("username") == "admin"


def test_valid_login_succeeds_with_email(client):
    """Verify logging in with valid email address establishes session."""
    response = client.post("/login", data={
        "identifier": "sales@acxiomcrm.com",
        "password": "Sales@123"
    })
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("user_id") == 3
        assert sess.get("username") == "sales1"


def test_invalid_password_returns_generic_error(client):
    """Verify wrong password returns generic 'Invalid credentials' error (HTTP 401)."""
    response = client.post("/login", data={
        "identifier": "admin",
        "password": "IncorrectPassword#123"
    })
    assert response.status_code == 401
    html = response.get_data(as_text=True)
    assert "Invalid credentials" in html
    assert "Incorrect password" not in html
    assert "Wrong password" not in html


def test_unknown_identifier_returns_generic_error(client):
    """Verify non-existent user returns the EXACT SAME generic error (HTTP 401)."""
    response = client.post("/login", data={
        "identifier": "completely_unknown_user",
        "password": "SomePassword#123"
    })
    assert response.status_code == 401
    html = response.get_data(as_text=True)
    assert "Invalid credentials" in html
    assert "User not found" not in html
    assert "Email does not exist" not in html


def test_failed_attempts_increment(client, db_conn):
    """Verify failed login attempts increment the counter in the database."""
    # Create test account
    client.post("/register", data={
        "username": "counter_test_user",
        "email": "counter@example.com",
        "password": "GoodPassword#123",
        "confirm_password": "GoodPassword#123"
    })

    # 1st failed attempt
    client.post("/login", data={"identifier": "counter_test_user", "password": "WrongPassword#1"})
    u = user_repository.find_by_username("counter_test_user", conn=db_conn)
    assert u["failed_login_attempts"] == 1

    # 2nd failed attempt
    client.post("/login", data={"identifier": "counter_test_user", "password": "WrongPassword#2"})
    u = user_repository.find_by_username("counter_test_user", conn=db_conn)
    assert u["failed_login_attempts"] == 2


def test_account_lockout_at_threshold(client, db_conn):
    """Verify that 5 consecutive failed attempts trigger account lockout."""
    username = "lockout_victim"
    client.post("/register", data={
        "username": username,
        "email": "lockout@example.com",
        "password": "GoodPassword#123",
        "confirm_password": "GoodPassword#123"
    })

    # Submit 5 failed attempts (MAX_LOGIN_ATTEMPTS = 5)
    for i in range(5):
        client.post("/login", data={"identifier": username, "password": f"BadPassword#{i}"})

    u = user_repository.find_by_username(username, conn=db_conn)
    assert u["failed_login_attempts"] >= 5
    assert u["lockout_until"] is not None
    # Lockout timestamp must be in the future
    now = datetime.now(timezone.utc)
    lockout = u["lockout_until"]
    if lockout.tzinfo is None:
        lockout = lockout.replace(tzinfo=timezone.utc)
    assert lockout > now


def test_locked_account_cannot_login_even_with_correct_password(client, db_conn):
    """Verify that a locked account is rejected even when providing the correct password."""
    username = "locked_account_user"
    client.post("/register", data={
        "username": username,
        "email": "lockeduser@example.com",
        "password": "CorrectPassword#123",
        "confirm_password": "CorrectPassword#123"
    })

    # Trigger lockout with 5 failed attempts
    for i in range(5):
        client.post("/login", data={"identifier": username, "password": "BadPassword#123"})

    # Now attempt with CORRECT password while locked
    response = client.post("/login", data={
        "identifier": username,
        "password": "CorrectPassword#123"
    })
    # Must reject with generic error
    assert response.status_code == 401
    html = response.get_data(as_text=True)
    assert "Invalid credentials" in html
    # Session must NOT be created
    with client.session_transaction() as sess:
        assert sess.get("user_id") is None


def test_successful_login_resets_failed_attempts(client, db_conn):
    """Verify that a successful login resets the failed login attempt counter to 0."""
    username = "reset_user_test"
    client.post("/register", data={
        "username": username,
        "email": "reset@example.com",
        "password": "CorrectPassword#123",
        "confirm_password": "CorrectPassword#123"
    })

    # Accumulate 2 failed attempts
    client.post("/login", data={"identifier": username, "password": "WrongPassword#1"})
    client.post("/login", data={"identifier": username, "password": "WrongPassword#2"})
    u = user_repository.find_by_username(username, conn=db_conn)
    assert u["failed_login_attempts"] == 2

    # Now login with CORRECT password
    response = client.post("/login", data={"identifier": username, "password": "CorrectPassword#123"})
    assert response.status_code == 302

    # Counter must be reset in database
    u = user_repository.find_by_username(username, conn=db_conn)
    assert u["failed_login_attempts"] == 0
    assert u["lockout_until"] is None


def test_logout_clears_session(client):
    """Verify that POST /logout clears user_id from session and redirects to login."""
    # First login as admin
    client.post("/login", data={"identifier": "admin", "password": "Admin@123"})
    with client.session_transaction() as sess:
        assert sess.get("user_id") == 1

    # Call logout
    response = client.post("/logout")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    # Session must be cleared
    with client.session_transaction() as sess:
        assert sess.get("user_id") is None


def test_inactive_user_cannot_authenticate(client, db_conn):
    """Verify that disabled/inactive user accounts are rejected."""
    # Create and deactivate user in database
    with db_conn.cursor() as cur:
        cur.execute("""
            UPDATE users SET is_active = FALSE WHERE username = 'sales2';
        """)
    db_conn.commit()

    # Attempt to login
    response = client.post("/login", data={
        "identifier": "sales2",
        "password": "Sales@123"
    })
    assert response.status_code == 401
    html = response.get_data(as_text=True)
    assert "Invalid credentials" in html

    # Reset active status for subsequent tests
    with db_conn.cursor() as cur:
        cur.execute("""
            UPDATE users SET is_active = TRUE WHERE username = 'sales2';
        """)
    db_conn.commit()


def test_inactive_user_session_cleared_on_subsequent_request(client, db_conn):
    """Verify that if an authenticated user is deactivated in the DB, their next request clears session."""
    # Login as sales1
    client.post("/login", data={"identifier": "sales1", "password": "Sales@123"})
    with client.session_transaction() as sess:
        assert sess.get("user_id") == 3

    # Admin deactivates sales1 in database
    with db_conn.cursor() as cur:
        cur.execute("UPDATE users SET is_active = FALSE WHERE user_id = 3;")
    db_conn.commit()

    # Sales1 attempts to access a page
    response = client.get("/")
    assert response.status_code == 200

    # User identity must be cleared from session
    with client.session_transaction() as sess:
        assert sess.get("user_id") is None

    # Restore active state
    with db_conn.cursor() as cur:
        cur.execute("UPDATE users SET is_active = TRUE WHERE user_id = 3;")
    db_conn.commit()


def test_session_contains_no_sensitive_secrets(client):
    """Verify that the session does not store password, password hash, or security secrets."""
    client.post("/login", data={"identifier": "admin", "password": "Admin@123"})
    with client.session_transaction() as sess:
        assert "password" not in sess
        assert "password_hash" not in sess
        assert "secret" not in sess
        assert "token" not in sess


def test_csrf_protection_blocks_unauthorized_post():
    """Verify that state-changing POST requests without CSRF token are blocked with 400 Bad Request."""
    # Instantiate app with CSRF explicitly enabled
    class CsrfEnabledConfig(TestingConfig):
        WTF_CSRF_ENABLED = True

    csrf_app = create_app(config_object=CsrfEnabledConfig)
    csrf_client = csrf_app.test_client()

    # Attempt POST to /login without CSRF token
    response = csrf_client.post("/login", data={
        "identifier": "admin",
        "password": "Admin@123"
    })
    # Must be rejected by Flask-WTF CSRFProtect
    assert response.status_code == 400
