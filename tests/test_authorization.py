"""
Authorization and RBAC Tests for AcxiomCRM.

Verifies role-based access control, server-side role enforcement, 401 vs 403 semantics,
ownership scope boundaries, and resilience against stale/tampered session roles.
Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md:
- Exactly 3 roles: Admin, Manager, Sales Executive.
- Roles are strictly loaded from PostgreSQL via get_current_user(), never trusting session role.
- Unauthenticated requests redirect to login; authenticated requests lacking role receive HTTP 403.
- Changes to user role or active status in PostgreSQL take immediate effect on the next request.
"""

import pytest
from flask import Blueprint
from security.authentication import login_required
from security.decorators import (
    role_required,
    admin_required,
    manager_required,
    sales_executive_required,
)
from security.authorization import (
    visible_user_ids,
    can_access_record,
    has_role,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES_EXECUTIVE,
)
from repositories import user_repository

# Minimal test routes Blueprint used to test RBAC decorators in isolation
test_rbac_bp = Blueprint("test_rbac", __name__)


@test_rbac_bp.route("/test/protected")
@login_required
def view_protected_route():
    return "Protected Access Granted", 200


@test_rbac_bp.route("/test/admin-only")
@admin_required
def view_admin_route():
    return "Admin Access Granted", 200


@test_rbac_bp.route("/test/manager-only")
@manager_required
def view_manager_route():
    return "Manager Access Granted", 200


@test_rbac_bp.route("/test/sales-exec")
@sales_executive_required
def view_sales_route():
    return "Sales Executive Access Granted", 200


@pytest.fixture
def rbac_client(app):
    """Register test RBAC routes blueprint on the test application client."""
    if "test_rbac" not in app.blueprints:
        app.register_blueprint(test_rbac_bp)
    return app.test_client()


def login_helper(client, identifier, password):
    """Authenticate a test user and store the session cookies."""
    return client.post("/login", data={
        "identifier": identifier,
        "password": password
    }, follow_redirects=False)



# =============================================================================
# 1. AUTHENTICATED VS UNAUTHENTICATED (401 / REDIRECT SEMANTICS)
# =============================================================================

def test_anonymous_user_cannot_access_protected_route(rbac_client):
    """Anonymous user attempting to access a protected route is redirected to /login."""
    response = rbac_client.get("/test/protected", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_anonymous_user_cannot_access_role_protected_route(rbac_client):
    """Anonymous user attempting to access a role-protected route is redirected to /login."""
    response = rbac_client.get("/test/admin-only", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# =============================================================================
# 2. ROLE-BASED ACCESS CONTROL (200 OK VS 403 FORBIDDEN)
# =============================================================================

def test_admin_can_access_admin_route(rbac_client):
    """Admin role can access Admin-only route."""
    login_helper(rbac_client, "admin", "Admin@123")
    response = rbac_client.get("/test/admin-only")
    assert response.status_code == 200
    assert b"Admin Access Granted" in response.data


def test_manager_can_access_manager_route(rbac_client):
    """Manager role can access Manager-allowed route."""
    login_helper(rbac_client, "manager", "Manager@123")
    response = rbac_client.get("/test/manager-only")
    assert response.status_code == 200
    assert b"Manager Access Granted" in response.data


def test_sales_executive_can_access_sales_route(rbac_client):
    """Sales Executive role can access Sales Executive-allowed route."""
    login_helper(rbac_client, "sales1", "Sales@123")
    response = rbac_client.get("/test/sales-exec")
    assert response.status_code == 200
    assert b"Sales Executive Access Granted" in response.data


def test_sales_executive_cannot_access_admin_route_receives_403(rbac_client):
    """Sales Executive attempting to access Admin-only route receives HTTP 403 Forbidden."""
    login_helper(rbac_client, "sales1", "Sales@123")
    response = rbac_client.get("/test/admin-only", follow_redirects=False)
    assert response.status_code == 403
    assert b"403" in response.data
    assert b"Forbidden" in response.data


def test_sales_executive_cannot_access_manager_route_receives_403(rbac_client):
    """Sales Executive attempting to access Manager-only route receives HTTP 403 Forbidden."""
    login_helper(rbac_client, "sales1", "Sales@123")
    response = rbac_client.get("/test/manager-only", follow_redirects=False)
    assert response.status_code == 403


def test_manager_cannot_access_admin_route_receives_403(rbac_client):
    """Manager attempting to access Admin-only route receives HTTP 403 Forbidden."""
    login_helper(rbac_client, "manager", "Manager@123")
    response = rbac_client.get("/test/admin-only", follow_redirects=False)
    assert response.status_code == 403


def test_authenticated_unauthorized_user_is_never_redirected_to_login(rbac_client):
    """
    Non-negotiable requirement:
    Authenticated users lacking permissions receive 403, NOT a redirect to login.
    """
    login_helper(rbac_client, "sales1", "Sales@123")
    response = rbac_client.get("/test/admin-only", follow_redirects=False)
    assert response.status_code == 403
    assert "Location" not in response.headers


# =============================================================================
# 3. DATABASE-BACKED ROLE INTEGRITY & IMMEDIATE PROPAGATION
# =============================================================================

def test_role_change_in_database_takes_immediate_effect(rbac_client, db_conn):
    """
    Role changes in PostgreSQL immediately affect authorization on subsequent requests
    without requiring the user to log out and log in again.
    """
    # 1. Login as sales executive
    login_helper(rbac_client, "sales1", "Sales@123")
    # Verify sales cannot access admin route
    res1 = rbac_client.get("/test/admin-only")
    assert res1.status_code == 403

    # 2. Promote sales user to Admin (role_id = 1) in database
    user = user_repository.find_by_username("sales1", conn=db_conn)
    user_repository.update_user_role(user["user_id"], role_id=1, conn=db_conn)
    db_conn.commit()

    try:
        # 3. Next request with same session cookie must succeed as Admin
        res2 = rbac_client.get("/test/admin-only")
        assert res2.status_code == 200
        assert b"Admin Access Granted" in res2.data
    finally:
        # Restore original Sales Executive role (role_id = 3)
        user_repository.update_user_role(user["user_id"], role_id=3, conn=db_conn)
        db_conn.commit()


def test_deactivated_user_loses_access_immediately(rbac_client, db_conn):
    """
    Deactivating a user in PostgreSQL immediately revokes access on the next request,
    clearing the session.
    """
    # 1. Login as sales executive
    login_helper(rbac_client, "sales1", "Sales@123")
    res1 = rbac_client.get("/test/sales-exec")
    assert res1.status_code == 200

    # 2. Deactivate user in PostgreSQL
    user = user_repository.find_by_username("sales1", conn=db_conn)
    user_repository.update_user_status(user["user_id"], is_active=False, conn=db_conn)
    db_conn.commit()

    try:
        # 3. Next request must be rejected and redirected to login
        res2 = rbac_client.get("/test/sales-exec", follow_redirects=False)
        assert res2.status_code == 302
        assert "/login" in res2.headers["Location"]
    finally:
        # Restore active status
        user_repository.update_user_status(user["user_id"], is_active=True, conn=db_conn)
        db_conn.commit()



def test_session_role_tampering_is_ignored(rbac_client):
    """
    If an attacker attempts to inject a 'role' or 'role_name' key into the session,
    the application reloads role from PostgreSQL and ignores the session claim.
    """
    login_helper(rbac_client, "sales1", "Sales@123")

    # Tamper with session directly
    with rbac_client.session_transaction() as sess:
        sess["role"] = "Admin"
        sess["role_name"] = "Admin"

    # Should still receive 403 because real database role is Sales Executive
    response = rbac_client.get("/test/admin-only")
    assert response.status_code == 403



# =============================================================================
# 4. SCOPE & OWNERSHIP AUTHORIZATION FOUNDATION
# =============================================================================

def test_visible_user_ids_scope_boundaries():
    """
    Test visible_user_ids helper:
    - Admin: None (unrestricted)
    - Manager: None (unrestricted per default scope)
    - Sales Executive: [user_id]
    - Inactive / None: []
    """
    admin_user = {"user_id": 1, "role_name": ROLE_ADMIN, "is_active": True}
    manager_user = {"user_id": 2, "role_name": ROLE_MANAGER, "is_active": True}
    sales_user = {"user_id": 3, "role_name": ROLE_SALES_EXECUTIVE, "is_active": True}
    inactive_user = {"user_id": 4, "role_name": ROLE_ADMIN, "is_active": False}

    assert visible_user_ids(admin_user) is None
    assert visible_user_ids(manager_user) is None
    assert visible_user_ids(sales_user) == [3]
    assert visible_user_ids(inactive_user) == []
    assert visible_user_ids(None) == []


def test_can_access_record_authorization():
    """
    Test can_access_record helper:
    - Admin & Manager can access any assigned record.
    - Sales Executive can only access records assigned to themselves.
    """
    admin_user = {"user_id": 1, "role_name": ROLE_ADMIN, "is_active": True}
    manager_user = {"user_id": 2, "role_name": ROLE_MANAGER, "is_active": True}
    sales_user = {"user_id": 3, "role_name": ROLE_SALES_EXECUTIVE, "is_active": True}

    # Admin and Manager can access record assigned to user 3 or user 99
    assert can_access_record(admin_user, record_assigned_to=3) is True
    assert can_access_record(admin_user, record_assigned_to=99) is True
    assert can_access_record(manager_user, record_assigned_to=3) is True
    assert can_access_record(manager_user, record_assigned_to=99) is True

    # Sales Executive can only access records assigned to user 3
    assert can_access_record(sales_user, record_assigned_to=3) is True
    assert can_access_record(sales_user, record_assigned_to=2) is False
    assert can_access_record(sales_user, record_assigned_to=99) is False
