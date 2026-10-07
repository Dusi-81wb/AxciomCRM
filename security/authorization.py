"""
Authorization and Role-Based Access Control (RBAC) Foundation for AcxiomCRM.

Defines roles, role-checking utilities, and data ownership/scope boundaries.
Per MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md:
- Exactly three primary roles: 'Admin', 'Manager', 'Sales Executive'.
- Roles are strictly validated against the database-backed user record, never trusting session state alone.
- Visible scope helper (visible_user_ids) centralizes query filtering boundaries:
  - Admin: Unrestricted (sees all records).
  - Manager: Sees all CRM records (per approved default until evaluator clarifies team hierarchy).
  - Sales Executive: Assigned records only (assigned_to = user_id).
"""

ROLE_ADMIN = "Admin"
ROLE_MANAGER = "Manager"
ROLE_SALES_EXECUTIVE = "Sales Executive"

ALL_ROLES = (ROLE_ADMIN, ROLE_MANAGER, ROLE_SALES_EXECUTIVE)

# Mapping from role_id to canonical role_name matching sql/schema.sql and sql/seed.sql
ROLE_ID_MAP = {
    1: ROLE_ADMIN,
    2: ROLE_MANAGER,
    3: ROLE_SALES_EXECUTIVE,
}


def has_role(user, *allowed_roles):
    """
    Check if the user is active and possesses one of the allowed roles.

    :param user: Database-backed user dictionary containing 'role_name' and 'is_active'.
    :param allowed_roles: Strings representing permissible roles (e.g., 'Admin', 'Manager').
    :return: True if user is active and has one of the specified roles; False otherwise.
    """
    if not user:
        return False

    if not user.get("is_active", True):
        return False

    user_role = user.get("role_name")
    if not user_role:
        role_id = user.get("role_id")
        user_role = ROLE_ID_MAP.get(role_id)

    return user_role in allowed_roles


def is_admin(user):
    """Return True if user is an active Administrator."""
    return has_role(user, ROLE_ADMIN)


def is_manager(user):
    """Return True if user is an active Manager."""
    return has_role(user, ROLE_MANAGER)


def is_sales_executive(user):
    """Return True if user is an active Sales Executive."""
    return has_role(user, ROLE_SALES_EXECUTIVE)


def visible_user_ids(user):
    """
    Determine the list of user IDs whose assigned records this user is authorized to access.
    Used by repository layers to apply server-side SQL predicates (WHERE assigned_to = %s).

    Scope Rules (MASTER_BLUEPRINT.md Section 44 & SPECIFICATION_NOTES.md Section 7):
    - Admin: Unrestricted -> Returns None (meaning no SQL WHERE filter needed).
    - Manager: Unrestricted CRM records -> Returns None (default scope until team model is clarified).
    - Sales Executive: Assigned records only -> Returns [user_id].
    - Unauthenticated/Inactive: Returns [] (no records visible).

    :param user: Current database-backed user dictionary.
    :return: None if unrestricted, or a list of authorized integer user IDs.
    """
    if not user or not user.get("is_active", True):
        return []

    user_role = user.get("role_name")
    if not user_role:
        user_role = ROLE_ID_MAP.get(user.get("role_id"))

    if user_role in (ROLE_ADMIN, ROLE_MANAGER):
        return None

    if user_role == ROLE_SALES_EXECUTIVE:
        return [user["user_id"]]

    return []


def can_access_record(user, record_assigned_to):
    """
    Check if a user is permitted to view or edit a specific record based on its owner.

    :param user: Current database-backed user dictionary.
    :param record_assigned_to: Integer user_id to whom the record is assigned, or None.
    :return: True if authorized, False otherwise.
    """
    if not user or not user.get("is_active", True):
        return False

    user_role = user.get("role_name")
    if not user_role:
        user_role = ROLE_ID_MAP.get(user.get("role_id"))

    if user_role in (ROLE_ADMIN, ROLE_MANAGER):
        return True

    if user_role == ROLE_SALES_EXECUTIVE:
        return record_assigned_to == user.get("user_id")

    return False
