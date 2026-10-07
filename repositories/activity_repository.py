"""
Activity Repository for AcxiomCRM (Phase 8).

Encapsulates all SQL execution for the activities table using psycopg2.
Adheres strictly to the architectural constraints:
- Repositories DO NOT commit or manage transactions (Services own commits).
- Strictly parameterized SQL (%s) for all variable bindings.
- Row-level locking (FOR UPDATE) supported on find_by_id.
- Ownership scoping implemented at SQL level via (%s::int[] IS NULL OR a.assigned_to = ANY(%s::int[])).
- Schema compliance: activities table links only to customers and leads (no opportunity_id).
"""

from database import get_db_connection


def _row_to_dict(cursor, row):
    """Convert database row tuple to dictionary using cursor descriptions."""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def _rows_to_dicts(cursor, rows):
    """Convert database row tuples to dictionaries."""
    if not rows:
        return []
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, r)) for r in rows]


def find_by_id(activity_id, conn=None, for_update=False):
    """
    Retrieve an activity by primary key with joined customer, lead, and assignee details.

    :param activity_id: Integer primary key.
    :param conn: Optional existing psycopg2 connection.
    :param for_update: If True, executes SELECT ... FOR UPDATE.
    :return: Dictionary record or None if not found.
    """
    connection = conn or get_db_connection()
    query = """
        SELECT
            a.activity_id,
            a.activity_type,
            a.subject,
            a.description,
            a.activity_date,
            a.customer_id,
            a.lead_id,
            a.assigned_to,
            a.status,
            a.created_date,
            a.modified_date,
            c.customer_name,
            c.customer_code,
            c.assigned_to AS customer_assigned_to,
            l.lead_name,
            l.lead_code,
            l.assigned_to AS lead_assigned_to,
            u.username AS assigned_username,
            u.email AS assigned_email
        FROM activities a
        LEFT JOIN customers c ON a.customer_id = c.customer_id
        LEFT JOIN leads l ON a.lead_id = l.lead_id
        LEFT JOIN users u ON a.assigned_to = u.user_id
        WHERE a.activity_id = %s
    """
    if for_update:
        query += " FOR UPDATE OF a"

    with connection.cursor() as cur:
        cur.execute(query, (activity_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def create_activity(
    activity_type,
    subject,
    activity_date,
    customer_id=None,
    lead_id=None,
    description=None,
    assigned_to=None,
    status="Completed",
    conn=None,
):
    """
    Insert a new activity record.

    :return: Dictionary representation of the inserted row.
    """
    connection = conn or get_db_connection()
    query = """
        INSERT INTO activities (
            activity_type,
            subject,
            description,
            activity_date,
            customer_id,
            lead_id,
            assigned_to,
            status,
            created_date
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
        )
        RETURNING *;
    """
    params = (
        activity_type,
        subject,
        description,
        activity_date,
        customer_id,
        lead_id,
        assigned_to,
        status,
    )
    with connection.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def update_activity(
    activity_id,
    activity_type,
    subject,
    activity_date,
    description,
    status,
    assigned_to,
    customer_id=None,
    lead_id=None,
    conn=None,
):
    """
    Update an existing activity record.

    :return: Updated dictionary representation.
    """
    connection = conn or get_db_connection()
    query = """
        UPDATE activities
        SET
            activity_type = %s,
            subject = %s,
            description = %s,
            activity_date = %s,
            status = %s,
            assigned_to = %s,
            customer_id = %s,
            lead_id = %s,
            modified_date = CURRENT_TIMESTAMP
        WHERE activity_id = %s
        RETURNING *;
    """
    params = (
        activity_type,
        subject,
        description,
        activity_date,
        status,
        assigned_to,
        customer_id,
        lead_id,
        activity_id,
    )
    with connection.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def update_status(activity_id, status, conn=None):
    """
    Update only the status of an activity.

    :return: Updated dictionary representation.
    """
    connection = conn or get_db_connection()
    query = """
        UPDATE activities
        SET
            status = %s,
            modified_date = CURRENT_TIMESTAMP
        WHERE activity_id = %s
        RETURNING *;
    """
    with connection.cursor() as cur:
        cur.execute(query, (status, activity_id))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def find_activities(
    visible_user_ids=None,
    search=None,
    activity_type=None,
    status=None,
    assigned_to=None,
    customer_id=None,
    lead_id=None,
    limit=20,
    offset=0,
    conn=None,
):
    """
    Search and filter activities with role-based ownership scoping in SQL.
    """
    connection = conn or get_db_connection()

    conditions = ["(%s::int[] IS NULL OR a.assigned_to = ANY(%s::int[]))"]
    params = [visible_user_ids, visible_user_ids]

    if search:
        search_term = f"%{search.strip()}%"
        conditions.append(
            """(
                a.subject ILIKE %s OR
                a.description ILIKE %s OR
                c.customer_name ILIKE %s OR
                l.lead_name ILIKE %s
            )"""
        )
        params.extend([search_term, search_term, search_term, search_term])

    if activity_type:
        conditions.append("a.activity_type = %s")
        params.append(activity_type.strip())

    if status:
        conditions.append("a.status = %s")
        params.append(status.strip())

    if assigned_to:
        conditions.append("a.assigned_to = %s")
        params.append(int(assigned_to))

    if customer_id:
        conditions.append("a.customer_id = %s")
        params.append(int(customer_id))
    if lead_id:
        conditions.append("a.lead_id = %s")
        params.append(int(lead_id))

    where_clause = " WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT
            a.activity_id,
            a.activity_type,
            a.subject,
            a.description,
            a.activity_date,
            a.customer_id,
            a.lead_id,
            a.assigned_to,
            a.status,
            a.created_date,
            a.modified_date,
            c.customer_name,
            c.customer_code,
            l.lead_name,
            l.lead_code,
            u.username AS assigned_username
        FROM activities a
        LEFT JOIN customers c ON a.customer_id = c.customer_id
        LEFT JOIN leads l ON a.lead_id = l.lead_id
        LEFT JOIN users u ON a.assigned_to = u.user_id
        {where_clause}
        ORDER BY a.activity_date DESC, a.created_date DESC
        LIMIT %s OFFSET %s;
    """
    params.extend([limit, offset])

    with connection.cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)


def count_activities(
    visible_user_ids=None,
    search=None,
    activity_type=None,
    status=None,
    assigned_to=None,
    customer_id=None,
    lead_id=None,
    conn=None,
):
    """
    Count total activities matching query filters for pagination.
    """
    connection = conn or get_db_connection()

    conditions = ["(%s::int[] IS NULL OR a.assigned_to = ANY(%s::int[]))"]
    params = [visible_user_ids, visible_user_ids]

    if search:
        search_term = f"%{search.strip()}%"
        conditions.append(
            """(
                a.subject ILIKE %s OR
                a.description ILIKE %s OR
                c.customer_name ILIKE %s OR
                l.lead_name ILIKE %s
            )"""
        )
        params.extend([search_term, search_term, search_term, search_term])

    if activity_type:
        conditions.append("a.activity_type = %s")
        params.append(activity_type.strip())

    if status:
        conditions.append("a.status = %s")
        params.append(status.strip())

    if assigned_to:
        conditions.append("a.assigned_to = %s")
        params.append(int(assigned_to))

    if customer_id:
        conditions.append("a.customer_id = %s")
        params.append(int(customer_id))
    if lead_id:
        conditions.append("a.lead_id = %s")
        params.append(int(lead_id))

    where_clause = " WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT COUNT(*) AS total
        FROM activities a
        LEFT JOIN customers c ON a.customer_id = c.customer_id
        LEFT JOIN leads l ON a.lead_id = l.lead_id
        {where_clause};
    """

    with connection.cursor() as cur:
        cur.execute(query, tuple(params))
        result = cur.fetchone()
        return result[0] if result else 0


def get_activity_metrics(visible_user_ids=None, conn=None):
    """
    Aggregate counts of activities grouped by type.
    """
    connection = conn or get_db_connection()
    query = """
        SELECT
            COUNT(*) FILTER (WHERE activity_type = 'Call') AS call_count,
            COUNT(*) FILTER (WHERE activity_type = 'Meeting') AS meeting_count,
            COUNT(*) FILTER (WHERE activity_type = 'Email') AS email_count,
            COUNT(*) FILTER (WHERE activity_type = 'Task') AS task_count,
            COUNT(*) AS total_count
        FROM activities
        WHERE (%s::int[] IS NULL OR assigned_to = ANY(%s::int[]));
    """
    with connection.cursor() as cur:
        cur.execute(query, (visible_user_ids, visible_user_ids))
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else {
            "call_count": 0,
            "meeting_count": 0,
            "email_count": 0,
            "task_count": 0,
            "total_count": 0,
        }
