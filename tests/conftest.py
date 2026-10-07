"""
Pytest configuration and fixtures for AcxiomCRM.

Provides standard test fixtures for the Flask application, test client, and test database connection.
Uses TestingConfig to ensure an isolated testing environment against PostgreSQL.
"""

import pytest
import psycopg2
from app import create_app
from config import TestingConfig
from database import init_db, seed_db


@pytest.fixture
def app():
    """
    Create and configure a Flask application instance for testing.
    Uses TestingConfig where TESTING=True and WTF_CSRF_ENABLED=False.
    """
    application = create_app(config_object=TestingConfig)

    with application.app_context():
        yield application


@pytest.fixture
def client(app):
    """
    Test client for sending HTTP requests to the application without a running web server.
    """
    return app.test_client()


@pytest.fixture
def runner(app):
    """
    Test CLI runner for invoking Click/Flask commands.
    """
    return app.test_cli_runner()


@pytest.fixture(scope="session")
def setup_test_db():
    """
    Session-level fixture that initializes test database schema and seed data.
    """
    db_url = TestingConfig.DATABASE_URL
    init_db(db_url=db_url)
    seed_db(db_url=db_url)
    return db_url


@pytest.fixture
def db_conn(setup_test_db):
    """
    Provides a per-test psycopg2 connection to the isolated test database.
    """
    conn = psycopg2.connect(setup_test_db)
    yield conn
    if not conn.closed:
        conn.close()
