"""
Authorization Decorators for AcxiomCRM.

Provides role-based access control decorators for Flask route handlers.
Adheres strictly to MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md:
- Never trusts stale session cookies; reloads user from PostgreSQL via get_current_user().
- Correct 401 vs 403 semantics:
  - Unauthenticated users are redirected to login (or 401).
  - Authenticated users without required role receive HTTP 403 Forbidden (never redirected to login).
"""

from functools import wraps
from flask import abort, flash, redirect, url_for, request
from security.authentication import get_current_user, login_required
from security.authorization import (
    has_role,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES_EXECUTIVE,
)


def role_required(*allowed_roles):
    """
    Route decorator requiring the authenticated user to possess at least one of the specified roles.

    Evaluation steps:
    1. Resolve database-backed current_user via get_current_user().
    2. If unauthenticated -> flash notice and redirect to login page.
    3. If authenticated but role is not permitted -> abort with HTTP 403 Forbidden.
    4. If role is permitted -> execute the view handler.

    :param allowed_roles: Strings representing allowed roles (e.g. 'Admin', 'Manager').
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            current_user = get_current_user()

            # 1. Unauthenticated request -> redirect to login
            if current_user is None:
                flash("Please log in to access this page.", "warning")
                return redirect(url_for("auth.login", next=request.path))

            # 2. Authenticated user lacks required role -> 403 Forbidden
            if not has_role(current_user, *allowed_roles):
                abort(403)

            # 3. Authorized -> proceed
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Convenience decorator restricting access strictly to Administrators."""
    return role_required(ROLE_ADMIN)(f)


def manager_required(f):
    """Convenience decorator permitting Administrators and Managers."""
    return role_required(ROLE_ADMIN, ROLE_MANAGER)(f)


def sales_executive_required(f):
    """Convenience decorator permitting all authenticated CRM roles."""
    return role_required(ROLE_ADMIN, ROLE_MANAGER, ROLE_SALES_EXECUTIVE)(f)
