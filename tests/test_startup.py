"""
Startup and Foundation Unit Tests for AcxiomCRM.

Verifies:
1. Flask application factory initializes correctly.
2. Testing configuration is loaded properly.
3. Core extensions (CSRF, Limiter) are registered.
4. Minimal startup/health verification endpoint (/health) responds with 200 OK.
"""

from database import close_db_connection


def test_app_creation(app):
    """
    Verify that create_app() produces a valid Flask application
    and that TestingConfig flags are active.
    """
    assert app is not None
    assert app.config["TESTING"] is True
    assert app.config["WTF_CSRF_ENABLED"] is False
    assert app.config["APPLICATION_TIMEZONE"] == "Asia/Kolkata"


def test_extensions_initialized(app):
    """
    Verify that required Phase 0 extensions (CSRFProtect, Limiter)
    are registered in the application's extension dictionary.
    """
    assert "csrf" in app.extensions
    assert "limiter" in app.extensions


def test_database_teardown_registered(app):
    """
    Verify that the database connection teardown handler is registered
    with Flask to prevent connection leaks.
    """
    assert close_db_connection in app.teardown_appcontext_funcs


def test_health_check_endpoint(client):
    """
    Verify that the development/startup verification endpoint (/health)
    responds with HTTP 200 and expected status information.
    """
    response = client.get("/health")
    assert response.status_code == 200

    data = response.get_json()
    assert data is not None
    assert data["status"] == "healthy"
    assert data["phase"] == "Phase 0 — Project Foundation"
    assert "initialized successfully" in data["message"]


def test_health_check_method_not_allowed(client):
    """
    Verify that state-changing HTTP methods on /health are rejected with 405 Method Not Allowed.
    """
    response = client.post("/health")
    assert response.status_code == 405
