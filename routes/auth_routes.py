"""
Authentication Routes for AcxiomCRM.

Handles HTTP request reception, parameter parsing, template rendering, and redirects
for user registration, login, logout, and the landing page.
Adheres strictly to layered architecture:
- Contains no SQL queries (all data access is in repositories/user_repository.py).
- Contains no password hashing logic (all business orchestration is in services/auth_service.py).
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from extensions import limiter
from services import auth_service
from security.authentication import get_current_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/", methods=["GET"])
def index():
    """Application landing page displaying authenticated status or public entry options."""
    return render_template("index.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"], exempt_when=lambda: current_app.config.get("TESTING", False))
def login():
    """
    Handle user login form display (GET) and credential authentication (POST).
    """
    # If already authenticated, redirect to home page
    if request.method == "GET" and get_current_user() is not None:
        return redirect(url_for("auth.index"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        success, user, error_message = auth_service.authenticate_user(identifier, password)

        if success:
            auth_service.login_user_session(user)
            flash(f"Welcome back, {user['username']}!", "success")

            # Validate next URL to avoid open redirect vulnerability
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return redirect(url_for("auth.index"))

        # Generic error message avoids username/email enumeration
        flash(error_message, "danger")
        return render_template(
            "login.html",
            form_data={"identifier": identifier},
            errors={"identifier": error_message}
        ), 401

    return render_template("login.html", form_data={}, errors={})


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"], exempt_when=lambda: current_app.config.get("TESTING", False))
def register():
    """
    Handle user registration form display (GET) and account creation (POST).
    Self-registered accounts are unconditionally assigned the 'Sales Executive' role.
    """
    # If already authenticated, redirect to home page
    if request.method == "GET" and get_current_user() is not None:
        return redirect(url_for("auth.index"))

    if request.method == "POST":
        success, user, errors = auth_service.register_user(request.form)

        if success:
            flash("Registration successful. Please log in with your credentials.", "success")
            return redirect(url_for("auth.login"))

        # Return form with validation errors and HTTP 400 Bad Request
        return render_template("register.html", form_data=request.form, errors=errors), 400

    return render_template("register.html", form_data={}, errors={})


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """
    Terminate authenticated session and redirect to login page.
    Requires POST method protected by CSRF token.
    """
    auth_service.logout_user_session()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("auth.login"))
