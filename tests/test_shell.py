"""
Application Shell, Navigation & Centralized Error Handling Tests for AcxiomCRM.

Verifies:
1. Public vs Authenticated application shell rendering.
2. Safe presentation of user identity (no passwords, hashes, secrets exposed).
3. Role-aware navigation visibility across Admin, Manager, and Sales Executive.
4. Navigation hiding does NOT replace route authorization (RBAC still enforces 403).
5. Centralized HTTP error handlers and friendly error pages (400, 401, 403, 404, 500).
6. Complete information concealment in 500 errors (no tracebacks, SQL, secrets, or file paths).
7. Flash message display and dismissal styling.
"""

import pytest
from flask import Blueprint, abort, flash, render_template
from security.decorators import admin_required


# Test Blueprint to provide test routes for error handlers and navigation
test_shell_bp = Blueprint("test_shell", __name__)


@test_shell_bp.route("/test-shell/admin-section")
@admin_required
def view_admin_section():
    return "Admin Core Section", 200



@test_shell_bp.route("/test-shell/trigger-400")
def trigger_400():
    abort(400)


@test_shell_bp.route("/test-shell/trigger-401")
def trigger_401():
    abort(401)


@test_shell_bp.route("/test-shell/trigger-500")
def trigger_500():
    abort(500)


@test_shell_bp.route("/test-shell/trigger-flash")
def trigger_flash():
    flash("Operation successful!", "success")
    flash("Critical error occurred!", "danger")
    return render_template("base.html")


@pytest.fixture
def shell_client(app):
    """Register test shell blueprint on the application test client."""
    if "test_shell" not in app.blueprints:
        app.register_blueprint(test_shell_bp)
    return app.test_client()


def login_user(client, identifier, password):
    """Helper to authenticate a user."""
    return client.post("/login", data={
        "identifier": identifier,
        "password": password
    }, follow_redirects=False)


# =============================================================================
# 1. PUBLIC VS AUTHENTICATED APPLICATION SHELL
# =============================================================================

def test_public_home_page_loads(shell_client):
    """Anonymous user accessing '/' receives the public landing view."""
    response = shell_client.get("/")
    assert response.status_code == 200
    assert b"Acxiom" in response.data
    assert b"Role-Based Customer Relationship Management" in response.data
    # Public actions visible
    assert b"Sign In" in response.data
    assert b"Register" in response.data
    # Authenticated actions hidden
    assert b"Signed in as" not in response.data
    assert b"Log Out" not in response.data


def test_login_and_register_pages_load_with_shell(shell_client):
    """Authentication pages load cleanly within the base application shell."""
    login_res = shell_client.get("/login")
    assert login_res.status_code == 200
    assert b"Sign In" in login_res.data
    assert b"Acxiom" in login_res.data

    reg_res = shell_client.get("/register")
    assert reg_res.status_code == 200
    assert b"Create Account" in reg_res.data
    assert b"Acxiom" in reg_res.data


def test_authenticated_user_receives_authenticated_shell(shell_client):
    """Authenticated user accessing '/' sees account overview and logout option."""
    login_user(shell_client, "sales1", "Sales@123")
    response = shell_client.get("/")
    assert response.status_code == 200
    assert b"Active User Session:" in response.data
    assert b"sales1" in response.data
    assert b"Sales Executive" in response.data
    assert b"Logout" in response.data


def test_authenticated_shell_displays_identity_safely(shell_client):
    """
    User identity is safely rendered (username, email, role)
    with absolutely NO passwords, hashes, session secrets, or tokens.
    """
    login_user(shell_client, "sales1", "Sales@123")
    response = shell_client.get("/")
    page_text = response.data.decode("utf-8").lower()

    # Safe identity elements present
    assert "sales1" in page_text
    assert "sales@acxiomcrm.com" in page_text
    assert "sales executive" in page_text

    # Sensitive values absent
    assert "password_hash" not in page_text
    assert "scrypt:" not in page_text
    assert "sales@123" not in page_text
    assert "secret_key" not in page_text


# =============================================================================
# 2. ROLE-AWARE NAVIGATION (PART 24)
# =============================================================================

def test_admin_sees_admin_navigation(shell_client):
    """Admin user sees the Admin-only navigation area."""
    login_user(shell_client, "admin", "Admin@123")
    response = shell_client.get("/")
    assert response.status_code == 200
    assert b"Admin Area" in response.data


def test_manager_does_not_see_admin_navigation(shell_client):
    """Manager user does not see the Admin-only navigation area."""
    login_user(shell_client, "manager", "Manager@123")
    response = shell_client.get("/")
    assert response.status_code == 200
    assert b"Admin Area" not in response.data


def test_sales_executive_does_not_see_admin_navigation(shell_client):
    """Sales Executive user does not see the Admin-only navigation area."""
    login_user(shell_client, "sales1", "Sales@123")
    response = shell_client.get("/")
    assert response.status_code == 200
    assert b"Admin Area" not in response.data


def test_navigation_hiding_does_not_replace_authorization(shell_client):
    """
    Even though the link is hidden, a Sales Executive directly requesting
    the Admin route must still be stopped with HTTP 403 Forbidden.
    """
    login_user(shell_client, "sales1", "Sales@123")
    response = shell_client.get("/test-shell/admin-section")
    assert response.status_code == 403
    assert b"403" in response.data
    assert b"Access Forbidden" in response.data


# =============================================================================
# 3. CENTRALIZED ERROR HANDLING (400, 401, 403, 404, 500)
# =============================================================================

def test_400_bad_request_handler(shell_client):
    """400 Bad Request renders the friendly 400 error page."""
    response = shell_client.get("/test-shell/trigger-400")
    assert response.status_code == 400
    assert b"400" in response.data
    assert b"Bad Request" in response.data
    assert b"Return to Home" in response.data


def test_401_unauthorized_handler(shell_client):
    """401 Unauthorized renders the friendly 401 error page."""
    response = shell_client.get("/test-shell/trigger-401")
    assert response.status_code == 401
    assert b"401" in response.data
    assert b"Authentication Required" in response.data


def test_403_forbidden_handler(shell_client):
    """403 Forbidden renders the friendly 403 error page."""
    login_user(shell_client, "sales1", "Sales@123")
    response = shell_client.get("/test-shell/admin-section")
    assert response.status_code == 403
    assert b"403" in response.data
    assert b"Access Forbidden" in response.data
    assert b"You do not have permission to access this resource" in response.data


def test_404_not_found_handler(shell_client):
    """Non-existent route renders the friendly 404 error page."""
    response = shell_client.get("/non-existent-endpoint-abc-xyz")
    assert response.status_code == 404
    assert b"404" in response.data
    assert b"Page Not Found" in response.data
    assert b"Return to Home" in response.data


def test_500_internal_server_error_handler(shell_client):
    """500 Internal Error renders the friendly 500 error page."""
    response = shell_client.get("/test-shell/trigger-500")
    assert response.status_code == 500
    assert b"500" in response.data
    assert b"Internal Server Error" in response.data


def test_500_error_page_conceals_all_sensitive_internals(shell_client):
    """
    Part 23 Security Test:
    Ensures that a 500 error page NEVER leaks internal stack traces,
    SQL statements, filesystem paths, database credentials, or secret keys.
    """
    response = shell_client.get("/test-shell/trigger-500")
    assert response.status_code == 500
    page_text = response.data.decode("utf-8").lower()

    # Must contain safe user-facing message
    assert "something went wrong on our end" in page_text

    # Must NOT contain tracebacks or internals
    assert "traceback" not in page_text
    assert "file \"" not in page_text
    assert ".py\", line" not in page_text
    assert "select *" not in page_text
    assert "psycopg2" not in page_text
    assert "password" not in page_text
    assert "secret_key" not in page_text


# =============================================================================
# 4. FLASH MESSAGES & LOGOUT FORM
# =============================================================================

def test_flash_messages_render_with_bootstrap_alerts(shell_client):
    """Flash messages render with proper alert classes and dismiss buttons."""
    response = shell_client.get("/test-shell/trigger-flash")
    assert response.status_code == 200
    assert b"alert-success" in response.data
    assert b"Operation successful!" in response.data
    assert b"alert-danger" in response.data
    assert b"Critical error occurred!" in response.data
    assert b"btn-close" in response.data


def test_logout_remains_post_method(shell_client):
    """Logout requires POST; GET /logout is rejected with 405 Method Not Allowed."""
    response = shell_client.get("/logout")
    assert response.status_code == 405
