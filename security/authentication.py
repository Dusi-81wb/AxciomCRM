"""
Authentication Security Foundation for AcxiomCRM.

Provides current-user resolution and session verification for protected requests.
Per MASTER_BLUEPRINT.md Section 39:
- Protected requests reload the user identity from PostgreSQL on each request.
- Never trusts stale role information stored only in the session cookie.
- If an account has been deactivated or removed in the database, the session is cleared immediately.
"""

from functools import wraps
from flask import session, g, redirect, url_for, flash, request
from repositories import user_repository


def get_current_user():
    """
    Load the currently authenticated user from PostgreSQL.
    Caches the user record on Flask's 'g' object for the duration of the request.

    :return: User dictionary (including current database role_name) or None.
    """
    if hasattr(g, "current_user"):
        return g.current_user

    user_id = session.get("user_id")
    if not user_id:
        g.current_user = None
        return None

    # Always reload user from PostgreSQL to verify current active status and current role
    user = user_repository.find_by_id(user_id)

    # If user does not exist or has been deactivated by an admin:
    if not user or not user.get("is_active", True):
        session.clear()
        g.current_user = None
        return None

    g.current_user = user
    return user


def login_required(f):
    """
    Decorator to protect views requiring an authenticated user.
    Redirects unauthenticated users to the login page.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = get_current_user()
        if current_user is None:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def init_app(app):
    """
    Register authentication context processors and hooks with the Flask application.
    Makes 'current_user' available in all Jinja templates.
    """
    @app.context_processor
    def inject_current_user():
        return {"current_user": get_current_user()}

    @app.teardown_request
    def clear_request_user(exception=None):
        """Ensure cached user does not persist across requests."""
        if hasattr(g, "current_user"):
            del g.current_user

