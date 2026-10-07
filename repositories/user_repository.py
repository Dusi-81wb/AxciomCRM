"""
User Repository for AcxiomCRM.

Encapsulates all SQL data access for the 'users' entity using raw psycopg2.
In accordance with architecture guidelines:
- All SQL queries are strictly parameterized with %s placeholders.
- No business logic or password hashing exists here.
- Functions accept an optional database connection to support transaction boundaries.
"""

from database import get_db_connection


def _row_to_dict(cursor, row):
    """Convert a database row tuple into a dictionary using column names."""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def find_by_id(user_id, conn=None):
    """
    Retrieve user by primary key ID, joined with role name.
    Used for current user loading on protected requests.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT u.user_id, u.username, u.email, u.password_hash, u.is_active,
                   u.failed_login_attempts, u.lockout_until, u.created_date,
                   u.modified_date, u.last_login_date, u.role_id, r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.user_id = %s;
        """, (user_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def find_by_username(username, conn=None):
    """Find a user record by username (case-sensitive exact match)."""
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT user_id, username, email, password_hash, is_active,
                   failed_login_attempts, lockout_until, created_date,
                   modified_date, last_login_date, role_id
            FROM users
            WHERE username = %s;
        """, (username,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def find_by_email(email, conn=None):
    """Find a user record by email address (case-insensitive search)."""
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT user_id, username, email, password_hash, is_active,
                   failed_login_attempts, lockout_until, created_date,
                   modified_date, last_login_date, role_id
            FROM users
            WHERE LOWER(email) = LOWER(%s);
        """, (email,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def find_by_identifier(identifier, conn=None):
    """
    Find a user by either username or email.
    Supports flexible login credential input without leaking account existence.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT user_id, username, email, password_hash, is_active,
                   failed_login_attempts, lockout_until, created_date,
                   modified_date, last_login_date, role_id
            FROM users
            WHERE username = %s OR LOWER(email) = LOWER(%s);
        """, (identifier, identifier))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def create_user(username, email, password_hash, role_id=3, is_active=True, conn=None):
    """
    Insert a new user record.
    Default role_id is 3 (Sales Executive) as mandated by blueprint registration rules.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO users (username, email, password_hash, role_id, is_active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING user_id, username, email, role_id, is_active;
        """, (username, email, password_hash, role_id, is_active))
        row = cur.fetchone()
        if conn is None:
            connection.commit()
        return _row_to_dict(cur, row)


def increment_failed_attempts(user_id, conn=None):
    """
    Increment the failed login attempt counter by 1.
    Returns the updated failed attempt count.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE users
            SET failed_login_attempts = failed_login_attempts + 1,
                modified_date = CURRENT_TIMESTAMP
            WHERE user_id = %s
            RETURNING failed_login_attempts;
        """, (user_id,))
        count = cur.fetchone()[0]
        if conn is None:
            connection.commit()
        return count


def set_lockout(user_id, lockout_until, conn=None):
    """
    Set the lockout expiration timestamp for a user.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE users
            SET lockout_until = %s,
                modified_date = CURRENT_TIMESTAMP
            WHERE user_id = %s;
        """, (lockout_until, user_id))
        if conn is None:
            connection.commit()


def reset_failed_attempts(user_id, conn=None):
    """
    Reset failed login attempts to 0, clear lockout_until, and update last_login_date.
    Executed immediately upon successful authentication.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE users
            SET failed_login_attempts = 0,
                lockout_until = NULL,
                last_login_date = CURRENT_TIMESTAMP,
                modified_date = CURRENT_TIMESTAMP
            WHERE user_id = %s;
        """, (user_id,))
        if conn is None:
            connection.commit()


def update_user_role(user_id, role_id, conn=None):
    """
    Update the role_id of a user in PostgreSQL.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE users
            SET role_id = %s,
                modified_date = CURRENT_TIMESTAMP
            WHERE user_id = %s;
        """, (role_id, user_id))
        if conn is None:
            connection.commit()


def update_user_status(user_id, is_active, conn=None):
    """
    Update the is_active status of a user in PostgreSQL.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE users
            SET is_active = %s,
                modified_date = CURRENT_TIMESTAMP
            WHERE user_id = %s;
        """, (is_active, user_id))
        if conn is None:
            connection.commit()

