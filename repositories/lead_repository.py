"""
Lead Repository for AcxiomCRM.

Encapsulates all SQL data access for the 'leads' entity (and associated conversion
records such as Opportunity insertion) using raw psycopg2 with strict parameterization.
Adheres strictly to architecture:
- All SQL queries are parameterized using %s placeholders.
- Scope-aware ownership filtering is applied directly inside SQL WHERE clauses.
- Accepts optional 'conn' parameter to participate in atomic business transactions.
- Never commits when 'conn' is provided by an external caller (service boundary).
"""

from decimal import Decimal
from database import get_db_connection

# Whitelists for dynamic query parameters to prevent SQL injection
ALLOWED_SORT_COLUMNS = {
    "lead_name": "l.lead_name",
    "company_name": "l.company_name",
    "email": "l.email",
    "status": "l.status",
    "expected_value": "l.expected_value",
    "created_date": "l.created_date",
}

ALLOWED_SORT_ORDERS = {
    "asc": "ASC",
    "desc": "DESC",
}


def _row_to_dict(cursor, row):
    """Convert database row tuple to dictionary using cursor descriptions."""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def get_next_lead_code(conn=None):
    """
    Generate the next sequential LeadCode (e.g. LEAD-001, LEAD-007).
    Computes MAX(lead_id) + 1.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(lead_id), 0) + 1 FROM leads;")
        next_id = cur.fetchone()[0]
        return f"LEAD-{next_id:03d}"


def find_by_id(lead_id, conn=None, for_update=False):
    """
    Retrieve lead by primary key ID, joined with assigned sales rep user info.

    :param lead_id: Integer primary key.
    :param conn: Optional active connection.
    :param for_update: If True, locks the row FOR UPDATE to prevent race conditions during conversion.
    :return: Lead dictionary or None.
    """
    connection = conn or get_db_connection()
    lock_clause = "FOR UPDATE OF l" if for_update else ""
    with connection.cursor() as cur:
        cur.execute(f"""
            SELECT l.lead_id, l.lead_code, l.lead_name, l.email, l.phone,
                   l.company_name, l.source, l.status, l.expected_value,
                   l.created_date, l.modified_date, l.assigned_to,
                   u.username AS assigned_to_name,
                   r.role_name AS assigned_to_role
            FROM leads l
            LEFT JOIN users u ON l.assigned_to = u.user_id
            LEFT JOIN roles r ON u.role_id = r.role_id
            WHERE l.lead_id = %s
            {lock_clause};
        """, (lead_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def find_by_code(lead_code, conn=None):
    """Find a lead by its unique business code (e.g. 'LEAD-001')."""
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT lead_id, lead_code, lead_name, email, phone,
                   company_name, source, status, expected_value,
                   created_date, modified_date, assigned_to
            FROM leads
            WHERE lead_code = %s;
        """, (lead_code,))
        row = cur.fetchone()
        return _row_to_dict(cur, row)


def create_lead(
    lead_code,
    lead_name,
    email,
    phone=None,
    company_name=None,
    source=None,
    status="New",
    expected_value=None,
    assigned_to=None,
    conn=None
):
    """
    Insert a new lead record into PostgreSQL.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO leads (
                lead_code, lead_name, email, phone, company_name,
                source, status, expected_value, assigned_to
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING lead_id, lead_code, lead_name, email, phone,
                      company_name, source, status, expected_value,
                      created_date, modified_date, assigned_to;
        """, (
            lead_code,
            lead_name,
            email,
            phone,
            company_name,
            source,
            status,
            expected_value,
            assigned_to
        ))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    if conn is None:
        connection.commit()

    return record


def update_lead(
    lead_id,
    lead_name,
    email,
    phone=None,
    company_name=None,
    source=None,
    expected_value=None,
    assigned_to=None,
    conn=None
):
    """
    Update core lead fields and stamp modified_date.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE leads
            SET lead_name = %s,
                email = %s,
                phone = %s,
                company_name = %s,
                source = %s,
                expected_value = %s,
                assigned_to = %s,
                modified_date = CURRENT_TIMESTAMP
            WHERE lead_id = %s
            RETURNING lead_id, lead_code, lead_name, email, phone,
                      company_name, source, status, expected_value,
                      created_date, modified_date, assigned_to;
        """, (
            lead_name,
            email,
            phone,
            company_name,
            source,
            expected_value,
            assigned_to,
            lead_id
        ))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    if conn is None:
        connection.commit()

    return record


def update_status(lead_id, new_status, conn=None):
    """
    Update lead status and stamp modified_date.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            UPDATE leads
            SET status = %s,
                modified_date = CURRENT_TIMESTAMP
            WHERE lead_id = %s
            RETURNING lead_id, lead_code, lead_name, email, phone,
                      company_name, source, status, expected_value,
                      created_date, modified_date, assigned_to;
        """, (new_status, lead_id))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    if conn is None:
        connection.commit()

    return record


def find_leads(
    allowed_user_ids=None,
    search=None,
    status=None,
    assigned_to=None,
    sort_by="created_date",
    sort_order="DESC",
    limit=10,
    offset=0,
    conn=None
):
    """
    Search and filter leads incorporating SQL-level ownership scope.
    """
    connection = conn or get_db_connection()
    conditions = ["1=1"]
    params = []

    # 1. SQL-level ownership scope
    if allowed_user_ids is not None:
        conditions.append("l.assigned_to = ANY(%s)")
        params.append(allowed_user_ids)

    # 2. Search filter across Name, Company, Email, Phone
    if search:
        search_pattern = f"%{search.strip().lower()}%"
        conditions.append("""(
            LOWER(l.lead_name) LIKE %s OR
            LOWER(COALESCE(l.company_name, '')) LIKE %s OR
            LOWER(l.email) LIKE %s OR
            COALESCE(l.phone, '') LIKE %s
        )""")
        params.extend([search_pattern, search_pattern, search_pattern, f"%{search.strip()}%"])

    # 3. Status filter
    if status:
        conditions.append("l.status = %s")
        params.append(status.strip())

    # 4. Assigned Sales Executive filter (for Admin / Manager)
    if assigned_to:
        conditions.append("l.assigned_to = %s")
        params.append(int(assigned_to))

    # 5. Whitelist sorting
    col = ALLOWED_SORT_COLUMNS.get(sort_by, "l.created_date")
    order = ALLOWED_SORT_ORDERS.get(sort_order.lower(), "DESC")

    # 6. Pagination limits
    params.extend([limit, offset])

    query = f"""
        SELECT l.lead_id, l.lead_code, l.lead_name, l.email, l.phone,
               l.company_name, l.source, l.status, l.expected_value,
               l.created_date, l.modified_date, l.assigned_to,
               u.username AS assigned_to_name,
               r.role_name AS assigned_to_role
        FROM leads l
        LEFT JOIN users u ON l.assigned_to = u.user_id
        LEFT JOIN roles r ON u.role_id = r.role_id
        WHERE {' AND '.join(conditions)}
        ORDER BY {col} {order}
        LIMIT %s OFFSET %s;
    """

    with connection.cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        return [_row_to_dict(cur, row) for row in rows]


def count_leads(
    allowed_user_ids=None,
    search=None,
    status=None,
    assigned_to=None,
    conn=None
):
    """
    Count leads matching criteria for pagination.
    """
    connection = conn or get_db_connection()
    conditions = ["1=1"]
    params = []

    if allowed_user_ids is not None:
        conditions.append("l.assigned_to = ANY(%s)")
        params.append(allowed_user_ids)

    if search:
        search_pattern = f"%{search.strip().lower()}%"
        conditions.append("""(
            LOWER(l.lead_name) LIKE %s OR
            LOWER(COALESCE(l.company_name, '')) LIKE %s OR
            LOWER(l.email) LIKE %s OR
            COALESCE(l.phone, '') LIKE %s
        )""")
        params.extend([search_pattern, search_pattern, search_pattern, f"%{search.strip()}%"])

    if status:
        conditions.append("l.status = %s")
        params.append(status.strip())

    if assigned_to:
        conditions.append("l.assigned_to = %s")
        params.append(int(assigned_to))

    query = f"""
        SELECT COUNT(*)
        FROM leads l
        WHERE {' AND '.join(conditions)};
    """

    with connection.cursor() as cur:
        cur.execute(query, tuple(params))
        return cur.fetchone()[0]


def create_opportunity(
    opportunity_name,
    customer_id,
    lead_id,
    amount,
    stage,
    probability,
    expected_close_date,
    status="Open",
    assigned_to=None,
    conn=None
):
    """
    Insert an Opportunity record created as part of the Lead conversion transaction.
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO opportunities (
                opportunity_name, customer_id, lead_id, amount,
                stage, probability, expected_close_date, status, assigned_to
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING opportunity_id, opportunity_name, customer_id, lead_id,
                      amount, stage, probability, expected_close_date, status,
                      created_date, modified_date, closed_date, assigned_to;
        """, (
            opportunity_name,
            customer_id,
            lead_id,
            amount,
            stage,
            probability,
            expected_close_date,
            status,
            assigned_to
        ))
        row = cur.fetchone()
        record = _row_to_dict(cur, row)

    if conn is None:
        connection.commit()

    return record


def get_active_sales_executives(conn=None):
    """
    Fetch all active users with role 'Sales Executive' (role_id = 3).
    """
    connection = conn or get_db_connection()
    with connection.cursor() as cur:
        cur.execute("""
            SELECT u.user_id, u.username, u.email, r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.is_active = TRUE AND u.role_id = 3
            ORDER BY u.username ASC;
        """)
        rows = cur.fetchall()
        return [_row_to_dict(cur, row) for row in rows]
