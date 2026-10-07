"""
Audit Repository for AcxiomCRM.

Encapsulates all SQL data access for the 'audit_logs' table using raw psycopg2.
In accordance with MASTER_BLUEPRINT.md and SPECIFICATION_NOTES.md:
- All SQL is strictly parameterized with %s placeholders.
- Supports external connection passing (conn) for atomic transaction binding with business operations.
- Dynamic filtering (user, module/entity, action, date range) and sorting strictly use whitelist validation.
- Audit records are append-oriented; no application-level update or delete functions exist.
"""

import json
from database import get_db_connection

# Explicit whitelists for dynamic query parameters to prevent SQL injection
ALLOWED_SORT_COLUMNS = {
    "audit_log_id": "audit_log_id",
    "created_date": "created_date",
    "action": "action",
    "entity_name": "entity_name",
    "user_id": "user_id",
    "result": "result",
}

ALLOWED_SORT_ORDERS = {
    "asc": "ASC",
    "desc": "DESC",
}


def _row_to_dict(cursor, row):
    """Convert a database row tuple into a dictionary using cursor column descriptions."""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def create_audit_log(
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
    Insert a new historical audit log record into PostgreSQL.

    :param action: Action performed (e.g. 'LOGIN_SUCCESS', 'CREATE', 'LOGOUT').
    :param entity_name: Entity/module involved (e.g. 'AUTH', 'USER', 'CUSTOMER').
    :param user_id: ID of the user performing the action, or None.
    :param record_id: Target entity identifier as string, or None.
    :param old_value: Dict or JSON string representing prior state, or None.
    :param new_value: Dict or JSON string representing new state, or None.
    :param result: Outcome string ('Success', 'Failure', etc.).
    :param ip_address: Client IP address string, or None.
    :param conn: Optional psycopg2 connection to join an ongoing business transaction.
    :return: Dictionary of the inserted audit record.
    """
    connection = conn or get_db_connection()

    # Serialize dictionaries to JSON strings for JSONB columns if needed
    old_val_json = json.dumps(old_value) if isinstance(old_value, (dict, list)) else old_value
    new_val_json = json.dumps(new_value) if isinstance(new_value, (dict, list)) else new_value

    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO audit_logs (
                user_id, action, entity_name, record_id, old_value, new_value, result, ip_address
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING audit_log_id, user_id, action, entity_name, record_id,
                      old_value, new_value, result, created_date, ip_address;
        """, (
            user_id,
            action,
            entity_name,
            str(record_id) if record_id is not None else None,
            old_val_json,
            new_val_json,
            result,
            ip_address
        ))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    # Only commit if repository opened the connection itself.
    # If conn was passed in, caller owns the transaction boundary (commit or rollback).
    if conn is None:
        connection.commit()

    return record


def get_audit_log_by_id(audit_log_id, conn=None):
    """Retrieve an audit log entry by its primary key ID."""
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT a.audit_log_id, a.user_id, a.action, a.entity_name, a.record_id,
                   a.old_value, a.new_value, a.result, a.created_date, a.ip_address,
                   u.username
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.user_id
            WHERE a.audit_log_id = %s;
        """, (audit_log_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def find_audit_logs(
    user_id=None,
    entity_name=None,
    action=None,
    start_date=None,
    end_date=None,
    limit=50,
    offset=0,
    sort_by="created_date",
    sort_order="DESC",
    conn=None
):
    """
    Search and filter audit logs using parameterized SQL and whitelist sorting.

    :param user_id: Filter by actor user_id.
    :param entity_name: Filter by module/entity name.
    :param action: Filter by action string.
    :param start_date: Filter records created on or after this timestamp.
    :param end_date: Filter records created on or before this timestamp.
    :param limit: Maximum records to return.
    :param offset: Pagination offset.
    :param sort_by: Column to sort by (must be in ALLOWED_SORT_COLUMNS).
    :param sort_order: Sort order ('ASC' or 'DESC').
    :param conn: Optional active connection.
    :return: List of audit record dictionaries.
    """
    connection = conn or get_db_connection()

    # Validate sort column and order against whitelists
    sort_col = ALLOWED_SORT_COLUMNS.get(sort_by.lower(), "created_date")
    order_dir = ALLOWED_SORT_ORDERS.get(sort_order.lower(), "DESC")

    conditions = []
    params = []

    if user_id is not None:
        conditions.append("a.user_id = %s")
        params.append(user_id)

    if entity_name:
        conditions.append("a.entity_name = %s")
        params.append(entity_name)

    if action:
        conditions.append("a.action = %s")
        params.append(action)

    if start_date:
        conditions.append("a.created_date >= %s")
        params.append(start_date)

    if end_date:
        conditions.append("a.created_date <= %s")
        params.append(end_date)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT a.audit_log_id, a.user_id, a.action, a.entity_name, a.record_id,
               a.old_value, a.new_value, a.result, a.created_date, a.ip_address,
               u.username
        FROM audit_logs a
        LEFT JOIN users u ON a.user_id = u.user_id
        {where_clause}
        ORDER BY a.{sort_col} {order_dir}
        LIMIT %s OFFSET %s;
    """
    params.extend([limit, offset])

    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [_row_to_dict(cur, r) for r in rows]


def count_audit_logs(
    user_id=None,
    entity_name=None,
    action=None,
    start_date=None,
    end_date=None,
    conn=None
):
    """Count total matching audit log records for pagination."""
    connection = conn or get_db_connection()

    conditions = []
    params = []

    if user_id is not None:
        conditions.append("user_id = %s")
        params.append(user_id)

    if entity_name:
        conditions.append("entity_name = %s")
        params.append(entity_name)

    if action:
        conditions.append("action = %s")
        params.append(action)

    if start_date:
        conditions.append("created_date >= %s")
        params.append(start_date)

    if end_date:
        conditions.append("created_date <= %s")
        params.append(end_date)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"SELECT COUNT(*) FROM audit_logs {where_clause};"

    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def get_recent_audit_logs(limit=50, conn=None):
    """Retrieve the most recent audit logs."""
    return find_audit_logs(limit=limit, conn=conn)
