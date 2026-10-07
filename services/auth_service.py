"""
Authentication Service for AcxiomCRM.

Orchestrates user registration, password verification, lockout logic, and session state.
In accordance with MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md:
- Uses Werkzeug password hashing (generate_password_hash, check_password_hash).
- Self-registration always assigns the 'Sales Executive' role (role_id = 3).
- Uses generic 'Invalid credentials' error for all login failures to prevent account enumeration.
- Enforces account lockout when failed login attempts reach MAX_LOGIN_ATTEMPTS.
- Clears the session on login before establishing the authenticated state.
"""

from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app, session

from repositories import user_repository
from schemas.auth_schema import validate_registration_form, validate_login_form
from services import audit_service


GENERIC_LOGIN_ERROR = "Invalid credentials"


def is_account_locked(lockout_until):
    """
    Check if a user account is currently locked.

    :param lockout_until: Datetime timestamp from database or None.
    :return: True if lockout is active; False otherwise.
    """
    if not lockout_until:
        return False

    now = datetime.now(timezone.utc)
    # Normalize timezone awareness
    if lockout_until.tzinfo is None:
        lockout_until = lockout_until.replace(tzinfo=timezone.utc)

    return lockout_until > now


def register_user(form_data):
    """
    Register a new user account as a Sales Executive.

    :param form_data: Dict containing username, email, password, confirm_password.
    :return: Tuple (success: bool, user_data: dict or None, errors: dict).
    """
    min_len = current_app.config.get("PASSWORD_MIN_LENGTH", 8)
    errors = validate_registration_form(form_data, min_password_length=min_len)

    if errors:
        return False, None, errors

    username = form_data["username"].strip()
    email = form_data["email"].strip().lower()
    password = form_data["password"]

    # Check for duplicate username
    if user_repository.find_by_username(username):
        errors["username"] = "Username is already taken."

    # Check for duplicate email
    if user_repository.find_by_email(email):
        errors["email"] = "Email address is already registered."

    if errors:
        return False, None, errors

    # Securely hash password using Werkzeug's adaptive algorithm
    password_hash = generate_password_hash(password)

    # Public registration unconditionally assigns Sales Executive (role_id = 3)
    user = user_repository.create_user(
        username=username,
        email=email,
        password_hash=password_hash,
        role_id=3,
        is_active=True
    )

    # Record user creation audit event
    audit_service.log_event(
        action=audit_service.ACTION_CREATE,
        entity_name=audit_service.ENTITY_USER,
        user_id=user["user_id"],
        record_id=str(user["user_id"]),
        result="Success"
    )

    return True, user, {}


def authenticate_user(identifier, password):
    """
    Verify credentials and manage failed attempts / lockout state.
    Integrates with audit_service for security event tracking.

    :param identifier: Username or email string.
    :param password: Plaintext candidate password.
    :return: Tuple (success: bool, user_dict: dict or None, error_message: str or None).
    """
    form_errors = validate_login_form({"identifier": identifier, "password": password})
    if form_errors:
        return False, None, GENERIC_LOGIN_ERROR

    identifier = identifier.strip()
    user = user_repository.find_by_identifier(identifier)

    # 1. User does not exist -> log failure and return generic error
    if not user:
        audit_service.log_login_failed(identifier=identifier, user=None)
        return False, None, GENERIC_LOGIN_ERROR

    user_id = user["user_id"]
    max_attempts = current_app.config.get("MAX_LOGIN_ATTEMPTS", 5)
    lockout_duration = current_app.config.get("LOCKOUT_DURATION_MINUTES", 15)

    # 2. Check if currently locked out
    if is_account_locked(user.get("lockout_until")):
        # Reject without revealing lockout status to prevent enumeration
        audit_service.log_login_failed(identifier=identifier, user=user)
        return False, None, GENERIC_LOGIN_ERROR

    # 3. Check if account is active
    if not user.get("is_active", True):
        # Inactive accounts cannot authenticate
        audit_service.log_login_failed(identifier=identifier, user=user)
        return False, None, GENERIC_LOGIN_ERROR

    # 4. Verify password hash
    if not check_password_hash(user["password_hash"], password):
        # Increment failed login attempts
        attempts = user_repository.increment_failed_attempts(user_id)
        audit_service.log_login_failed(identifier=identifier, user=user)

        # Check if threshold reached
        if attempts >= max_attempts:
            lockout_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_duration)
            user_repository.set_lockout(user_id, lockout_until)
            audit_service.log_account_locked(user=user)

        return False, None, GENERIC_LOGIN_ERROR

    # 5. Successful authentication
    user_repository.reset_failed_attempts(user_id)
    audit_service.log_login_success(user=user)
    return True, user, None


def login_user_session(user):
    """
    Establish a secure authenticated session.
    Clears existing session first to prevent session fixation.

    :param user: Validated user dict from database.
    """
    session.clear()
    session["user_id"] = user["user_id"]
    session["username"] = user["username"]


def logout_user_session():
    """
    Clear all session state to terminate the authenticated session.
    Audits the logout event before session destruction.
    """
    user_id = session.get("user_id")
    session.clear()
    if user_id:
        audit_service.log_logout(user_id=user_id)

