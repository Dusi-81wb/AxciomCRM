"""
Audit Service for AcxiomCRM.

Coordinates system audit logging across authentication and CRM modules.
Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md:
- Implements audit logging for authentication, security, and data events.
- Strictly forbids storing sensitive secrets (passwords, hashes, tokens, API keys).
- Supports atomic transaction binding via optional 'conn' parameter:
  Normal business data changes + audit log record must commit/rollback together.
- For failed login and security rejection events where no business transaction exists,
  records are committed independently.
- Sanitizes old_value and new_value payloads.
"""

from flask import has_request_context, request, session, g
from repositories import audit_repository

# Standard Action Constants
ACTION_LOGIN_SUCCESS = "LOGIN_SUCCESS"
ACTION_LOGIN_FAILED = "LOGIN_FAILED"
ACTION_ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
ACTION_LOGOUT = "LOGOUT"
ACTION_ROLE_CHANGED = "ROLE_CHANGED"
ACTION_PASSWORD_CHANGED = "PASSWORD_CHANGED"
ACTION_ACCOUNT_ACTIVATED = "ACCOUNT_ACTIVATED"
ACTION_ACCOUNT_DEACTIVATED = "ACCOUNT_DEACTIVATED"
ACTION_CREATE = "CREATE"
ACTION_UPDATE = "UPDATE"
ACTION_DELETE = "DELETE"
ACTION_STATUS_CHANGE = "STATUS_CHANGE"

# Standard Entity Constants
ENTITY_AUTH = "AUTH"
ENTITY_USER = "USER"
ENTITY_CUSTOMER = "CUSTOMER"
ENTITY_LEAD = "LEAD"
ENTITY_OPPORTUNITY = "OPPORTUNITY"
ENTITY_FOLLOWUP = "FOLLOWUP"
ENTITY_ACTIVITY = "ACTIVITY"
ENTITY_SECURITY = "SECURITY"

# Blacklist of keys that must NEVER be written to audit logs
SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "confirm_password",
    "token",
    "secret",
    "csrf_token",
    "api_key",
    "secret_key"
}


def sanitize_payload(data):
    """
    Recursively sanitize dictionaries/lists to ensure sensitive keys are redacted.

    :param data: Input data (dict, list, or primitive).
    :return: Sanitized copy with sensitive values replaced by '[REDACTED]'.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_payload(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_payload(item) for item in data]
    return data


def log_event(
    action,
    entity_name,
    user_id=None,
    record_id=None,
    old_value=None,
    new_value=None,
    result="Success",
    ip_address=None,
    conn=None
):
    """
    Record an audit trail event.

    Automatically extracts current actor user_id and IP address from Flask request context
    if they are not explicitly supplied.

    :param action: Action performed (e.g. 'LOGIN_SUCCESS', 'CREATE').
    :param entity_name: Affected module/entity (e.g. 'AUTH', 'USER', 'CUSTOMER').
    :param user_id: ID of the user performing the action (or None).
    :param record_id: Identifier of the subject record as string (or None).
    :param old_value: State prior to action (or None).
    :param new_value: State following action (or None).
    :param result: 'Success', 'Failure', etc.
    :param ip_address: Remote client IP address (or None).
    :param conn: Active psycopg2 connection if part of a parent business transaction.
    :return: Created audit record dict.
    """
    # Context-aware fallback for actor user_id
    if user_id is None and has_request_context():
        if hasattr(g, "current_user") and g.current_user:
            user_id = g.current_user.get("user_id")
        elif "user_id" in session:
            user_id = session.get("user_id")

    # Context-aware fallback for IP address
    if ip_address is None and has_request_context():
        ip_address = request.remote_addr

    # Sanitize payload dictionaries to prevent accidental credential leakage
    safe_old_value = sanitize_payload(old_value) if old_value is not None else None
    safe_new_value = sanitize_payload(new_value) if new_value is not None else None

    return audit_repository.create_audit_log(
        action=action,
        entity_name=entity_name,
        user_id=user_id,
        record_id=str(record_id) if record_id is not None else None,
        old_value=safe_old_value,
        new_value=safe_new_value,
        result=result,
        ip_address=ip_address,
        conn=conn
    )


def log_login_success(user, ip_address=None, conn=None):
    """Log an authenticated login event."""
    return log_event(
        action=ACTION_LOGIN_SUCCESS,
        entity_name=ENTITY_AUTH,
        user_id=user["user_id"],
        record_id=str(user["user_id"]),
        result="Success",
        ip_address=ip_address,
        conn=conn
    )


def log_login_failed(identifier, user=None, ip_address=None, conn=None):
    """
    Log an authentication failure.
    Passwords and sensitive candidate values are never stored.
    """
    user_id = user["user_id"] if user else None
    record_id = str(user_id) if user_id else None
    return log_event(
        action=ACTION_LOGIN_FAILED,
        entity_name=ENTITY_AUTH,
        user_id=user_id,
        record_id=record_id,
        result="Failure",
        ip_address=ip_address,
        conn=conn
    )


def log_account_locked(user, ip_address=None, conn=None):
    """Log an account lockout event triggered by excessive failed login attempts."""
    return log_event(
        action=ACTION_ACCOUNT_LOCKED,
        entity_name=ENTITY_AUTH,
        user_id=user["user_id"],
        record_id=str(user["user_id"]),
        result="Locked",
        ip_address=ip_address,
        conn=conn
    )


def log_logout(user_id, ip_address=None, conn=None):
    """Log an explicit session termination event."""
    return log_event(
        action=ACTION_LOGOUT,
        entity_name=ENTITY_AUTH,
        user_id=user_id,
        record_id=str(user_id) if user_id else None,
        result="Success",
        ip_address=ip_address,
        conn=conn
    )


def log_role_changed(target_user_id, old_role, new_role, actor_user_id=None, ip_address=None, conn=None):
    """Log a user role modification event."""
    return log_event(
        action=ACTION_ROLE_CHANGED,
        entity_name=ENTITY_USER,
        user_id=actor_user_id,
        record_id=str(target_user_id),
        old_value={"role": old_role},
        new_value={"role": new_role},
        result="Success",
        ip_address=ip_address,
        conn=conn
    )


def get_audit_trail(
    user_id=None,
    entity_name=None,
    action=None,
    start_date=None,
    end_date=None,
    limit=50,
    offset=0,
    sort_by="created_date",
    sort_order="DESC"
):
    """Query audit logs with criteria filtering and pagination."""
    return audit_repository.find_audit_logs(
        user_id=user_id,
        entity_name=entity_name,
        action=action,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order
    )


def get_audit_record(audit_log_id):
    """Retrieve an audit log by its primary key ID."""
    return audit_repository.get_audit_log_by_id(audit_log_id)
