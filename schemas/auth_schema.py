"""
Authentication Schemas for AcxiomCRM.

Performs field-level and form-level validation for registration and login requests.
Separates schema checks from database queries and service orchestration.
"""

from validation.business_rules import (
    validate_password_policy,
    validate_username,
    validate_email_format,
)


def validate_registration_form(form_data, min_password_length=8):
    """
    Validate incoming registration request data.

    :param form_data: Mapping/dict containing username, email, password, confirm_password.
    :param min_password_length: Minimum password length configured in app settings.
    :return: Dict of field errors {field_name: error_message}. Empty dict if valid.
    """
    errors = {}

    username = form_data.get("username", "")
    email = form_data.get("email", "")
    password = form_data.get("password", "")
    confirm_password = form_data.get("confirm_password", "")

    # 1. Username validation
    valid_u, u_err = validate_username(username)
    if not valid_u:
        errors["username"] = u_err

    # 2. Email format validation
    valid_e, e_err = validate_email_format(email)
    if not valid_e:
        errors["email"] = e_err

    # 3. Password policy validation
    valid_p, p_err = validate_password_policy(password, min_length=min_password_length)
    if not valid_p:
        errors["password"] = p_err

    # 4. Password confirmation match
    if password and confirm_password != password:
        errors["confirm_password"] = "Passwords do not match."

    return errors


def validate_login_form(form_data):
    """
    Validate incoming login request data.

    :param form_data: Mapping/dict containing identifier and password.
    :return: Dict of field errors {field_name: error_message}. Empty dict if valid.
    """
    errors = {}

    identifier = form_data.get("identifier", "")
    password = form_data.get("password", "")

    if not identifier or not identifier.strip():
        errors["identifier"] = "Username or email is required."

    if not password:
        errors["password"] = "Password is required."

    return errors
