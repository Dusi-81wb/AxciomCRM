"""
Configuration module for AcxiomCRM.

Provides environment-based configuration for Development, Testing, and Production environments.
All sensitive settings (SECRET_KEY, DATABASE_URL) are read from environment variables
to prevent hardcoding secrets in source code.
"""

import os
from dotenv import load_dotenv

# Load local environment variables from a .env file if present
load_dotenv()


class Config:
    """Base configuration with shared defaults and security settings."""

    # Secret key for signing session cookies and CSRF tokens
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret-key-replace-in-env")

    # PostgreSQL database connection URL for psycopg2
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:password@localhost:5432/acxiomcrm"
    )

    # Session cookie security settings
    # In production, SESSION_COOKIE_SECURE must be True (requires HTTPS)
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() in ("true", "1")
    SESSION_COOKIE_HTTPONLY = os.environ.get("SESSION_COOKIE_HTTPONLY", "True").lower() in ("true", "1")
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")

    # Business timezone mandated by MASTER_BLUEPRINT.md
    APPLICATION_TIMEZONE = os.environ.get("APPLICATION_TIMEZONE", "Asia/Kolkata")

    # Account security parameters
    PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", "8"))
    MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
    LOCKOUT_DURATION_MINUTES = int(os.environ.get("LOCKOUT_DURATION_MINUTES", "15"))

    # Testing flag
    TESTING = False
    DEBUG = False


class DevelopmentConfig(Config):
    """Configuration for local development."""

    DEBUG = True


class TestingConfig(Config):
    """Configuration for automated tests."""

    TESTING = True
    DEBUG = True
    # Test database URL is isolated from development/production
    DATABASE_URL = os.environ.get(
        "TEST_DATABASE_URL", "postgresql://postgres:password@localhost:5432/acxiomcrm_test"
    )
    # Testing over plain HTTP
    SESSION_COOKIE_SECURE = False
    # Disable CSRF in tests to simplify automated testing of endpoints
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Configuration for production deployment."""

    DEBUG = False
    SESSION_COOKIE_SECURE = True


# Simple dictionary mapping for convenient configuration selection
config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
