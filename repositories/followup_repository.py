"""
Follow-Up Repository for AcxiomCRM (Phase 8).

Encapsulates all SQL execution for the followups table using psycopg2.
Adheres strictly to the architectural constraints:
- Repositories DO NOT commit or manage transactions (Services own commits).
- Strictly parameterized SQL (%s) for all variable bindings.
- Row-level locking (FOR UPDATE) supported on find_by_id.
- Ownership scoping implemented at SQL level via (%s::int[] IS NULL OR f.assigned_to = ANY(%s::int[])).
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


def find_by_id(followup_id, conn=None, for_update=False):
    """
    Retrieve a follow-up by primary key with joined relation names.

    :param followup_id: Integer primary key.
    :param conn: Optional existing psycopg2 connection.
    :param for_update: If True, executes SELECT ... FOR UPDATE for concurrency safety.
    :return: Dictionary record or None if not found.
    """
    connection = conn or get_db_connection()
    query = """
        SELECT
            f.followup_id,
            f.customer_id,
            f.lead_id,
            f.opportunity_id,
            f.subject,
            f.followup_date,
            f.followup_type,
            f.remarks,
            f.status,
            f.assigned_to,
            f.created_date,
            f.modified_date,
            c.customer_name,
            c.customer_code,
            c.assigned_to AS customer_assigned_to,
            l.lead_name,
            l.lead_code,
            l.assigned_to AS lead_assigned_to,
            o.opportunity_name,
            o.assigned_to AS opportunity_assigned_to,
            u.username AS assigned_username,
            u.email AS assigned_email
        FROM followups f
        LEFT JOIN customers c ON f.customer_id = c.customer_id
        LEFT JOIN leads l ON f.lead_id = l.lead_id
        LEFT JOIN opportunities o ON f.opportunity_id = o.opportunity_id
        LEFT JOIN users u ON f.assigned_to = u.user_id
        WHERE f.followup_id = %s
    """
    if for_update:
        query += " FOR UPDATE OF f"

    with connection.cursor() as cur:
        cur.execute(query, (followup_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def create_followup(
    subject,
    followup_date,
    followup_type,
    customer_id=None,
    lead_id=None,
    opportunity_id=None,
    remarks=None,
    status="Planned",
    assigned_to=None,
    conn=None,
):
    """
    Insert a new follow-up record.

    :return: Dictionary representation of the inserted row.
    """
    connection = conn or get_db_connection()
    query = """
        INSERT INTO followups (
            customer_id,
            lead_id,
            opportunity_id,
            subject,
            followup_date,
            followup_type,
            remarks,
            status,
            assigned_to,
            created_date
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
        )
        RETURNING *;
    """
    params = (
        customer_id,
        lead_id,
        opportunity_id,
        subject,
        followup_date,
        followup_type,
        remarks,
        status,
        assigned_to,
    )
    with connection.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def update_followup(
    followup_id,
    subject,
    followup_date,
    followup_type,
    remarks,
    status,
    assigned_to,
    customer_id=None,
    lead_id=None,
    opportunity_id=None,
    conn=None,
):
    """
    Update an existing follow-up record.

    :return: Updated dictionary representation.
    """
    connection = conn or get_db_connection()
    query = """
        UPDATE followups
        SET
            subject = %s,
            followup_date = %s,
            followup_type = %s,
            remarks = %s,
            status = %s,
            assigned_to = %s,
            customer_id = %s,
            lead_id = %s,
            opportunity_id = %s,
            modified_date = CURRENT_TIMESTAMP
        WHERE followup_id = %s
        RETURNING *;
    """
    params = (
        subject,
        followup_date,
        followup_type,
        remarks,
        status,
        assigned_to,
        customer_id,
        lead_id,
        opportunity_id,
        followup_id,
    )
    with connection.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def update_status(followup_id, status, conn=None):
    """
    Update only the status of a follow-up.

    :return: Updated dictionary representation.
    """
    connection = conn or get_db_connection()
    query = """
        UPDATE followups
        SET
            status = %s,
            modified_date = CURRENT_TIMESTAMP
        WHERE followup_id = %s
        RETURNING *;
    """
    with connection.cursor() as cur:
        cur.execute(query, (status, followup_id))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def reschedule_followup(followup_id, new_date, status="Planned", conn=None):
    """
    Reschedule a follow-up to a new date, resetting status to Planned if Missed.

    :return: Updated dictionary representation.
    """
    connection = conn or get_db_connection()
    query = """
        UPDATE followups
        SET
            followup_date = %s,
            status = %s,
            modified_date = CURRENT_TIMESTAMP
        WHERE followup_id = %s
        RETURNING *;
    """
    with connection.cursor() as cur:
        cur.execute(query, (new_date, status, followup_id))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def find_followups(
    visible_user_ids=None,
    search=None,
    status=None,
    ftype=None,
    assigned_to=None,
    view_filter=None,
    customer_id=None,
    lead_id=None,
    opportunity_id=None,
    limit=20,
    offset=0,
    conn=None,
):
    """
    Search and filter follow-ups with role-based ownership scoping in SQL.
    """
    connection = conn or get_db_connection()

    conditions = ["(%s::int[] IS NULL OR f.assigned_to = ANY(%s::int[]))"]
    params = [visible_user_ids, visible_user_ids]

    # Search filter
    if search:
        search_term = f"%{search.strip()}%"
        conditions.append(
            """(
                f.subject ILIKE %s OR
                c.customer_name ILIKE %s OR
                l.lead_name ILIKE %s OR
                o.opportunity_name ILIKE %s OR
                f.remarks ILIKE %s
            )"""
        )
        params.extend([search_term, search_term, search_term, search_term, search_term])

    # Status filter
    if status:
        conditions.append("f.status = %s")
        params.append(status.strip())

    # Follow-Up Type filter
    if ftype:
        conditions.append("f.followup_type = %s")
        params.append(ftype.strip())

    # Assigned To filter
    if assigned_to:
        conditions.append("f.assigned_to = %s")
        params.append(int(assigned_to))

    # Entity filters
    if customer_id:
        conditions.append("f.customer_id = %s")
        params.append(int(customer_id))
    if lead_id:
        conditions.append("f.lead_id = %s")
        params.append(int(lead_id))
    if opportunity_id:
        conditions.append("f.opportunity_id = %s")
        params.append(int(opportunity_id))

    # Upcoming / Overdue / Completed view filter
    if view_filter == "upcoming":
        conditions.append("(f.status = 'Planned' AND f.followup_date >= CURRENT_DATE)")
    elif view_filter == "overdue":
        conditions.append("(f.status = 'Planned' AND f.followup_date < CURRENT_DATE)")
    elif view_filter == "completed":
        conditions.append("f.status = 'Completed'")

    where_clause = " WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT
            f.followup_id,
            f.customer_id,
            f.lead_id,
            f.opportunity_id,
            f.subject,
            f.followup_date,
            f.followup_type,
            f.remarks,
            f.status,
            f.assigned_to,
            f.created_date,
            f.modified_date,
            c.customer_name,
            c.customer_code,
            l.lead_name,
            l.lead_code,
            o.opportunity_name,
            u.username AS assigned_username
        FROM followups f
        LEFT JOIN customers c ON f.customer_id = c.customer_id
        LEFT JOIN leads l ON f.lead_id = l.lead_id
        LEFT JOIN opportunities o ON f.opportunity_id = o.opportunity_id
        LEFT JOIN users u ON f.assigned_to = u.user_id
        {where_clause}
        ORDER BY f.followup_date ASC, f.created_date DESC
        LIMIT %s OFFSET %s;
    """
    params.extend([limit, offset])

    with connection.cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)


def count_followups(
    visible_user_ids=None,
    search=None,
    status=None,
    ftype=None,
    assigned_to=None,
    view_filter=None,
    customer_id=None,
    lead_id=None,
    opportunity_id=None,
    conn=None,
):
    """
    Count total follow-ups matching query filters for pagination.
    """
    connection = conn or get_db_connection()

    conditions = ["(%s::int[] IS NULL OR f.assigned_to = ANY(%s::int[]))"]
    params = [visible_user_ids, visible_user_ids]

    if search:
        search_term = f"%{search.strip()}%"
        conditions.append(
            """(
                f.subject ILIKE %s OR
                c.customer_name ILIKE %s OR
                l.lead_name ILIKE %s OR
                o.opportunity_name ILIKE %s OR
                f.remarks ILIKE %s
            )"""
        )
        params.extend([search_term, search_term, search_term, search_term, search_term])

    if status:
        conditions.append("f.status = %s")
        params.append(status.strip())

    if ftype:
        conditions.append("f.followup_type = %s")
        params.append(ftype.strip())

    if assigned_to:
        conditions.append("f.assigned_to = %s")
        params.append(int(assigned_to))

    if customer_id:
        conditions.append("f.customer_id = %s")
        params.append(int(customer_id))
    if lead_id:
        conditions.append("f.lead_id = %s")
        params.append(int(lead_id))
    if opportunity_id:
        conditions.append("f.opportunity_id = %s")
        params.append(int(opportunity_id))

    if view_filter == "upcoming":
        conditions.append("(f.status = 'Planned' AND f.followup_date >= CURRENT_DATE)")
    elif view_filter == "overdue":
        conditions.append("(f.status = 'Planned' AND f.followup_date < CURRENT_DATE)")
    elif view_filter == "completed":
        conditions.append("f.status = 'Completed'")

    where_clause = " WHERE " + " AND ".join(conditions)

    query = f"""
        SELECT COUNT(*) AS total
        FROM followups f
        LEFT JOIN customers c ON f.customer_id = c.customer_id
        LEFT JOIN leads l ON f.lead_id = l.lead_id
        LEFT JOIN opportunities o ON f.opportunity_id = o.opportunity_id
        {where_clause};
    """

    with connection.cursor() as cur:
        cur.execute(query, tuple(params))
        result = cur.fetchone()
        return result[0] if result else 0


def get_followup_metrics(visible_user_ids=None, conn=None):
    """
    Get aggregated counts for Planned, Upcoming, Overdue, and Completed follow-ups.
    """
    connection = conn or get_db_connection()
    query = """
        SELECT
            COUNT(*) FILTER (WHERE status = 'Planned' AND followup_date >= CURRENT_DATE) AS upcoming_count,
            COUNT(*) FILTER (WHERE status = 'Planned' AND followup_date < CURRENT_DATE) AS overdue_count,
            COUNT(*) FILTER (WHERE status = 'Completed') AS completed_count,
            COUNT(*) FILTER (WHERE status = 'Planned') AS total_planned,
            COUNT(*) AS total_count
        FROM followups
        WHERE (%s::int[] IS NULL OR assigned_to = ANY(%s::int[]));
    """
    with connection.cursor() as cur:
        cur.execute(query, (visible_user_ids, visible_user_ids))
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else {
            "upcoming_count": 0,
            "overdue_count": 0,
            "completed_count": 0,
            "total_planned": 0,
            "total_count": 0,
        }
